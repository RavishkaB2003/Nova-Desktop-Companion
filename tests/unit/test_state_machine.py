"""
Project NOVA - Unit Tests for State Machine
"""

import threading
import unittest
from nova.core.enums import MascotVisualState, SystemEventType, SystemState
from nova.core.state_machine import StateMachine, SystemEvent


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.sm = StateMachine(initial_state=SystemState.STANDBY)

    def test_initial_state(self):
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)
        self.assertEqual(self.sm.current_visual_state, MascotVisualState.SLEEPING)

    def test_valid_transitions(self):
        # STANDBY -> WAKING -> IDLE_ACTIVE -> LISTENING -> EXECUTING -> IDLE_ACTIVE -> STANDBY
        self.assertTrue(self.sm.transition_to(SystemState.WAKING))
        self.assertEqual(self.sm.current_state, SystemState.WAKING)
        self.assertEqual(self.sm.current_visual_state, MascotVisualState.WAKING)

        self.assertTrue(self.sm.transition_to(SystemState.IDLE_ACTIVE))
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertEqual(self.sm.current_visual_state, MascotVisualState.LISTENING)

        self.assertTrue(self.sm.transition_to(SystemState.LISTENING))
        self.assertEqual(self.sm.current_state, SystemState.LISTENING)

        self.assertTrue(self.sm.transition_to(SystemState.EXECUTING))
        self.assertEqual(self.sm.current_state, SystemState.EXECUTING)
        self.assertEqual(self.sm.current_visual_state, MascotVisualState.EXECUTING)

        self.assertTrue(self.sm.transition_to(SystemState.IDLE_ACTIVE))
        self.assertTrue(self.sm.transition_to(SystemState.STANDBY))
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

    def test_invalid_transitions(self):
        # Cannot jump from STANDBY directly to EXECUTING or DICTATING
        self.assertFalse(self.sm.transition_to(SystemState.EXECUTING))
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

        self.assertFalse(self.sm.transition_to(SystemState.DICTATING))
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

    def test_idempotent_self_transition(self):
        self.assertTrue(self.sm.transition_to(SystemState.STANDBY))
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

    def test_observer_subscription(self):
        notifications = []

        def on_change(old, new):
            notifications.append((old, new))

        unsubscribe = self.sm.subscribe(on_change)
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)

        self.assertEqual(
            notifications,
            [
                (SystemState.STANDBY, SystemState.WAKING),
                (SystemState.WAKING, SystemState.IDLE_ACTIVE),
            ],
        )

        # Unsubscribe and verify no further notifications
        unsubscribe()
        self.sm.transition_to(SystemState.LISTENING)
        self.assertEqual(len(notifications), 2)

    def test_handle_wake_event(self):
        # WAKE_WORD_DETECTED from STANDBY transitions through WAKING to IDLE_ACTIVE
        res = self.sm.handle_event(SystemEvent(event_type=SystemEventType.WAKE_WORD_DETECTED))
        self.assertTrue(res)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

    def test_handle_sleep_event(self):
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

        res = self.sm.handle_event(SystemEvent(event_type=SystemEventType.SLEEP_TRIGGERED))
        self.assertTrue(res)
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

    def test_handle_emergency_halt(self):
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)
        self.sm.transition_to(SystemState.EXECUTING)

        res = self.sm.handle_event(SystemEvent(event_type=SystemEventType.EMERGENCY_HALT))
        self.assertTrue(res)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

    def test_handle_audio_error_and_recovery(self):
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)

        self.sm.handle_event(SystemEvent(event_type=SystemEventType.AUDIO_STREAM_ERROR))
        self.assertEqual(self.sm.current_state, SystemState.ERROR)
        self.assertEqual(self.sm.current_visual_state, MascotVisualState.ERROR)

        self.sm.handle_event(SystemEvent(event_type=SystemEventType.AUDIO_STREAM_RESTORED))
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)

    def test_concurrent_transitions_thread_safety(self):
        errors = []

        def worker(target_state):
            try:
                for _ in range(50):
                    self.sm.transition_to(target_state)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker, args=(SystemState.STANDBY,))
        t2 = threading.Thread(target=worker, args=(SystemState.WAKING,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])
        self.assertIn(self.sm.current_state, (SystemState.STANDBY, SystemState.WAKING))


if __name__ == "__main__":
    unittest.main()
