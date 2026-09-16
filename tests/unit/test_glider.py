"""
Unit tests for NOVA Continuous Glider Subsystem (MOD-003)
Verifies:
- FR-016: Continuous cursor gliding along heading vector at 200 px/s
- FR-017: Spoken directional heading update ("Left", "Right", "Up", "Down")
- FR-015 / FR-11b: Atomic halt-and-click execution
"""

import unittest
from nova.core.glider import ContinuousGlider
from nova.input.driver import InputDriver


class TestContinuousGlider(unittest.TestCase):
    """Test suite for ContinuousGlider."""

    def setUp(self):
        self.driver = InputDriver(headless=True)
        self.glider = ContinuousGlider(driver=self.driver, speed_px_s=200.0)

    def test_default_heading(self):
        """Default heading should be 0.0 deg (Right)."""
        self.assertEqual(self.glider.heading_degrees, 0.0)
        self.assertFalse(self.glider.is_gliding)

    def test_directional_steering(self):
        """FR-017: Directional commands update heading vector."""
        self.assertTrue(self.glider.set_heading_direction("left"))
        self.assertEqual(self.glider.heading_degrees, 180.0)

        self.assertTrue(self.glider.set_heading_direction("up"))
        self.assertEqual(self.glider.heading_degrees, 270.0)

        self.assertTrue(self.glider.set_heading_direction("down"))
        self.assertEqual(self.glider.heading_degrees, 90.0)

        self.assertTrue(self.glider.set_heading_direction("right"))
        self.assertEqual(self.glider.heading_degrees, 0.0)

        self.assertFalse(self.glider.set_heading_direction("diagonal_invalid"))

    def test_heading_rotation(self):
        """Relative heading rotation."""
        self.glider.set_heading_direction("right")
        self.glider.rotate_heading(90.0)
        self.assertEqual(self.glider.heading_degrees, 90.0)
        self.glider.rotate_heading(90.0)
        self.assertEqual(self.glider.heading_degrees, 180.0)

    def test_glide_step_motion(self):
        """FR-016: Glider advances cursor at 200 px/s along heading."""
        self.driver.set_cursor_pos(500, 500)
        self.glider.set_heading_direction("right")  # 0 deg: dx positive, dy 0
        self.glider.start_glide()
        self.assertTrue(self.glider.is_gliding)

        # Step 0.1s: dx = 200 * 0.1 = 20 px
        new_x, new_y = self.glider.step(dt_s=0.1)
        self.assertEqual(new_x, 520)
        self.assertEqual(new_y, 500)

        # Change direction to Down (90 deg): dy positive, dx 0
        self.glider.set_heading_direction("down")
        new_x, new_y = self.glider.step(dt_s=0.1)
        self.assertEqual(new_x, 520)
        self.assertEqual(new_y, 520)

    def test_stop_glide(self):
        """Stop glide halts movement and returns cursor position."""
        self.driver.set_cursor_pos(300, 300)
        self.glider.start_glide()
        self.assertTrue(self.glider.is_gliding)

        pos_x, pos_y = self.glider.stop_glide()
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(pos_x, 300)
        self.assertEqual(pos_y, 300)

    def test_atomic_halt_and_click(self):
        """FR-015 / FR-11b: Atomic halt-and-click halts glide and fires click in same tick."""
        self.driver.set_cursor_pos(400, 400)
        self.glider.set_heading_direction("right")
        self.glider.start_glide()
        self.glider.step(dt_s=0.1)  # moves to 420, 400

        halt_x, halt_y = self.glider.halt_and_click(button="left")
        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(halt_x, 420)
        self.assertEqual(halt_y, 400)

        # Verify click recorded in driver
        self.assertEqual(len(self.driver.injected_clicks), 1)
        click_x, click_y, button, count = self.driver.injected_clicks[0]
        self.assertEqual(click_x, 420)
        self.assertEqual(click_y, 400)
        self.assertEqual(button, "left")
        self.assertEqual(count, 1)

    def test_autonomous_glider_tick_scheduling(self):
        """Autonomous mode schedules 16ms animation ticks via root."""
        class MockRoot:
            def __init__(self):
                self.scheduled = []
                self.cancelled = []
            def after(self, ms, callback):
                self.scheduled.append((ms, callback))
                return len(self.scheduled)
            def after_cancel(self, job_id):
                self.cancelled.append(job_id)

        mock_root = MockRoot()
        glider = ContinuousGlider(driver=self.driver, root=mock_root)
        glider.start_glide(autonomous=True)
        self.assertTrue(glider.is_gliding)
        self.assertTrue(glider.is_autonomous)
        self.assertEqual(len(mock_root.scheduled), 1)
        self.assertEqual(mock_root.scheduled[0][0], 16)

        # Simulate tick
        callback = mock_root.scheduled[0][1]
        callback()
        self.assertEqual(len(mock_root.scheduled), 2)

        # Stop glide cancels
        glider.stop_glide()
        self.assertFalse(glider.is_gliding)
        self.assertFalse(glider.is_autonomous)
        self.assertEqual(len(mock_root.cancelled), 1)

    def test_autonomous_glider_boundary_triggers_on_halt(self):
        """When autonomous glider hits desktop boundary, on_halt callback is invoked."""
        halt_called = []
        glider = ContinuousGlider(driver=self.driver, on_halt=lambda: halt_called.append(True))
        self.driver.set_cursor_pos(0, 500)
        glider.set_heading_direction("left")
        glider.start_glide(autonomous=True)
        glider.step(dt_s=0.1)
        self.assertFalse(glider.is_gliding)
        self.assertEqual(len(halt_called), 1)


if __name__ == "__main__":
    unittest.main()
