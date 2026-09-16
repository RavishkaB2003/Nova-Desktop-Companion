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
DEFAULT_SWEEP_SPEED_PX_S = 180.0  # 180 px/second sweep speed (tuned for precise auditory-vocal human latency)
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
        snap_resolver: Optional[Callable[[int, int], Optional[Tuple[int, int]]]] = None,
    ) -> None:
        self.root = root
        self.driver = driver or InputDriver()
        self.sweep_speed = sweep_speed
        self.on_hit_complete = on_hit_complete
        self.snap_resolver = snap_resolver

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
    def is_active(self) -> bool:
        """Alias for is_visible to preserve interface compatibility."""
        return self.is_visible

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

            def _show_window() -> None:
                if self.window:
                    geom = f"{self.vw}x{self.vh}+{self.vx}+{self.vy}"
                    try:
                        self.window.geometry(geom)
                        self.window.deiconify()
                        self.window.lift()
                        self.window.attributes("-topmost", True)
                    except Exception as exc:
                        logger.debug("Crosshair deiconify skipped: %s", exc)
                    self._draw_lines()
                    self._schedule_tick()

            if threading.current_thread() is threading.main_thread():
                _show_window()
            elif self.root:
                try:
                    self.root.after(0, _show_window)
                except Exception:
                    _show_window()
            else:
                _show_window()

            logger.info("Crosshair scanner started (Phase 1: Horizontal Sweep). Bounds: %dx%d", self.vw, self.vh)

    def set_sweep_direction(self, direction: str) -> bool:
        """Spoken directional steering for crosshair sweep (FR-017)."""
        d = direction.strip().lower()
        with self._lock:
            if self._phase == 1:
                if d in ("up", "go up"):
                    self._sweep_dir_y = -1
                    return True
                elif d in ("down", "go down"):
                    self._sweep_dir_y = 1
                    return True
                elif d in ("left", "go left"):
                    self.lock_y(initial_x_dir=-1)
                    return True
                elif d in ("right", "go right"):
                    self.lock_y(initial_x_dir=1)
                    return True
            elif self._phase == 2:
                if d in ("left", "go left"):
                    self._sweep_dir_x = -1
                    return True
                elif d in ("right", "go right"):
                    self._sweep_dir_x = 1
                    return True
                return False
        return False

    def set_sweep_speed(self, speed_px_s: float) -> None:
        """Adjust crosshair sweep speed at runtime with bounds safety."""
        with self._lock:
            self.sweep_speed = max(50.0, min(800.0, float(speed_px_s)))
            logger.info("Crosshair sweep speed set to %.1f px/s", self.sweep_speed)

    def lock_y(self, initial_x_dir: int = 1) -> int:
        """
        Phase 1 completion: Locks Y coordinate and transitions to Phase 2 (vertical sweep).
        Suppresses OS click (FR-015).
        """
        with self._lock:
            self._locked_y = int(round(self._cur_y))
            self._phase = 2
            if initial_x_dir == -1:
                self._cur_x = float(self.v_max_x)
                self._sweep_dir_x = -1
            else:
                self._cur_x = float(self.vx)
                self._sweep_dir_x = 1
            logger.info(
                "Crosshair Y coordinate locked at %d. Initiating Phase 2 (Vertical Sweep dir=%d).",
                self._locked_y, self._sweep_dir_x
            )
            if self.root:
                try:
                    self.root.after(0, self._draw_lines)
                except Exception:
                    self._draw_lines()
            else:
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

            # Magnetic CTA Snapping: Automatically pull cursor to center of closest interactive button if within gravity well
            if self.snap_resolver:
                try:
                    snapped = self.snap_resolver(final_x, final_y)
                    if snapped is not None:
                        sx, sy = snapped
                        import math
                        dist = math.hypot(sx - final_x, sy - final_y)
                        logger.info(
                            "Magnetic Snap: Snapped cursor from (%d, %d) to nearby CTA at (%d, %d) (distance: %.1f px).",
                            final_x, final_y, sx, sy, dist,
                        )
                        final_x, final_y = sx, sy
                except Exception as exc:
                    logger.debug("Magnetic CTA snap resolution skipped: %s", exc)

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

            def _hide_window() -> None:
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

            if threading.current_thread() is threading.main_thread():
                _hide_window()
            elif self.root:
                try:
                    self.root.after(0, _hide_window)
                except Exception:
                    _hide_window()
            else:
                _hide_window()

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
                    self._cur_y = float(self.v_max_y)
                    self._sweep_dir_y = -1
                elif self._cur_y <= self.vy:
                    self._cur_y = float(self.vy)
                    self._sweep_dir_y = 1
            else:
                # Vertical line sweeping X
                self._cur_x += self._sweep_dir_x * self.sweep_speed * dt_s
                if self._cur_x >= self.v_max_x:
                    self._cur_x = float(self.v_max_x)
                    self._sweep_dir_x = -1
                elif self._cur_x <= self.vx:
                    self._cur_x = float(self.vx)
                    self._sweep_dir_x = 1

    def _schedule_tick(self) -> None:
        """Schedule next animation step on Tkinter event loop."""
        if not self._is_visible:
            return

        if self.root:
            try:
                self._anim_job = self.root.after(ANIMATION_TICK_MS, self._on_tick)
            except Exception as exc:
                logger.debug("Failed to schedule crosshair tick: %s", exc)
        else:
            # Headless / synthetic mode
            pass

    def _on_tick(self) -> None:
        """Periodic animation tick advancing sweep line coordinates."""
        now = time.monotonic()
        dt_s = max(0.001, min(0.1, now - self._last_tick_time))
        self._last_tick_time = now

        self.step(dt_s)
        self._draw_lines()
        self._schedule_tick()

    def _draw_lines(self) -> None:
        """Render scanning laser lines and status banner onto HUD canvas."""
        if not self.canvas:
            return

        try:
            self.canvas.delete("all")

            # Local coordinates relative to virtual desktop origin
            local_x = int(self._cur_x - self.vx)
            local_y = int(self._cur_y - self.vy)

            if self._phase == 1:
                # Phase 1: Horizontal line sweeping Y
                self.canvas.create_line(
                    0, local_y, self.vw, local_y,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )
            else:
                # Phase 2: Locked Horizontal line at _locked_y + Sweeping Vertical line at _cur_x
                locked_local_y = int(self._locked_y - self.vy)
                self.canvas.create_line(
                    0, locked_local_y, self.vw, locked_local_y,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )
                self.canvas.create_line(
                    local_x, 0, local_x, self.vh,
                    fill=COLOR_CROSSHAIR_LINE,
                    width=CROSSHAIR_LINE_WIDTH,
                )
                # Intersecting reticle circle at crosshair point
                r = 12
                self.canvas.create_oval(
                    local_x - r, locked_local_y - r, local_x + r, locked_local_y + r,
                    outline=COLOR_CROSSHAIR_LINE,
                    width=2,
                )

            # High-contrast HUD Banner at top-center
            banner_x = self.vw // 2
            if self._phase == 1:
                hint = "CROSSHAIR [Phase 1/2]: Say 'LOCK' or 'CLICK' to freeze line | Say 'LEFT'/'RIGHT' to switch"
            else:
                hint = "CROSSHAIR [Phase 2/2]: Say 'CLICK' or 'HIT' to snap & click | Say 'LEFT'/'RIGHT' to steer"

            self.canvas.create_text(
                banner_x, 32,
                text=hint,
                fill=COLOR_CROSSHAIR_LINE,
                font=("Segoe UI", 12, "bold"),
            )
        except Exception as exc:
            logger.debug("Error rendering crosshair lines: %s", exc)

    def destroy(self) -> None:
        """Cleanly destroy Tkinter resources."""
        if self._anim_job and self.root:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        self.hide()
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
            self.canvas = None
