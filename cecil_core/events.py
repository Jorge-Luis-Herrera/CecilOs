"""
CecilOs Event Definitions.

These dataclasses define the contracts between all Cecil services.
Each event is a typed message that flows through the event bus.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """Types of events that flow through the CecilOs event bus."""
    WAKE_UP = auto()
    USER_COMMAND = auto()
    SCREEN_LAYOUT = auto()
    SCREEN_CAPTURE_REQUEST = auto()
    ACTION_PLAN = auto()
    EXECUTION_RESULT = auto()
    SYSTEM_ERROR = auto()
    SHUTDOWN = auto()


@dataclass
class CecilEvent:
    """Base class for all Cecil events."""
    source: str  # Service name that emitted the event
    event_type: EventType = None  # Auto-set by subclass __post_init__
    timestamp: float = 0.0


@dataclass
class WakeUpEvent(CecilEvent):
    """Emitted by Cecil-Ear when wake word is detected."""
    trigger_phrase: str = ""
    similarity: float = 0.0

    def __post_init__(self):
        self.event_type = EventType.WAKE_UP


@dataclass
class UserCommandEvent(CecilEvent):
    """Emitted by Cecil-Ear when a full user command is transcribed."""
    text: str = ""
    confidence: float = 0.0

    def __post_init__(self):
        self.event_type = EventType.USER_COMMAND


@dataclass
class ScreenElement:
    """A single interactable element on screen."""
    name: str
    role: str  # button, text_field, label, image, etc.
    x: int
    y: int
    width: int
    height: int
    text: str = ""
    state: str = ""  # enabled, disabled, focused, etc.


@dataclass
class ScreenLayoutEvent(CecilEvent):
    """Emitted by Cecil-Vision with the parsed screen structure."""
    elements: List[ScreenElement] = field(default_factory=list)
    screenshot_path: str = ""
    window_title: str = ""
    app_name: str = ""

    def __post_init__(self):
        self.event_type = EventType.SCREEN_LAYOUT


@dataclass
class ScreenCaptureRequestEvent(CecilEvent):
    """Emitted by Cecil-Brain to request a new screen capture."""

    def __post_init__(self):
        self.event_type = EventType.SCREEN_CAPTURE_REQUEST


@dataclass
class ActionStep:
    """A single action to be executed by Cecil-Hand."""
    action_type: str  # tap, type, key, swipe, wait
    target: str = ""  # Description of the target element
    x: int = 0
    y: int = 0
    x2: int = 0  # For swipe end point
    y2: int = 0
    text: str = ""  # For type action
    key_combo: str = ""  # For key action (e.g., "super", "ctrl+c")
    duration: float = 0.0  # For wait action (seconds)


@dataclass
class ActionPlanEvent(CecilEvent):
    """Emitted by Cecil-Brain with a plan of actions to execute."""
    steps: List[ActionStep] = field(default_factory=list)
    reasoning: str = ""
    user_command: str = ""

    def __post_init__(self):
        self.event_type = EventType.ACTION_PLAN


@dataclass
class ExecutionResultEvent(CecilEvent):
    """Emitted by Cecil-Hand after executing an action plan."""
    success: bool = False
    steps_completed: int = 0
    total_steps: int = 0
    error_message: str = ""
    action_plan: Optional[ActionPlanEvent] = None

    def __post_init__(self):
        self.event_type = EventType.EXECUTION_RESULT


@dataclass
class SystemErrorEvent(CecilEvent):
    """Emitted by any service when a critical error occurs."""
    error_message: str = ""
    error_type: str = ""
    recoverable: bool = True

    def __post_init__(self):
        self.event_type = EventType.SYSTEM_ERROR


@dataclass
class ShutdownEvent(CecilEvent):
    """Emitted to gracefully shut down all services."""
    reason: str = ""

    def __post_init__(self):
        self.event_type = EventType.SHUTDOWN
