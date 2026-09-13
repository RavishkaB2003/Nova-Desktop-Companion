"""
Project NOVA - Win32 Mouse Input Driver
Provides bounds-checked coordinate clamping (SEC-003), 78ms non-blocking cursor glide (FR-009),
in-place clicking (FR-010), and action modifier arming with a 750ms debounce window (FR-012).
"""

import ctypes
import logging
import threading
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Virtual desktop system metric constants
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Mouse event flags
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

DEFAULT_GLIDE_STEPS = 5
DEFAULT_STEP_INTERVAL_S = 0.0156  # ~15.6ms native WM_TIMER interval (~78ms total)
DEFAULT_MODIFIER_DEBOUNCE_S = 0.75  # 750ms debounce window (FR-012)


def get_virtual_desktop_bounds() -> Tuple[int, int, int, int]:
    """Return (min_x, min_y, max_x, max_y) for the entire virtual desktop span."""
    try:
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return (vx, vy, vx + vw, vy + vh)
    except Exception:
        # Fallback to standard 1080p single monitor bounds
        return (0, 0, 1920, 1080)


def clamp_coordinates(x: int, y: int) -> Tuple[int, int]:
    """Clamp (x, y) coordinates strictly within virtual desktop boundaries (SEC-003)."""
    min_x, min_y, max_x, max_y = get_virtual_desktop_bounds()
    clamped_x = max(min_x, min(x, max_x - 1))
    clamped_y = max(min_y, min(y, max_y - 1))
    return (clamped_x, clamped_y)


class InputDriver:
    """
    Win32 SendInput driver orchestrating cursor glide interpolation and click events.
    """

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._lock = threading.RLock()

        # Modifier state
        self._active_modifier: Optional[str] = None
        self._modifier_armed_at: float = 0.0
        self._modifier_window_s: float = DEFAULT_MODIFIER_DEBOUNCE_S

        # Diagnostics & test recorder
        self.injected_glides: List[Tuple[int, int]] = []
        self.injected_clicks: List[Tuple[int, int, str, int]] = []

    def get_cursor_pos(self) -> Tuple[int, int]:
        """Get current screen coordinates of mouse cursor."""
        if self.headless:
            if self.injected_glides:
                return self.injected_glides[-1]
            return (0, 0)

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def set_cursor_pos(self, x: int, y: int) -> None:
        """Set physical cursor position with strict bounds clamping (SEC-003)."""
        cx, cy = clamp_coordinates(x, y)
        if self.headless:
            self.injected_glides.append((cx, cy))
            return

        ctypes.windll.user32.SetCursorPos(cx, cy)

    def glide_to(
        self,
        target_x: int,
        target_y: int,
        steps: int = DEFAULT_GLIDE_STEPS,
        step_interval_s: float = DEFAULT_STEP_INTERVAL_S,
        reduced_motion: bool = False,
    ) -> Tuple[int, int]:
        """
        Glide cursor from current position to target over ~78ms (FR-009).
        When reduced_motion is True, snaps instantly to the target.
        """
        dest_x, dest_y = clamp_coordinates(target_x, target_y)

        if reduced_motion or steps <= 1:
            self.set_cursor_pos(dest_x, dest_y)
            return (dest_x, dest_y)

        start_x, start_y = self.get_cursor_pos()

        for step in range(1, steps + 1):
            t = step / float(steps)
            interp_x = int(start_x + (dest_x - start_x) * t)
            interp_y = int(start_y + (dest_y - start_y) * t)
            self.set_cursor_pos(interp_x, interp_y)
            if not self.headless:
                time.sleep(step_interval_s)

        # Final guarantee snap
        self.set_cursor_pos(dest_x, dest_y)
        return (dest_x, dest_y)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        """
        Dispatch mouse click event via Win32 SendInput or mouse_event.
        """
        if x is not None and y is not None:
            self.set_cursor_pos(x, y)

        cur_x, cur_y = self.get_cursor_pos()

        if self.headless:
            self.injected_clicks.append((cur_x, cur_y, button, click_count))
            logger.info("Headless click recorded: (%d, %d), %s x %d", cur_x, cur_y, button, click_count)
            return

        user32 = ctypes.windll.user32

        for i in range(click_count):
            if button == "right":
                user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            else:
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            if click_count > 1 and i < click_count - 1:
                time.sleep(0.05)

        logger.info("Mouse click dispatched: (%d, %d), %s x %d", cur_x, cur_y, button, click_count)

    # Action modifier management (FR-012)
    def arm_modifier(
        self,
        modifier: str,
        window_s: float = DEFAULT_MODIFIER_DEBOUNCE_S,
    ) -> None:
        """
        Arm an action modifier ('double' or 'right') with a 750ms expiry window.
        """
        with self._lock:
            self._active_modifier = modifier.lower()
            self._modifier_armed_at = time.monotonic()
            self._modifier_window_s = window_s
            logger.info("Action modifier armed: '%s' (valid for %.2fs)", modifier, window_s)

    def get_active_modifier(self) -> Optional[str]:
        """
        Return the currently armed modifier if within the 750ms window, and disarm it.
        Returns None if no modifier was armed or if the window has expired.
        """
        with self._lock:
            if not self._active_modifier:
                return None

            now = time.monotonic()
            elapsed = now - self._modifier_armed_at

            if elapsed <= self._modifier_window_s:
                mod = self._active_modifier
                self._active_modifier = None
                return mod
            else:
                logger.debug("Action modifier '%s' expired after %.2fs", self._active_modifier, elapsed)
                self._active_modifier = None
                return None

    def disarm_modifier(self) -> None:
        """Manually disarm any active modifier."""
        with self._lock:
            self._active_modifier = None
