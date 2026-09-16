"""
Project NOVA - Unit Tests for System Tray Component
"""

import unittest
from unittest.mock import MagicMock
from PIL import Image

from nova.ui.tray import NovaTrayIcon, create_default_tray_image, load_mascot_tray_image


class TestNovaTray(unittest.TestCase):
    def test_create_default_tray_image(self):
        img = create_default_tray_image(size=64)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_load_mascot_tray_image(self):
        img = load_mascot_tray_image(size=64)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (64, 64))

    def test_tray_icon_lifecycle(self):
        activated = []
        deactivated = []
        toggled = []
        quitted = []

        tray = NovaTrayIcon(
            on_activate=lambda: activated.append(True),
            on_deactivate=lambda: deactivated.append(True),
            on_toggle_panel=lambda: toggled.append(True),
            on_quit=lambda: quitted.append(True),
        )

        self.assertFalse(tray.is_running)

        # Test menu callbacks directly
        tray._menu_activate()
        self.assertEqual(len(activated), 1)

        tray._menu_deactivate()
        self.assertEqual(len(deactivated), 1)

        tray._menu_toggle_panel()
        self.assertEqual(len(toggled), 1)

        tray._menu_quit()
        self.assertEqual(len(quitted), 1)

    def test_tray_update_title(self):
        tray = NovaTrayIcon()
        mock_icon = MagicMock()
        tray._icon = mock_icon
        tray.update_title("Test Title")
        self.assertEqual(mock_icon.title, "Test Title")


if __name__ == "__main__":
    unittest.main()
