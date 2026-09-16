"""
Project NOVA - Unit Tests for Continuous Fluid Mouse Wheel Scroll Controller (FR-019, FR-016)
"""

import unittest
import tkinter as tk
from unittest.mock import MagicMock
from nova.input.driver import InputDriver, WHEEL_DELTA
from nova.input.scroll_controller import ScrollController, MIN_DELTA, MAX_DELTA


class TestScrollController(unittest.TestCase):
    def setUp(self):
        self.driver = InputDriver(headless=True)
        self.controller = ScrollController(driver=self.driver, tick_ms=40, base_delta=15)

    def test_initial_state(self):
        self.assertFalse(self.controller.is_scrolling)
        self.assertEqual(self.controller.direction, "down")
        self.assertEqual(self.controller.current_speed, 15.0)

    def test_default_base_delta_gentle_pacing(self):
        ctrl = ScrollController(driver=self.driver)
        self.assertEqual(ctrl.base_delta, 15)
        self.assertEqual(ctrl.current_speed, 15.0)
        self.assertEqual(ctrl.tick_ms, 40)

    def test_start_and_stop_scroll(self):
        res = self.controller.start_scroll("down")
        self.assertTrue(res)
        self.assertTrue(self.controller.is_scrolling)
        self.assertEqual(self.controller.direction, "down")

        stop_res = self.controller.stop_scroll()
        self.assertTrue(stop_res)
        self.assertFalse(self.controller.is_scrolling)

        # Stopping when not scrolling returns False
        self.assertFalse(self.controller.stop_scroll())

    def test_direction_handling_and_reversal(self):
        self.controller.start_scroll("up")
        self.assertEqual(self.controller.direction, "up")
        self.controller.stop_scroll()

        # Invalid direction defaults to "down"
        self.controller.start_scroll("diagonal")
        self.assertEqual(self.controller.direction, "down")

        # In-flight direction reversal without resetting speed
        self.controller.set_direction("up")
        self.assertEqual(self.controller.direction, "up")
        self.controller.set_direction("down")
        self.assertEqual(self.controller.direction, "down")
        self.controller.stop_scroll()

    def test_speed_modulation_and_clamping(self):
        # Modulation ignored when not scrolling
        speed = self.controller.modulate_speed(2.0)
        self.assertEqual(speed, 15.0)

        self.controller.start_scroll("down")

        # Double speed: 15 -> 30
        speed = self.controller.modulate_speed(2.0)
        self.assertEqual(speed, 30.0)
        self.assertEqual(self.controller.current_speed, 30.0)

        # Double again: 30 -> 60 (MAX_DELTA)
        speed = self.controller.modulate_speed(2.0)
        self.assertEqual(speed, 60.0)

        # Upper bound clamp: 60 * 4 -> clamped to MAX_DELTA (60)
        speed = self.controller.modulate_speed(4.0)
        self.assertEqual(speed, float(MAX_DELTA))

        # Halve speed: 60 -> 30
        speed = self.controller.modulate_speed(0.5)
        self.assertEqual(speed, 30.0)

        # Lower bound clamp: 30 * 0.01 -> clamped to MIN_DELTA (5)
        speed = self.controller.modulate_speed(0.01)
        self.assertEqual(speed, float(MIN_DELTA))

        self.controller.stop_scroll()

    def test_step_pulse_generation(self):
        # When not scrolling, step does nothing
        self.controller.step()
        self.assertEqual(len(self.driver.injected_scrolls), 0)

        # Scroll down produces negative delta
        self.controller.start_scroll("down")
        self.controller.step()
        self.assertEqual(self.driver.injected_scrolls[-1], -15)

        # Scroll up produces positive delta
        self.controller.start_scroll("up")
        self.controller.step()
        self.assertEqual(self.driver.injected_scrolls[-1], 15)

        self.controller.stop_scroll()

    def test_tkinter_timer_cancellation(self):
        root = tk.Tk()
        root.withdraw()
        try:
            ctrl = ScrollController(root=root, driver=self.driver, tick_ms=50)
            ctrl.start_scroll("down")
            self.assertIsNotNone(ctrl._anim_job)

            ctrl.stop_scroll()
            self.assertIsNone(ctrl._anim_job)
            self.assertFalse(ctrl.is_scrolling)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
