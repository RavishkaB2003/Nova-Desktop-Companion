"""
Project NOVA - Core System Enums and Types
Authoritative enumeration definitions for system states, visual states, and event dispatch.
"""

from enum import Enum, unique


@unique
class SystemState(str, Enum):
    """Lifecycle and operational states of the NOVA desktop daemon."""
    STANDBY = "STANDBY"
    WAKING = "WAKING"
    IDLE_ACTIVE = "IDLE_ACTIVE"
    LISTENING = "LISTENING"
    DICTATING = "DICTATING"
    TRACKING = "TRACKING"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"


@unique
class MascotVisualState(str, Enum):
    """Glanceable visual states rendered on the MascotWidget canvas."""
    SLEEPING = "SLEEPING"
    WAKING = "WAKING"
    LISTENING = "LISTENING"
    DICTATING = "DICTATING"
    TRACKING = "TRACKING"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"


@unique
class SystemEventType(str, Enum):
    """Asynchronous system event types dispatched across threads."""
    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    SLEEP_TRIGGERED = "SLEEP_TRIGGERED"
    EMERGENCY_HALT = "EMERGENCY_HALT"
    COMMAND_DETECTED = "COMMAND_DETECTED"
    DICTATION_START = "DICTATION_START"
    DICTATION_END = "DICTATION_END"
    ACTION_COMMITTED = "ACTION_COMMITTED"
    AUDIO_STREAM_ERROR = "AUDIO_STREAM_ERROR"
    AUDIO_STREAM_RESTORED = "AUDIO_STREAM_RESTORED"