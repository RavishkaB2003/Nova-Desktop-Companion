"""
Project NOVA - Unit Tests for Win32 Input Driver
"""

import time
import unittest
from nova.input.driver import (
    DEFAULT_GLIDE_STEPS,
    DEFAULT_MODIFIER_DEBOUNCE_S,
    InputDriver,
    clamp_coordinates,
    get_virtual_desktop_bounds,
)


class TestInputDriver(unittest.TestCase):
    def setUp(self):
        self.driver = InputDriver(headless=True)

    def test_constants(self):
        self.assertEqual(DEFAULT_GLIDE_STEPS, 5)
        self.assertEqual(DEFAULT_MODIFIER_DEBOUNCE_S, 0.75)

    def test_virtual_desktop_bounds(self):
        min_x, min_y, max_x, max_y = get_virtual_desktop_bounds()
        self.assertLess(min_x, max_x)
        self.assertLess(min_y, max_y)

    def test_coordinate_clamping(self):
        min_x, min_y, max_x, max_y = get_virtual_desktop_bounds()

        # Out of bounds left/top
        cx, cy = clamp_coordinates(min_x - 1000, min_y - 1000)
        self.assertEqual(cx, min_x)
        self.assertEqual(cy, min_y)

        # Out of bounds right/bottom
        cx, cy = clamp_coordinates(max_x + 5000, max_y + 5000)
        self.assertEqual(cx, max_x - 1)
        self.assertEqual(cy, max_y - 1)

    def test_glide_interpolation(self):
        self.driver.glide_to(target_x=500, target_y=300, steps=DEFAULT_GLIDE_STEPS)
        self.assertEqual(len(self.driver.injected_glides), DEFAULT_GLIDE_STEPS + 1)
        self.assertEqual(self.driver.injected_glides[-1], (500, 300))

    def test_reduced_motion_glide_snap(self):
        self.driver.glide_to(target_x=800, target_y=600, reduced_motion=True)
        self.assertEqual(self.driver.injected_glides[-1], (800, 600))
        # Instant snap only adds 1 position
        self.assertEqual(len(self.driver.injected_glides), 1)

    def test_action_modifier_arming_and_consumption(self):
        self.assertIsNone(self.driver.get_active_modifier())

        # Arm 'double'
        self.driver.arm_modifier("double", window_s=0.5)
        mod = self.driver.get_active_modifier()
        self.assertEqual(mod, "double")

        # Once consumed, modifier should be auto-cleared
        self.assertIsNone(self.driver.get_active_modifier())

    def test_action_modifier_timeout_expiry(self):
        # 0.2s debounce window
        self.driver.arm_modifier("right", window_s=0.2)
        time.sleep(0.25)
        # Should be expired
        self.assertIsNone(self.driver.get_active_modifier())

    def test_headless_click_recording(self):
        self.driver.click(x=200, y=150, button="left", click_count=1)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0], (200, 150, "left", 1))

        self.driver.click(button="right", click_count=2)
        self.assertEqual(len(self.driver.injected_clicks), 2)
        self.assertEqual(self.driver.injected_clicks[1], (200, 150, "right", 2))


if __name__ == "__main__":
    unittest.main()
