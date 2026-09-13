"""
Project NOVA - Continuous Cursor Glider Subsystem
Implements continuous cursor gliding at 200 px/s (FR-016),
spoken directional heading steering (FR-017),
and atomic halt-and-click execution (FR-015, FR-11b).
"""

import logging
import math
import threading
import time
from typing import Optional, Tuple

from nova.input.driver import InputDriver

logger = logging.getLogger(__name__)

DEFAULT_GLIDE_SPEED_PX_S = 200.0  # 200 px/sec as specified by FR-016


class ContinuousGlider:
    """
    Manages continuous cursor gliding along a directional heading vector.
    Used during canvas/drawing mode (GLIDE_ACTIVE) driven by vowel voicing or voice commands.
    """

    DIRECTION_HEADINGS = {
        "right": 0.0,
        "east": 0.0,
        "down": 90.0,
        "south": 90.0,
        "left": 180.0,
        "west": 180.0,
        "up": 270.0,
        "north": 270.0,
    }

    def __init__(
        self,
        driver: InputDriver,
        speed_px_s: float = DEFAULT_GLIDE_SPEED_PX_S,
    ) -> None:
        self.driver = driver
        self.speed_px_s = speed_px_s

        self._lock = threading.RLock()
        self._heading_deg: float = 0.0  # Default: Right (0 deg)
        self._is_gliding = False
        self._pos_x: float = 0.0
        self._pos_y: float = 0.0
        self._last_step_time: float = 0.0

    @property
    def is_gliding(self) -> bool:
        with self._lock:
            return self._is_gliding

    @property
    def heading_degrees(self) -> float:
        with self._lock:
            return self._heading_deg

    def set_heading_direction(self, direction: str) -> bool:
        """
        Updates heading vector by spoken direction ('left', 'right', 'up', 'down') (FR-017).
        """
        dir_clean = direction.strip().lower()
        with self._lock:
            if dir_clean in self.DIRECTION_HEADINGS:
                self._heading_deg = self.DIRECTION_HEADINGS[dir_clean]
                logger.info("Cursor glider heading set to %.1f deg ('%s')", self._heading_deg, dir_clean)
                return True
        logger.warning("Unrecognized glider direction: '%s'", direction)
        return False

    def rotate_heading(self, delta_deg: float) -> float:
        """Rotate current heading by delta degrees (e.g. +90 or -90)."""
        with self._lock:
            self._heading_deg = (self._heading_deg + delta_deg) % 360.0
            logger.info("Cursor glider heading rotated to %.1f deg", self._heading_deg)
            return self._heading_deg

    def start_glide(self) -> None:
        """Initializes continuous gliding from the current physical cursor position."""
        with self._lock:
            cur_x, cur_y = self.driver.get_cursor_pos()
            self._pos_x = float(cur_x)
            self._pos_y = float(cur_y)
            self._last_step_time = time.monotonic()
            self._is_gliding = True
            logger.info("Continuous glider started at (%.1f, %.1f), heading=%.1f deg", self._pos_x, self._pos_y, self._heading_deg)

    def step(self, dt_s: Optional[float] = None) -> Tuple[int, int]:
        """
        Advances cursor position along heading vector by speed * dt (FR-016).
        Returns the clamped integer cursor position (x, y).
        """
        with self._lock:
            if not self._is_gliding:
                cur_x, cur_y = self.driver.get_cursor_pos()
                return (cur_x, cur_y)

            now = time.monotonic()
            if dt_s is None:
                dt_s = (now - self._last_step_time) if self._last_step_time > 0 else 0.02
            self._last_step_time = now

            rad = math.radians(self._heading_deg)
            dx = self.speed_px_s * math.cos(rad) * dt_s
            dy = self.speed_px_s * math.sin(rad) * dt_s

            self._pos_x += dx
            self._pos_y += dy

            target_x = int(round(self._pos_x))
            target_y = int(round(self._pos_y))

            self.driver.set_cursor_pos(target_x, target_y)
            actual_x, actual_y = self.driver.get_cursor_pos()
            # Synchronize internal float position with clamped desktop bounds
            self._pos_x = float(actual_x)
            self._pos_y = float(actual_y)

            return (actual_x, actual_y)

    def stop_glide(self) -> Tuple[int, int]:
        """Halts continuous cursor gliding."""
        with self._lock:
            self._is_gliding = False
            cur_x, cur_y = self.driver.get_cursor_pos()
            logger.info("Continuous glider stopped at (%d, %d)", cur_x, cur_y)
            return (cur_x, cur_y)

    def halt_and_click(self, button: str = "left", click_count: int = 1) -> Tuple[int, int]:
        """
        Atomic halt-and-click (FR-015, FR-11b):
        Halts glide and dispatches mouse click in the exact same tick that freezes the cursor,
        preventing any race between cursor stoppage and click execution.
        """
        with self._lock:
            self._is_gliding = False
            cur_x, cur_y = self.driver.get_cursor_pos()
            self.driver.click(x=cur_x, y=cur_y, button=button, click_count=click_count)
            logger.info("Atomic HALT_GLIDE_AND_CLICK executed at (%d, %d)", cur_x, cur_y)
            return (cur_x, cur_y)
