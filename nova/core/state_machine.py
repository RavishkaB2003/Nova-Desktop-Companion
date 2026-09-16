"""
Project NOVA - Central State Machine
Thread-safe lifecycle coordinator managing state transitions, validation, and observer notifications.
"""

from dataclasses import dataclass
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set

from nova.core.enums import MascotVisualState, SystemEventType, SystemState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemEvent:
    """Typed event payload dispatched to the state machine."""
    event_type: SystemEventType
    payload: Optional[Dict[str, Any]] = None


# Allowed state transitions: Source -> Set[Destination] (Strictly distinct destinations; no self-loops)
ALLOWED_TRANSITIONS: Dict[SystemState, Set[SystemState]] = {
    SystemState.STANDBY: {
        SystemState.WAKING,
        SystemState.ERROR,
    },
    SystemState.WAKING: {
        SystemState.IDLE_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.IDLE_ACTIVE: {
        SystemState.LISTENING,
        SystemState.DICTATING,
        SystemState.TRACKING,
        SystemState.EXECUTING,
        SystemState.GLIDE_ACTIVE,
        SystemState.CROSSHAIR_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.LISTENING: {
        SystemState.IDLE_ACTIVE,
        SystemState.EXECUTING,
        SystemState.DICTATING,
        SystemState.TRACKING,
        SystemState.GLIDE_ACTIVE,
        SystemState.CROSSHAIR_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.DICTATING: {
        SystemState.IDLE_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.TRACKING: {
        SystemState.EXECUTING,
        SystemState.IDLE_ACTIVE,
        SystemState.GLIDE_ACTIVE,
        SystemState.CROSSHAIR_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.EXECUTING: {
        SystemState.IDLE_ACTIVE,
        SystemState.TRACKING,
        SystemState.GLIDE_ACTIVE,
        SystemState.CROSSHAIR_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.GLIDE_ACTIVE: {
        SystemState.IDLE_ACTIVE,
        SystemState.EXECUTING,
        SystemState.CROSSHAIR_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.CROSSHAIR_ACTIVE: {
        SystemState.IDLE_ACTIVE,
        SystemState.EXECUTING,
        SystemState.GLIDE_ACTIVE,
        SystemState.STANDBY,
        SystemState.ERROR,
    },
    SystemState.ERROR: {
        SystemState.STANDBY,
        SystemState.IDLE_ACTIVE,
    },
}

STATE_TO_VISUAL_MAP: Dict[SystemState, MascotVisualState] = {
    SystemState.STANDBY: MascotVisualState.SLEEPING,
    SystemState.WAKING: MascotVisualState.WAKING,
    SystemState.IDLE_ACTIVE: MascotVisualState.LISTENING,
    SystemState.LISTENING: MascotVisualState.LISTENING,
    SystemState.DICTATING: MascotVisualState.DICTATING,
    SystemState.TRACKING: MascotVisualState.TRACKING,
    SystemState.EXECUTING: MascotVisualState.EXECUTING,
    SystemState.GLIDE_ACTIVE: MascotVisualState.TRACKING,
    SystemState.CROSSHAIR_ACTIVE: MascotVisualState.TRACKING,
    SystemState.ERROR: MascotVisualState.ERROR,
}


class StateMachine:
    """
    Central thread-safe state machine for Project NOVA.
    Guarantees consistent state transitions, observer dispatch, visual mappings,
    and action generation tracking for stale action invalidation.
    """

    def __init__(
        self,
        initial_state: SystemState = SystemState.STANDBY,
        arbiter: Optional[Any] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._current_state: SystemState = initial_state
        from nova.core.safety import ActionArbiter
        self._arbiter: ActionArbiter = arbiter or ActionArbiter(initial_generation=0)
        self._subscribers: List[Callable[[SystemState, SystemState], None]] = []

    @property
    def arbiter(self) -> Any:
        return self._arbiter

    @property
    def current_state(self) -> SystemState:
        with self._lock:
            return self._current_state

    @property
    def current_generation(self) -> int:
        """Returns current monotonically increasing action generation counter (FR-022)."""
        return self._arbiter.current_generation

    @property
    def generation(self) -> int:
        """Alias for current_generation."""
        return self.current_generation

    def bump_generation(self, reason: str = "") -> int:
        """
        Monotonically increment generation counter to invalidate any pending or in-flight actions.
        Returns the new generation id.
        """
        return self._arbiter.bump_generation(reason=reason)

    @property
    def current_visual_state(self) -> MascotVisualState:
        with self._lock:
            return STATE_TO_VISUAL_MAP[self._current_state]

    def subscribe(self, callback: Callable[[SystemState, SystemState], None]) -> Callable[[], None]:
        """Subscribe an observer to state transition notifications."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def transition_to(self, new_state: SystemState) -> bool:
        """
        Attempt a state transition.
        Returns True if successful, False if disallowed by state machine transition rules.
        """
        with self._lock:
            old_state = self._current_state
            if old_state == new_state:
                return True

            allowed_next = ALLOWED_TRANSITIONS.get(old_state, set())
            if new_state not in allowed_next:
                logger.warning("Rejected invalid transition: %s -> %s", old_state, new_state)
                return False

            self._current_state = new_state
            logger.info("State transition committed: %s -> %s", old_state, new_state)
            subscribers_snapshot = list(self._subscribers)

        # Notify observers outside the state lock to avoid reentrancy deadlocks
        for callback in subscribers_snapshot:
            try:
                callback(old_state, new_state)
            except Exception as err:
                logger.exception("Error in state change subscriber: %s", err)

        return True

    def handle_event(self, event: SystemEvent) -> bool:
        """Translate typed system events into state transitions."""
        with self._lock:
            current = self._current_state

            if event.event_type == SystemEventType.EMERGENCY_HALT:
                self.bump_generation(reason="EMERGENCY_HALT")
                return self.transition_to(SystemState.IDLE_ACTIVE if current != SystemState.STANDBY else SystemState.STANDBY)

            if event.event_type == SystemEventType.AUDIO_STREAM_ERROR:
                return self.transition_to(SystemState.ERROR)

            if event.event_type == SystemEventType.AUDIO_STREAM_RESTORED:
                if current == SystemState.ERROR:
                    return self.transition_to(SystemState.STANDBY)
                return True

            if event.event_type == SystemEventType.WAKE_WORD_DETECTED:
                if current == SystemState.STANDBY:
                    if self.transition_to(SystemState.WAKING):
                        return self.transition_to(SystemState.IDLE_ACTIVE)
                    return False
                elif current == SystemState.ERROR:
                    return self.transition_to(SystemState.IDLE_ACTIVE)
                return True

            if event.event_type == SystemEventType.ACTIVATE_TRIGGERED:
                if current == SystemState.ERROR:
                    return self.transition_to(SystemState.STANDBY)
                return True

            if event.event_type == SystemEventType.DEACTIVATE_TRIGGERED:
                self.bump_generation(reason="DEACTIVATE_TRIGGERED")
                if current != SystemState.STANDBY:
                    return self.transition_to(SystemState.STANDBY)
                return True

            if event.event_type == SystemEventType.SLEEP_TRIGGERED:
                self.bump_generation(reason="SLEEP_TRIGGERED")
                return self.transition_to(SystemState.STANDBY)


            if event.event_type == SystemEventType.DICTATION_START:
                return self.transition_to(SystemState.DICTATING)

            if event.event_type == SystemEventType.DICTATION_END:
                return self.transition_to(SystemState.IDLE_ACTIVE)

            if event.event_type == SystemEventType.ACTION_COMMITTED:
                return self.transition_to(SystemState.EXECUTING)

            if event.event_type == SystemEventType.GLIDE_START:
                return self.transition_to(SystemState.GLIDE_ACTIVE)

            if event.event_type == SystemEventType.GLIDE_STOP:
                return self.transition_to(SystemState.IDLE_ACTIVE)

            if event.event_type == SystemEventType.CROSSHAIR_START:
                return self.transition_to(SystemState.CROSSHAIR_ACTIVE)

            if event.event_type == SystemEventType.CROSSHAIR_STOP:
                return self.transition_to(SystemState.IDLE_ACTIVE)

            logger.debug("Unhandled event type %s in state %s", event.event_type, current)
            return False