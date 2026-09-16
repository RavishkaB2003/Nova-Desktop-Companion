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
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

# Keyboard SendInput flags
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_MENU = 0x12   # Alt key
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LWIN = 0x5B   # Left Windows key
VK_D = 0x44      # D key
VK_F4 = 0x73     # F4 key

VK_MAP = {
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "backspace": VK_BACK,
    "tab": VK_TAB,
    "escape": VK_ESCAPE,
    "space": VK_SPACE,
    "alt": VK_MENU,
    "menu": VK_MENU,
    "win": VK_LWIN,
    "windows": VK_LWIN,
    "f4": VK_F4,
    "d": VK_D,
}

DEFAULT_GLIDE_STEPS = 5
DEFAULT_STEP_INTERVAL_S = 0.0156  # ~15.6ms native WM_TIMER interval (~78ms total)
DEFAULT_MODIFIER_DEBOUNCE_S = 1.5  # 1.5s debounce window (FR-012)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", INPUT_UNION),
    ]


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
        self.injected_scrolls: List[int] = []
        self.injected_keystrokes: List[str] = []

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
            elif button == "middle":
                user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
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

    def scroll(self, delta: int) -> None:
        """
        Inject mouse wheel scroll delta via Win32 mouse_event (FR-019).
        Positive delta scrolls up (forward rotation).
        Negative delta scrolls down (backward rotation).
        """
        with self._lock:
            if self.headless:
                self.injected_scrolls.append(delta)
                logger.info("Headless mouse wheel scroll recorded: delta=%d", delta)
                return

            try:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
                logger.debug("Mouse wheel scroll dispatched: delta=%d", delta)
            except Exception as exc:
                logger.error("Failed to dispatch mouse wheel scroll: %s", exc)

    def type_text(self, text: str) -> None:
        """
        Inject arbitrary Unicode string into active focused control via Win32 SendInput (FR-020).
        """
        if not text:
            return

        with self._lock:
            if self.headless:
                self.injected_keystrokes.append(text)
                logger.info("Headless keystrokes recorded: '%s'", text)
                return

            user32 = ctypes.windll.user32
            for char in text:
                code_point = ord(char)
                # Key down
                ki_down = KEYBDINPUT(wVk=0, wScan=code_point, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)
                inp_down = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_down))
                # Key up
                ki_up = KEYBDINPUT(wVk=0, wScan=code_point, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
                inp_up = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_up))

                inputs = (INPUT * 2)(inp_down, inp_up)
                user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
            logger.info("Typed text injected into foreground control: '%s'", text)

    def press_key(self, key_name: str) -> None:
        """
        Press and release a special control key (e.g. 'enter', 'backspace', 'tab', 'escape').
        """
        vk = VK_MAP.get(key_name.lower())
        if not vk:
            logger.warning("Unrecognized special key name: '%s'", key_name)
            return

        with self._lock:
            if self.headless:
                self.injected_keystrokes.append(f"<{key_name.upper()}>")
                logger.info("Headless special key recorded: <%s>", key_name.upper())
                return

            user32 = ctypes.windll.user32
            ki_down = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
            inp_down = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_down))
            ki_up = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            inp_up = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_up))

            inputs = (INPUT * 2)(inp_down, inp_up)
            user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
            logger.info("Special key dispatched: <%s>", key_name.upper())

    def press_hotkey(self, *key_names: str) -> None:
        """
        Press and release a combination of keys simultaneously (e.g. 'alt', 'tab' or 'win', 'd').
        Keys are pressed down in order and released in reverse order via SendInput (FR-020).
        """
        if not key_names:
            return

        vks = []
        for name in key_names:
            k = name.strip().lower()
            vk = VK_MAP.get(k)
            if not vk:
                if len(k) == 1 and k.isalnum():
                    vk = ord(k.upper())
                else:
                    logger.warning("Unrecognized hotkey component: '%s'", name)
                    return
            vks.append(vk)

        hotkey_str = "+".join(k.upper() for k in key_names)

        with self._lock:
            if self.headless:
                self.injected_keystrokes.append(f"<{hotkey_str}>")
                logger.info("Headless hotkey recorded: <%s>", hotkey_str)
                return

            user32 = ctypes.windll.user32
            inputs_down = [
                INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)))
                for vk in vks
            ]
            inputs_up = [
                INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)))
                for vk in reversed(vks)
            ]

            all_inputs = inputs_down + inputs_up
            arr_inputs = (INPUT * len(all_inputs))(*all_inputs)
            user32.SendInput(len(all_inputs), ctypes.byref(arr_inputs), ctypes.sizeof(INPUT))
            logger.info("Hotkey dispatched: <%s>", hotkey_str)

