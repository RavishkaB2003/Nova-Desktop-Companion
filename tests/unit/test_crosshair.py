"""
Unit tests for NOVA Crosshair HUD Overlay Subsystem (MOD-003)
Verifies:
- FR-018: Dual-axis crosshair scanner bounded by virtual desktop metrics
- FR-017: Directional steering ("Left", "Right", "Up", "Down")
- FR-015 / FR-11b: Two-phase coordinate lock and hit execution
"""

import unittest
from nova.input.driver import InputDriver
from nova.ui.crosshair import CrosshairOverlay


class TestCrosshairOverlay(unittest.TestCase):
    """Test suite for CrosshairOverlay."""

    def setUp(self):
        self.driver = InputDriver(headless=True)
        self.hit_coords = None

        def on_hit(x, y):
            self.hit_coords = (x, y)

        self.crosshair = CrosshairOverlay(
            root=None,
            driver=self.driver,
            sweep_speed=400.0,
            on_hit_complete=on_hit,
        )

    def test_initial_state(self):
        """Overlay starts hidden, in phase 1."""
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.crosshair.phase, 1)

    def test_start_and_phase_1_horizontal_sweep(self):
        """Start initiates Phase 1 sweeping Y across screen."""
        self.crosshair.start()
        self.assertTrue(self.crosshair.is_visible)
        self.assertEqual(self.crosshair.phase, 1)

        # Step 0.1s: sweep_speed = 400 px/s -> cur_y increases by 40 px
        start_x, start_y = self.crosshair.current_coordinates
        self.crosshair.step(0.1)
        next_x, next_y = self.crosshair.current_coordinates
        self.assertEqual(next_y, start_y + 40)

    def test_directional_steering(self):
        """FR-017: Spoken direction updates sweep vector."""
        self.crosshair.start()
        # In Phase 1, up sweeps up (-1)
        self.assertTrue(self.crosshair.set_sweep_direction("up"))
        self.crosshair.step(0.1)
        # In Phase 2, left sweeps left (-1)
        self.crosshair.lock_y()
        self.assertTrue(self.crosshair.set_sweep_direction("left"))

    def test_two_phase_lock_and_hit(self):
        """FR-018: Phase 1 locks Y, Phase 2 locks X, snaps, and fires click."""
        self.crosshair.start()
        self.crosshair.step(0.2)  # y moves by 80
        locked_y = self.crosshair.lock_y()

        self.assertEqual(self.crosshair.phase, 2)
        self.assertEqual(self.crosshair._locked_y, locked_y)
        # Suppresses OS click in Phase 1 (no click fired yet)
        self.assertEqual(len(self.driver.injected_clicks), 0)

        # Step in Phase 2: x moves
        self.crosshair.step(0.25)  # x moves by 100
        final_x, final_y = self.crosshair.hit_and_click()

        # Overlay dismisses after hit
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(final_y, locked_y)
        self.assertEqual(self.hit_coords, (final_x, final_y))

        # Click recorded in driver at exact locked intersection
        self.assertEqual(len(self.driver.injected_clicks), 1)
        click_x, click_y, button, count = self.driver.injected_clicks[0]
        self.assertEqual(click_x, final_x)
        self.assertEqual(click_y, final_y)
        self.assertEqual(button, "left")

    def test_hide_dismisses_cleanly(self):
        """Hiding overlay resets phase and visibility."""
        self.crosshair.start()
        self.assertTrue(self.crosshair.is_visible)
        self.crosshair.hide()
        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.crosshair.phase, 1)

    def test_hit_and_click_with_magnetic_snap(self):
        """Magnetic CTA snapping pulls final click to CTA centroid when resolver returns match."""
        # Resolver maps (140, 160) to nearby CTA at (150, 165)
        def mock_resolver(x, y):
            if abs(x - 140) <= 20 and abs(y - 160) <= 20:
                return (150, 165)
            return None

        self.crosshair.snap_resolver = mock_resolver
        self.crosshair.start()
        self.crosshair._cur_y = 160.0
        self.crosshair.lock_y()
        self.crosshair._cur_x = 140.0

        final_x, final_y = self.crosshair.hit_and_click()

        # Final click pulled to CTA centroid (150, 165)
        self.assertEqual((final_x, final_y), (150, 165))
        self.assertEqual(self.hit_coords, (150, 165))
        self.assertEqual(len(self.driver.injected_clicks), 1)
        click_x, click_y, button, count = self.driver.injected_clicks[0]
        self.assertEqual((click_x, click_y), (150, 165))

    def test_hit_and_click_magnetic_snap_miss(self):
        """When resolver returns None (no CTA within radius), click at raw laser reticle."""
        self.crosshair.snap_resolver = lambda x, y: None
        self.crosshair.start()
        self.crosshair._cur_y = 200.0
        self.crosshair.lock_y()
        self.crosshair._cur_x = 300.0

        final_x, final_y = self.crosshair.hit_and_click()

        self.assertEqual((final_x, final_y), (300, 200))
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][:2], (300, 200))

    def test_hit_and_click_magnetic_snap_exception_graceful_fallback(self):
        """If snap_resolver throws an exception, click falls back safely to raw reticle."""
        def broken_resolver(x, y):
            raise RuntimeError("UI Automation tree inaccessible")

        self.crosshair.snap_resolver = broken_resolver
        self.crosshair.start()
        self.crosshair._cur_y = 250.0
        self.crosshair.lock_y()
        self.crosshair._cur_x = 350.0

        final_x, final_y = self.crosshair.hit_and_click()

        self.assertEqual((final_x, final_y), (350, 250))
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][:2], (350, 250))

    def test_phase1_directional_left_and_right_steering(self):
        """Saying 'left' in Phase 1 locks Y and sweeps left starting from right boundary."""
        self.crosshair.start()
        self.assertEqual(self.crosshair.phase, 1)

        # Steering left in Phase 1
        handled = self.crosshair.set_sweep_direction("left")
        self.assertTrue(handled)
        self.assertEqual(self.crosshair.phase, 2)
        self.assertEqual(self.crosshair._sweep_dir_x, -1)
        self.assertEqual(self.crosshair._cur_x, float(self.crosshair.v_max_x))

    def test_phase2_directional_left_and_right_steering(self):
        """Steering left and right in Phase 2 changes horizontal direction; up/down returns False."""
        self.crosshair.start()
        self.crosshair.lock_y()
        self.assertEqual(self.crosshair.phase, 2)

        self.assertTrue(self.crosshair.set_sweep_direction("left"))
        self.assertEqual(self.crosshair._sweep_dir_x, -1)

        self.assertTrue(self.crosshair.set_sweep_direction("right"))
        self.assertEqual(self.crosshair._sweep_dir_x, 1)

        # Up and Down do not apply to Phase 2 vertical sweep
        self.assertFalse(self.crosshair.set_sweep_direction("up"))
        self.assertFalse(self.crosshair.set_sweep_direction("down"))


if __name__ == "__main__":
    unittest.main()

