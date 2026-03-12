"""
Cecil-Voice — Text-to-Speech (Piper TTS).

Síntesis de voz local usando Piper TTS con modelos ONNX.
Corre 100% en CPU, 0 VRAM. Soporta español (es_MX).

Uso:
    voice = CecilVoice()
    voice.speak("Hola, soy Cecil")          # blocking
    voice.speak_async("Hola, soy Cecil")    # non-blocking (thread)
    voice.stop()                             # interrupt playback
"""

import io
import logging
import os
import threading
import wave
from typing import Optional

logger = logging.getLogger("cecil.voice")

# Default model path (relative to project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_MODEL = os.path.join(_PROJECT_ROOT, "models", "tts", "es_MX-claude-high.onnx")


class CecilVoice:
    """
    Local text-to-speech engine using Piper TTS.

    Synthesizes Spanish speech on CPU (ONNX Runtime).
    Plays audio via sounddevice. Thread-safe.
    """

    def __init__(self, model_path: Optional[str] = None):
        self._model_path = model_path or _DEFAULT_MODEL
        self._voice = None
        self._lock = threading.Lock()
        self._playing = False
        self._stop_event = threading.Event()
        self._playback_thread: Optional[threading.Thread] = None
        self._sample_rate = 22050  # Piper default

        if not os.path.isfile(self._model_path):
            logger.error(f"TTS model not found: {self._model_path}")
        else:
            logger.info(f"TTS model: {os.path.basename(self._model_path)}")

    def _ensure_loaded(self):
        """Lazy-load the Piper voice model."""
        if self._voice is not None:
            return
        try:
            from piper import PiperVoice
            self._voice = PiperVoice.load(self._model_path)
            # Read sample rate from config
            config_path = self._model_path + ".json"
            if os.path.isfile(config_path):
                import json
                with open(config_path) as f:
                    config = json.load(f)
                self._sample_rate = config.get("audio", {}).get("sample_rate", 22050)
            logger.info(f"TTS loaded: {self._sample_rate}Hz")
        except Exception as e:
            logger.error(f"Failed to load TTS: {e}")
            raise

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to WAV audio bytes.

        Args:
            text: Text to speak (Spanish).

        Returns:
            WAV file bytes (int16, mono, at self._sample_rate).
        """
        self._ensure_loaded()

        buf = io.BytesIO()
        wav_file = wave.open(buf, "wb")
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(self._sample_rate)

        # Piper synthesize() yields AudioChunk objects
        for chunk in self._voice.synthesize(text):
            wav_file.writeframes(chunk.audio_int16_bytes)

        wav_file.close()
        return buf.getvalue()

    def speak(self, text: str) -> None:
        """
        Speak text aloud (blocking). Can be interrupted by stop().

        Args:
            text: Text to speak.
        """
        if not text or not os.path.isfile(self._model_path):
            return

        try:
            import sounddevice as sd
            import numpy as np

            self._ensure_loaded()
            self._stop_event.clear()
            self._playing = True

            # Collect all audio chunks (Piper yields AudioChunk objects)
            audio_chunks = []
            for chunk in self._voice.synthesize(text):
                if self._stop_event.is_set():
                    break
                audio_chunks.append(chunk.audio_float_array)
                self._sample_rate = chunk.sample_rate

            if self._stop_event.is_set():
                self._playing = False
                return

            if not audio_chunks:
                self._playing = False
                return

            audio = np.concatenate(audio_chunks)

            # Play with sounddevice (blocking but interruptible)
            sd.play(audio, samplerate=self._sample_rate)

            # Wait for playback, checking stop_event every 100ms
            while sd.get_stream().active and not self._stop_event.is_set():
                sd.sleep(100)

            if self._stop_event.is_set():
                sd.stop()

            self._playing = False

        except Exception as e:
            logger.error(f"TTS playback error: {e}")
            self._playing = False

    def speak_async(self, text: str) -> None:
        """
        Speak text aloud in a background thread (non-blocking).

        Args:
            text: Text to speak.
        """
        if not text:
            return

        # Stop any current playback first
        self.stop()

        self._playback_thread = threading.Thread(
            target=self.speak, args=(text,), daemon=True
        )
        self._playback_thread.start()

    def stop(self) -> None:
        """Stop any current playback immediately."""
        self._stop_event.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.0)
        self._playing = False

    @property
    def is_playing(self) -> bool:
        """Whether audio is currently playing."""
        return self._playing

    @property
    def available(self) -> bool:
        """Whether TTS is available (model file exists)."""
        return os.path.isfile(self._model_path)
