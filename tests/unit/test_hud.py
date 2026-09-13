"""
Project NOVA - Unit Tests for Target Snapping HUD Overlay
"""

import tkinter as tk
import unittest
from nova.automation.crawler import UIElementTarget
from nova.ui.hud_overlay import (
    BADGE_HEIGHT,
    BADGE_WIDTH,
    COLOR_AMBER_LOCKED,
    COLOR_CYAN_BORDER,
    COLOR_OBSIDIAN,
    TRANSPARENT_COLORKEY,
    HudOverlay,
)


class TestHudOverlay(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.hud = HudOverlay(root=self.root)

    def tearDown(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.hud.destroy()
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_badge_specs_and_colors(self):
        self.assertEqual(BADGE_WIDTH, 58)
        self.assertEqual(BADGE_HEIGHT, 38)
        self.assertEqual(TRANSPARENT_COLORKEY, "#010203")
        self.assertEqual(COLOR_OBSIDIAN, "#050811")
        self.assertEqual(COLOR_CYAN_BORDER, "#00F0FF")
        self.assertEqual(COLOR_AMBER_LOCKED, "#FFB800")

    def test_show_and_hide_targets(self):
        targets = [
            UIElementTarget(
                target_id=1,
                title="File",
                control_type="MenuItemControl",
                bounding_box=(50, 50, 100, 80),
                centroid_x=75,
                centroid_y=65,
                page_index=0,
                window_handle=1000,
            ),
            UIElementTarget(
                target_id=2,
                title="Edit",
                control_type="MenuItemControl",
                bounding_box=(110, 50, 160, 80),
                centroid_x=135,
                centroid_y=65,
                page_index=0,
                window_handle=1000,
            ),
        ]

        self.hud.show_targets(targets, current_page=0, total_pages=2)
        self.root.update()

        self.assertTrue(self.hud.is_visible)
        self.assertEqual(len(self.hud._active_targets), 2)
        self.assertIn(1, self.hud._badge_tag_map)
        self.assertIn(2, self.hud._badge_tag_map)

        # Highlight target 1
        self.hud.highlight_target(1)
        self.root.update()

        # Hide HUD
        self.hud.hide()
        self.root.update()
        self.assertFalse(self.hud.is_visible)


if __name__ == "__main__":
    unittest.main()
