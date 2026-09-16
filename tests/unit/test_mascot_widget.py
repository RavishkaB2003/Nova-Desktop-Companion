"""
Project NOVA - Unit Tests for Mascot Widget UI
"""

import tkinter as tk
import unittest
from nova.core.enums import MascotVisualState
from nova.ui.mascot import (
    ASSET_FILENAMES,
    DEFAULT_WINDOW_SIZE,
    TRANSPARENT_COLORKEY,
    MascotWidget,
)


class TestMascotWidget(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.widget = MascotWidget(root=self.root, size=DEFAULT_WINDOW_SIZE, reduced_motion=True)

    def tearDown(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.widget.destroy()
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_window_properties(self):
        self.assertEqual(self.widget.size, DEFAULT_WINDOW_SIZE)
        self.assertEqual(TRANSPARENT_COLORKEY, "#010203")

    def test_asset_mapping_completeness(self):
        for state in MascotVisualState:
            self.assertIn(state, ASSET_FILENAMES)
            self.assertTrue(ASSET_FILENAMES[state].endswith(".svg"))

    def test_visual_state_updates(self):
        for state in MascotVisualState:
            self.widget.set_visual_state(state)
            self.root.update()
            self.assertEqual(self.widget.current_visual_state, state)

    def test_reduced_motion_flag(self):
        self.assertTrue(self.widget.reduced_motion)

    def test_all_seven_states_loaded(self):
        # Verify that all 7 vector states were successfully rasterized and stored
        for state in MascotVisualState:
            self.assertIn(state, self.widget._raw_images)
            img = self.widget._raw_images[state]
            self.assertEqual(img.size, (DEFAULT_WINDOW_SIZE, DEFAULT_WINDOW_SIZE))

    def test_double_click_callback(self):
        clicked = []
        self.widget.on_double_click = lambda: clicked.append(True)
        self.widget._handle_double_click()
        self.assertEqual(len(clicked), 1)


if __name__ == "__main__":
    unittest.main()
