"""
Project NOVA - Dual-Axis Crosshair HUD Overlay Subsystem
Implements dynamic virtual-desktop bounded laser crosshair scanner (FR-018),
directional steering (FR-017), and state-dependent coordinate lock & hit snapping.
Tokens: HUD_CROSSHAIR_LINE = #00FF9D (WCAG AAA compliant >7:1 against dark backgrounds).
"""

import logging
import threading
import time
import tkinter as tk
from typing import Callable, Optional, Tuple

from nova.input.driver import InputDriver, get_virtual_desktop_bounds

logger = logging.getLogger(__name__)

COLOR_CROSSHAIR_LINE = "#00FF9D"
CROSSHAIR_LINE_WIDTH = 2
DEFAULT_SWEEP_SPEED_PX_S = 400.0  # 400 px/second sweep speed
ANIMATION_TICK_MS = 16  # ~60 FPS


class CrosshairOverlay:
    """
    Transparent fullscreen HUD displaying sweeping laser crosshairs across virtual desktop metrics (FR-018).
    Phase 1: Horizontal line sweeps Y. Locked by 'Lock' or acoustic impulse.
    Phase 2: Vertical line sweeps X. Locked by 'Hit' or acoustic impulse -> snaps & clicks.
    """

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        driver: Optional[InputDriver] = None,
        sweep_speed: float = DEFAULT_SWEEP_SPEED_PX_S,
        on_hit_complete: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        self.root = root
        self.driver = driver or InputDriver()
        self.sweep_speed = sweep_speed
        self.on_hit_complete = on_hit_complete

        self._lock = threading.RLock()
        self._is_visible = False
        self._phase = 1  # 1 = Horizontal sweep (Y), 2 = Vertical sweep (X)
        self._sweep_dir_y = 1  # 1 = down, -1 = up
        self._sweep_dir_x = 1  # 1 = right, -1 = left

        # Desktop bounds
        self.vx, self.vy, self.v_max_x, self.v_max_y = get_virtual_desktop_bounds()
        self.vw = max(100, self.v_max_x - self.vx)
        self.vh = max(100, self.v_max_y - self.vy)

        self._cur_y = float(self.vy)
        self._cur_x = float(self.vx)
        self._locked_y: Optional[int] = None
        self._locked_x: Optional[int] = None
        self._last_tick_time: float = 0.0

        # Tkinter window and canvas
        self.window: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self._anim_job = None

        if self.root:
            self._create_window()

    def _create_window(self) -> None:
        """Create transparent topmost borderless canvas spanning virtual desktop."""
        if not self.root:
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("NOVA Crosshair Overlay")
        self.window.attributes("-topmost", True)
        self.window.overrideredirect(True)

        geom = f"{self.vw}x{self.vh}+{self.vx}+{self.vy}"
        self.window.geometry(geom)

        trans_color = "#000001"
        try:
            self.window.config(bg=trans_color)
            self.window.wm_attributes("-transparentcolor", trans_color)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.window,
            width=self.vw,
            height=self.vh,
            bg=trans_color,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.window.withdraw()

    @property
    def is_visible(self) -> bool:
        with self._lock:
            return self._is_visible

    @property
    def phase(self) -> int:
        with self._lock:
            return self._phase

    @property
    def current_coordinates(self) -> Tuple[int, int]:
        with self._lock:
            return (int(round(self._cur_x)), int(round(self._cur_y)))

    def start(self) -> None:
        """Start Phase 1 crosshair sweep from virtual desktop origin."""
        with self._lock:
            self.vx, self.vy, self.v_max_x, self.v_max_y = get_virtual_desktop_bounds()
            self.vw = max(100, self.v_max_x - self.vx)
            self.vh = max(100, self.v_max_y - self.vy)

            self._phase = 1
            self._sweep_dir_y = 1
            self._sweep_dir_x = 1
            self._cur_y = float(self.vy)
            self._cur_x = float(self.vx)
            self._locked_y = None
            self._locked_x = None
            self._is_visible = True
            self._last_tick_time = time.monotonic()

            if self.window:
                self.window.deiconify()
                self._draw_lines()
                self._schedule_tick()

            logger.info("Crosshair scanner started (Phase 1: Horizontal Sweep). Bounds: %dx%d", self.vw, self.vh)

    def set_sweep_direction(self, direction: str) -> bool:
        """Spoken directional steering for crosshair sweep (FR-017)."""
        d = direction.strip().lower()
        with self._lock:
            if d == "up":
                self._sweep_dir_y = -1
                return True
            elif d == "down":
                self._sweep_dir_y = 1
                return True
            elif d == "left":
                self._sweep_dir_x = -1
                return True
            elif d == "right":
                self._sweep_dir_x = 1
                return True
        return False

    def lock_y(self) -> int:
        """
        Phase 1 completion: Locks Y coordinate and transitions to Phase 2 (vertical sweep).
        Suppresses OS click (FR-015).
        """
        with self._lock:
            self._locked_y = int(round(self._cur_y))
            self._phase = 2
            self._cur_x = float(self.vx)
            self._sweep_dir_x = 1
            logger.info("Crosshair Y coordinate locked at %d. Initiating Phase 2 (Vertical Sweep).", self._locked_y)
            self._draw_lines()
            return self._locked_y

    def hit_and_click(self) -> Tuple[int, int]:
        """
        Phase 2 completion: Locks X coordinate, snaps cursor to (X, Y),
        dispatches mouse click, and dismisses overlay (FR-018).
        """
        with self._lock:
            self._locked_x = int(round(self._cur_x))
            final_y = self._locked_y if self._locked_y is not None else int(round(self._cur_y))
            final_x = self._locked_x

            logger.info("Crosshair Hit at (%d, %d). Snapping cursor and clicking.", final_x, final_y)

            # Snap physical cursor and click
            self.driver.set_cursor_pos(final_x, final_y)
            self.driver.click(x=final_x, y=final_y, button="left")

            self.hide()

            if self.on_hit_complete:
                try:
                    self.on_hit_complete(final_x, final_y)
                except Exception as exc:
                    logger.exception("Error in crosshair hit callback: %s", exc)

            return (final_x, final_y)

    def hide(self) -> None:
        """Hide crosshair overlay and stop animation."""
        with self._lock:
            self._is_visible = False
            self._phase = 1
            if self._anim_job and self.root:
                try:
                    self.root.after_cancel(self._anim_job)
                except Exception:
                    pass
                self._anim_job = None

            if self.canvas:
                try:
                    self.canvas.delete("all")
                except Exception:
                    pass

            if self.window:
                try:
                    self.window.withdraw()
                except Exception:
                    pass
            logger.info("Crosshair scanner hidden.")

    def step(self, dt_s: float) -> None:
        """Advances laser sweep line according to elapsed time delta (useful for headless tests)."""
        with self._lock:
            if not self._is_visible:
                return

            if self._phase == 1:
                # Horizontal line sweeping Y
                self._cur_y += self._sweep_dir_y * self.sweep_speed * dt_s
                if self._cur_y >= self.v_max_y:
                    self._cur_y = float(self.vy)
                elif self._cur_y < self.vy:
                    self._cur_y = float(self.v_max_y - 1)
            elif self._phase == 2:
                # Vertical line sweeping X
                self._cur_x += self._sweep_dir_x * self.sweep_speed * dt_s
                if self._cur_x >= self.v_max_x:
                    self._cur_x = float(self.vx)
                elif self._cur_x < self.vx:
                    self._cur_x = float(self.v_max_x - 1)

    def _schedule_tick(self) -> None:
        """Schedules the next GUI animation frame at ~60 FPS."""
        if self._is_visible and self.root:
            self._anim_job = self.root.after(ANIMATION_TICK_MS, self._on_anim_tick)

    def _on_anim_tick(self) -> None:
        """Frame update executed on Tkinter thread."""
        with self._lock:
            if not self._is_visible:
                return

            now = time.monotonic()
            dt_s = (now - self._last_tick_time) if self._last_tick_time > 0 else (ANIMATION_TICK_MS / 1000.0)
            self._last_tick_time = now

            self.step(dt_s)
            self._draw_lines()
            self._schedule_tick()

    def _draw_lines(self) -> None:
        """Renders the laser sweep lines and intersection reticle on Tkinter canvas."""
        if not self.canvas:
            return

        try:
            self.canvas.delete("all")

            if self._phase == 1:
                # Draw sweeping horizontal line
                rel_y = int(self._cur_y - self.vy)
                self.canvas.create_line(
                    0, rel_y, self.vw, rel_y,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )
            elif self._phase == 2:
                # Draw locked horizontal line
                rel_y = int((self._locked_y if self._locked_y is not None else self._cur_y) - self.vy)
                self.canvas.create_line(
                    0, rel_y, self.vw, rel_y,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )

                # Draw sweeping vertical line
                rel_x = int(self._cur_x - self.vx)
                self.canvas.create_line(
                    rel_x, 0, rel_x, self.vh,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )

                # Draw intersection reticle circle (radius 12px)
                r = 12
                self.canvas.create_oval(
                    rel_x - r, rel_y - r, rel_x + r, rel_y + r,
                    outline=COLOR_CROSSHAIR_LINE,
                    width=2,
                )
        except Exception as exc:
            logger.debug("Error rendering crosshair lines: %s", exc)

    def destroy(self) -> None:
        """Cleanly destroy Tkinter resources."""
        self.hide()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
            self.canvas = None
