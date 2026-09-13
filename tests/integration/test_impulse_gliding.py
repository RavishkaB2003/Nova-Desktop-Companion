"""
Integration tests for Project NOVA Acoustic Impulse Routing & Continuous Gliding (MOD-003)
Verifies end-to-end interaction across:
- FR-013 & FR-015: State-dependent impulse routing across STANDBY, DICTATING, IDLE_ACTIVE, TRACKING, GLIDE_ACTIVE, CROSSHAIR_ACTIVE
- FR-016 & FR-017: Continuous gliding, spoken directional steering, and atomic halt-and-click
- FR-018: Dual-axis crosshair scanner via voice ("Crosshair", "Lock", "Hit") and acoustic impulses
- FR-021: Emergency stop / cancellation across all active modes
"""

import unittest
from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemState
from nova.core.glider import ContinuousGlider
from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver
from nova.ui.crosshair import CrosshairOverlay
from nova.ui.hud_overlay import HudOverlay


class MockCrawler(UIAutomationCrawler):
    def __init__(self, targets=None):
        super().__init__()
        self._targets = targets or [
            UIElementTarget(1, "Button 1", "Button", (100, 100, 200, 150), 150, 125, 0, 1234),
            UIElementTarget(2, "Button 2", "Button", (300, 100, 400, 150), 350, 125, 0, 1234),
        ]

    def query_foreground_elements(self):
        return [self._targets]

    def revalidate_target(self, target, tolerance_px=5):
        return True


class TestImpulseGlidingIntegration(unittest.TestCase):
    """End-to-end integration test suite for MOD-003."""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()

        self.state_machine = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        self.crawler = MockCrawler()
        self.driver = InputDriver(headless=True)
        self.hud = HudOverlay(root=self.root)
        self.crosshair = CrosshairOverlay(root=self.root, driver=self.driver)
        self.glider = ContinuousGlider(driver=self.driver, speed_px_s=200.0)

        self.coordinator = TagSnapCoordinator(
            state_machine=self.state_machine,
            crawler=self.crawler,
            hud=self.hud,
            driver=self.driver,
            crosshair=self.crosshair,
            glider=self.glider,
        )

    def tearDown(self):
        try:
            self.hud.destroy()
            self.crosshair.destroy()
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_impulse_suppressed_in_standby(self):
        """FR-015: Impulse arriving in STANDBY must be suppressed without clicking."""
        self.state_machine.transition_to(SystemState.STANDBY)
        self.assertEqual(self.state_machine.current_state, SystemState.STANDBY)
        handled = self.coordinator.handle_impulse()
        self.assertFalse(handled)
        self.assertEqual(len(self.driver.injected_clicks), 0)

    def test_impulse_suppressed_in_dictating(self):
        """FR-015: Impulse arriving in DICTATING must be suppressed to prevent accidental clicks."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.state_machine.transition_to(SystemState.DICTATING)
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        handled = self.coordinator.handle_impulse()
        self.assertFalse(handled)
        self.assertEqual(len(self.driver.injected_clicks), 0)

    def test_impulse_in_idle_active_executes_direct_click(self):
        """FR-015: In IDLE_ACTIVE, impulse executes instantaneous left click at cursor."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(500, 300)

        handled = self.coordinator.handle_impulse()
        self.assertTrue(handled)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        cx, cy, button, count = self.driver.injected_clicks[0]
        self.assertEqual((cx, cy), (500, 300))
        self.assertEqual(button, "left")

    def test_impulse_in_tracking_executes_target_click(self):
        """FR-015: In TRACKING with aimed badge, impulse fires target click."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        # Scan targets
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertEqual(self.state_machine.current_state, SystemState.TRACKING)

        # Aim badge 1 (Button 1 at centroid 150, 125)
        self.coordinator.handle_speech_phrase("one")
        self.root.update()
        self.assertIsNotNone(self.coordinator.selected_target)

        # Non-verbal mouth click fires target
        handled = self.coordinator.handle_impulse()
        self.assertTrue(handled)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        cx, cy, button, count = self.driver.injected_clicks[0]
        self.assertEqual((cx, cy), (150, 125))

    def test_glide_mode_steering_and_atomic_halt_click(self):
        """
        FR-016, FR-017, FR-015:
        1. Spoken 'glide' enters GLIDE_ACTIVE
        2. Glider moves at 200 px/s
        3. Spoken 'down' sets heading to 90 deg
        4. Impulse triggers atomic HALT_GLIDE_AND_CLICK and returns to IDLE_ACTIVE
        """
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(200, 200)

        # 1. Spoken 'glide' enters canvas gliding mode
        handled = self.coordinator.handle_speech_phrase("glide")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.GLIDE_ACTIVE)
        self.assertTrue(self.glider.is_gliding)

        # 2. Advance 0.1s east (default heading 0 deg)
        self.glider.step(0.1)
        self.assertEqual(self.driver.get_cursor_pos(), (220, 200))

        # 3. Spoken 'down' updates heading by 90 degrees
        steered = self.coordinator.handle_speech_phrase("down")
        self.assertTrue(steered)
        self.assertEqual(self.glider.heading_degrees, 90.0)

        # Advance 0.1s south
        self.glider.step(0.1)
        self.assertEqual(self.driver.get_cursor_pos(), (220, 220))

        # 4. Acoustic impulse halts glide and clicks at exact stopped coordinate
        impulse_handled = self.coordinator.handle_impulse()
        self.assertTrue(impulse_handled)
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        self.assertEqual(len(self.driver.injected_clicks), 1)
        click_x, click_y, button, count = self.driver.injected_clicks[0]
        self.assertEqual((click_x, click_y), (220, 220))
        self.assertEqual(button, "left")

    def test_crosshair_two_phase_impulse_flow(self):
        """
        FR-018 & FR-015:
        1. Spoken 'crosshair' activates CROSSHAIR_ACTIVE (Phase 1)
        2. Acoustic impulse locks Y (Phase 1 -> Phase 2, click suppressed)
        3. Acoustic impulse locks X, snaps to (X, Y), clicks, and exits to IDLE_ACTIVE
        """
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

        # 1. Spoken 'crosshair'
        handled = self.coordinator.handle_speech_phrase("crosshair")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)
        self.assertTrue(self.crosshair.is_visible)
        self.assertEqual(self.crosshair.phase, 1)

        # Step horizontal sweep down
        self.crosshair.step(0.2)  # Y advances by 80px

        # 2. First impulse: Lock Y
        handled_impulse_1 = self.coordinator.handle_impulse()
        self.assertTrue(handled_impulse_1)
        self.assertEqual(self.crosshair.phase, 2)
        self.assertEqual(len(self.driver.injected_clicks), 0)  # No click yet!

        # Step vertical sweep across
        self.crosshair.step(0.25)  # X advances by 100px

        # 3. Second impulse: Hit and click
        handled_impulse_2 = self.coordinator.handle_impulse()
        self.assertTrue(handled_impulse_2)
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # Click recorded at intersection
        self.assertEqual(len(self.driver.injected_clicks), 1)
        cx, cy, button, count = self.driver.injected_clicks[0]
        self.assertEqual(button, "left")

    def test_crosshair_voice_commands_lock_and_hit(self):
        """FR-018: Spoken 'Lock' and 'Hit' control crosshair scanner."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.handle_speech_phrase("crosshair")
        self.crosshair.step(0.1)

        # Spoken 'lock'
        self.assertTrue(self.coordinator.handle_speech_phrase("lock"))
        self.assertEqual(self.crosshair.phase, 2)
        self.crosshair.step(0.1)

        # Spoken 'hit'
        self.assertTrue(self.coordinator.handle_speech_phrase("hit"))
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertEqual(len(self.driver.injected_clicks), 1)

    def test_emergency_halt_dismisses_all_modes(self):
        """FR-021: Spoken 'halt' dismisses crosshair, halts glider, and resets active state."""
        # Test in GLIDE_ACTIVE
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.handle_speech_phrase("glide")
        self.assertTrue(self.glider.is_gliding)
        self.coordinator.handle_speech_phrase("halt")
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # Test in CROSSHAIR_ACTIVE
        self.coordinator.handle_speech_phrase("crosshair")
        self.assertTrue(self.crosshair.is_visible)
        self.coordinator.handle_speech_phrase("cancel")
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)


if __name__ == "__main__":
    unittest.main()
