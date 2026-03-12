"""
Cecil-Vision Service.

Captures and parses the screen on demand, publishing ScreenLayoutEvent
to the event bus when requested.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cecil_core.events import (
    EventType,
    ScreenCaptureRequestEvent,
    ScreenLayoutEvent,
    ScreenElement,
    SystemErrorEvent,
)
from cecil_core.event_bus import EventBus
from cecil_vision.capture import ScreenCapture
from cecil_vision.parser import ScreenParser

logger = logging.getLogger("cecil.vision")


class VisionService:
    """
    Cecil-Vision service that captures and parses the screen.

    Operates on-demand: captures a screenshot and parses it only when
    the event bus receives a ScreenCaptureRequestEvent.
    """

    SERVICE_NAME = "cecil-vision"

    def __init__(self, event_bus: EventBus):
        """
        Initialize the Vision service.

        Args:
            event_bus: The CecilOs event bus.
        """
        self._bus = event_bus
        self._capture = ScreenCapture()
        self._parser = ScreenParser()
        self._running = False

        # Subscribe to capture requests
        self._bus.subscribe(
            EventType.SCREEN_CAPTURE_REQUEST, self._on_capture_request
        )

    def _on_capture_request(self, event: ScreenCaptureRequestEvent) -> None:
        """Handle a screen capture request."""
        if not self._running:
            return

        logger.info("Screen capture requested")
        self.capture_and_publish()

    def capture_and_publish(self) -> None:
        """Capture the screen, parse it, and publish the result."""
        # Take screenshot
        screenshot_path = self._capture.capture()
        if screenshot_path is None:
            self._bus.publish(
                SystemErrorEvent(
                    source=self.SERVICE_NAME,
                    error_message="Failed to capture screenshot",
                    error_type="CaptureError",
                    recoverable=True,
                )
            )
            return

        # Parse screen elements
        raw_elements = self._parser.parse(screenshot_path)

        # Convert to ScreenElement dataclasses
        elements = []
        for el in raw_elements:
            elements.append(
                ScreenElement(
                    name=el.get("name", ""),
                    role=el.get("role", ""),
                    x=el.get("x", 0),
                    y=el.get("y", 0),
                    width=el.get("width", 0),
                    height=el.get("height", 0),
                    text=el.get("text", ""),
                    state=el.get("state", ""),
                )
            )

        # Get window info (best effort)
        window_title = ""
        app_name = ""
        if raw_elements:
            app_name = raw_elements[0].get("app", "")

        # Publish
        layout_event = ScreenLayoutEvent(
            source=self.SERVICE_NAME,
            elements=elements,
            screenshot_path=screenshot_path,
            window_title=window_title,
            app_name=app_name,
        )

        logger.info(
            f"Screen parsed: {len(elements)} elements "
            f"(app: {app_name or 'unknown'})"
        )
        self._bus.publish(layout_event)

    def start(self) -> None:
        """Start the Vision service."""
        self._running = True
        logger.info(
            f"Cecil-Vision started "
            f"(capture: {self._capture.backend})"
        )

    def stop(self) -> None:
        """Stop the Vision service."""
        self._running = False
        logger.info("Cecil-Vision stopped.")

    def close(self) -> None:
        """Release resources."""
        self.stop()
