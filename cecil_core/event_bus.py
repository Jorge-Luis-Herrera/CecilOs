"""
CecilOs Event Bus.

A lightweight, asyncio-based event bus that connects all Cecil services.
Each service runs in its own process and communicates via multiprocessing queues.
"""

import asyncio
import logging
import time
from multiprocessing import Queue
from typing import Callable, Dict, List, Optional

from .events import CecilEvent, EventType, ShutdownEvent

logger = logging.getLogger("cecil.eventbus")


class EventBus:
    """
    In-process event bus using asyncio.

    Services register handlers for specific event types.
    When an event is published, all registered handlers for that type are invoked.
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._global_handlers: List[Callable] = []
        self._running = False
        self._event_queue: asyncio.Queue = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """
        Subscribe a handler to a specific event type.

        Args:
            event_type: The type of event to listen for.
            handler: Async or sync callable that takes a CecilEvent.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.name}")

    def subscribe_all(self, handler: Callable) -> None:
        """Subscribe a handler to ALL event types (for logging, etc.)."""
        self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """Remove a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    def publish(self, event: CecilEvent) -> None:
        """
        Publish an event to the bus.

        Sets the timestamp if not already set, then dispatches to handlers.
        """
        if event.timestamp == 0.0:
            event.timestamp = time.time()

        logger.debug(
            f"Event published: {event.event_type.name} from {event.source}"
        )

        # Dispatch to type-specific handlers
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    if self._loop and self._loop.is_running():
                        self._loop.create_task(handler(event))
                    else:
                        asyncio.run(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"Error in handler for {event.event_type.name}: {e}",
                    exc_info=True,
                )

        # Dispatch to global handlers
        for handler in self._global_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    if self._loop and self._loop.is_running():
                        self._loop.create_task(handler(event))
                    else:
                        asyncio.run(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in global handler: {e}", exc_info=True)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop for async handler dispatch."""
        self._loop = loop


class MultiProcessEventBus:
    """
    Cross-process event bus using multiprocessing.Queue.

    Each process gets a local EventBus + a shared Queue for cross-process comms.
    A dispatcher thread reads from the shared queue and publishes to the local bus.
    """

    def __init__(self):
        self._shared_queue: Queue = Queue()
        self._local_bus = EventBus()
        self._running = False

    @property
    def local(self) -> EventBus:
        """Get the local (in-process) event bus."""
        return self._local_bus

    @property
    def queue(self) -> Queue:
        """Get the shared multiprocessing queue."""
        return self._shared_queue

    def publish(self, event: CecilEvent) -> None:
        """Publish an event to both local and shared buses."""
        if event.timestamp == 0.0:
            event.timestamp = time.time()
        # Local dispatch
        self._local_bus.publish(event)
        # Cross-process dispatch
        try:
            self._shared_queue.put_nowait(event)
        except Exception as e:
            logger.error(f"Failed to publish to shared queue: {e}")

    def start_dispatcher(self) -> None:
        """Start the background dispatcher that reads from the shared queue."""
        import threading

        self._running = True

        def _dispatch_loop():
            while self._running:
                try:
                    event = self._shared_queue.get(timeout=0.1)
                    self._local_bus.publish(event)
                except Exception:
                    continue  # Timeout or empty queue

        thread = threading.Thread(target=_dispatch_loop, daemon=True)
        thread.start()
        logger.info("Event bus dispatcher started")

    def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False
        # Publish shutdown to local bus
        self._local_bus.publish(
            ShutdownEvent(source="eventbus", reason="Bus stopping")
        )
        logger.info("Event bus stopped")
