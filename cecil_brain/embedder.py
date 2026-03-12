"""
Cecil-Brain Semantic Embedder  (Phase 5)

Converts natural-language commands into dense vector embeddings so that
semantically similar commands (e.g. "abre el navegador" vs "lanza firefox")
resolve to the same cached skill.

Backend
───────
Primary  : ONNX Runtime + all-MiniLM-L6-v2 (384-dim, ~23 MB)
            — CPU-only, no PyTorch/GPU required
Fallback : TF-IDF-style bag-of-words sparse vector (no model file needed)

Model download
──────────────
The ONNX model is fetched on first use from Hugging Face Hub and stored at
~/.cache/cecil/embeddings/  — subsequent uses are instant (no network).

Usage
─────
    from cecil_brain.embedder import Embedder, cosine_similarity

    emb = Embedder()
    v1  = emb.encode("abre el navegador")
    v2  = emb.encode("lanza firefox")
    sim = cosine_similarity(v1, v2)   # → ~0.87
"""

import hashlib
import json
import logging
import math
import os
import re
import threading
from typing import List, Optional

import numpy as np

logger = logging.getLogger("cecil.brain.embedder")

# ── Constants ──────────────────────────────────────────────────────────────────

_CACHE_DIR    = os.path.join(os.path.expanduser("~"), ".cache", "cecil", "embeddings")
_MODEL_SUBDIR = "all-MiniLM-L6-v2-onnx"

# Hugging Face ONNX export (optimum-cli export)
_HF_BASE = "https://huggingface.co/optimum/all-MiniLM-L6-v2/resolve/main"

_MODEL_FILES = {
    "model.onnx":    f"{_HF_BASE}/model.onnx",
    "tokenizer.json":f"{_HF_BASE}/tokenizer.json",
    "config.json":   f"{_HF_BASE}/config.json",
    "tokenizer_config.json": f"{_HF_BASE}/tokenizer_config.json",
    "special_tokens_map.json": f"{_HF_BASE}/special_tokens_map.json",
    "vocab.txt":     f"{_HF_BASE}/vocab.txt",
}

EMBEDDING_DIM = 384   # all-MiniLM-L6-v2 output dimension


# ── Math helpers ───────────────────────────────────────────────────────────────

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Cosine similarity between two vectors.
    Returns value in [-1, 1]; 1 = identical direction.
    """
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


# ── Fallback: sparse BoW embedder ─────────────────────────────────────────────

_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "y", "o", "a", "por", "para",
    "con", "sin", "que", "se", "es", "su", "sus", "me", "te",
    "le", "nos", "les", "lo", "esta", "este", "ese", "esa",
    "mi", "tu", "si", "no", "hay", "muy", "más", "como",
}
_STOPWORDS_EN = {
    "the", "a", "an", "of", "in", "and", "or", "to", "for",
    "with", "by", "is", "it", "at", "on", "be", "this",
    "that", "my", "your", "its", "we", "i", "me",
}
_STOPWORDS = _STOPWORDS_ES | _STOPWORDS_EN


class _BowEmbedder:
    """
    Bag-of-words sparse embedder — no model files needed.

    Uses a fixed vocabulary built from frequently observed OS/app words
    plus an ad-hoc hash bucket for OOV terms.  Produces a 512-dim vector
    that captures rough semantic overlap well enough for cache recall.
    """

    DIM = 512

    # Seed vocabulary: high-signal words for OS commands (ES + EN)
    _VOCAB = [
        # verbs
        "abre", "abrir", "lanza", "lanzar", "inicia", "iniciar",
        "cierra", "cerrar", "ejecuta", "ejecutar", "corre", "correr",
        "compila", "compilar", "escribe", "escribir", "teclea",
        "navega", "navegar", "crea", "crear", "borra", "borrar",
        "abre", "sube", "baja", "maximiza", "minimiza",
        "open", "launch", "close", "run", "execute", "type",
        "write", "create", "delete", "compile", "navigate",
        # nouns
        "terminal", "consola", "navegador", "browser", "firefox",
        "chrome", "editor", "vscode", "kitty", "archivo", "file",
        "carpeta", "folder", "ventana", "window", "app", "programa",
        "script", "main", "codigo", "código", "proyecto",
        # langs
        "python", "rust", "java", "javascript", "c", "cpp",
        "go", "ruby", "typescript",
        # misc
        "hola", "mundo", "hello", "world", "nuevo", "new",
        "instala", "install", "actualiza", "update",
    ]

    def __init__(self):
        self._word2idx = {w: i for i, w in enumerate(self._VOCAB)}
        self._vocab_size = len(self._VOCAB)

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r"[a-záéíóúüñ]+", text.lower())
        return [w for w in words if w not in _STOPWORDS]

    def encode(self, text: str) -> List[float]:
        vec = np.zeros(self.DIM, dtype=np.float32)
        tokens = self._tokenize(text)
        for tok in tokens:
            if tok in self._word2idx:
                vec[self._word2idx[tok]] += 1.0
            else:
                # Hash bucket for OOV
                bucket = int(hashlib.md5(tok.encode()).hexdigest(), 16) % (self.DIM - self._vocab_size)
                vec[self._vocab_size + bucket] += 1.0
        # L2-normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()


# ── ONNX tokenizer (pure-Python, no transformers lib) ─────────────────────────

class _WordPieceTokenizer:
    """
    Minimal WordPiece tokenizer that reads a HuggingFace vocab.txt.
    Supports the subset needed for all-MiniLM-L6-v2.
    """

    def __init__(self, vocab_path: str, max_len: int = 128):
        self._vocab: dict[str, int] = {}
        self._max_len = max_len
        with open(vocab_path, encoding="utf-8") as f:
            for idx, line in enumerate(f):
                self._vocab[line.rstrip("\n")] = idx
        self._unk = self._vocab.get("[UNK]", 100)
        self._cls = self._vocab.get("[CLS]", 101)
        self._sep = self._vocab.get("[SEP]", 102)
        self._pad = self._vocab.get("[PAD]", 0)

    def _tokenize_word(self, word: str) -> List[int]:
        """WordPiece sub-word tokenization for a single word."""
        if word in self._vocab:
            return [self._vocab[word]]

        tokens: List[int] = []
        start = 0
        while start < len(word):
            end = len(word)
            found = False
            while start < end:
                sub = word[start:end]
                if start > 0:
                    sub = "##" + sub
                if sub in self._vocab:
                    tokens.append(self._vocab[sub])
                    found = True
                    break
                end -= 1
            if not found:
                return [self._unk]
            start = end
        return tokens

    def encode(self, text: str) -> dict:
        """
        Returns {input_ids, attention_mask, token_type_ids} as lists.
        """
        words = re.findall(r"\w+|[^\w\s]", text.lower())
        ids: List[int] = [self._cls]
        for word in words:
            ids.extend(self._tokenize_word(word))
            if len(ids) >= self._max_len - 1:
                break
        ids.append(self._sep)

        # Truncate + pad to max_len
        ids = ids[: self._max_len]
        pad_len = self._max_len - len(ids)
        mask = [1] * len(ids) + [0] * pad_len
        ids  = ids + [self._pad] * pad_len
        type_ids = [0] * self._max_len

        return {
            "input_ids":      [ids],
            "attention_mask": [mask],
            "token_type_ids": [type_ids],
        }


# ── ONNX-backed neural embedder ────────────────────────────────────────────────

class _OnnxEmbedder:
    """
    Wraps the all-MiniLM-L6-v2 ONNX model.
    Mean-pools the last hidden state and L2-normalizes to get 384-dim embeddings.
    """

    def __init__(self, model_dir: str):
        import onnxruntime as ort  # lazy import — only needed if ONNX path taken

        self._tokenizer = _WordPieceTokenizer(
            os.path.join(model_dir, "vocab.txt")
        )
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            os.path.join(model_dir, "model.onnx"),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

    def encode(self, text: str) -> List[float]:
        inputs = self._tokenizer.encode(text)
        feed = {
            "input_ids":      np.array(inputs["input_ids"],      dtype=np.int64),
            "attention_mask": np.array(inputs["attention_mask"], dtype=np.int64),
            "token_type_ids": np.array(inputs["token_type_ids"], dtype=np.int64),
        }
        outputs = self._session.run(None, feed)
        # outputs[0] = last_hidden_state [1, seq_len, 384]
        hidden  = outputs[0][0]  # [seq_len, 384]
        mask    = np.array(inputs["attention_mask"][0], dtype=np.float32)  # [seq_len]
        # Mean pooling (ignore padding)
        pooled  = (hidden * mask[:, None]).sum(axis=0) / mask.sum()
        # L2 normalize
        norm    = np.linalg.norm(pooled)
        if norm > 0:
            pooled /= norm
        return pooled.tolist()


# ── Model download ─────────────────────────────────────────────────────────────

def _download_model(model_dir: str) -> bool:
    """
    Download all-MiniLM-L6-v2 ONNX model files to model_dir.
    Returns True on success, False on any network/IO failure.
    """
    import urllib.request

    os.makedirs(model_dir, exist_ok=True)
    for fname, url in _MODEL_FILES.items():
        dest = os.path.join(model_dir, fname)
        if os.path.exists(dest):
            continue
        logger.info(f"Downloading {fname} …")
        try:
            urllib.request.urlretrieve(url, dest)
            logger.info(f"  ✓ {fname} ({os.path.getsize(dest) // 1024} KB)")
        except Exception as e:
            logger.warning(f"  ✗ download failed for {fname}: {e}")
            return False
    return True


# ── Public Embedder façade ─────────────────────────────────────────────────────

class Embedder:
    """
    Public embedding interface.

    Tries to use the ONNX neural embedder; falls back silently to BoW if:
      - onnxruntime not installed
      - model download fails or files are corrupt
      - any runtime error during inference

    Thread-safe (one session, multiple threads can call encode() concurrently).
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        auto_download: bool = True,
    ):
        self._model_dir  = model_dir or os.path.join(_CACHE_DIR, _MODEL_SUBDIR)
        self._auto_dl    = auto_download
        self._lock       = threading.Lock()
        self._backend: Optional[_OnnxEmbedder] = None
        self._fallback   = _BowEmbedder()
        self._initialized = False

        # Try to initialize on construction (non-blocking if download needed)
        threading.Thread(target=self._lazy_init, daemon=True).start()

    def _lazy_init(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            try:
                import onnxruntime  # noqa: F401 — probe availability
            except ImportError:
                logger.warning("onnxruntime not installed — using BoW fallback")
                return

            model_ready = os.path.isfile(
                os.path.join(self._model_dir, "model.onnx")
            )
            if not model_ready and self._auto_dl:
                logger.info("Downloading embedding model (first run)…")
                ok = _download_model(self._model_dir)
                if not ok:
                    logger.warning("Model download failed — using BoW fallback")
                    return

            if os.path.isfile(os.path.join(self._model_dir, "model.onnx")):
                try:
                    self._backend = _OnnxEmbedder(self._model_dir)
                    logger.info("ONNX embedder initialized (all-MiniLM-L6-v2)")
                except Exception as e:
                    logger.warning(f"ONNX init failed: {e} — using BoW fallback")
                    self._backend = None
            else:
                logger.info("No ONNX model found — using BoW fallback")

    def encode(self, text: str) -> List[float]:
        """
        Encode text into a dense vector.

        Returns a 384-dim list (ONNX) or 512-dim list (BoW fallback).
        Both are L2-normalized.
        """
        if not self._initialized:
            # Init thread not done yet — use fallback immediately
            return self._fallback.encode(text)
        if self._backend is not None:
            try:
                return self._backend.encode(text)
            except Exception as e:
                logger.warning(f"ONNX encode failed: {e} — using BoW")
        return self._fallback.encode(text)

    @property
    def backend_name(self) -> str:
        if self._backend is not None:
            return "onnx-MiniLM-L6-v2"
        return "bow-fallback"

    @property
    def dim(self) -> int:
        if self._backend is not None:
            return EMBEDDING_DIM
        return _BowEmbedder.DIM


# ── Module-level singleton ─────────────────────────────────────────────────────

_global_embedder: Optional[Embedder] = None
_global_lock = threading.Lock()


def get_embedder() -> Embedder:
    """Return (or create) the module-level Embedder singleton."""
    global _global_embedder
    if _global_embedder is None:
        with _global_lock:
            if _global_embedder is None:
                _global_embedder = Embedder()
    return _global_embedder


def encode(text: str) -> List[float]:
    """Convenience: encode text using the global embedder."""
    return get_embedder().encode(text)
