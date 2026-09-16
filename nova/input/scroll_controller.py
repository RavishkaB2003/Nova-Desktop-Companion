"""
Project NOVA - Continuous Fluid Mouse Wheel Scroll Controller
Implements fluid mouse wheel event generation (FR-019), voice-controlled speed modulation (FR-016),
and instant halting via spoken words or acoustic mouth clicks.
"""

import logging
import threading
import tkinter as tk
from typing import Optional

from nova.input.driver import InputDriver, WHEEL_DELTA

logger = logging.getLogger(__name__)

DEFAULT_TICK_MS = 40  # 25 FPS scrolling pulses (smooth, gentle pacing)
DEFAULT_BASE_DELTA = 15  # 15 units per tick (~375 delta/sec, ~3 wheel notches/sec - comfortable reading velocity)
MIN_DELTA = 5
MAX_DELTA = 60


class ScrollController:
    """
    Timer-driven continuous mouse wheel scrolling controller.
    Runs an autonomous loop via Tkinter's event loop to inject smooth scroll events.
    """

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        driver: Optional[InputDriver] = None,
        tick_ms: int = DEFAULT_TICK_MS,
        base_delta: int = DEFAULT_BASE_DELTA,
    ) -> None:
        self.root = root
        self.driver = driver or InputDriver()
        self.tick_ms = tick_ms
        self.base_delta = base_delta

        self._lock = threading.RLock()
        self._is_scrolling = False
        self._direction = "down"  # "down" or "up"
        self._current_magnitude = float(base_delta)
        self._anim_job: Optional[str] = None

    @property
    def is_scrolling(self) -> bool:
        with self._lock:
            return self._is_scrolling

    @property
    def direction(self) -> str:
        with self._lock:
            return self._direction

    @property
    def current_speed(self) -> float:
        with self._lock:
            return self._current_magnitude

    def start_scroll(self, direction: str = "down") -> bool:
        """
        Start continuous mouse wheel scrolling in specified direction ('down' or 'up').
        """
        d = direction.strip().lower()
        if d not in ("down", "up"):
            logger.warning("Invalid scroll direction: '%s'. Defaulting to 'down'.", direction)
            d = "down"

        with self._lock:
            self._direction = d
            self._is_scrolling = True
            self._current_magnitude = float(self.base_delta)

            logger.info("Continuous scrolling started: direction=%s, speed=%.0f delta/tick", d, self._current_magnitude)

            # Schedule tick on GUI loop
            self._schedule_tick()
            return True

    def set_direction(self, direction: str) -> None:
        """Update scrolling direction without resetting current modulated speed."""
        d = direction.strip().lower()
        if d in ("down", "up"):
            with self._lock:
                self._direction = d
                logger.info("Scroll direction changed to: %s (speed: %.1f delta/tick)", d, self._current_magnitude)

    def modulate_speed(self, factor: float) -> float:
        """
        Scale scroll speed by factor (e.g. 2.0 to double on 'faster', 0.5 to halve on 'slower').
        Clamped between MIN_DELTA (30) and MAX_DELTA (960).
        """
        with self._lock:
            if not self._is_scrolling:
                logger.debug("Speed modulation ignored: not currently scrolling.")
                return self._current_magnitude

            new_mag = max(float(MIN_DELTA), min(float(MAX_DELTA), self._current_magnitude * factor))
            self._current_magnitude = new_mag
            logger.info("Scroll speed modulated by %.2fx -> %.1f delta/tick", factor, self._current_magnitude)
            return self._current_magnitude

    def stop_scroll(self) -> bool:
        """
        Immediately halt active scrolling and cancel scheduled animation callbacks.
        """
        with self._lock:
            if not self._is_scrolling:
                return False

            self._is_scrolling = False
            if self._anim_job and self.root:
                try:
                    self.root.after_cancel(self._anim_job)
                except Exception:
                    pass
                self._anim_job = None

            logger.info("Continuous scrolling stopped.")
            return True

    def step(self) -> None:
        """
        Execute a single scroll pulse and schedule the subsequent tick if scrolling is active.
        """
        with self._lock:
            if not self._is_scrolling:
                return

            # In Windows mouse_event:
            # Positive delta = rotate wheel forward (scroll up)
            # Negative delta = rotate wheel backward (scroll down)
            signed_delta = int(round(self._current_magnitude if self._direction == "up" else -self._current_magnitude))

            self.driver.scroll(signed_delta)
            self._schedule_tick()

    def _schedule_tick(self) -> None:
        """Schedule next animation step on Tkinter event loop."""
        if not self._is_scrolling:
            return

        if self.root:
            try:
                self._anim_job = self.root.after(self.tick_ms, self.step)
            except Exception as exc:
                logger.debug("Failed to schedule scroll tick: %s", exc)
                self.step()
        else:
            # Headless / synthetic mode
            pass

    def destroy(self) -> None:
        """Cancel any pending animation timers and halt scrolling."""
        self.stop_scroll()
