"""
Phase 5 Test Suite — Semantic Embedder + Cache Similarity

Tests cover:
  1.  cosine_similarity: identical, orthogonal, opposite vectors
  2.  BoW embedder: encodes, L2-normalized, non-zero for known words
  3.  BoW embedder: similar commands → high similarity
  4.  BoW embedder: dissimilar commands → low similarity
  5.  BoW embedder: OOV words handled (hash bucket)
  6.  Embedder facade: encode returns list of floats
  7.  Embedder facade: L2-norm close to 1.0
  8.  Embedder facade: backend_name and dim properties
  9.  SkillCache.save() auto-generates embedding
  10. SkillCache.query() cosine threshold respected (no false positives)
  11. SkillCache.query() semantic recall: paraphrase variants resolve same skill
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math
from typing import List

from cecil_brain.embedder import (
    Embedder, _BowEmbedder, cosine_similarity, encode,
)
from cecil_brain.skill_cache import SkillCache, CachedSkill, SemanticStep


# ── Helpers ────────────────────────────────────────────────

def _make_cache() -> SkillCache:
    return SkillCache(cache_dir=tempfile.mkdtemp(prefix="cecil_emb_test_"))


def _make_skill(id_: str, command: str) -> CachedSkill:
    return CachedSkill(
        id=id_,
        command=command,
        command_embedding=[],
        steps=[SemanticStep(intent="launch_app", app="firefox")],
        success_count=5,
        failure_count=0,
    )


def _banner(title: str):
    print(f"\n{'='*60}")
    print(f"TEST: {title}")
    print("=" * 60)


# ── TEST 1: cosine_similarity math ─────────────────────────

def test_cosine_identical():
    _banner("cosine_similarity — identical vectors → 1.0")
    v = [1.0, 0.0, 0.5, -0.3]
    sim = cosine_similarity(v, v)
    print(f"  sim(v, v) = {sim:.4f}")
    assert abs(sim - 1.0) < 1e-5, f"Expected 1.0, got {sim}"
    print("  ✓")


def test_cosine_orthogonal():
    _banner("cosine_similarity — orthogonal vectors → 0.0")
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    sim = cosine_similarity(a, b)
    print(f"  sim(a, b) = {sim:.4f}")
    assert abs(sim) < 1e-5, f"Expected 0.0, got {sim}"
    print("  ✓")


def test_cosine_opposite():
    _banner("cosine_similarity — opposite vectors → -1.0")
    v = [1.0, 0.5, -0.5]
    sim = cosine_similarity(v, [-x for x in v])
    print(f"  sim(v, -v) = {sim:.4f}")
    assert abs(sim + 1.0) < 1e-5, f"Expected -1.0, got {sim}"
    print("  ✓")


# ── TEST 2-5: BoW embedder ──────────────────────────────────

def test_bow_encode_basic():
    _banner("BoW embedder — encode returns L2-normalized non-zero vector")
    bow = _BowEmbedder()
    vec = bow.encode("abre firefox")
    norm = math.sqrt(sum(x * x for x in vec))
    print(f"  dim={len(vec)}  norm={norm:.4f}  non-zero={sum(1 for x in vec if x != 0)}")
    assert len(vec) == _BowEmbedder.DIM
    assert abs(norm - 1.0) < 1e-4, f"Expected unit norm, got {norm}"
    assert any(x != 0 for x in vec)
    print("  ✓")


def test_bow_similar_commands():
    _banner("BoW embedder — similar commands → cosine > 0.4")
    bow = _BowEmbedder()
    pairs = [
        ("abre firefox",       "lanza firefox"),
        ("abre la terminal",   "abre la consola"),
        ("ejecuta python main","corre python main"),
        ("open terminal",      "launch terminal"),
    ]
    for a, b in pairs:
        va = bow.encode(a)
        vb = bow.encode(b)
        sim = cosine_similarity(va, vb)
        print(f"  {a!r:30} ↔ {b!r:30}  sim={sim:.3f}")
        assert sim > 0.4, f"Expected sim > 0.4 for ({a!r}, {b!r}), got {sim:.3f}"
    print("  ✓")


def test_bow_dissimilar_commands():
    _banner("BoW embedder — dissimilar commands → cosine < 0.7")
    bow = _BowEmbedder()
    pairs = [
        ("abre firefox",    "compila main.rs"),
        ("escribe hola",    "cierra vscode"),
    ]
    for a, b in pairs:
        va = bow.encode(a)
        vb = bow.encode(b)
        sim = cosine_similarity(va, vb)
        print(f"  {a!r:30} ↔ {b!r:30}  sim={sim:.3f}")
        assert sim < 0.7, f"Expected sim < 0.7 for ({a!r}, {b!r}), got {sim:.3f}"
    print("  ✓")


def test_bow_oov():
    _banner("BoW embedder — OOV words handled via hash bucket")
    bow = _BowEmbedder()
    vec = bow.encode("xyzabc123 foobarqux")
    norm = math.sqrt(sum(x * x for x in vec))
    print(f"  OOV encode norm={norm:.4f}")
    # Should still produce a non-zero normalized vector
    assert abs(norm - 1.0) < 1e-4
    print("  ✓")


# ── TEST 6-8: Embedder facade ───────────────────────────────

def test_embedder_returns_floats():
    _banner("Embedder.encode() — returns list of float")
    emb = Embedder(auto_download=False)
    vec = emb.encode("abre firefox")
    print(f"  dim={len(vec)}  type(vec[0])={type(vec[0]).__name__}")
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)
    print("  ✓")


def test_embedder_unit_norm():
    _banner("Embedder.encode() — output is unit-normalized")
    emb = Embedder(auto_download=False)
    vec = emb.encode("ejecuta rustc main.rs")
    norm = math.sqrt(sum(x * x for x in vec))
    print(f"  norm={norm:.4f}")
    assert abs(norm - 1.0) < 1e-3, f"Expected unit norm, got {norm}"
    print("  ✓")


def test_embedder_properties():
    _banner("Embedder.backend_name and .dim")
    emb = Embedder(auto_download=False)
    print(f"  backend={emb.backend_name}  dim={emb.dim}")
    assert isinstance(emb.backend_name, str)
    assert emb.dim > 0
    print("  ✓")


# ── TEST 9: SkillCache.save() auto-embeds ──────────────────

def test_cache_save_autoembed():
    _banner("SkillCache.save() — auto-generates embedding on save")
    cache = _make_cache()
    skill = _make_skill("s1", "abre firefox")
    assert skill.command_embedding == [], "Pre-condition: no embedding"
    cache.save(skill)

    # Reload from DB
    retrieved = cache.list_skills()
    assert len(retrieved) == 1
    saved = retrieved[0]
    print(f"  embedding dim={len(saved.command_embedding)}")
    assert len(saved.command_embedding) > 0, "Expected embedding after save"
    print("  ✓")


# ── TEST 10: threshold respected ───────────────────────────

def test_cache_query_threshold():
    _banner("SkillCache.query() — threshold respected (no false positives)")
    cache = _make_cache()
    cache.save(_make_skill("s1", "abre firefox"))

    # A completely unrelated command at high threshold should miss
    result = cache.query("compila un programa en rust", threshold=0.95)
    print(f"  query result for unrelated cmd at 0.95: {result}")
    assert result is None, "Expected None for unrelated command at high threshold"
    print("  ✓")


# ── TEST 11: semantic recall — paraphrases → same skill ────

def test_cache_query_semantic_recall():
    _banner("SkillCache.query() — paraphrases resolve to same skill")
    cache = _make_cache()
    cache.save(_make_skill("browser", "abre firefox"))

    # Paraphrase variants — lower threshold since we're using BoW
    paraphrases = [
        ("abre firefox",  0.85),   # exact
        ("lanza firefox", 0.50),   # synonym verb
        ("abre el navegador firefox", 0.50),  # with article
    ]
    for cmd, thresh in paraphrases:
        result = cache.query(cmd, threshold=thresh)
        sim_indicator = "✓" if result is not None else "✗"
        print(f"  {sim_indicator}  {cmd!r:40} threshold={thresh}  → {result.id if result else None}")
        assert result is not None, f"Expected cache hit for {cmd!r} at threshold={thresh}"
    print("  ✓ semantic recall")


# ── Runner ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🧠 CecilOs Phase 5 Test Suite")
    print("Semantic Embedder + Cosine Cache Similarity\n")

    tests = [
        test_cosine_identical,
        test_cosine_orthogonal,
        test_cosine_opposite,
        test_bow_encode_basic,
        test_bow_similar_commands,
        test_bow_dissimilar_commands,
        test_bow_oov,
        test_embedder_returns_floats,
        test_embedder_unit_norm,
        test_embedder_properties,
        test_cache_save_autoembed,
        test_cache_query_threshold,
        test_cache_query_semantic_recall,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAIL: {exc}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"{'✓ Todos los tests de Fase 5 completados' if failed == 0 else f'✗ {failed}/{passed+failed} tests fallaron'}")
    print(f"{'='*60}\n")
    sys.exit(0 if failed == 0 else 1)
