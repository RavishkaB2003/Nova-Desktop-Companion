"""
Project NOVA - Semantic UI Target Snapping HUD Overlay
Projects high-contrast 58x38px obsidian badges (Screen SCR-002) over clickable UI controls.
Enforces WCAG AAA >= 7:1 contrast ratio (~18.5:1), colorkey transparency (#010203),
Per-Monitor-V2 DPI scaling, and arm's length 1-meter legibility (NFR-008, NFR-009, NFR-010).
"""

import logging
from typing import Dict, List, Optional
import tkinter as tk

from nova.automation.crawler import UIElementTarget
from nova.input.driver import get_virtual_desktop_bounds

logger = logging.getLogger(__name__)

TRANSPARENT_COLORKEY = "#010203"
BADGE_WIDTH = 58
BADGE_HEIGHT = 38
CORNER_RADIUS = 6

# Color Tokens
COLOR_OBSIDIAN = "#050811"
COLOR_CYAN_BORDER = "#00F0FF"
COLOR_AMBER_LOCKED = "#FFB800"
COLOR_TEXT_WHITE = "#FFFFFF"
COLOR_FOOTER_BG = "#0B1021"
COLOR_FOOTER_BORDER = "#1E293B"


class HudOverlay:
    """
    Transparent fullscreen HUD window projecting target badges over the Windows desktop.
    """

    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        self._root = root
        self._owns_root = root is None
        self._window: Optional[tk.Tk | tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._is_visible = False
        self._is_destroyed = False

        self._active_targets: Dict[int, UIElementTarget] = {}
        self._badge_tag_map: Dict[int, List[int]] = {}  # target_id -> canvas object IDs
        self._footer_tag_ids: List[int] = []
        self._min_x: int = 0
        self._min_y: int = 0

        self._init_overlay_window()

    @property
    def is_visible(self) -> bool:
        return self._is_visible

    @property
    def window(self) -> Optional[tk.Tk | tk.Toplevel]:
        return self._window

    def _init_overlay_window(self) -> None:
        """Create frameless, transparent, click-through capable topmost overlay."""
        if self._root is None:
            self._root = tk.Tk()
            self._window = self._root
            self._owns_root = True
        else:
            self._window = tk.Toplevel(self._root)
            self._owns_root = False

        self._window.title("NOVA Target Snapping HUD")
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)

        min_x, min_y, max_x, max_y = get_virtual_desktop_bounds()
        self._min_x = min_x
        self._min_y = min_y
        width = max(100, max_x - min_x)
        height = max(100, max_y - min_y)

        self._window.geometry(f"{width}x{height}+{min_x}+{min_y}")

        try:
            self._window.wm_attributes("-transparentcolor", TRANSPARENT_COLORKEY)
            self._window.config(bg=TRANSPARENT_COLORKEY)
        except Exception as exc:
            logger.debug("Transparent colorkey not supported on host OS: %s", exc)

        self._canvas = tk.Canvas(
            self._window,
            width=width,
            height=height,
            bg=TRANSPARENT_COLORKEY,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Initially hidden
        self._window.withdraw()

    def show_targets(
        self,
        targets: List[UIElementTarget],
        current_page: int = 0,
        total_pages: int = 1,
    ) -> None:
        """Project badges 1..9 for the current target page."""
        if self._is_destroyed or not self._canvas or not self._window:
            return

        def _render() -> None:
            self.clear()
            self._active_targets = {t.target_id: t for t in targets}

            for t in targets:
                self._draw_badge(t)

            if total_pages > 1:
                self._draw_pagination_footer(current_page, total_pages)

            self._window.deiconify()
            self._window.lift()
            self._window.attributes("-topmost", True)
            self._is_visible = True
            logger.info("Projected %d HUD target badges (Page %d/%d).", len(targets), current_page + 1, total_pages)

        self._window.after(0, _render)

    def _draw_badge(self, target: UIElementTarget, locked: bool = False) -> None:
        """Draw an individual 58x38px obsidian target badge centered on (centroid_x, centroid_y)."""
        if not self._canvas:
            return

        cx = target.centroid_x - self._min_x
        cy = target.centroid_y - self._min_y
        w2 = BADGE_WIDTH // 2
        h2 = BADGE_HEIGHT // 2
        x0, y0 = cx - w2, cy - h2
        x1, y1 = cx + w2, cy + h2

        border_color = COLOR_AMBER_LOCKED if locked else COLOR_CYAN_BORDER
        border_width = 3 if locked else 2

        # Badge obsidian body
        rect_id = self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=COLOR_OBSIDIAN,
            outline=border_color,
            width=border_width,
        )

        # Centered bold digit (18pt, ~18.5:1 contrast ratio against obsidian)
        text_id = self._canvas.create_text(
            cx, cy,
            text=str(target.target_id),
            fill=COLOR_TEXT_WHITE,
            font=("Segoe UI", 18, "bold"),
        )

        self._badge_tag_map[target.target_id] = [rect_id, text_id]

    def _draw_pagination_footer(self, current_page: int, total_pages: int) -> None:
        """Draw navigation status bar at bottom-center of the screen."""
        if not self._canvas or not self._root:
            return

        screen_w = self._canvas.winfo_reqwidth()
        screen_h = self._canvas.winfo_reqheight()

        footer_w = 340
        footer_h = 36
        cx = screen_w // 2
        cy = max(screen_h - 60, 60)

        x0 = cx - (footer_w // 2)
        y0 = cy - (footer_h // 2)
        x1 = cx + (footer_w // 2)
        y1 = cy + (footer_h // 2)

        rect_id = self._canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=COLOR_FOOTER_BG,
            outline=COLOR_FOOTER_BORDER,
            width=1,
        )
        msg = f"Page {current_page + 1} of {total_pages} | Say 'Next' or 'Back'"
        text_id = self._canvas.create_text(
            cx, cy,
            text=msg,
            fill="#94A3B8",
            font=("Segoe UI", 11, "bold"),
        )
        self._footer_tag_ids = [rect_id, text_id]

    def highlight_target(self, target_id: int) -> None:
        """Lock and highlight selected target in golden amber (#FFB800) during cursor glide."""
        if self._is_destroyed or not self._canvas or not self._window:
            return

        def _highlight() -> None:
            if target_id in self._active_targets:
                target = self._active_targets[target_id]
                # Re-draw as locked
                if target_id in self._badge_tag_map:
                    for tag_id in self._badge_tag_map[target_id]:
                        self._canvas.delete(tag_id)
                self._draw_badge(target, locked=True)

        self._window.after(0, _highlight)

    def clear(self) -> None:
        """Erase all active badges and footers from canvas."""
        if not self._canvas:
            return

        for tag_ids in self._badge_tag_map.values():
            for tid in tag_ids:
                self._canvas.delete(tid)
        self._badge_tag_map.clear()

        for fid in self._footer_tag_ids:
            self._canvas.delete(fid)
        self._footer_tag_ids.clear()
        self._active_targets.clear()

    def hide(self) -> None:
        """Dismiss HUD overlay instantly."""
        if self._is_destroyed or not self._window:
            return

        def _hide() -> None:
            self.clear()
            self._window.withdraw()
            self._is_visible = False
            logger.info("HUD target overlay dismissed.")

        self._window.after(0, _hide)

    def destroy(self) -> None:
        """Clean up overlay window resources."""
        self._is_destroyed = True
        self._is_visible = False
        if self._owns_root and self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None
            self._window = None
        elif self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
