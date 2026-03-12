"""
Cecil-Hand Service.

Receives ActionPlanEvent from the event bus and executes each step
using the InputExecutor. Reports results back via ExecutionResultEvent.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cecil_core.events import (
    ActionPlanEvent,
    ActionStep,
    ExecutionResultEvent,
    EventType,
    SystemErrorEvent,
)
from cecil_core.event_bus import EventBus
from cecil_hand.executor import InputExecutor

logger = logging.getLogger("cecil.hand")


class HandService:
    """
    Cecil-Hand service that executes action plans on the desktop.

    Listens for ActionPlanEvent, executes each step, and publishes
    ExecutionResultEvent with the outcome.
    """

    SERVICE_NAME = "cecil-hand"

    def __init__(self, event_bus: EventBus):
        """
        Initialize the Hand service.

        Args:
            event_bus: The CecilOs event bus.
        """
        self._bus = event_bus
        self._executor = InputExecutor()
        self._running = False

        # Subscribe to action plan events
        self._bus.subscribe(EventType.ACTION_PLAN, self._on_action_plan)

    def _on_action_plan(self, event: ActionPlanEvent) -> None:
        """Handle an incoming action plan."""
        if not self._running:
            logger.warning("HandService not running, ignoring action plan")
            return

        if not self._executor.available:
            self._bus.publish(
                ExecutionResultEvent(
                    source=self.SERVICE_NAME,
                    success=False,
                    steps_completed=0,
                    total_steps=len(event.steps),
                    error_message="No input backend available (install ydotool or xdotool)",
                    action_plan=event,
                )
            )
            return

        logger.info(
            f"Executing action plan: {len(event.steps)} steps "
            f"(command: '{event.user_command}')"
        )
        if event.reasoning:
            logger.info(f"Reasoning: {event.reasoning}")

        steps_completed = 0
        error_message = ""

        for i, step in enumerate(event.steps):
            logger.info(f"Step {i + 1}/{len(event.steps)}: {step.action_type}")
            success = self._execute_step(step)
            if success:
                steps_completed += 1
            else:
                error_message = (
                    f"Step {i + 1} failed: {step.action_type} "
                    f"(target: '{step.target}')"
                )
                logger.error(error_message)
                break

        result = ExecutionResultEvent(
            source=self.SERVICE_NAME,
            success=(steps_completed == len(event.steps)),
            steps_completed=steps_completed,
            total_steps=len(event.steps),
            error_message=error_message,
            action_plan=event,
        )

        logger.info(
            f"Execution {'succeeded' if result.success else 'failed'}: "
            f"{steps_completed}/{len(event.steps)} steps completed"
        )
        self._bus.publish(result)

    def _execute_step(self, step: ActionStep) -> bool:
        """Execute a single action step."""
        try:
            if step.action_type == "tap":
                return self._executor.tap(step.x, step.y)
            elif step.action_type == "type":
                return self._executor.type_text(step.text)
            elif step.action_type == "key":
                return self._executor.key(step.key_combo)
            elif step.action_type == "swipe":
                return self._executor.swipe(
                    step.x, step.y, step.x2, step.y2, step.duration or 0.3
                )
            elif step.action_type == "wait":
                return self._executor.wait(step.duration or 1.0)
            else:
                logger.warning(f"Unknown action type: {step.action_type}")
                return False
        except Exception as e:
            logger.error(f"Exception executing step {step.action_type}: {e}")
            return False

    def start(self) -> None:
        """Start the Hand service."""
        self._running = True
        logger.info(
            f"Cecil-Hand started (backend: {self._executor.backend})"
        )

    def stop(self) -> None:
        """Stop the Hand service."""
        self._running = False
        logger.info("Cecil-Hand stopped.")

    def close(self) -> None:
        """Release resources."""
        self.stop()
