"""
Cecil-Ear Service.

Wraps the Moonshine Voice MicTranscriber and IntentRecognizer into a service
that publishes WakeUpEvent and UserCommandEvent to the CecilOs event bus.
"""

import logging
import os
import sys
import time
from typing import Optional

# Add the Moonshine Python package to the path
MOONSHINE_PYTHON_SRC = os.path.join(
    os.path.dirname(__file__),
    "..",
    "Cecil-Ear",
    "moonshine",
    "python",
    "src",
)
if os.path.isdir(MOONSHINE_PYTHON_SRC):
    sys.path.insert(0, os.path.abspath(MOONSHINE_PYTHON_SRC))

from moonshine_voice import (
    MicTranscriber,
    IntentRecognizer,
    IntentMatch,
    TranscriptEventListener,
    LineCompleted,
    LineTextChanged,
    LineStarted,
    ModelArch,
)
from moonshine_voice.download import EmbeddingModelArch

# Use absolute imports from project root (added to sys.path by main.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cecil_core.events import (
    WakeUpEvent,
    UserCommandEvent,
    SystemErrorEvent,
)
from cecil_core.event_bus import EventBus

logger = logging.getLogger("cecil.ear")


class EarService(TranscriptEventListener):
    """
    Cecil-Ear service that listens to the microphone and emits events.

    Responsibilities:
    - Wake word detection via IntentRecognizer (semantic matching).
    - Full speech transcription via MicTranscriber.
    - Publishing WakeUpEvent and UserCommandEvent to the event bus.
    """

    SERVICE_NAME = "cecil-ear"

    def __init__(
        self,
        event_bus: EventBus,
        model_path: str,
        model_arch: ModelArch = ModelArch.BASE,
        embedding_model_path: Optional[str] = None,
        embedding_model_arch: EmbeddingModelArch = EmbeddingModelArch.GEMMA_300M,
        embedding_variant: str = "fp32",
        wake_phrases: Optional[list] = None,
        wake_threshold: float = 0.7,
        device: Optional[int] = None,
        samplerate: int = 16000,
    ):
        """
        Initialize the Ear service.

        Args:
            event_bus: The CecilOs event bus to publish events to.
            model_path: Path to the Moonshine STT model directory.
            model_arch: Model architecture (TINY, BASE, etc.).
            embedding_model_path: Path to embedding model for intent recognition.
            embedding_model_arch: Embedding model architecture.
            embedding_variant: Model variant (fp32, fp16, q8, q4, q4f16).
            wake_phrases: List of wake word phrases (e.g., ["Cecil", "Oye Cecil"]).
            wake_threshold: Similarity threshold for wake word detection.
            device: Audio input device index (None = default).
            samplerate: Audio sample rate in Hz.
        """
        self._bus = event_bus
        self._model_path = model_path
        self._model_arch = model_arch
        self._device = device
        self._samplerate = samplerate
        self._running = False
        self._awake = False  # Whether wake word has been detected

        # Initialize MicTranscriber
        self._mic = MicTranscriber(
            model_path=model_path,
            model_arch=model_arch,
            device=device,
            samplerate=samplerate,
        )
        self._mic.add_listener(self)

        # Initialize IntentRecognizer for wake word detection (if embedding model provided)
        self._intent_recognizer: Optional[IntentRecognizer] = None
        if embedding_model_path and os.path.isdir(embedding_model_path):
            try:
                self._intent_recognizer = IntentRecognizer(
                    model_path=embedding_model_path,
                    model_arch=embedding_model_arch,
                    model_variant=embedding_variant,
                    threshold=wake_threshold,
                )
                # Register wake phrases
                phrases = wake_phrases or ["Cecil", "Oye Cecil", "Hey Cecil"]
                for phrase in phrases:
                    self._intent_recognizer.register_intent(
                        phrase, self._on_wake_detected
                    )
                # Also attach to transcriber so it auto-processes lines
                self._mic.add_listener(self._intent_recognizer)
                logger.info(
                    f"IntentRecognizer loaded with {len(phrases)} wake phrases"
                )
            except Exception as e:
                logger.warning(
                    f"IntentRecognizer not available: {e}. "
                    "Running without wake word detection (always-on mode)."
                )
                self._awake = True  # Always-on if no intent recognizer
        else:
            logger.info(
                "No embedding model path provided. Running in always-on mode "
                "(no wake word detection)."
            )
            self._awake = True

    def _on_wake_detected(
        self, trigger_phrase: str, utterance: str, similarity: float
    ) -> None:
        """Called when a wake phrase is detected by IntentRecognizer."""
        logger.info(
            f"Wake word detected: '{trigger_phrase}' "
            f"(utterance: '{utterance}', similarity: {similarity:.2%})"
        )
        self._awake = True
        self._bus.publish(
            WakeUpEvent(
                source=self.SERVICE_NAME,
                trigger_phrase=trigger_phrase,
                similarity=similarity,
            )
        )

    # --- TranscriptEventListener implementation ---

    def on_line_started(self, event: LineStarted) -> None:
        """A new transcript line has started."""
        pass  # We wait for text to appear

    def on_line_text_changed(self, event: LineTextChanged) -> None:
        """Transcript text is updating in real-time."""
        if self._awake and event.line and event.line.text:
            logger.debug(f"Transcribing: {event.line.text}")

    def on_line_completed(self, event: LineCompleted) -> None:
        """A transcript line is complete — emit UserCommandEvent."""
        if not event.line or not event.line.text:
            return

        text = event.line.text.strip()
        if not text:
            return

        if self._awake:
            logger.info(f"User command: '{text}'")
            self._bus.publish(
                UserCommandEvent(
                    source=self.SERVICE_NAME,
                    text=text,
                )
            )
            # Reset wake state if using wake word detection
            if self._intent_recognizer is not None:
                self._awake = False
                logger.debug("Wake state reset. Waiting for next wake word.")

    # --- Service lifecycle ---

    def start(self) -> None:
        """Start listening to the microphone."""
        logger.info("Cecil-Ear starting...")
        self._running = True
        self._mic.start()
        logger.info("Cecil-Ear listening.")

    def stop(self) -> None:
        """Stop the microphone and release resources."""
        logger.info("Cecil-Ear stopping...")
        self._running = False
        try:
            self._mic.stop()
        except Exception as e:
            logger.error(f"Error stopping MicTranscriber: {e}")
        logger.info("Cecil-Ear stopped.")

    def close(self) -> None:
        """Release all resources."""
        self.stop()
        try:
            self._mic.close()
        except Exception:
            pass
        if self._intent_recognizer:
            try:
                self._intent_recognizer.close()
            except Exception:
                pass
        logger.info("Cecil-Ear resources released.")
