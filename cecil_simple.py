#!/usr/bin/env python3
"""
CecilOs — Asistente de Escritorio con Voz.

Modos de operación:
  1. GUI manual: escribe un comando → ejecuta
  2. Push-to-talk: click 🎙️ → graba → transcribe → ejecuta
  3. Always-on: "Hola Cecil" → escucha comando → ejecuta → responde con voz
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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Cecil-Ear", "moonshine", "python", "src"))

from cecil_hand.executor import InputExecutor
from cecil_brain.intent_parser import parse as parse_intent
from cecil_brain.keybindings import keybindings_to_context
from cecil_brain.skill_cache import SkillCache, CachedSkill, SemanticStep
from cecil_vision.capture import ScreenCapture
from cecil_vision.parser import ScreenParser
from cecil_voice.tts import CecilVoice

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cecil")

# Wake word patterns (case-insensitive)
_WAKE_PATTERNS = re.compile(
    r"\b(?:hola\s+cecil|oye\s+cecil|hey\s+cecil|cecil)\b", re.IGNORECASE
)
# Stop command patterns
_STOP_PATTERNS = re.compile(
    r"\b(?:detente|para|stop|cancela|basta)\b", re.IGNORECASE
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
        SLEEPING  → waiting for wake word ("Hola Cecil")
        LISTENING → wake word detected, capturing next command
        EXECUTING → running command, listening for "detente"
    """

    STATE_SLEEPING = "sleeping"
    STATE_LISTENING = "listening"
    STATE_EXECUTING = "executing"

    def __init__(self, model_dir: str, on_wake, on_command, on_stop_command,
                 on_partial_text, on_error):
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

                    state = self._parent._state

                    # During execution, check for stop command immediately
                    if state == AlwaysOnListener.STATE_EXECUTING:
                        if _STOP_PATTERNS.search(text):
                            self._parent._on_stop_command()
                            return

                    # Show partial text
                    self._parent._on_partial_text(text)

                def on_line_completed(self, event):
                    """Fires when VAD detects silence after speech (segment done)."""
                    text = event.line.text.strip()
                    if not text:
                        return

                    state = self._parent._state

                    if state == AlwaysOnListener.STATE_SLEEPING:
                        # Check for wake word
                        if _WAKE_PATTERNS.search(text):
                            # Extract any command after the wake word
                            after = _WAKE_PATTERNS.sub("", text).strip()
                            self._parent.state = AlwaysOnListener.STATE_LISTENING
                            self._parent._on_wake()
                            if after and len(after) > 3:
                                # Wake word + command in same utterance
                                self._parent._on_command(after)
                            return

                    elif state == AlwaysOnListener.STATE_LISTENING:
                        # Full command captured
                        if _STOP_PATTERNS.search(text):
                            self._parent.state = AlwaysOnListener.STATE_SLEEPING
                            return
                        if _WAKE_PATTERNS.search(text):
                            # Just repeated the wake word, ignore
                            return
                        self._parent._on_command(text)
                        return

                    elif state == AlwaysOnListener.STATE_EXECUTING:
                        if _STOP_PATTERNS.search(text):
                            self._parent._on_stop_command()
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
    """Simple push-to-talk: start recording → stop → transcribe."""

    SAMPLE_RATE = 16000

    def __init__(self, model_dir: str):
        import sounddevice as sd
        import numpy as np

        self.sd = sd
        self.np = np
        self._recording = False
        self._audio_chunks = []
        self._transcriber = None
        self._model_dir = model_dir

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

        def callback(indata, frames, time_info, status):
            if self._recording:
                self._audio_chunks.append(indata[:, 0].copy())

        self._stream = self.sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=4096,
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
        self.vision_capture = ScreenCapture()
        self.vision_parser = ScreenParser()
        self.tts = CecilVoice()
        self.skill_cache = SkillCache()  # Layer 0.5: Semantic skill cache

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
        brain_s = f"Qwen ({os.path.basename(self.brain._model_path)})" if self.brain.available else "No disponible"
        cache_s = f"SQLite+JSON ({self.skill_cache.count} skills cached)" if self.skill_cache else "Deshabilitado"
        self._log(f"  Cache:   {cache_s}", self.SUBTEXT)
        self._log(f"  Brain:   L0.5 + L1 + L2 + L3 — {brain_s}", self.SUBTEXT)
        self._log("", self.TEXT)
        self._log("Tip: Activa 'Always-on' y di \"Hola Cecil\"", self.SUBTEXT)
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
        )
        self.listener.start()
        self._always_on = True
        self._update_always_on_button()
        self._log("🎙️ Modo always-on activado", self.GREEN)
        self._log("  Di \"Hola Cecil\" para activar", self.SUBTEXT)

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
            self.always_on_status.set("🟢 Escuchando... di \"Hola Cecil\"")
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
            self.tts.speak_async("Dime")
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
        self.status_var.set("🔴 Grabando... (click para detener)")
        self._log("🎙️ Grabando...", self.RED)
        self.recorder.start_recording()

    def _stop_record(self):
        self._is_recording = False
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

    # ── Four-Layer Pipeline (with Skill Cache) ────────────

    def _think_and_run(self, command: str):
        """
        Four-layer execution pipeline:
        Layer 0.5: Skill Cache (cached semantic plans) — instantly matched commands
        Layer 1: Intent Parser (instant, no GPU) — direct OS actions
        Layer 2: LLM action tree (no vision) — multi-step plans with keybindings
        Layer 3: Vision + LLM + Keybindings (PRA loop) — in-app GUI interaction
        """
        # ── Layer 0.5: Skill Cache ────────────────────────
        try:
            cached_skill = self.skill_cache.query(command, threshold=0.85)
            if cached_skill is not None:
                self.root.after(0, lambda: self._log(
                    f"  ⚡ L0.5 CACHE HIT → '{cached_skill.command}' ({cached_skill.success_rate:.0%} success)", self.MAUVE))
                self.root.after(0, lambda: self.status_var.set(f"Ejecutando desde cache..."))
                self._current_skill_id = cached_skill.id
                
                self.root.after(0, self.root.iconify)
                time.sleep(0.5)
                
                if self._cancel_flag.is_set():
                    self.root.after(0, lambda: self._finish_execution("Cancelado"))
                    return
                
                # Execute cached semantic plan
                ok = self._execute_cached_skill(cached_skill)
                
                if ok:
                    self.skill_cache.record_success(cached_skill.id)
                    self.root.after(0, lambda: self._log("  ✓ Plan en cache ejecutado exitosamente", self.GREEN))
                    self.root.after(0, lambda: self._finish_execution("Listo, ejecutado desde cache"))
                else:
                    self.skill_cache.record_failure(cached_skill.id)
                    self.root.after(0, lambda: self._log(
                        "  🔄 Cache falló → escalando a L1 (Intent Parser)", self.YELLOW))
                    # Fall through to L1
                    self._think_and_run_from_layer1(command)
                
                return
        except Exception as e:
            logger.warning(f"Cache lookup error: {e}")
            # Fall through to L1 if cache fails
            pass
        
        # If no cache hit or cache disabled, proceed to L1
        self._think_and_run_from_layer1(command)
    
    def _think_and_run_from_layer1(self, command: str):
        """Continue pipeline from Layer 1 (Intent Parser)."""
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

            tag = self.GREEN if ok else self.RED
            sym = "✓" if ok else "✗"
            msg = f"{action} {'completado' if ok else 'falló'}"
            self.root.after(0, lambda: self._log(
                f"  {sym} {msg}", tag))
            tts_msg = f"Listo, {entity or action}" if ok else f"No pude {action}"
            self.root.after(0, lambda: self._finish_execution(tts_msg))
            return

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

        try:
            result = self.brain.generate_plan(
                command, "[]",
                keybinding_context=kb_context,
                active_app=active_app,
            )
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(
                f"  ✗ Error LLM: {err}", self.RED))
            self.root.after(0, lambda: self._finish_execution("Error generando plan"))
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

    def _execute_plan(self, actions: list, layer_tag: str) -> bool:
        """Execute a list of LLM-generated actions. Returns True if all succeeded."""
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

            ok = self._execute_llm_action(step)

            tag = self.GREEN if ok else self.RED
            sym = "✓" if ok else "✗"
            self.root.after(0, lambda s=sym, tg=tag: self._log(f"      {s}", tg))

            if not ok:
                return False

            time.sleep(0.15)

        return True

    def _execute_llm_action(self, step: dict) -> bool:
        """Execute a single action from an LLM-generated plan."""
        stype = step.get("type", "")

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
        
        Converts semantic steps to concrete actions:
        - SemanticStep(intent="click_button", target="Compile") → Find "Compile" button, click it
        - SemanticStep(intent="type_text", text="hello") → Type the text
        - SemanticStep(intent="key_press", key="Return") → Press the key
        
        Returns True if all steps executed successfully, False otherwise.
        """
        if not skill or not skill.steps:
            return False
        
        for i, step in enumerate(skill.steps):
            if self._cancel_flag.is_set():
                return False
            
            try:
                if step.intent == "click_button":
                    # Semantic: find button by label, then click
                    if step.target:
                        # TODO: Use AT-SPI2/OCR to resolve target_label → coordinates
                        self.root.after(0, lambda t=step.target: self._log(
                            f"    - Clicking button '{t}'...", self.SUBTEXT))
                        # For now, log it (actual coordinate resolution in Phase 2)
                        ok = True  # Placeholder: would be actual click via executor
                    elif step.fallback:
                        # Fallback to key combo
                        self.root.after(0, lambda f=step.fallback: self._log(
                            f"    - Pressing fallback key: {f}", self.SUBTEXT))
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
        """Restore UI and optionally speak a response."""
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

        # Resume always-on listener → back to sleeping
        if self.listener and self.listener.running:
            self.listener.state = AlwaysOnListener.STATE_SLEEPING
            self._update_always_on_button()

        # Speak response via TTS (non-blocking)
        if tts_msg and self.tts.available:
            self.tts.speak_async(tts_msg)


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = CecilApp(root)

    # Clean shutdown
    def on_closing():
        if app.listener:
            app.listener.stop()
        app.tts.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
