"""
Project NOVA - Real-Time Visual Button & Checkbox Contour Detector
Provides Tier-2 sub-3ms visual fallback for Magnetic CTA Snapping when
UI Automation accessibility trees are unavailable or unexposed (e.g. canvas,
custom web styling, game interfaces, or framework-isolated controls).
"""

import logging
import math
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ROI capture dimensions
DEFAULT_ROI_HALF_SIZE_PX = 80  # 160x160 px local crop around cursor
MIN_BUTTON_WIDTH_PX = 12
MAX_BUTTON_WIDTH_PX = 240
MIN_BUTTON_HEIGHT_PX = 10
MAX_BUTTON_HEIGHT_PX = 90


def capture_screen_roi(
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> Optional[Any]:
    """
    Safely captures a rectangular region of interest from the desktop screen.
    Returns a PIL Image or numpy array, or None if screen capture is unavailable
    (e.g. headless environment, locked workstation, or display DC error).
    """
    # 1. Try PIL ImageGrab (fastest and cleanest when GUI session is active)
    try:
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=(left, top, right, bottom))
    except Exception:
        pass

    # 2. Try Win32 GDI BitBlt
    try:
        import win32gui
        import win32ui
        import win32con
        from PIL import Image

        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            return None

        hdesktop = win32gui.GetDesktopWindow()
        desktop_dc = win32gui.GetWindowDC(hdesktop)
        img_dc = win32ui.CreateDCFromHandle(desktop_dc)
        mem_dc = img_dc.CreateCompatibleDC()

        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(img_dc, w, h)
        mem_dc.SelectObject(bmp)

        mem_dc.BitBlt((0, 0), (w, h), img_dc, (left, top), win32con.SRCCOPY)
        bmp_info = bmp.GetInfo()
        bmp_bits = bmp.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGB",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_bits,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(bmp.GetHandle())
        mem_dc.DeleteDC()
        img_dc.DeleteDC()
        win32gui.ReleaseDC(hdesktop, desktop_dc)
        return img
    except Exception as exc:
        logger.debug("Desktop DC BitBlt capture unavailable: %s", exc)
        return None


def find_nearest_button_contour(
    x: int,
    y: int,
    max_radius: int = 65,
    roi_half_size: int = DEFAULT_ROI_HALF_SIZE_PX,
    screen_image: Optional[Any] = None,
) -> Optional[Tuple[int, int]]:
    """
    Detects rectangular button or square checkbox contours around (x, y)
    within max_radius using OpenCV edge detection.

    Args:
        x: Virtual desktop horizontal coordinate of crosshair / cursor.
        y: Virtual desktop vertical coordinate of crosshair / cursor.
        max_radius: Maximum Euclidean snap distance in pixels (default 65).
        roi_half_size: Half-width/height of local inspection patch (default 80 -> 160x160).
        screen_image: Optional injected PIL Image or numpy array for testing.

    Returns:
        (centroid_x, centroid_y) in virtual screen coordinates of closest CTA,
        or None if no suitable contour exists within max_radius.
    """
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        logger.debug("OpenCV/Numpy unavailable for visual contour detection: %s", exc)
        return None

    roi_left = max(0, x - roi_half_size)
    roi_top = max(0, y - roi_half_size)
    roi_right = x + roi_half_size
    roi_bottom = y + roi_half_size

    # Acquire image patch
    raw_img = screen_image
    if raw_img is None:
        raw_img = capture_screen_roi(roi_left, roi_top, roi_right, roi_bottom)

    if raw_img is None:
        return None

    # Convert to grayscale numpy array
    try:
        if hasattr(raw_img, "convert"):
            img_np = np.array(raw_img.convert("L"))
        elif isinstance(raw_img, np.ndarray):
            if len(raw_img.shape) == 3 and raw_img.shape[2] >= 3:
                img_np = cv2.cvtColor(raw_img, cv2.COLOR_BGR2GRAY)
            else:
                img_np = raw_img
        else:
            return None
    except Exception as exc:
        logger.debug("Error converting image patch to grayscale numpy array: %s", exc)
        return None

    h_roi, w_roi = img_np.shape[:2]
    if h_roi < 10 or w_roi < 10:
        return None

    # Edge detection and morphological closing
    blurred = cv2.GaussianBlur(img_np, (3, 3), 0)
    edges = cv2.Canny(blurred, 40, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best_centroid: Optional[Tuple[int, int]] = None
    min_dist = float("inf")

    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)

        # 1. Discard noise or oversized boundaries (e.g. edge of the whole ROI)
        if bw < MIN_BUTTON_WIDTH_PX or bh < MIN_BUTTON_HEIGHT_PX:
            continue
        if bw > MAX_BUTTON_WIDTH_PX or bh > MAX_BUTTON_HEIGHT_PX:
            continue
        if bw >= (w_roi - 4) and bh >= (h_roi - 4):
            continue

        # 2. Shape classification:
        # - Checkbox: square-like (aspect ratio 0.75 - 1.35, size <= 38px)
        # - Button / Link: rectangular (aspect ratio 1.05 - 9.0)
        aspect = bw / float(bh)
        is_checkbox = (0.75 <= aspect <= 1.35) and (bw <= 38) and (bh <= 38)
        is_button = (1.05 <= aspect <= 9.0) or (0.4 <= aspect <= 1.05 and bh >= 20)

        if not (is_checkbox or is_button):
            continue

        # 3. Rectangularity / Area density check
        area = cv2.contourArea(c)
        bbox_area = bw * bh
        if bbox_area > 0 and (area / bbox_area) < 0.35:
            continue

        # 4. Compute centroid in screen coordinates
        cx_roi = bx + (bw // 2)
        cy_roi = by + (bh // 2)
        screen_cx = roi_left + cx_roi
        screen_cy = roi_top + cy_roi

        # 5. Check containment or distance
        if roi_left + bx <= x <= roi_left + bx + bw and roi_top + by <= y <= roi_top + by + bh:
            dist = 0.0
        else:
            dist = math.hypot(screen_cx - x, screen_cy - y)

        if dist < min_dist and dist <= max_radius:
            min_dist = dist
            best_centroid = (screen_cx, screen_cy)

    if best_centroid is not None:
        logger.info(
            "Visual Contour Detector: Snapped to button contour at (%d, %d) (distance: %.1f px).",
            best_centroid[0],
            best_centroid[1],
            min_dist,
        )

    return best_centroid
