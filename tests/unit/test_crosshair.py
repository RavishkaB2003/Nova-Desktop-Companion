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


if __name__ == "__main__":
    unittest.main()
