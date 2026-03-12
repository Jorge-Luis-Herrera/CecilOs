"""
Cecil-Brain Service.

The decision-making core of CecilOs. Receives user commands and screen layouts,
generates action plans using a local LLM, and publishes them for execution.
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cecil_core.events import (
    EventType,
    UserCommandEvent,
    ScreenLayoutEvent,
    ScreenCaptureRequestEvent,
    ActionPlanEvent,
    ActionStep,
    ExecutionResultEvent,
    SystemErrorEvent,
)
from cecil_core.event_bus import EventBus
from cecil_brain.llm_engine import LLMEngine
from cecil_brain.task_cache import TaskCache

logger = logging.getLogger("cecil.brain")


class BrainService:
    """
    Cecil-Brain service that generates action plans from voice commands.

    Flow:
    1. Receives UserCommandEvent from Cecil-Ear.
    2. Requests screen capture from Cecil-Vision.
    3. Waits for ScreenLayoutEvent.
    4. Generates ActionPlanEvent using LLM + task cache.
    5. After execution, stores successful plans in cache.
    """

    SERVICE_NAME = "cecil-brain"
    MAX_RETRIES = 3

    def __init__(
        self,
        event_bus: EventBus,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        cache_dir: str = None,
    ):
        """
        Initialize the Brain service.

        Args:
            event_bus: The CecilOs event bus.
            model_path: Path to the GGUF model file.
            n_gpu_layers: GPU layers to offload (-1 = all).
            n_ctx: Context window size.
            cache_dir: Directory for task cache.
        """
        self._bus = event_bus
        self._llm = LLMEngine(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
        )
        self._cache = TaskCache(cache_dir)
        self._running = False

        # State for the current task
        self._pending_command: str = ""
        self._current_screen_layout: str = ""
        self._current_app: str = ""
        self._retry_count: int = 0

        # Subscribe to events
        self._bus.subscribe(EventType.USER_COMMAND, self._on_user_command)
        self._bus.subscribe(EventType.SCREEN_LAYOUT, self._on_screen_layout)
        self._bus.subscribe(EventType.EXECUTION_RESULT, self._on_execution_result)

    def _on_user_command(self, event: UserCommandEvent) -> None:
        """Handle a new user command."""
        if not self._running:
            return

        logger.info(f"Received user command: '{event.text}'")
        self._pending_command = event.text
        self._retry_count = 0

        # Request screen capture
        self._bus.publish(
            ScreenCaptureRequestEvent(source=self.SERVICE_NAME)
        )

    def _on_screen_layout(self, event: ScreenLayoutEvent) -> None:
        """Handle screen layout data — generate action plan."""
        if not self._running or not self._pending_command:
            return

        self._current_app = event.app_name
        logger.info(
            f"Screen layout received: {len(event.elements)} elements "
            f"(app: {event.app_name or 'unknown'})"
        )

        # Convert elements to JSON for the LLM
        elements_for_llm = []
        for el in event.elements:
            elements_for_llm.append({
                "name": el.text or el.name,
                "role": el.role,
                "x": el.x + el.width // 2,  # Center X
                "y": el.y + el.height // 2,  # Center Y
                "state": el.state,
            })
        self._current_screen_layout = json.dumps(
            elements_for_llm, ensure_ascii=False, separators=(",", ":")
        )

        # Check task cache for similar commands
        cached = self._cache.find_similar(
            self._pending_command, app_name=event.app_name
        )
        if cached:
            logger.info(f"Found {len(cached)} similar cached tasks")

        # Generate action plan
        logger.info("Generating action plan with LLM...")
        plan = self._llm.generate_action_plan(
            user_command=self._pending_command,
            screen_layout=self._current_screen_layout,
            cached_plans=cached,
        )

        # Convert to ActionPlanEvent
        steps = []
        for action in plan.get("actions", []):
            steps.append(
                ActionStep(
                    action_type=action.get("type", ""),
                    target=action.get("target", ""),
                    x=int(action.get("x", 0)),
                    y=int(action.get("y", 0)),
                    x2=int(action.get("x2", 0)),
                    y2=int(action.get("y2", 0)),
                    text=action.get("text", ""),
                    key_combo=action.get("key_combo", ""),
                    duration=float(action.get("duration", 0)),
                )
            )

        if not steps:
            logger.warning(
                f"LLM generated empty plan. Reasoning: {plan.get('reasoning', 'none')}"
            )

        action_plan = ActionPlanEvent(
            source=self.SERVICE_NAME,
            steps=steps,
            reasoning=plan.get("reasoning", ""),
            user_command=self._pending_command,
        )

        logger.info(
            f"Action plan generated: {len(steps)} steps. "
            f"Reasoning: {plan.get('reasoning', '')[:100]}"
        )
        self._bus.publish(action_plan)

    def _on_execution_result(self, event: ExecutionResultEvent) -> None:
        """Handle execution results — cache success or retry on failure."""
        if not self._running:
            return

        if event.success:
            logger.info("Task completed successfully!")
            # Cache the successful plan
            if event.action_plan and self._pending_command:
                actions = [
                    {
                        "type": s.action_type,
                        "target": s.target,
                        "x": s.x,
                        "y": s.y,
                        "text": s.text,
                        "key_combo": s.key_combo,
                    }
                    for s in event.action_plan.steps
                ]
                self._cache.store(
                    command=self._pending_command,
                    actions=actions,
                    app_name=self._current_app,
                    reasoning=event.action_plan.reasoning,
                )
                logger.info("Successful plan cached for future use")

            # Reset state
            self._pending_command = ""
            self._retry_count = 0
        else:
            # Retry logic
            self._retry_count += 1
            if self._retry_count < self.MAX_RETRIES:
                logger.warning(
                    f"Execution failed ({self._retry_count}/{self.MAX_RETRIES}). "
                    f"Error: {event.error_message}. Retrying..."
                )
                # Request new screen capture and re-plan
                self._bus.publish(
                    ScreenCaptureRequestEvent(source=self.SERVICE_NAME)
                )
            else:
                logger.error(
                    f"Task failed after {self.MAX_RETRIES} retries: "
                    f"{event.error_message}"
                )
                self._pending_command = ""
                self._retry_count = 0

    def start(self) -> None:
        """Start the Brain service and load the LLM."""
        logger.info("Cecil-Brain starting...")
        self._running = True
        try:
            self._llm.load()
        except Exception as e:
            logger.error(f"Failed to load LLM: {e}")
            self._bus.publish(
                SystemErrorEvent(
                    source=self.SERVICE_NAME,
                    error_message=str(e),
                    error_type="ModelLoadError",
                    recoverable=False,
                )
            )
            return
        logger.info(
            f"Cecil-Brain started (cache: {self._cache.count} tasks)"
        )

    def stop(self) -> None:
        """Stop the Brain service."""
        self._running = False
        logger.info("Cecil-Brain stopped.")

    def close(self) -> None:
        """Release all resources."""
        self.stop()
        self._llm.unload()
        logger.info("Cecil-Brain resources released.")
