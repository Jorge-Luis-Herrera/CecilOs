"""Quick import verification test for CecilOs."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing CecilOs imports...")
print()

# 1. Core events
from cecil_core.events import (
    EventType, WakeUpEvent, UserCommandEvent,
    ScreenElement, ScreenLayoutEvent, ScreenCaptureRequestEvent,
    ActionStep, ActionPlanEvent, ExecutionResultEvent,
    SystemErrorEvent, ShutdownEvent,
)
print("  [OK] cecil_core.events")

# 2. Event bus
from cecil_core.event_bus import EventBus
bus = EventBus()
received = []
bus.subscribe(EventType.WAKE_UP, lambda e: received.append(e))
bus.publish(WakeUpEvent(source="test"))
assert len(received) == 1, "EventBus publish/subscribe failed"
print("  [OK] cecil_core.event_bus (pub/sub verified)")

# 3. Hand executor
from cecil_hand.executor import InputExecutor
executor = InputExecutor()
print(f"  [OK] cecil_hand.executor (backend={executor._backend})")

# 4. Vision capture
from cecil_vision.capture import ScreenCapture
cap = ScreenCapture()
print(f"  [OK] cecil_vision.capture (backend={cap._backend})")

# 5. Brain task cache
from cecil_brain.task_cache import TaskCache
cache = TaskCache()
print(f"  [OK] cecil_brain.task_cache (count={cache.count})")

# 6. Brain LLM engine (import only)
from cecil_brain.llm_engine import LLMEngine
print("  [OK] cecil_brain.llm_engine (import only)")

print()
print("All imports verified successfully!")
