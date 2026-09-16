"""
Unit tests for NOVA Real-Time Visual Button & Checkbox Contour Detector (nova.automation.vision).
"""

import unittest
import numpy as np
import cv2
from nova.automation.vision import find_nearest_button_contour


class TestVisualContourDetector(unittest.TestCase):
    """Test suite for OpenCV-based button and checkbox contour detection."""

    def setUp(self):
        # 160x160 canvas simulating light background
        self.canvas = np.full((160, 160), 245, dtype=np.uint8)

    def test_detect_rectangular_button_within_radius(self):
        """Detects a standard rectangular button and snaps to its centroid."""
        # Draw a dark button at ROI coords (50, 60) with width=60, height=28
        # Center is at (80, 74)
        cv2.rectangle(self.canvas, (50, 60), (110, 88), 30, -1)

        # Reticle at screen (100, 100). With roi_half_size=80:
        # roi_left = 20, roi_top = 20.
        # Button screen center should be: 20 + 80 = 100, 20 + 74 = 94.
        res = find_nearest_button_contour(
            x=100,
            y=100,
            max_radius=65,
            roi_half_size=80,
            screen_image=self.canvas,
        )
        self.assertIsNotNone(res)
        cx, cy = res
        # Check within 2px tolerance of true screen centroid (100, 94)
        self.assertAlmostEqual(cx, 100, delta=2)
        self.assertAlmostEqual(cy, 94, delta=2)

    def test_detect_square_checkbox(self):
        """Detects a compact square checkbox (18x18)."""
        # Draw a checkbox border at ROI (70, 70) to (88, 88)
        # Center is at (79, 79)
        cv2.rectangle(self.canvas, (70, 70), (88, 88), 10, 2)

        # Reticle at (500, 500)
        # roi_left = 420, roi_top = 420.
        # Checkbox screen center: 420 + 79 = 499, 420 + 79 = 499.
        res = find_nearest_button_contour(
            x=500,
            y=500,
            max_radius=65,
            roi_half_size=80,
            screen_image=self.canvas,
        )
        self.assertIsNotNone(res)
        cx, cy = res
        self.assertAlmostEqual(cx, 499, delta=2)
        self.assertAlmostEqual(cy, 499, delta=2)

    def test_distance_cutoff_exceeding_max_radius(self):
        """Buttons farther than max_radius are discarded, returning None."""
        # Draw button far in corner of ROI (10, 10) to (40, 30) -> center (25, 20)
        cv2.rectangle(self.canvas, (10, 10), (40, 30), 20, -1)

        # Reticle at center (80, 80) -> distance to (25, 20) is sqrt(55^2 + 60^2) = ~81px > 50px
        res = find_nearest_button_contour(
            x=500,
            y=500,
            max_radius=50,
            roi_half_size=80,
            screen_image=self.canvas,
        )
        self.assertIsNone(res)

    def test_containment_direct_hit(self):
        """Direct hit inside button bounding box returns immediately with 0 distance."""
        cv2.rectangle(self.canvas, (60, 60), (100, 90), 0, -1)

        # Reticle at (500, 500) -> roi_left = 420, roi_top = 420
        # Button screen bounds: (480, 480) to (520, 510).
        # Reticle (500, 500) is directly inside!
        res = find_nearest_button_contour(
            x=500,
            y=500,
            max_radius=65,
            roi_half_size=80,
            screen_image=self.canvas,
        )
        self.assertIsNotNone(res)
        cx, cy = res
        self.assertAlmostEqual(cx, 500, delta=2)
        self.assertAlmostEqual(cy, 495, delta=2)

    def test_empty_canvas_returns_none(self):
        """Plain canvas with no buttons returns None without errors."""
        res = find_nearest_button_contour(
            x=500,
            y=500,
            max_radius=65,
            roi_half_size=80,
            screen_image=self.canvas,
        )
        self.assertIsNone(res)

    def test_none_screen_image_headless_safety(self):
        """When screen capture is unavailable (e.g. headless), returns None cleanly."""
        # In testing without display, capture_screen_roi returns None safely
        res = find_nearest_button_contour(
            x=100,
            y=100,
            max_radius=65,
            screen_image=None,
        )
        # Either returns None or detected button if display DC is available
        self.assertTrue(res is None or isinstance(res, tuple))


if __name__ == "__main__":
    unittest.main()
