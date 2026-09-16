"""
Project NOVA - Unit Tests for Control Panel & Command Cheat Sheet UI
"""

import tkinter as tk
import unittest
from unittest.mock import MagicMock

from nova.ui.control_panel import (
    COMMAND_CATEGORIES,
    BG_COLOR,
    ACCENT_CYAN,
    ControlPanel,
)


class TestControlPanel(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.closed_calls = []
        self.feedback_toggles = []

        self.panel = ControlPanel(
            root=self.root,
            on_close=lambda: self.closed_calls.append(True),
            on_feedback_toggle=lambda enabled: self.feedback_toggles.append(enabled),
        )

    def tearDown(self):
        try:
            if self.panel._window:
                self.panel._window.destroy()
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_initial_state(self):
        self.assertFalse(self.panel.is_visible)
        self.assertIsNone(self.panel._window)
        self.assertTrue(self.panel._voice_feedback_enabled)

    def test_command_categories_structure(self):
        self.assertGreaterEqual(len(COMMAND_CATEGORIES), 8)
        for cat in COMMAND_CATEGORIES:
            self.assertIn("title", cat)
            self.assertIn("color", cat)
            self.assertIn("commands", cat)
            self.assertGreater(len(cat["commands"]), 0)
            for cmd, desc in cat["commands"]:
                self.assertTrue(isinstance(cmd, str) and len(cmd) > 0)
                self.assertTrue(isinstance(desc, str) and len(desc) > 0)

    def test_show_and_hide(self):
        self.panel.show()
        self.root.update()
        self.assertTrue(self.panel.is_visible)
        self.assertIsNotNone(self.panel._window)

        self.panel.hide()
        self.root.update()
        self.assertFalse(self.panel.is_visible)
        self.assertEqual(len(self.closed_calls), 1)

    def test_toggle(self):
        self.assertFalse(self.panel.is_visible)
        self.panel.toggle()
        self.root.update()
        self.assertTrue(self.panel.is_visible)

        self.panel.toggle()
        self.root.update()
        self.assertFalse(self.panel.is_visible)

    def test_update_status(self):
        self.panel.update_status("SystemState.IDLE_ACTIVE")
        self.assertIn("IDLE_ACTIVE", self.panel._status_var.get())

        self.panel.update_status("SystemState.GLIDE_ACTIVE")
        self.assertIn("GLIDE_ACTIVE", self.panel._status_var.get())

    def test_feedback_toggle_callback(self):
        self.panel.show()
        self.root.update()

        # Initial state is True
        self.assertTrue(self.panel._voice_feedback_enabled)

        # Toggle to False
        self.panel._toggle_feedback()
        self.assertFalse(self.panel._voice_feedback_enabled)
        self.assertEqual(self.feedback_toggles, [False])

        # Toggle back to True
        self.panel._toggle_feedback()
        self.assertTrue(self.panel._voice_feedback_enabled)
        self.assertEqual(self.feedback_toggles, [False, True])


if __name__ == "__main__":
    unittest.main()
