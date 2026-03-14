#!/usr/bin/env python3
"""
CecilOs — Asistente de Escritorio con Voz.

Modos de operación:
  1. GUI manual: escribe un comando → ejecuta
  2. Push-to-talk: click 🎙️ → graba → transcribe → ejecuta
  3. Always-on: "Cecilia" → escucha comando → ejecuta → responde con voz
     - "Detente" cancela la acción en curso
     - Se detiene cuando dejas de hablar (~2-3s silencio, VAD automático)

Pipeline de 4 capas:
  L0.5: Skill Cache (cached semantic plans)
  L1: Intent Parser (instant, regex)
  L2: LLM plan (Qwen, sin visión)
  L3: Vision + LLM + Keybindings (PRA loop)
"""

import logging
import os
import re
import sys
import threading
import time
import tkinter as tk
from typing import Any, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Cecil-Ear", "moonshine", "python", "src"))

from cecil_hand.executor import InputExecutor
from cecil_brain.intent_parser import parse as parse_intent
from cecil_brain.keybindings import keybindings_to_context
from cecil_brain.skill_cache import SkillCache, CachedSkill, SemanticStep
from cecil_brain.resolver import UIResolver  # Phase 2: Coordinate resolution
from cecil_brain.decomposer import decompose as decompose_command  # Phase 3: Task decomposition
from cecil_brain.validator import RollingValidator, ValidationEvent, make_validator  # Phase 4: Rolling validation
from cecil_brain.confidence import score_action, CONFIRM_THRESHOLD              # Phase 6: Confidence scoring
from cecil_brain.self_correction import (                                        # Phase 7: Self-correction
    SelfCorrector, RetryStrategy, CorrectionResult,
    suggest_layer_escalation, TERMINAL_FALLBACKS,
)
from cecil_vision.capture import ScreenCapture
from cecil_vision.parser import ScreenParser
from cecil_voice.tts import CecilVoice


# ── OpenClaw Planner (agent orchestrator) ───────────────────────────

class OpenClawPlanner:
    """Wrapper around local openclaw CLI using local gateway."""

    def __init__(self):
        self.available = False
        self.last_error = ""
        self.cli_path = self._find_cli()

    def _find_cli(self) -> str:
        import shutil
        candidates = [
            "openclaw",
            os.path.expanduser("~/.npm-global/bin/openclaw"),
            "/usr/local/bin/openclaw"
        ]
        for c in candidates:
            if shutil.which(c) or os.path.isfile(c):
                return c
        return ""

    def connect(self) -> bool:
        if self.cli_path:
            self.available = True
            self.last_error = ""
            return True
        self.available = False
        self.last_error = "CLI openclaw no encontrado"
        return False

    def plan(self, command: str, active_app: str = "", keybindings: str = "") -> Optional[List[dict]]:
        """Request a plan from OpenClaw CLI. Returns list of actions or None."""
        if not self.connect():
            return None

        # Provide a concise tool spec so the remote agent produces executor-friendly steps.
        tool_spec = (
            "Available tools (emit JSON array of actions):\n"
            "- tap(x,y): click at screen coords\n"
            "- double_click(x,y), right_click(x,y)\n"
            "- type(text): type literal text\n"
            "- key(key_combo): press combo like ctrl+c\n"
            "- scroll(x,y,direction,clicks)\n"
            "- wait(duration)\n"
            "- launch_app(app)\n"
            "Respond ONLY with JSON array of actions matching these fields."
        )

        context_bits = ["You are the planner for CecilOs. Generate a minimal sequence of GUI actions for the user command."]
        if active_app:
            context_bits.append(f"Active app: {active_app}")
        if keybindings:
            context_bits.append(f"Keybindings:\n{keybindings}")
        context_bits.append(f"Command: {command}")
        context_bits.append(tool_spec)
        prompt = "\n\n".join(context_bits)

        import subprocess
        import json

        try:
            env = os.environ.copy()
            env["NODE_OPTIONS"] = "--no-warnings"
            
            result = subprocess.run(
                [self.cli_path, "agent", "--session-id", "cecil-local", "--message", prompt, "--json"],
                capture_output=True, text=True, env=env
            )
            
            if result.returncode != 0:
                self.last_error = f"openclaw cli fail: {result.stderr}"
                return None
                
            data = json.loads(result.stdout)
            text = ""
            for p in data.get("result", {}).get("payloads", []):
                text += p.get("text", "")

            # Extract first JSON array found in the response
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1:
                return None
            payload = text[start:end + 1]
            actions = json.loads(payload)
            if isinstance(actions, list):
                return actions
        except Exception as e:
            self.last_error = f"openclaw error: {e}"
            return None
        return None

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cecil")

# Wake word patterns (case-insensitive)
_WAKE_PATTERNS = re.compile(
    r"\b(?:cecilia)\b", re.IGNORECASE
)
# Stop command patterns
_STOP_PATTERNS = re.compile(
    r"\b(?:detente|para|stop|cancela|basta)\b", re.IGNORECASE
)
# Shutdown always-on patterns
_SHUTDOWN_PATTERNS = re.compile(
    r"\b(?:ap[aá]gate|apagar|cierra|cerrar|desactívate|desactivate)\b", re.IGNORECASE
)


# ── Local LLM Brain (Layer 2 + 3) ────────────────────────

class LocalBrain:
    """LLM brain using local Qwen model via llama-cpp-python."""

    def __init__(self):
        self._engine = None
        self._model_path = self._find_model()

    def _find_model(self) -> str:
        """Find the GGUF model file."""
        candidates = [
            os.path.expanduser("~/qwen2.5-1.5b.gguf"),
            os.path.expanduser("~/models/qwen2.5-1.5b.gguf"),
            os.path.expanduser("~/models/qwen2.5-3b-instruct-q4_k_m.gguf"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return ""

    @property
    def available(self) -> bool:
        return bool(self._model_path)

    def load(self):
        """Lazy-load the LLM engine."""
        if self._engine is not None:
            return
        if not self._model_path:
            raise FileNotFoundError("No GGUF model found")
        from cecil_brain.llm_engine import LLMEngine
        self._engine = LLMEngine(
            model_path=self._model_path,
            n_gpu_layers=-1,
            n_ctx=2048,
            n_threads=4,
            temperature=0.1,
            max_tokens=512,
        )
        self._engine.load()

    def generate_plan(self, command: str, screen_layout: str,
                      keybinding_context: str = "", active_app: str = "") -> dict:
        """Generate an action plan from command + screen context + keybindings."""
        self.load()
        return self._engine.generate_action_plan(
            command, screen_layout,
            keybinding_context=keybinding_context,
            active_app=active_app,
        )


# ── Always-On Listening (MicTranscriber + VAD) ───────────

class AlwaysOnListener:
    """
    Continuous microphone listener using Moonshine MicTranscriber.

    Moonshine's built-in Silero VAD segments speech automatically:
    - Detects voice start (with 256ms look-behind buffer)
    - Accumulates audio while speaking
    - Detects silence → fires on_line_completed with full transcription
    - No manual chunking needed — VAD handles everything

    States:
        SLEEPING  → waiting for wake word ("Cecilia")
        LISTENING → wake word detected, capturing next command
        EXECUTING → running command, listening for "detente"
    """

    STATE_SLEEPING = "sleeping"
    STATE_LISTENING = "listening"
    STATE_EXECUTING = "executing"

    def __init__(self, model_dir: str, on_wake, on_command, on_stop_command,
                 on_partial_text, on_error, on_shutdown=None):
        """
        Args:
            model_dir: Path to Moonshine model directory.
            on_wake: Callback() when wake word detected.
            on_command: Callback(text) when full command captured.
            on_stop_command: Callback() when "detente" detected during execution.
            on_partial_text: Callback(text) for live partial transcription.
            on_error: Callback(error) for errors.
        """
        self._model_dir = model_dir
        self._on_wake = on_wake
        self._on_command = on_command
        self._on_stop_command = on_stop_command
        self._on_partial_text = on_partial_text
        self._on_error = on_error
        self._on_shutdown = on_shutdown or (lambda: None)
        self._tts_playing = False   # True mientras el TTS habla → ignora mic
        self._mic = None
        self._state = self.STATE_SLEEPING
        self._running = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str):
        with self._lock:
            old = self._state
            self._state = value
            logger.info(f"Listener: {old} → {value}")

    def start(self):
        """Start always-on listening."""
        if self._running:
            return

        try:
            from moonshine_voice import MicTranscriber, ModelArch, TranscriptEventListener

            class _Listener(TranscriptEventListener):
                def __init__(self, parent):
                    self._parent = parent

                def on_line_text_changed(self, event):
                    """Fires when partial text changes (live preview)."""
                    text = event.line.text.strip()
                    if not text:
                        return
                    # Ignorar si el TTS está hablando (eco del altavoz)
                    if self._parent._tts_playing:
                        return
                    state = self._parent._state
                    if state == AlwaysOnListener.STATE_EXECUTING:
                        if _STOP_PATTERNS.search(text):
                            self._parent._on_stop_command()
                            return
                    self._parent._on_partial_text(text)

                def on_line_completed(self, event):
                    """Fires cuando el VAD detecta silencio tras habla (segmento completo)."""
                    text = event.line.text.strip()
                    if not text:
                        return
                    # Ignorar eco del TTS
                    if self._parent._tts_playing:
                        return

                    state = self._parent._state

                    if state == AlwaysOnListener.STATE_SLEEPING:
                        if _SHUTDOWN_PATTERNS.search(text):
                            self._parent._on_shutdown()
                            return
                        if _WAKE_PATTERNS.search(text):
                            after = _WAKE_PATTERNS.sub("", text).strip()
                            self._parent.state = AlwaysOnListener.STATE_LISTENING
                            self._parent._on_wake()
                            if after and len(after) > 3:
                                self._parent._on_command(after)
                            return

                    elif state == AlwaysOnListener.STATE_LISTENING:
                        # Filtrar fragmentos cortos (sílabas sueltas, ruido)
                        if len(text.split()) < 2:
                            return
                        if _SHUTDOWN_PATTERNS.search(text):
                            self._parent._on_shutdown()
                            return
                        if _STOP_PATTERNS.search(text):
                            self._parent.state = AlwaysOnListener.STATE_SLEEPING
                            return
                        if _WAKE_PATTERNS.search(text):
                            return  # repetición del wake word — ignorar
                        self._parent._on_command(text)
                        return

                    elif state == AlwaysOnListener.STATE_EXECUTING:
                        if _STOP_PATTERNS.search(text):
                            self._parent._on_stop_command()
                            return
                        if _SHUTDOWN_PATTERNS.search(text):
                            self._parent._on_stop_command()
                            self._parent._on_shutdown()
                            return

                def on_error(self, event):
                    self._parent._on_error(event.error)

            self._mic = MicTranscriber(
                model_path=self._model_dir,
                model_arch=ModelArch.BASE,
                update_interval=0.3,
                blocksize=1024,
            )
            self._mic.add_listener(_Listener(self))
            self._mic.start()
            self._running = True
            self._state = self.STATE_SLEEPING
            logger.info("Always-on listener started (Moonshine + VAD)")

        except Exception as e:
            logger.error(f"Failed to start always-on listener: {e}")
            self._on_error(e)

    def stop(self):
        """Stop listening."""
        if not self._running:
            return
        try:
            self._mic.stop()
            self._mic.close()
        except Exception:
            pass
        self._running = False
        self._state = self.STATE_SLEEPING
        logger.info("Always-on listener stopped")

    @property
    def running(self) -> bool:
        return self._running


# ── Audio / STT (Push-to-Talk fallback) ───────────────────
class PushToTalkRecorder:
    """
    Push-to-talk recorder con VAD por energía (RMS).

    Comportamiento:
    - start_recording() abre el micrófono y empieza a acumular audio.
    - Un hilo interno monitorea el nivel RMS de cada bloque.
    - Cuando el RMS cae por debajo de SILENCE_THRESHOLD durante
      SILENCE_SECONDS consecutivos, el hilo llama a on_silence_stop()
      (callback que el GUI conecta para disparar _stop_record).
    - stop_and_transcribe() puede seguir llamándose manualmente (botón).
    - El VAD solo actúa después de que ya se detectó al menos un bloque
      con habla (evita parar inmediatamente si arrancas en silencio).
    """

    SAMPLE_RATE       = 16000
    BLOCKSIZE         = 4096          # ~256 ms por bloque
    SILENCE_THRESHOLD = 0.015         # RMS mínimo para considerar habla
    SILENCE_SECONDS   = 3.0           # segundos de silencio antes de parar

    def __init__(self, model_dir: str):
        import sounddevice as sd
        import numpy as np

        self.sd = sd
        self.np = np
        self._recording = False
        self._audio_chunks = []
        self._transcriber = None
        self._model_dir = model_dir
        self.on_silence_stop = None   # callback() → lo conecta el GUI

    def _ensure_transcriber(self):
        if self._transcriber is not None:
            return
        from moonshine_voice import Transcriber, ModelArch
        self._transcriber = Transcriber(
            self._model_dir, model_arch=ModelArch.BASE
        )

    def start_recording(self):
        self._audio_chunks = []
        self._recording = True
        self._has_speech = False          # ¿ya se detectó habla?
        self._silence_accum = 0.0         # segundos acumulados de silencio
        self._block_duration = self.BLOCKSIZE / self.SAMPLE_RATE  # s/bloque

        def callback(indata, frames, time_info, status):
            if not self._recording:
                return
            chunk = indata[:, 0].copy()
            self._audio_chunks.append(chunk)

            # ── VAD por energía ──────────────────────────────
            rms = float(self.np.sqrt(self.np.mean(chunk ** 2)))
            if rms >= self.SILENCE_THRESHOLD:
                self._has_speech = True
                self._silence_accum = 0.0
            elif self._has_speech:
                # Solo acumula silencio si ya hubo habla antes
                self._silence_accum += self._block_duration
                if self._silence_accum >= self.SILENCE_SECONDS:
                    # Disparar stop en hilo separado para no bloquear el callback
                    self._recording = False
                    if callable(self.on_silence_stop):
                        threading.Thread(
                            target=self.on_silence_stop, daemon=True
                        ).start()

        self._stream = self.sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=self.BLOCKSIZE,
            callback=callback,
        )
        self._stream.start()

    def stop_and_transcribe(self) -> str:
        self._recording = False
        self._stream.stop()
        self._stream.close()

        if not self._audio_chunks:
            return ""

        audio = self.np.concatenate(self._audio_chunks)

        # Normalize
        peak = self.np.max(self.np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.9

        self._ensure_transcriber()
        transcript = self._transcriber.transcribe_without_streaming(
            audio.tolist(), self.SAMPLE_RATE
        )

        # Collect all lines
        text_parts = []
        for line in transcript.lines:
            if line.text.strip():
                text_parts.append(line.text.strip())

        return " ".join(text_parts)


# ── GUI ───────────────────────────────────────────────────
class CecilApp:
    # Catppuccin Mocha palette
    BG      = "#1e1e2e"
    SURFACE = "#313244"
    TEXT    = "#cdd6f4"
    SUBTEXT = "#a6adc8"
    RED     = "#f38ba8"
    GREEN   = "#a6e3a1"
    BLUE    = "#89b4fa"
    YELLOW  = "#f9e2af"
    MAUVE   = "#cba6f7"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CecilOs")
        self.root.geometry("700x540")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)

        # Core modules
        self.executor = InputExecutor()
        self.brain = LocalBrain()
        self.openclaw = OpenClawPlanner()
        self.vision_capture = ScreenCapture()
        self.vision_parser = ScreenParser()
        self.tts = CecilVoice()
        self.skill_cache = SkillCache()  # Layer 0.5: Semantic skill cache
        self.resolver = UIResolver()     # Phase 2: Coordinate resolver (AT-SPI2 + OCR)
        self.corrector = SelfCorrector()   # Phase 7: Self-correction loop
        self.validator = make_validator(   # Phase 4: Rolling background validation
            self.skill_cache,
            interval_s=3600,
            batch_size=10,
            on_event=self._on_validation_event,
        )

        # Voice
        self._model_dir = self._find_stt_model()
        self.recorder = None       # push-to-talk fallback
        self.listener = None       # always-on listener
        self._is_recording = False
        self._always_on = False

        # Execution state
        self._busy = False
        self._cancel_flag = threading.Event()
        self._current_skill_id = None  # Track current skill for success/failure recording

        self._init_recorder()
        self._build_ui()
        self._print_startup_info()

    def _find_stt_model(self) -> str:
        """Find Moonshine model directory."""
        candidates = [
            os.path.join(PROJECT_ROOT, "Cecil-Ear", "moonshine", "test-assets", "moonshine-es"),
            os.path.join(PROJECT_ROOT, "Cecil-Ear", "moonshine", "test-assets", "tiny-en"),
        ]
        for d in candidates:
            if os.path.isdir(d):
                return d
        return ""

    def _init_recorder(self):
        """Initialize push-to-talk recorder."""
        if not self._model_dir:
            return
        try:
            self.recorder = PushToTalkRecorder(self._model_dir)
            logger.info(f"STT model: {os.path.basename(self._model_dir)}")
        except Exception as e:
            logger.error(f"STT init failed: {e}")
            self.recorder = None

    def _print_startup_info(self):
        self._log("CecilOs listo", self.GREEN)
        self._log(f"  Input:   {self.executor.backend}", self.SUBTEXT)
        self._log(f"  STT:     {'Moonshine (' + os.path.basename(self._model_dir) + ')' if self._model_dir else 'No disponible'}", self.SUBTEXT)
        self._log(f"  TTS:     {'Piper (es_MX)' if self.tts.available else 'No disponible'}", self.SUBTEXT)
        self._log(f"  Vision:  AT-SPI2={'✓' if self.vision_parser._has_atspi else '✗'}  OCR={'✓' if self.vision_parser._has_tesseract else '✗'}", self.SUBTEXT)
        oc_ok = self.openclaw.connect()
        oc_s = "OpenClaw (local)" if oc_ok else f"No disponible ({self.openclaw.last_error or 'sin cliente'})"
        brain_s = f"Qwen ({os.path.basename(self.brain._model_path)})" if self.brain.available else "No disponible"
        cache_s = f"SQLite+JSON ({self.skill_cache.count} skills cached)" if self.skill_cache else "Deshabilitado"
        val_s   = f"Rolling (interval=1h, batch=10)" if self.validator and self.validator.running else "Deshabilitado"
        self._log(f"  Planner: {oc_s}", self.SUBTEXT)
        self._log(f"  Cache:   {cache_s}", self.SUBTEXT)
        self._log(f"  Validator: {val_s}", self.SUBTEXT)
        self._log(f"  Brain:   L0.5 + L1 + L2 + L3 — {brain_s}", self.SUBTEXT)
        self._log("", self.TEXT)
        self._log("Tip: Activa 'Always-on' y di \"Cecilia\"", self.SUBTEXT)
        self._log("", self.TEXT)

    def _build_ui(self):
        # ── Title ──
        title = tk.Label(
            self.root, text="🤖 CecilOs",
            bg=self.BG, fg=self.BLUE,
            font=("Cantarell", 20, "bold"),
        )
        title.pack(pady=(12, 3))

        subtitle = tk.Label(
            self.root, text="Habla o escribe un comando",
            bg=self.BG, fg=self.SUBTEXT,
            font=("Cantarell", 11),
        )
        subtitle.pack(pady=(0, 8))

        # ── Always-on row ──
        ao_frame = tk.Frame(self.root, bg=self.BG)
        ao_frame.pack(fill=tk.X, padx=20, pady=(0, 5))

        tk.Label(
            ao_frame, text="Always-on:",
            bg=self.BG, fg=self.SUBTEXT,
            font=("Cantarell", 10),
        ).pack(side=tk.LEFT)

        self.btn_always_on = tk.Button(
            ao_frame, text="🔇 OFF",
            font=("Cantarell", 10, "bold"),
            bg=self.SURFACE, fg=self.GREEN,
            activebackground="#45475a",
            relief=tk.FLAT, borderwidth=0,
            padx=10, pady=2,
            command=self._toggle_always_on,
            cursor="hand2",
        )
        self.btn_always_on.pack(side=tk.LEFT, padx=(8, 10))

        self.always_on_status = tk.StringVar(value="Always-on desactivado")
        tk.Label(
            ao_frame, textvariable=self.always_on_status,
            bg=self.BG, fg=self.SUBTEXT,
            font=("Cantarell", 9),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Input row ──
        input_frame = tk.Frame(self.root, bg=self.BG)
        input_frame.pack(fill=tk.X, padx=20, pady=5)

        # Record button
        self.btn_record = tk.Button(
            input_frame, text="🎙️",
            font=("Cantarell", 16),
            bg=self.SURFACE, fg=self.RED,
            activebackground="#45475a", activeforeground=self.RED,
            relief=tk.FLAT, borderwidth=0,
            width=3, height=1,
            command=self._toggle_record,
            cursor="hand2",
        )
        self.btn_record.pack(side=tk.LEFT, padx=(0, 8))

        # Text input
        self.cmd_var = tk.StringVar()
        self.cmd_entry = tk.Entry(
            input_frame,
            textvariable=self.cmd_var,
            font=("Cantarell", 14),
            bg=self.SURFACE, fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=0)
        self.cmd_entry.bind("<Return>", lambda e: self._execute())

        # Execute button
        self.btn_exec = tk.Button(
            input_frame, text="▶ Ejecutar",
            font=("Cantarell", 12, "bold"),
            bg=self.BLUE, fg="#1e1e2e",
            activebackground="#74c7ec", activeforeground="#1e1e2e",
            relief=tk.FLAT, borderwidth=0,
            padx=15, pady=5,
            command=self._execute,
            cursor="hand2",
        )
        self.btn_exec.pack(side=tk.LEFT, padx=(8, 0))

        # ── Status ──
        self.status_var = tk.StringVar(value="Listo")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var,
            bg=self.BG, fg=self.SUBTEXT,
            font=("Cantarell", 10),
        )
        self.status_label.pack(pady=(5, 2))

        # ── Terminal / Log ──
        log_label = tk.Label(
            self.root, text="Terminal",
            bg=self.BG, fg=self.SUBTEXT,
            font=("Cantarell", 10, "bold"),
            anchor=tk.W,
        )
        log_label.pack(fill=tk.X, padx=20, pady=(5, 0))

        self.terminal = tk.Text(
            self.root,
            font=("Cascadia Code", 11),
            bg="#11111b", fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            wrap=tk.WORD,
            state=tk.DISABLED,
            padx=12, pady=10,
        )
        self.terminal.pack(fill=tk.BOTH, expand=True, padx=20, pady=(2, 15))

        # Tag colors
        self.terminal.tag_configure("green", foreground=self.GREEN)
        self.terminal.tag_configure("red", foreground=self.RED)
        self.terminal.tag_configure("blue", foreground=self.BLUE)
        self.terminal.tag_configure("yellow", foreground=self.YELLOW)
        self.terminal.tag_configure("mauve", foreground=self.MAUVE)
        self.terminal.tag_configure("dim", foreground=self.SUBTEXT)
        self.terminal.tag_configure("text", foreground=self.TEXT)

    # ── Logging ───────────────────────────────────────────

    def _log(self, msg: str, color: str = None):
        tag = {
            self.GREEN: "green", self.RED: "red", self.BLUE: "blue",
            self.YELLOW: "yellow", self.MAUVE: "mauve", self.SUBTEXT: "dim",
        }.get(color, "text")

        self.terminal.configure(state=tk.NORMAL)
        ts = time.strftime("%H:%M:%S")
        if msg.startswith("  "):
            self.terminal.insert(tk.END, f"{msg}\n", tag)
        else:
            self.terminal.insert(tk.END, f"[{ts}] ", "dim")
            self.terminal.insert(tk.END, f"{msg}\n", tag)
        self.terminal.see(tk.END)
        self.terminal.configure(state=tk.DISABLED)

    # ── Always-on controls ─────────────────────────────────

    def _start_always_on(self):
        """Start always-on listening mode."""
        if not self._model_dir:
            self._log("✗ STT no disponible — no hay modelo", self.RED)
            return
        if self.listener and self.listener.running:
            return

        self.listener = AlwaysOnListener(
            model_dir=self._model_dir,
            on_wake=self._on_wake_word,
            on_command=self._on_voice_command,
            on_stop_command=self._on_stop_command,
            on_partial_text=self._on_partial_text,
            on_error=lambda e: self.root.after(0, lambda: self._log(f"✗ {e}", self.RED)),
            on_shutdown=self._on_shutdown_command,
        )
        self.listener.start()
        self._always_on = True
        self._update_always_on_button()
        self._log("🎙️ Modo always-on activado", self.GREEN)
        self._log("  Di \"Cecilia\" para activar", self.SUBTEXT)

    def _stop_always_on(self):
        """Stop always-on listening."""
        if self.listener:
            self.listener.stop()
        self._always_on = False
        self._update_always_on_button()
        self._log("⏹️ Modo always-on desactivado", self.SUBTEXT)

    def _toggle_always_on(self):
        if self._always_on:
            self._stop_always_on()
        else:
            self._start_always_on()

    def _update_always_on_button(self):
        if self._always_on:
            self.btn_always_on.configure(
                bg=self.GREEN, fg="#1e1e2e", text="🔊 ON",
            )
            self.always_on_status.set("🟢 Escuchando... di \"Cecilia\"")
        else:
            self.btn_always_on.configure(
                bg=self.SURFACE, fg=self.GREEN, text="🔇 OFF",
            )
            self.always_on_status.set("Always-on desactivado")

    # ── Always-on callbacks ───────────────────────────────

    def _on_wake_word(self):
        """Called when wake word detected."""
        def _ui():
            self._log("✨ ¡Hola! Escuchando comando...", self.GREEN)
            self.status_var.set("🎙️ Escuchando tu comando...")
            self.always_on_status.set("🟡 Escuchando comando...")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self._speak_muted("Dime")
        self.root.after(0, _ui)

    def _on_voice_command(self, text: str):
        """Called when full command captured after wake word."""
        def _ui():
            self._log(f"🗣️ \"{text}\"", self.BLUE)
            self.cmd_var.set(text)
            self.always_on_status.set("🔴 Ejecutando...")
            if self.listener:
                self.listener.state = AlwaysOnListener.STATE_EXECUTING
            self._execute_command(text)
        self.root.after(0, _ui)

    def _on_stop_command(self):
        """Called when 'detente' detected during execution."""
        def _ui():
            self._cancel_flag.set()
            self._log("⏹️ Detente — cancelando acción...", self.YELLOW)
            self.tts.stop()  # Stop any TTS playback too
        self.root.after(0, _ui)

    def _on_shutdown_command(self):
        """Called when 'apágate' detected — turns off always-on."""
        def _ui():
            self._log("🔇 Apagando always-on...", self.YELLOW)
            self._speak_muted("Hasta luego")
            self._stop_always_on()
        self.root.after(0, _ui)

    def _speak_muted(self, text: str):
        """
        Reproduce TTS sin que always-on se escuche a sí mismo.
        Activa un flag temporal para que el listener ignore el micrófono
        mientras Piper está hablando.
        """
        if not text or not self.tts.available:
            return

        def _do_speak():
            if self.listener:
                self.listener._tts_playing = True
            try:
                self.tts.speak(text)
            finally:
                if self.listener:
                    self.listener._tts_playing = False

        threading.Thread(target=_do_speak, daemon=True).start()

    def _speak_muted_blocking(self, text: str):
        """Blocking variant used before voice confirmations to avoid echo."""
        if not text or not self.tts.available:
            return
        if self.listener:
            self.listener._tts_playing = True
        try:
            self.tts.speak(text)
        finally:
            if self.listener:
                self.listener._tts_playing = False

    def _on_partial_text(self, text: str):
        """Called with live partial transcription."""
        def _ui():
            state = self.listener.state if self.listener else ""
            if state == AlwaysOnListener.STATE_LISTENING:
                self.cmd_var.set(text)
                self.status_var.set(f"🎙️ {text}")
            elif state == AlwaysOnListener.STATE_SLEEPING:
                self.always_on_status.set(f"🟢 {text[:50]}")
        self.root.after(0, _ui)

    # ── Recording (push-to-talk) ──────────────────────────

    def _toggle_record(self):
        if not self.recorder:
            self._log("✗ STT no disponible (Moonshine no cargado)", self.RED)
            return

        if self._is_recording:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self):
        # Pause always-on listener while push-to-talk is active
        if self.listener and self.listener.running:
            self.listener.stop()
            self._log("  (always-on pausado)", self.SUBTEXT)

        self._is_recording = True
        self.btn_record.configure(bg=self.RED, fg="#1e1e2e", text="⏹️")
        self.status_var.set("🔴 Grabando... (para al detectar silencio de 3 s)")
        self._log("🎙️ Grabando — para automáticamente al dejar de hablar...", self.RED)

        # VAD callback: se llama desde el hilo de audio cuando hay 3 s de silencio
        def _on_vad_silence():
            if self._is_recording:
                self.root.after(0, self._stop_record)

        self.recorder.on_silence_stop = _on_vad_silence
        self.recorder.start_recording()

        # Pulsar el botón de nuevo sigue funcionando como stop manual

    def _stop_record(self):
        if not self._is_recording:
            return  # ya parado (VAD lo disparó antes que el botón)
        self._is_recording = False
        self.recorder.on_silence_stop = None   # desconectar VAD callback
        self.btn_record.configure(bg=self.SURFACE, fg=self.RED, text="🎙️")
        self.status_var.set("⏳ Transcribiendo...")
        self._log("⏳ Transcribiendo audio...", self.YELLOW)

        def do_transcribe():
            try:
                text = self.recorder.stop_and_transcribe()
                self.root.after(0, lambda: self._on_transcription(text))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"✗ Error STT: {e}", self.RED))
                self.root.after(0, lambda: self.status_var.set("Error en transcripción"))
            finally:
                # Resume always-on if it was active
                if self._always_on and (not self.listener or not self.listener.running):
                    self.root.after(500, self._start_always_on)

        threading.Thread(target=do_transcribe, daemon=True).start()

    def _on_transcription(self, text: str):
        if text:
            self._log(f"✓ \"{text}\"", self.GREEN)
            self.cmd_var.set(text)
            self.status_var.set("Listo — presiona Ejecutar o Enter")
        else:
            self._log("⚠ No se detectó habla", self.YELLOW)
            self.status_var.set("No se detectó habla")

    # ── Execution entry points ─────────────────────────────

    def _execute(self):
        """Execute from GUI button/Enter."""
        command = self.cmd_var.get().strip()
        if not command:
            self._log("⚠ Escribe o graba un comando primero", self.YELLOW)
            return
        self._execute_command(command)

    def _execute_command(self, command: str):
        """Execute a command (from GUI, push-to-talk, or always-on)."""
        if self._busy:
            self._log("⚠ Ya hay una acción en ejecución", self.YELLOW)
            return

        self._busy = True
        self._cancel_flag.clear()
        self.btn_exec.configure(state=tk.DISABLED, bg=self.SURFACE)
        self.cmd_entry.configure(state=tk.DISABLED)
        self.root.focus_set()
        self._log(f"▶ Comando: \"{command}\"", self.BLUE)
        self.status_var.set("🧠 Pensando...")

        threading.Thread(target=self._think_and_run, args=(command,), daemon=True).start()

    # ── Five-Layer Pipeline (Cache + Decomposer + L1/L2/L3) ─

    def _think_and_run(self, command: str):
        """
        Five-layer execution pipeline:
        Layer 0.5: Skill Cache (cached semantic plans) — instant plan recall
        Layer 0.7: Task Decomposer — complex commands → ordered atomic sub-tasks
        Layer 1:   Intent Parser (instant, no GPU) — direct OS actions
        Layer 2:   LLM action tree (no vision) — multi-step plans with keybindings
        Layer 3:   Vision + LLM + Keybindings (PRA loop) — in-app GUI interaction
        """
        # ── Layer 0.5: Skill Cache ────────────────────────
        try:
            cached_skill = self.skill_cache.query(command, threshold=0.85)
            if cached_skill is not None:
                self.root.after(0, lambda: self._log(
                    f"  ⚡ L0.5 CACHE HIT → '{cached_skill.command}' ({cached_skill.success_rate:.0%} success)", self.MAUVE))

                # ── Phase 6: confidence check ──────────────
                # Re-query to get the actual similarity score stored by the last query call
                conf = score_action(
                    command,
                    semantic_sim=getattr(cached_skill, '_last_sim', 1.0),
                    success_rate=cached_skill.success_rate,
                    is_cache_hit=True,
                )
                self.root.after(0, lambda c=conf: self._log(
                    f"  📊 Confianza: {c.score:.0%}  {c.explanation}",
                    self.YELLOW if c.needs_confirm else self.SUBTEXT))

                if conf.needs_confirm:
                    confirmed = self._request_confirmation(
                        f"Ejecutar: '{cached_skill.command}'?",
                        detail=conf.explanation,
                        destructive=conf.is_destructive,
                    )
                    if not confirmed:
                        self.root.after(0, lambda: self._finish_execution("Acción cancelada por el usuario"))
                        return

                self.root.after(0, lambda: self.status_var.set("Ejecutando desde cache..."))
                self._current_skill_id = cached_skill.id

                self.root.after(0, self.root.iconify)
                time.sleep(0.5)

                if self._cancel_flag.is_set():
                    self.root.after(0, lambda: self._finish_execution("Cancelado"))
                    return

                ok = self._execute_cached_skill(cached_skill)

                if ok:
                    self.skill_cache.record_success(cached_skill.id)
                    self.root.after(0, lambda: self._log("  ✓ Plan en cache ejecutado exitosamente", self.GREEN))
                    self.root.after(0, lambda: self._finish_execution("Listo, ejecutado desde cache"))
                else:
                    self.skill_cache.record_failure(cached_skill.id)
                    self.root.after(0, lambda: self._log(
                        "  🔄 Cache falló → continuando con descomposición", self.YELLOW))
                    self._decompose_and_run(command)
                return
        except Exception as e:
            logger.warning(f"Cache lookup error: {e}")

        # ── Layer 0.7: Task Decomposer ────────────────────
        self._decompose_and_run(command)

    def _decompose_and_run(self, command: str):
        """
        Layer 0.7: Decompose command into atomic sub-tasks, then execute each.

        If composite: executes each sub-task in order through the full L1-L3 pipeline,
        so each sub-task benefits from cache, intent parser, and LLM.

        If single/passthrough: falls directly into L1-L3 as before.
        """
        try:
            result = decompose_command(command)
        except Exception as e:
            logger.warning(f"Decomposer error: {e}")
            self._think_and_run_from_layer1(command)
            return

        if result.is_composite:
            n = len(result.subtasks)
            self.root.after(0, lambda: self._log(
                f"  🧩 L0.7 DESCOMPOSICIÓN → {n} sub-tareas ({result.decomposition_method}, {result.confidence:.0%})",
                self.MAUVE))

            all_ok = True
            for subtask in result.subtasks:
                if self._cancel_flag.is_set():
                    self.root.after(0, lambda: self._finish_execution("Cancelado"))
                    return

                self.root.after(0, lambda st=subtask: self._log(
                    f"  ▸ [{st.order+1}/{n}] {st.task_type}: \"{st.command}\"", self.BLUE))

                # Each sub-task runs through the full pipeline (cache → L1 → L2 → L3)
                ok = self._run_subtask(subtask)

                if not ok and not subtask.optional:
                    self.root.after(0, lambda st=subtask: self._log(
                        f"  ✗ Sub-tarea '{st.task_type}' falló — abortando plan", self.RED))
                    all_ok = False
                    break

            msg = "Plan compuesto completado" if all_ok else "Plan compuesto falló"
            tag = self.GREEN if all_ok else self.RED
            self.root.after(0, lambda: self._log(f"  {'✓' if all_ok else '✗'} {msg}", tag))
            self.root.after(0, lambda: self._finish_execution(msg))
        else:
            # Single task: pass directly to L1-L3
            self._think_and_run_from_layer1(command)

    def _run_subtask(self, subtask) -> bool:
        """
        Execute a single sub-task through the cache → L1 → L2 → L3 pipeline.

        Converts task_type + args into a natural-language command and runs it,
        or directly executes known task types without LLM involvement.

        Self-correction (Phase 7):
        - Terminal / app failures try alternatives before escalating.
        - Typing / command failures get one free retry (transient lag).
        - L1 failures automatically escalate to L2 instead of silently failing.
        """
        task_type = subtask.task_type
        args = subtask.args

        # ── open_terminal: cycle through TERMINAL_FALLBACKS ──────────────
        if task_type == "open_terminal":
            current_terminal = TERMINAL_FALLBACKS[0]
            for attempt in range(SelfCorrector.MAX_ATTEMPTS):
                ok = self.executor.launch_app(current_terminal)
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "open_terminal", {"app": current_terminal}, attempt, "launch_failed"
                )
                if correction.strategy == RetryStrategy.TRY_ALTERNATIVE:
                    next_term = correction.alternative_args.get("app", current_terminal)
                    self.root.after(0, lambda o=current_terminal, n=next_term: self._log(
                        f"  ↩ Corrección: '{o}' falló → intentando '{n}'", self.YELLOW))
                    current_terminal = next_term
                elif correction.strategy == RetryStrategy.ESCALATE_L2:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: terminales agotados → escalando L2", self.YELLOW))
                    self._think_and_run_from_layer1(subtask.command)
                    return True  # async
                else:
                    break
            return False

        # ── open_app: try app aliases ─────────────────────────────────────
        if task_type == "open_app":
            app = args.get("app", "")
            if not app:
                return False
            current_app = app
            for attempt in range(SelfCorrector.MAX_ATTEMPTS):
                ok = self.executor.launch_app(current_app)
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "open_app", {"app": current_app}, attempt, "launch_failed"
                )
                if correction.strategy == RetryStrategy.TRY_ALTERNATIVE:
                    next_app = correction.alternative_args.get("app", current_app)
                    self.root.after(0, lambda o=current_app, n=next_app: self._log(
                        f"  ↩ Corrección: '{o}' no encontrado → intentando '{n}'", self.YELLOW))
                    current_app = next_app
                elif correction.needs_escalation:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: app no encontrada → escalando L2", self.YELLOW))
                    self._think_and_run_from_layer1(subtask.command)
                    return True  # async
                else:
                    break
            return False

        # ── run_command: retry once on transient failure ──────────────────
        if task_type == "run_command":
            cmd = args.get("cmd", "")
            if not cmd:
                return False
            for attempt in range(SelfCorrector.MAX_ATTEMPTS):
                ok = self.executor.type_text(cmd, delay=0.03)
                if ok:
                    time.sleep(0.1)
                    ok = self.executor.press_keys("Return")
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "run_command", args, attempt, "type_failed"
                )
                if correction.strategy == RetryStrategy.RETRY_SAME:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: error al escribir comando — reintentando", self.YELLOW))
                    time.sleep(0.3)
                elif correction.needs_escalation:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: run_command → escalando L2", self.YELLOW))
                    self._think_and_run_from_layer1(subtask.command)
                    return True  # async
                else:
                    break
            return False

        # ── compile: retry once, then escalate to L2 ─────────────────────
        if task_type == "compile":
            cmd = args.get("cmd", "")
            if not cmd:
                return False
            for attempt in range(SelfCorrector.MAX_ATTEMPTS):
                ok = self.executor.type_text(cmd, delay=0.03)
                if ok:
                    time.sleep(0.1)
                    ok = self.executor.press_keys("Return")
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "compile", args, attempt, "type_failed"
                )
                if correction.strategy == RetryStrategy.RETRY_SAME:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: error de escritura en compilación — reintentando", self.YELLOW))
                    time.sleep(0.3)
                elif correction.needs_escalation:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: compile → escalando L2", self.YELLOW))
                    self._think_and_run_from_layer1(subtask.command)
                    return True  # async
                else:
                    break
            return False

        # ── type_text: retry once (ydotool lag) ──────────────────────────
        if task_type == "type_text":
            text = args.get("text", "")
            if not text:
                return False
            for attempt in range(SelfCorrector.MAX_ATTEMPTS):
                ok = self.executor.type_text(text, delay=0.04)
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "type_text", args, attempt, "type_failed"
                )
                if correction.strategy == RetryStrategy.RETRY_SAME:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: error de escritura — reintentando", self.YELLOW))
                    time.sleep(0.3)
                elif correction.strategy == RetryStrategy.ESCALATE_L3:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: type_text → escalando L3 (Vision)", self.YELLOW))
                    self._run_layer3(subtask.command)
                    return True  # async
                else:
                    break
            return False

        # ── create_file: escalate to L2 on failure ───────────────────────
        if task_type == "create_file":
            filename = args.get("filename", "")
            content = args.get("content", "")
            if filename and content:
                escaped = content.replace("'", "'\"'\"'")
                cmd = f"printf '{escaped}' > {filename}"
                ok = self.executor.type_text(cmd, delay=0.02)
                if ok:
                    time.sleep(0.1)
                    ok = self.executor.press_keys("Return")
                if ok:
                    return True
                correction = self.corrector.suggest(
                    "create_file", args, 0, "write_failed"
                )
                if correction.needs_escalation:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: create_file → escalando L2", self.YELLOW))
                    self._think_and_run_from_layer1(subtask.command)
                    return True  # async
            return False

        # ── navigate: delegate to L2 (OpenClaw) ──────────────────────────
        if task_type == "navigate":
            target = args.get("target", "")
            if not target:
                return False
            self.root.after(0, lambda: self._log(
                f"  Navegación detectada ('{target}') → delegando a L2 (OpenClaw)", self.CYAN))
            self._think_and_run_from_layer1(subtask.command)
            return True  # async delegated

        # ── close_app: confirm + retry once ──────────────────────────────
        if task_type == "close_app":
            app = args.get("app", "")
            if app:
                conf = score_action(subtask.command, task_type="close_app", is_cache_hit=False)
                if conf.needs_confirm:
                    confirmed = self._request_confirmation(
                        f"Cerrar '{app}'?",
                        detail=conf.explanation,
                        destructive=conf.is_destructive,
                    )
                    if not confirmed:
                        return True   # user cancelled — not an execution failure
            if not app:
                return False
            ok = self.executor.close_window()
            if not ok:
                correction = self.corrector.suggest(
                    "close_app", args, 0, "close_failed"
                )
                if correction.strategy == RetryStrategy.RETRY_SAME:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: close_app — reintentando", self.YELLOW))
                    time.sleep(0.4)
                    ok = self.executor.close_window()
                elif correction.strategy == RetryStrategy.ESCALATE_L3:
                    self.root.after(0, lambda: self._log(
                        "  ↩ Corrección: close_app → escalando L3", self.YELLOW))
                    self._run_layer3(subtask.command)
                    return True  # async
            return ok

        # Fallback: delegate unknown task_type to full L1-L3 pipeline
        self._think_and_run_from_layer1(subtask.command)
        return True  # result handled async by pipeline
    
    def _think_and_run_from_layer1(self, command: str):
        """Continue pipeline from Layer 1 (Intent Parser).

        Phase 7 self-correction:
        - L1 execution failure → escalate to L2 instead of silently finishing.
        - L2 execution failure → escalate to L3.
        """
        # ── Layer 1: Intent Parser ────────────────────────
        intent = parse_intent(command)

        if intent is not None and intent.confidence >= 0.7:
            action = intent.action
            entity = intent.entity
            conf = intent.confidence

            # IN_APP commands go straight to Layer 3
            if action == "IN_APP":
                self.root.after(0, lambda: self._log(
                    "  🎯 L1 → IN_APP detectado → Layer 3", self.MAUVE))
                self._run_layer3(command)
                return

            self.root.after(0, lambda: self._log(
                f"  🎯 L1 → {action}  {entity or ''}  ({conf:.0%})", self.MAUVE))
            self.root.after(0, lambda: self.status_var.set(f"Ejecutando: {action} {entity}"))

            self.root.after(0, self.root.iconify)
            time.sleep(0.5)

            if self._cancel_flag.is_set():
                self.root.after(0, lambda: self._finish_execution("Cancelado"))
                return

            ok = self._execute_intent(intent)

            if ok:
                self.root.after(0, lambda: self._log(
                    f"  ✓ {action} completado", self.GREEN))
                self.root.after(0, lambda: self._finish_execution(
                    f"Listo, {entity or action}"))
                return

            # L1 intent failed → self-correction: escalate to L2
            correction = suggest_layer_escalation(
                current_layer=1, attempt=0, error="intent_failed"
            )
            self.root.after(0, lambda a=action, r=correction.reason: self._log(
                f"  ✗ {a} falló — {r}", self.YELLOW))

            if correction.strategy == RetryStrategy.ABORT or not self.brain.available:
                self.root.after(0, lambda a=action: self._finish_execution(
                    f"No pude {a}"))
                return
            # Fall through to L2 below

        # ── Layer 2: LLM action tree (no vision) ─────────
        if not self.brain.available:
            self.root.after(0, lambda: self._log(
                "  ⚠ No entendido y LLM no disponible", self.YELLOW))
            self.root.after(0, lambda: self._finish_execution(
                "No entendí el comando"))
            return

        self.root.after(0, lambda: self._log(
            "  🔄 L1 no reconoció → escalando a L2 (LLM)", self.YELLOW))
        self.root.after(0, lambda: self.status_var.set("🧠 Generando plan..."))

        self.root.after(0, self.root.iconify)
        time.sleep(0.5)

        if self._cancel_flag.is_set():
            self.root.after(0, lambda: self._finish_execution("Cancelado"))
            return

        # Get active app + keybindings for context
        active_win = self.executor.get_active_window()
        active_app = active_win.get("class", "").lower()
        kb_context = keybindings_to_context(active_app, include_hyprland=True)

        self.root.after(0, lambda a=active_app: self._log(
            f"  📱 App activa: {a or 'desconocida'}", self.SUBTEXT))

        # ── OpenClaw planner (agent) ─────────────────────
        try:
            oc_actions = None
            if self.openclaw.connect():
                oc_actions = self.openclaw.plan(command, active_app, kb_context)
            if oc_actions:
                self.root.after(0, lambda n=len(oc_actions): self._log(
                    f"  🦾 OpenClaw → {n} acciones", self.MAUVE))
                ok = self._execute_plan(oc_actions, "OpenClaw", confirm_each=True)
                if ok:
                    msg = "Plan OpenClaw completado" if not self._cancel_flag.is_set() else "Cancelado"
                    self.root.after(0, lambda m=msg: self._finish_execution(m))
                    return
                self.root.after(0, lambda: self._log(
                    "  ⚠ OpenClaw falló — regresando a L2 local", self.YELLOW))
            elif self.openclaw.last_error:
                self.root.after(0, lambda e=self.openclaw.last_error: self._log(
                    f"  ⚠ OpenClaw no disponible: {e}", self.YELLOW))
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(f"  ⚠ OpenClaw error: {err}", self.YELLOW))

        try:
            result = self.brain.generate_plan(
                command, "[]",
                keybinding_context=kb_context,
                active_app=active_app,
            )
        except Exception as e:
            # L2 exception → self-correction: escalate to L3
            correction = suggest_layer_escalation(
                current_layer=2, attempt=0, error=str(e)
            )
            self.root.after(0, lambda err=e: self._log(
                f"  ✗ Error LLM: {err}", self.RED))
            if correction.strategy == RetryStrategy.ABORT or not self.brain.available:
                self.root.after(0, lambda: self._finish_execution("Error generando plan"))
            else:
                self.root.after(0, lambda r=correction.reason: self._log(
                    f"  ↩ Corrección: {r}", self.YELLOW))
                self._run_layer3(command)
            return

        actions = result.get("actions", [])
        reasoning = result.get("reasoning", "")

        if reasoning:
            self.root.after(0, lambda r=reasoning: self._log(
                f"  💬 {r}", self.SUBTEXT))

        if not actions:
            self.root.after(0, lambda: self._log(
                "  🔄 L2 sin plan → escalando a L3 (Vision+LLM)", self.YELLOW))
            self._run_layer3(command)
            return

        ok = self._execute_plan(actions, "L2")
        if not ok and not self._cancel_flag.is_set():
            self.root.after(0, lambda: self._log(
                "  🔄 L2 falló → escalando a L3 (Vision)", self.YELLOW))
            self._run_layer3(command)
            return

        msg = "Cancelado" if self._cancel_flag.is_set() else "Plan completado"
        self.root.after(0, lambda: self._log(f"  ✓ {msg}", self.GREEN))
        self.root.after(0, lambda: self._finish_execution(msg))

    # ── Layer 3: Vision + LLM + Keybindings (PRA) ────────

    def _run_layer3(self, command: str):
        """
        Layer 3: Vision + LLM + Keybindings (PRA loop).
        Captures the screen, parses UI elements, reads keybindings for the
        active app, and asks the LLM to generate coordinate/key-based actions.
        """
        if not self.brain.available:
            self.root.after(0, lambda: self._log(
                "  ⚠ Layer 3 requiere LLM — no disponible", self.YELLOW))
            self.root.after(0, lambda: self._finish_execution(
                "No puedo hacer eso sin el modelo LLM"))
            return

        self.root.after(0, lambda: self.status_var.set("🧠 L3: Analizando pantalla..."))
        self.root.after(0, self.root.iconify)
        time.sleep(0.5)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            if self._cancel_flag.is_set():
                self.root.after(0, lambda: self._finish_execution("Cancelado"))
                return

            self.root.after(0, lambda a=attempt: self._log(
                f"  📸 L3 intento {a}/{max_attempts}: capturando pantalla...", self.SUBTEXT))

            # PERCEIVE
            active_win = self.executor.get_active_window()
            active_app = active_win.get("class", "").lower()
            active_title = active_win.get("title", "")

            screenshot = self.vision_capture.capture()
            elements = self.vision_parser.parse(screenshot)
            layout_json = self.vision_parser.elements_to_json(elements)
            kb_context = keybindings_to_context(active_app, include_hyprland=False)

            self.root.after(0, lambda a=active_app, t=active_title, n=len(elements): self._log(
                f"  👁 {a}: \"{t[:40]}\" — {n} elementos UI", self.SUBTEXT))

            if kb_context:
                kb_count = kb_context.count("\n")
                self.root.after(0, lambda n=kb_count: self._log(
                    f"  ⌨️  {n} atajos de teclado cargados", self.SUBTEXT))

            # REASON
            self.root.after(0, lambda: self._log(
                "  🧠 LLM razonando (pantalla + atajos)...", self.MAUVE))
            self.root.after(0, lambda: self.status_var.set("🧠 Generando plan in-app..."))

            try:
                result = self.brain.generate_plan(
                    command, layout_json,
                    keybinding_context=kb_context,
                    active_app=active_app,
                )
            except Exception as e:
                self.root.after(0, lambda err=e: self._log(
                    f"  ✗ Error LLM: {err}", self.RED))
                self.root.after(0, lambda: self._finish_execution("Error en análisis"))
                return

            actions = result.get("actions", [])
            reasoning = result.get("reasoning", "")

            if reasoning:
                self.root.after(0, lambda r=reasoning: self._log(
                    f"  💬 {r}", self.SUBTEXT))

            if not actions:
                self.root.after(0, lambda: self._log(
                    "  ⚠ LLM no generó acciones", self.YELLOW))
                self.root.after(0, lambda: self._finish_execution(
                    "No encontré cómo hacer eso"))
                return

            # ACT
            all_ok = self._execute_plan(actions, "L3")

            if all_ok:
                self.root.after(0, lambda: self._log(
                    "  ✓ Plan in-app completado", self.GREEN))
                self.root.after(0, lambda: self._finish_execution("Listo"))
                return
            else:
                if self._cancel_flag.is_set():
                    self.root.after(0, lambda: self._finish_execution("Cancelado"))
                    return
                if attempt < max_attempts:
                    self.root.after(0, lambda: self._log(
                        "  ⚠ Acción falló — reintentando con nueva captura...", self.YELLOW))
                    time.sleep(1)

        self.root.after(0, lambda: self._log(
            "  ✗ No se pudo completar tras 3 intentos", self.RED))
        self.root.after(0, lambda: self._finish_execution(
            "No pude completar la acción"))

    # ── Shared plan executor ──────────────────────────────

    def _listen_for_yes(self, timeout: float = 5.0) -> Optional[bool]:
        """Listen briefly for a spoken 'sí'. Returns True/False/None on error."""
        if not self._model_dir:
            return None
        try:
            import sounddevice as sd  # type: ignore
            import numpy as np  # type: ignore
            from moonshine_voice import Transcriber, ModelArch
        except Exception as e:
            self.root.after(0, lambda: self._log(f"  STT confirmación no disponible: {e}", self.YELLOW))
            return None

        fs = 16000
        dur = max(1.5, min(timeout, 6.0))
        try:
            audio = sd.rec(int(dur * fs), samplerate=fs, channels=1, dtype="float32")
            sd.wait(dur + 0.5)
        except Exception as e:
            self.root.after(0, lambda: self._log(f"  Mic no disponible: {e}", self.YELLOW))
            return None

        data = audio[:, 0].copy() if audio.size else None
        if data is None or not data.size:
            return False

        peak = float(np.max(np.abs(data))) if data.size else 0.0
        if peak > 0:
            data = data / peak * 0.9

        try:
            transcriber = Transcriber(self._model_dir, model_arch=ModelArch.BASE)
            transcript = transcriber.transcribe_without_streaming(data.tolist(), fs)
        except Exception as e:
            self.root.after(0, lambda: self._log(f"  Error transcribiendo confirmación: {e}", self.YELLOW))
            return None

        text_parts = [line.text.strip().lower() for line in transcript.lines if line.text.strip()]
        if not text_parts:
            return False
        text = " ".join(text_parts)
        if "sí" in text or "si" in text:
            return True
        if "no" in text:
            return False
        return False

    def _voice_confirm_action(self, step: dict, desc: str) -> bool:
        """Ask for visual confirmation before executing an action."""
        question = f"¿Ejecutar {step.get('type', 'acción')}: {desc}?"
        self.root.after(0, lambda q=question: self._log(f"  🔐 Esperando confirmación: {q}", self.YELLOW))

        # Directamente mostrar la interfaz gráfica de confirmación en lugar de voz
        confirmed = self._request_confirmation(question)

        if confirmed:
            self.root.after(0, lambda: self._log("    ✔ Confirmado", self.GREEN))
        else:
            self.root.after(0, lambda: self._log("    ✘ Rechazado", self.YELLOW))
        return bool(confirmed)

    def _execute_plan(self, actions: list, layer_tag: str, confirm_each: bool = False) -> bool:
        """Execute a list of actions. Optionally require voice confirm per step."""
        self.root.after(0, lambda n=len(actions): self._log(
            f"  📋 Plan ({layer_tag}): {n} acciones", self.MAUVE))

        for i, step in enumerate(actions):
            if self._cancel_flag.is_set():
                self.root.after(0, lambda: self._log("  ⏹️ Cancelado", self.YELLOW))
                return False

            desc = step.get("target", step.get("text",
                   step.get("key_combo", step.get("type", "?"))))
            stype = step.get("type", "")
            self.root.after(0, lambda d=desc, n=i, t=stype: self._log(
                f"    ▶ [{n+1}] {t}: {d}", self.MAUVE))

            if confirm_each:
                confirmed = self._voice_confirm_action(step, desc)
                if not confirmed:
                    return False

            ok = self._execute_llm_action(step)

            tag = self.GREEN if ok else self.RED
            sym = "✓" if ok else "✗"
            self.root.after(0, lambda s=sym, tg=tag: self._log(f"      {s}", tg))

            if not ok:
                return False

            time.sleep(0.15)

        return True

    def _execute_llm_action(self, step: dict) -> bool:
        """Execute a single action from an LLM-generated plan.
        
        Handles both {'type': 'launch_app'} (local LLM) and
        {'action': 'launch_app'} (OpenClaw CLI) formats.
        """
        # Normalise: OpenClaw returns 'action' key, local LLM uses 'type'
        stype = step.get("type") or step.get("action", "")

        if stype == "tap":
            return self.executor.tap(int(step.get("x", 0)), int(step.get("y", 0)))
        elif stype == "double_click":
            return self.executor.double_click(int(step.get("x", 0)), int(step.get("y", 0)))
        elif stype == "right_click":
            return self.executor.right_click(int(step.get("x", 0)), int(step.get("y", 0)))
        elif stype == "type":
            return self.executor.type_text(step.get("text", ""))
        elif stype == "key":
            return self.executor.key(step.get("key_combo", step.get("key", "")))
        elif stype == "scroll":
            return self.executor.scroll(
                int(step.get("x", 960)), int(step.get("y", 540)),
                step.get("direction", "down"), int(step.get("clicks", 3)))
        elif stype == "hover":
            return self.executor.hover(int(step.get("x", 0)), int(step.get("y", 0)))
        elif stype == "wait":
            time.sleep(step.get("duration", 1))
            return True
        elif stype == "launch_app":
            return self.executor.launch_app(step.get("app", ""))
        elif stype == "close_window":
            return self.executor.close_window()
        elif stype == "focus_window":
            return self.executor.focus_window(step.get("window_class", ""))
        else:
            logger.warning(f"Unknown action type: {stype}")
            return False

    # ── Layer 0.5: Cached skill executor ──────────────────

    def _execute_cached_skill(self, skill: CachedSkill) -> bool:
        """
        Execute a cached semantic skill.
        
        Converts semantic steps to concrete actions using Phase 2 resolver:
        - SemanticStep(intent="click_button", target="Compile") 
          → Resolve "Compile" → (x, y) via AT-SPI2 → Click
        - SemanticStep(intent="type_text", text="hello") → Type the text
        - SemanticStep(intent="key_press", key="Return") → Press the key
        
        Returns True if all steps executed successfully, False otherwise.
        """
        if not skill or not skill.steps:
            return False
        
        # Get active app context for resolver
        active_win = self.executor.get_active_window()
        active_app = active_win.get("class", "").lower()
        
        for i, step in enumerate(skill.steps):
            if self._cancel_flag.is_set():
                return False
            
            try:
                if step.intent == "click_button":
                    # Phase 2: Resolve semantic target → coordinates
                    if step.target:
                        self.root.after(0, lambda t=step.target: self._log(
                            f"    - Resolving button '{t}'...", self.SUBTEXT))
                        
                        # Use AT-SPI2 + OCR resolver
                        element = self.resolver.find_element(step.target, active_app)
                        
                        if element:
                            self.root.after(0, lambda t=step.target, c=element.confidence: self._log(
                                f"    - Found '{t}' at ({element.x}, {element.y}) [{element.method}, {c:.0%}]", self.SUBTEXT))
                            
                            # Click at resolved coordinates
                            ok = self.executor.click_at(element.x, element.y)
                        else:
                            # Phase 2 fallback: Use fallback key combo
                            if step.fallback:
                                self.root.after(0, lambda t=step.target, f=step.fallback: self._log(
                                    f"    - '{t}' not found, using fallback: {f}", self.YELLOW))
                                ok = self.executor.press_keys(step.fallback)
                            else:
                                self.root.after(0, lambda t=step.target: self._log(
                                    f"    - Could not resolve '{t}' and no fallback available", self.RED))
                                ok = False
                    elif step.fallback:
                        # No target, use fallback
                        self.root.after(0, lambda f=step.fallback: self._log(
                            f"    - Using fallback key: {f}", self.SUBTEXT))
                        ok = self.executor.press_keys(step.fallback)
                    else:
                        return False
                
                elif step.intent == "type_text":
                    # Type text directly
                    if step.text:
                        self.root.after(0, lambda t=step.text: self._log(
                            f"    - Typing: '{t}'...", self.SUBTEXT))
                        ok = self.executor.type_text(step.text, delay=0.05)
                    else:
                        return False
                
                elif step.intent == "key_press":
                    # Press key combo
                    if step.key:
                        self.root.after(0, lambda k=step.key: self._log(
                            f"    - Pressing key: {k}", self.SUBTEXT))
                        ok = self.executor.press_keys(step.key)
                    else:
                        return False
                
                elif step.intent == "launch_app":
                    # Launch application
                    if step.target:
                        self.root.after(0, lambda t=step.target: self._log(
                            f"    - Launching app: {t}", self.SUBTEXT))
                        ok = self.executor.launch_app(step.target)
                    else:
                        return False
                
                elif step.intent == "pause":
                    # Sleep for a moment (default 0.5s)
                    delay = float(step.text) if step.text else 0.5
                    self.root.after(0, lambda d=delay: self._log(
                        f"    - Pausing for {d}s...", self.SUBTEXT))
                    time.sleep(delay)
                    ok = True
                
                else:
                    self.root.after(0, lambda intent=step.intent: self._log(
                        f"    ✗ Unknown semantic intent: {intent}", self.RED))
                    return False
                
                if not ok:
                    self.root.after(0, lambda i=i: self._log(
                        f"    ✗ Step {i+1} failed", self.RED))
                    return False
                
                # Small delay between steps for stability
                time.sleep(0.2)
            
            except Exception as e:
                self.root.after(0, lambda err=e, i=i: self._log(
                    f"    ✗ Step {i+1} exception: {err}", self.RED))
                logger.error(f"Cached skill step {i} failed: {e}")
                return False
        
        return True

    # ── Layer 1 intent executor ───────────────────────────

    def _execute_intent(self, intent) -> bool:
        """Execute a parsed intent using Cecil-Hand native actions."""
        action = intent.action
        entity = intent.entity

        if action == "OPEN_APP":
            return self.executor.launch_app(entity)
        elif action == "CLOSE_WINDOW":
            return self.executor.close_window()
        elif action == "MAXIMIZE":
            return self.executor.maximize_window()
        elif action == "MINIMIZE":
            return self.executor.minimize_window()
        elif action == "TYPE_TEXT":
            return self.executor.type_text(entity)
        elif action == "OPEN_PATH":
            return self.executor.open_path(entity)
        elif action == "SWITCH_WS":
            try:
                ws = int(entity)
            except ValueError:
                ws = 1
            return self.executor.switch_workspace(ws)
        elif action == "OPEN_LAUNCHER":
            return self.executor.open_launcher()
        elif action == "CANCEL":
            return self.executor.key("ctrl+c")
        elif action == "SCREENSHOT":
            import subprocess
            try:
                subprocess.Popen(["grim", "-g", "$(slurp)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                return self.executor.key("Print")
        else:
            return False

    def _finish_execution(self, tts_msg: str = ""):
        """Restore UI, optionally speak, and resume continuous always-on listening."""
        self.root.deiconify()
        self.root.lift()

        if self._cancel_flag.is_set():
            self._log("⏹️ Acción cancelada", self.YELLOW)
        else:
            self._log("✓ Completado", self.GREEN)

        self._log("", self.TEXT)
        self.status_var.set("Listo")
        self.btn_exec.configure(state=tk.NORMAL, bg=self.BLUE)
        self.cmd_entry.configure(state=tk.NORMAL)
        self._busy = False
        self._cancel_flag.clear()

        # ── TTS + volver a escuchar ───────────────────────
        if tts_msg:
            self._speak_muted(tts_msg)

        # Always-on continuo: no hace falta repetir "Cecilia" entre comandos.
        if self._always_on and self.listener and self.listener.running:
            self.listener.state = AlwaysOnListener.STATE_LISTENING
            self.always_on_status.set("🟡 Escuchando comando...")
            self.status_var.set("🎙️ Escuchando...")

    # ── Validator callbacks (Phase 4) ─────────────────────

    def _on_validation_event(self, event: ValidationEvent) -> None:
        """
        Receives ValidationEvent from the background validator thread.
        Logs notable events to the GUI terminal (non-blocking via root.after).
        """
        if event.result == "ok":
            return  # Silent for healthy skills — avoid log noise

        if event.result == "degraded":
            msg = f"  ⚠ Validator: skill {event.skill_id[:8]}… degradada ({event.reason})"
            color = self.YELLOW
        elif event.result == "invalid":
            msg = f"  ✗ Validator: skill {event.skill_id[:8]}… eviccionada ({event.reason})"
            color = self.RED
        else:
            return  # "skipped" — nothing to log

        self.root.after(0, lambda m=msg, c=color: self._log(m, c))

    # ── Confidence gate (Phase 6) ────────────────────

    def _request_confirmation(
        self,
        message: str,
        detail: str = "",
        destructive: bool = False,
    ) -> bool:
        """
        Block the calling (worker) thread and show a modal confirmation dialog
        on the main tkinter thread.  Returns True if the user confirms.

        Uses threading.Event to bridge the worker thread and the GUI thread.
        """
        import threading as _th
        result_event = _th.Event()
        confirmed_box = [False]  # mutable container accessible from closure

        def _show_dialog():
            color = self.RED if destructive else self.YELLOW
            icon  = "⚠️ Acción de riesgo" if destructive else "❓ Confirmación"

            # Log the confirmation request
            self._log(f"  {icon}: {message}", color)
            if detail:
                self._log(f"  {detail}", self.SUBTEXT)

            # Build a simple inline confirm row inside the terminal area
            frame = tk.Frame(self.root, bg="#313244", pady=6, padx=10)
            frame.pack(fill=tk.X, padx=20, pady=(0, 6))

            lbl = tk.Label(
                frame, text=f"{icon}  {message}",
                bg="#313244",
                fg=self.RED if destructive else self.YELLOW,
                font=("Cantarell", 11, "bold"),
                wraplength=460, justify=tk.LEFT,
            )
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _confirm():
                confirmed_box[0] = True
                frame.destroy()
                result_event.set()

            def _cancel():
                confirmed_box[0] = False
                frame.destroy()
                result_event.set()

            btn_yes = tk.Button(
                frame, text="✔ Sí",
                font=("Cantarell", 10, "bold"),
                bg=self.RED if destructive else self.GREEN,
                fg="#1e1e2e",
                relief=tk.FLAT, borderwidth=0,
                padx=10, pady=3,
                command=_confirm,
                cursor="hand2",
            )
            btn_yes.pack(side=tk.RIGHT, padx=(4, 0))

            btn_no = tk.Button(
                frame, text="✘ No",
                font=("Cantarell", 10),
                bg="#45475a", fg=self.TEXT,
                relief=tk.FLAT, borderwidth=0,
                padx=10, pady=3,
                command=_cancel,
                cursor="hand2",
            )
            btn_no.pack(side=tk.RIGHT, padx=(0, 4))

            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        self.root.after(0, _show_dialog)
        result_event.wait(timeout=30.0)   # auto-cancel after 30 s
        return confirmed_box[0]


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = CecilApp(root)

    # Clean shutdown
    def on_closing():
        if app.listener:
            app.listener.stop()
        if app.validator and app.validator.running:
            app.validator.stop(timeout=2.0)
        app.tts.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
