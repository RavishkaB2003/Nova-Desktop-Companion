"""
Project NOVA - Unit Tests for Safety Subsystem
Tests ActionArbiter monotonic invalidation (FR-022),
GlobalHotkeyManager interception and clean release (FR-023, SEC-005),
and SafetyCoordinator subsystem orchestration.
"""

import threading
import time
import unittest
from nova.core.enums import SystemEventType, SystemState
from nova.core.safety import (
    ActionArbiter,
    ActionToken,
    GlobalHotkeyManager,
    HOTKEY_ID_CTRL_SHIFT_Q,
    HOTKEY_ID_ESCAPE,
    SafetyCoordinator,
)
from nova.core.state_machine import StateMachine, SystemEvent


class TestSafetyActionArbiter(unittest.TestCase):
    """Unit tests for ActionArbiter (FR-022)."""

    def setUp(self):
        self.arbiter = ActionArbiter(initial_generation=0)

    def test_initial_generation(self):
        self.assertEqual(self.arbiter.current_generation, 0)
        self.assertEqual(self.arbiter.generation, 0)

    def test_monotonic_increment(self):
        gen1 = self.arbiter.bump_generation(reason="TEST_1")
        self.assertEqual(gen1, 1)
        self.assertEqual(self.arbiter.current_generation, 1)

        gen2 = self.arbiter.bump_generation(reason="TEST_2")
        self.assertEqual(gen2, 2)
        self.assertEqual(self.arbiter.current_generation, 2)

    def test_is_valid_generation_check(self):
        token_gen = self.arbiter.current_generation
        self.assertTrue(self.arbiter.is_valid(token_gen))

        # Bump generation: prior generation must be invalid
        self.arbiter.bump_generation(reason="HALT")
        self.assertFalse(self.arbiter.is_valid(token_gen))
        self.assertTrue(self.arbiter.is_valid(self.arbiter.current_generation))
        self.assertFalse(self.arbiter.is_valid(999))

    def test_token_minting_and_validation(self):
        token1 = self.arbiter.mint_token(action_type="tag_click")
        self.assertIsInstance(token1, ActionToken)
        self.assertEqual(token1.generation, 0)
        self.assertEqual(token1.action_type, "tag_click")
        self.assertTrue(self.arbiter.validate_token(token1))

        # Bump generation invalidates token1
        self.arbiter.bump_generation(reason="ESCAPE")
        self.assertFalse(self.arbiter.validate_token(token1))

        # Mint token2 in new generation
        token2 = self.arbiter.mint_token(action_type="dictation_inject")
        self.assertEqual(token2.generation, 1)
        self.assertTrue(self.arbiter.validate_token(token2))

    def test_invalidation_listeners(self):
        notifications = []

        def listener(new_gen: int, reason: str):
            notifications.append((new_gen, reason))

        unregister = self.arbiter.register_invalidation_listener(listener)

        self.arbiter.bump_generation(reason="VOCAL_HALT")
        self.assertEqual(notifications, [(1, "VOCAL_HALT")])

        self.arbiter.bump_generation(reason="HOTKEY_ESCAPE")
        self.assertEqual(notifications, [(1, "VOCAL_HALT"), (2, "HOTKEY_ESCAPE")])

        # Unregister and verify no more notifications
        unregister()
        self.arbiter.bump_generation(reason="ANOTHER_HALT")
        self.assertEqual(len(notifications), 2)

    def test_audit_log_recording(self):
        self.arbiter.bump_generation(reason="REASON_A")
        self.arbiter.bump_generation(reason="REASON_B")

        log = self.arbiter.get_audit_log()
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["generation"], 1)
        self.assertEqual(log[0]["reason"], "REASON_A")
        self.assertEqual(log[1]["generation"], 2)
        self.assertEqual(log[1]["reason"], "REASON_B")

    def test_concurrent_generation_bumps_thread_safety(self):
        threads = []

        def worker():
            for _ in range(25):
                self.arbiter.bump_generation(reason="CONCURRENT_BUMP")

        for _ in range(4):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(self.arbiter.current_generation, 100)


class TestGlobalHotkeyManager(unittest.TestCase):
    """Unit tests for GlobalHotkeyManager (FR-023, SEC-005)."""

    def test_headless_lifecycle(self):
        manager = GlobalHotkeyManager(headless=True)
        self.assertFalse(manager.is_running)

        started = manager.start()
        self.assertTrue(started)
        self.assertTrue(manager.is_running)

        # Stop manager
        manager.stop()
        self.assertFalse(manager.is_running)

    def test_simulate_hotkey_escape(self):
        events = []
        manager = GlobalHotkeyManager(
            on_emergency_hotkey=lambda hid, name: events.append((hid, name)),
            headless=True,
        )
        manager.start()

        manager.simulate_hotkey("escape")
        self.assertEqual(events, [(HOTKEY_ID_ESCAPE, "ESCAPE")])

        manager.simulate_hotkey("esc")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1], (HOTKEY_ID_ESCAPE, "ESCAPE"))

        manager.simulate_hotkey(HOTKEY_ID_ESCAPE)
        self.assertEqual(len(events), 3)

        manager.stop()

    def test_simulate_hotkey_ctrl_shift_q(self):
        events = []
        manager = GlobalHotkeyManager(
            on_emergency_hotkey=lambda hid, name: events.append((hid, name)),
            headless=True,
        )
        manager.start()

        manager.simulate_hotkey("ctrl_shift_q")
        self.assertEqual(events, [(HOTKEY_ID_CTRL_SHIFT_Q, "CTRL_SHIFT_Q")])

        manager.simulate_hotkey(HOTKEY_ID_CTRL_SHIFT_Q)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1], (HOTKEY_ID_CTRL_SHIFT_Q, "CTRL_SHIFT_Q"))

        manager.stop()

    def test_idempotent_stop(self):
        manager = GlobalHotkeyManager(headless=True)
        manager.start()
        manager.stop()
        # Second call to stop should be safe and idempotent
        manager.stop()
        self.assertFalse(manager.is_running)


class TestSafetyCoordinator(unittest.TestCase):
    """Unit tests for SafetyCoordinator."""

    def setUp(self):
        self.arbiter = ActionArbiter()
        self.sm = StateMachine(initial_state=SystemState.STANDBY, arbiter=self.arbiter)
        self.feedbacks = []
        self.coordinator = SafetyCoordinator(
            arbiter=self.arbiter,
            state_machine=self.sm,
            on_halt_feedback=lambda src: self.feedbacks.append(src),
            headless=True,
        )

    def test_trigger_emergency_halt_hooks_and_generation(self):
        hooks_called = []
        self.coordinator.register_cancellation_hook(lambda: hooks_called.append("HUD"))
        self.coordinator.register_cancellation_hook(lambda: hooks_called.append("GLIDER"))
        self.coordinator.register_cancellation_hook(lambda: hooks_called.append("SCROLLER"))

        self.assertEqual(self.arbiter.current_generation, 0)

        new_gen = self.coordinator.trigger_emergency_halt(source="VOCAL_HALT", reset_to_standby=False)
        self.assertEqual(new_gen, 1)
        self.assertEqual(self.arbiter.current_generation, 1)
        self.assertEqual(hooks_called, ["HUD", "GLIDER", "SCROLLER"])
        self.assertEqual(self.feedbacks, ["VOCAL_HALT"])

    def test_physical_hotkey_resets_to_standby(self):
        # Wake up state machine to IDLE_ACTIVE
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

        # Trigger simulated physical hotkey
        self.coordinator.hotkey_manager.simulate_hotkey("escape")

        # Physical hotkey must force state to STANDBY (FR-023)
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)
        self.assertEqual(self.arbiter.current_generation, 1)
        self.assertEqual(self.feedbacks, ["HOTKEY_ESCAPE"])

    def test_hotkey_ctrl_shift_q_forces_standby(self):
        self.sm.transition_to(SystemState.WAKING)
        self.sm.transition_to(SystemState.IDLE_ACTIVE)
        self.sm.transition_to(SystemState.DICTATING)

        self.coordinator.hotkey_manager.simulate_hotkey("ctrl_shift_q")

        self.assertEqual(self.sm.current_state, SystemState.STANDBY)
        self.assertEqual(self.arbiter.current_generation, 1)
        self.assertEqual(self.feedbacks, ["HOTKEY_CTRL_SHIFT_Q"])


if __name__ == "__main__":
    unittest.main()
