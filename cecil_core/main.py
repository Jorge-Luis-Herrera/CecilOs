"""
CecilOs — Main Orchestrator.

Bootstraps all services (Ear, Vision, Brain, Hand), wires them
through the event bus, and manages the application lifecycle.

Usage:
    python -m cecil_core.main
    python cecil-core/main.py
"""

import asyncio
import logging
import os
import signal
import sys

# -- Path setup ---------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from cecil_core.events import EventType, ShutdownEvent, SystemErrorEvent
from cecil_core.event_bus import EventBus

# -- Logging ------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_LEVEL = os.getenv("CECIL_LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure structured logging for all Cecil modules."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=LOG_FORMAT,
        datefmt="%H:%M:%S",
    )
    # Suppress noisy third-party loggers
    for name in ("urllib3", "chromadb", "llama_cpp", "onnxruntime"):
        logging.getLogger(name).setLevel(logging.WARNING)


logger = logging.getLogger("cecil.main")


# -- Configuration ------------------------------------------------------------
class CecilConfig:
    """Centralized configuration loaded from environment variables."""

    # Cecil-Ear (Moonshine)
    MOONSHINE_ROOT: str = os.path.join(PROJECT_ROOT, "Cecil-Ear", "moonshine")
    MOONSHINE_MODEL: str = os.getenv(
        "CECIL_MOONSHINE_MODEL", "moonshine-es"
    )
    MOONSHINE_USE_INTENT: bool = os.getenv(
        "CECIL_USE_INTENT", "true"
    ).lower() == "true"

    # Cecil-Brain (LLM)
    LLM_MODEL_PATH: str = os.getenv(
        "CECIL_LLM_MODEL",
        os.path.expanduser("~/qwen2.5-1.5b.gguf"),
    )
    LLM_GPU_LAYERS: int = int(os.getenv("CECIL_GPU_LAYERS", "-1"))
    LLM_CTX_SIZE: int = int(os.getenv("CECIL_CTX_SIZE", "4096"))

    # Cecil-Brain (Cache)
    CACHE_DIR: str = os.getenv(
        "CECIL_CACHE_DIR",
        os.path.join(os.path.expanduser("~"), ".cache", "cecil", "task_cache"),
    )

    @classmethod
    def print_config(cls) -> None:
        """Log the active configuration."""
        logger.info("="*60)
        logger.info("CecilOs Configuration")
        logger.info("="*60)
        logger.info(f"  Moonshine root : {cls.MOONSHINE_ROOT}")
        logger.info(f"  Moonshine model: {cls.MOONSHINE_MODEL}")
        logger.info(f"  Intent recognizer: {cls.MOONSHINE_USE_INTENT}")
        logger.info(f"  LLM model      : {cls.LLM_MODEL_PATH}")
        logger.info(f"  LLM GPU layers : {cls.LLM_GPU_LAYERS}")
        logger.info(f"  LLM context    : {cls.LLM_CTX_SIZE}")
        logger.info(f"  Cache dir      : {cls.CACHE_DIR}")
        logger.info("="*60)


# -- Main Application --------------------------------------------------------
class CecilOs:
    """
    Main CecilOs application.

    Orchestrates all four services:
    - Ear:    STT + Wake Word detection
    - Vision: Screen capture + parsing
    - Brain:  LLM action planning
    - Hand:   Input execution
    """

    def __init__(self, config: CecilConfig):
        self.config = config
        self.event_bus = EventBus()
        self.services = {}
        self._shutdown_event = asyncio.Event()

    def _init_services(self) -> None:
        """Initialize all services."""
        logger.info("Initializing services...")

        # -- Cecil-Ear --
        try:
            from cecil_ear.service import EarService
            self.services["ear"] = EarService(
                event_bus=self.event_bus,
                moonshine_root=self.config.MOONSHINE_ROOT,
                model_name=self.config.MOONSHINE_MODEL,
                use_intent_recognizer=self.config.MOONSHINE_USE_INTENT,
            )
            logger.info("✓ Cecil-Ear initialized")
        except Exception as e:
            logger.error(f"✗ Cecil-Ear failed: {e}")

        # -- Cecil-Vision --
        try:
            from cecil_vision.service import VisionService
            self.services["vision"] = VisionService(
                event_bus=self.event_bus,
            )
            logger.info("✓ Cecil-Vision initialized")
        except Exception as e:
            logger.error(f"✗ Cecil-Vision failed: {e}")

        # -- Cecil-Brain --
        try:
            from cecil_brain.service import BrainService
            self.services["brain"] = BrainService(
                event_bus=self.event_bus,
                model_path=self.config.LLM_MODEL_PATH,
                n_gpu_layers=self.config.LLM_GPU_LAYERS,
                n_ctx=self.config.LLM_CTX_SIZE,
                cache_dir=self.config.CACHE_DIR,
            )
            logger.info("✓ Cecil-Brain initialized")
        except Exception as e:
            logger.error(f"✗ Cecil-Brain failed: {e}")

        # -- Cecil-Hand --
        try:
            from cecil_hand.service import HandService
            self.services["hand"] = HandService(
                event_bus=self.event_bus,
            )
            logger.info("✓ Cecil-Hand initialized")
        except Exception as e:
            logger.error(f"✗ Cecil-Hand failed: {e}")

        # -- System event handlers --
        self.event_bus.subscribe(EventType.SHUTDOWN, self._on_shutdown)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._on_system_error)

    def _on_shutdown(self, event: ShutdownEvent) -> None:
        """Handle shutdown event."""
        logger.info(f"Shutdown requested by {event.source}: {event.reason}")
        self._shutdown_event.set()

    def _on_system_error(self, event: SystemErrorEvent) -> None:
        """Handle system errors."""
        if event.recoverable:
            logger.warning(
                f"Recoverable error from {event.source}: "
                f"{event.error_type}: {event.error_message}"
            )
        else:
            logger.critical(
                f"Fatal error from {event.source}: "
                f"{event.error_type}: {event.error_message}"
            )
            self._shutdown_event.set()

    def _start_services(self) -> None:
        """Start all initialized services."""
        logger.info("Starting services...")
        for name, service in self.services.items():
            try:
                service.start()
                logger.info(f"  ▶ {name} started")
            except Exception as e:
                logger.error(f"  ✗ {name} failed to start: {e}")

    def _stop_services(self) -> None:
        """Stop all services gracefully."""
        logger.info("Stopping services...")
        for name, service in reversed(list(self.services.items())):
            try:
                if hasattr(service, "close"):
                    service.close()
                elif hasattr(service, "stop"):
                    service.stop()
                logger.info(f"  ■ {name} stopped")
            except Exception as e:
                logger.error(f"  ✗ {name} failed to stop: {e}")

    async def run(self) -> None:
        """Run CecilOs until shutdown."""
        self.config.print_config()
        self._init_services()

        if not self.services:
            logger.critical("No services initialized. Exiting.")
            return

        self._start_services()

        logger.info("")
        logger.info("╔══════════════════════════════════════════╗")
        logger.info("║   CecilOs is running. Say 'Cecil'!      ║")
        logger.info("║   Press Ctrl+C to stop.                 ║")
        logger.info("╚══════════════════════════════════════════╝")
        logger.info("")

        # Wait for shutdown
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass

        self._stop_services()
        logger.info("CecilOs stopped. Goodbye!")


# -- Entry point --------------------------------------------------------------
def main() -> None:
    """Entry point for CecilOs."""
    setup_logging()
    logger.info("CecilOs starting...")

    config = CecilConfig()
    app = CecilOs(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Handle SIGINT/SIGTERM for graceful shutdown
    def signal_handler():
        logger.info("Signal received, shutting down...")
        app._shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
