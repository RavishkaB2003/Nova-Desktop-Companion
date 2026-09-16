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
        self._last_crawled_targets = list(self._targets)

    def query_foreground_elements(self):
        self._last_crawled_targets = list(self._targets)
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
            self.coordinator.destroy()
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

    def test_impulse_in_idle_active_disarmed(self):
        """User feedback: In-place mouth click in IDLE_ACTIVE is disarmed to prevent accidental triggers."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(500, 300)

        handled = self.coordinator.handle_impulse()
        self.assertFalse(handled)
        self.assertEqual(len(self.driver.injected_clicks), 0)

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
        4. Impulse triggers clean halt of glider without firing accidental clicks
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

        # 4. Acoustic impulse halts glide cleanly without injecting accidental clicks
        impulse_handled = self.coordinator.handle_impulse()
        self.assertTrue(impulse_handled)
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        self.assertEqual(len(self.driver.injected_clicks), 0)

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

    def test_crosshair_vocabulary_alternatives(self):
        """Verify 'cross hair', 'scanner', 'laser', 'freeze', 'mark' work smoothly."""
        # Trigger via 'cross hair'
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.assertTrue(self.coordinator.handle_speech_phrase("cross hair"))
        self.assertEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)
        self.assertTrue(self.crosshair.is_visible)

        # Lock via 'freeze'
        self.assertTrue(self.coordinator.handle_speech_phrase("freeze"))
        self.assertEqual(self.crosshair.phase, 2)

        # Hit via 'mark'
        self.assertTrue(self.coordinator.handle_speech_phrase("mark"))
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

    def test_glider_voice_stop_and_click_controls(self):
        """Verify spoken 'move' triggers glider, 'stop' halts, and 'click' fires in GLIDE_ACTIVE."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(300, 300)

        # Trigger via 'move'
        self.assertTrue(self.coordinator.handle_speech_phrase("move"))
        self.assertEqual(self.state_machine.current_state, SystemState.GLIDE_ACTIVE)
        self.assertTrue(self.glider.is_gliding)

        # Stop via 'stop'
        self.assertTrue(self.coordinator.handle_speech_phrase("stop"))
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # Trigger again and halt-click via spoken 'click'
        self.assertTrue(self.coordinator.handle_speech_phrase("glide"))
        self.assertTrue(self.glider.is_gliding)
        self.assertTrue(self.coordinator.handle_speech_phrase("click"))
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertGreaterEqual(len(self.driver.injected_clicks), 1)

    def test_crosshair_phase_1_click_and_direction_locks(self):
        """Spoken 'click' or 'right' in Phase 1 locks Y and transitions to Phase 2."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.handle_speech_phrase("laser")
        self.assertEqual(self.crosshair.phase, 1)

        # Spoken 'click' locks Phase 1 Y coordinate
        self.assertTrue(self.coordinator.handle_speech_phrase("click"))
        self.assertEqual(self.crosshair.phase, 2)

        # Restart and test that 'right' in Phase 1 auto-locks Y and steers Phase 2 right
        self.coordinator.handle_speech_phrase("cancel")
        self.coordinator.handle_speech_phrase("laser")
        self.assertEqual(self.crosshair.phase, 1)
        self.assertTrue(self.coordinator.handle_speech_phrase("right"))
        self.assertEqual(self.crosshair.phase, 2)
        self.assertEqual(self.crosshair._sweep_dir_x, 1)

    def test_glide_no_drift_until_direction_given(self):
        """Spoken 'glide' alone does not start autonomous movement until direction is spoken."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.assertTrue(self.coordinator.handle_speech_phrase("glide"))
        self.assertTrue(self.glider.is_gliding)
        self.assertFalse(self.glider.is_autonomous)

        # Spoken 'down' starts autonomous cruising down
        self.assertTrue(self.coordinator.handle_speech_phrase("down"))
        self.assertTrue(self.glider.is_autonomous)
        self.assertEqual(self.glider.heading_degrees, 90.0)

    def test_closed_dismisses_hud_and_crosshair(self):
        """Spoken 'closed' dismisses HUD and crosshair without starting laser."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.trigger_tag_scan()
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # Spoken 'closed' closes HUD
        self.assertTrue(self.coordinator.handle_speech_phrase("closed"))
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertFalse(self.crosshair.is_visible)
        self.assertNotEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)

    def test_bare_cross_does_not_trigger_laser(self):
        """Bare 'cross' is de-collided and does not start crosshair scanner; 'cross hair' does."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        # 'cross' alone should NOT trigger scanner
        handled = self.coordinator.handle_speech_phrase("cross")
        self.assertFalse(handled)
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # 'cross hair' triggers scanner
        self.assertTrue(self.coordinator.handle_speech_phrase("cross hair"))
        self.assertTrue(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)

    def test_crosshair_speed_modulation(self):
        """Spoken 'slow', 'fast', and 'normal' modulate crosshair sweep speed."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.handle_speech_phrase("laser")
        self.assertEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)
        self.assertEqual(self.crosshair.sweep_speed, 180.0)

        # Spoken 'slow'
        self.assertTrue(self.coordinator.handle_speech_phrase("slow"))
        self.assertEqual(self.crosshair.sweep_speed, 100.0)

        # Spoken 'fast'
        self.assertTrue(self.coordinator.handle_speech_phrase("fast"))
        self.assertEqual(self.crosshair.sweep_speed, 320.0)

        # Spoken 'normal'
        self.assertTrue(self.coordinator.handle_speech_phrase("normal"))
        self.assertEqual(self.crosshair.sweep_speed, 180.0)

    def test_tag_suppression_during_glide(self):
        """Spoken 'tag' or vowel hum is suppressed during GLIDE_ACTIVE without opening badges."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.coordinator.handle_speech_phrase("glide")
        self.assertEqual(self.state_machine.current_state, SystemState.GLIDE_ACTIVE)

        # Spoken 'tag' during glide should be swallowed and NOT transition to TRACKING or show HUD
        self.assertTrue(self.coordinator.handle_speech_phrase("tag"))
        self.assertEqual(self.state_machine.current_state, SystemState.GLIDE_ACTIVE)
        self.assertFalse(self.hud.is_visible)

    def test_crosshair_magnetic_snap_end_to_end(self):
        """Crosshair hit magnetically snaps click to nearby CTA centroid within 65px radius."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

        # 1. Start laser scanner via voice
        self.assertTrue(self.coordinator.handle_speech_phrase("laser"))
        self.assertEqual(self.state_machine.current_state, SystemState.CROSSHAIR_ACTIVE)
        self.assertTrue(self.crosshair.is_visible)

        # 2. Lock Y near Button 1 (bounds: (100, 100, 200, 150), centroid: (150, 125))
        # Lock at Y=115 (10px above centroid)
        self.crosshair._cur_y = 115.0
        self.assertTrue(self.coordinator.handle_speech_phrase("lock"))
        self.assertEqual(self.crosshair.phase, 2)
        self.assertEqual(self.crosshair._locked_y, 115)

        # 3. Hit at X=160 (10px right of centroid, inside button bounds)
        self.crosshair._cur_x = 160.0
        self.assertTrue(self.coordinator.handle_speech_phrase("hit"))

        # 4. Verify overlay dismissed, state returned to IDLE_ACTIVE
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # 5. Verify magnetic snap pulled click to CTA centroid (150, 125)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        click_x, click_y, button, count = self.driver.injected_clicks[0]
        self.assertEqual((click_x, click_y), (150, 125))
        self.assertEqual(button, "left")

    def test_voice_directional_nudging_in_idle_active(self):
        """Spoken 'up', 'down', 'left', 'right', 'nudge', 'jump' step cursor in IDLE_ACTIVE."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(500, 500)

        # 1. Spoken 'up' -> dy = -65 (new calibrated default distance)
        self.assertTrue(self.coordinator.handle_speech_phrase("up"))
        self.assertEqual(self.driver.get_cursor_pos(), (500, 435))

        # 2. Spoken 'nudge down' -> dy = +18 (new micro-nudge distance)
        self.assertTrue(self.coordinator.handle_speech_phrase("nudge down"))
        self.assertEqual(self.driver.get_cursor_pos(), (500, 453))

        # 3. Spoken 'jump left' -> dx = -160 (new jump distance)
        self.assertTrue(self.coordinator.handle_speech_phrase("jump left"))
        self.assertEqual(self.driver.get_cursor_pos(), (340, 453))

        # 4. Spoken 'click' executes direct click at current nudged location
        self.assertTrue(self.coordinator.handle_speech_phrase("click"))
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][:2], (340, 453))

    def test_kinetic_momentum_and_chaining(self):
        """Rapid consecutive nudges accelerate distance, and chained phrases advance in one shot."""
        self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
        self.driver.set_cursor_pos(500, 500)

        # 1. 1st 'up': 65px (1.0x) -> y = 435
        self.assertTrue(self.coordinator.handle_speech_phrase("up"))
        self.assertEqual(self.driver.get_cursor_pos(), (500, 435))

        # 2. 2nd 'up' immediately (<1.2s): 130px (2.0x) -> y = 305
        self.assertTrue(self.coordinator.handle_speech_phrase("up"))
        self.assertEqual(self.driver.get_cursor_pos(), (500, 305))

        # 3. 3rd 'up' immediately: 195px (3.0x) -> y = 110
        self.assertTrue(self.coordinator.handle_speech_phrase("up"))
        self.assertEqual(self.driver.get_cursor_pos(), (500, 110))

        # 4. Single-breath chained utterance 'right right right' -> 3 * 65 = 195px -> x = 695
        self.assertTrue(self.coordinator.handle_speech_phrase("right right right"))
        self.assertEqual(self.driver.get_cursor_pos(), (695, 110))


if __name__ == "__main__":
    unittest.main()
