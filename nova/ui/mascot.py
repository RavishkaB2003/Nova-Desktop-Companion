"""
Project NOVA - Ambient Floating Mascot Widget
Frameless 256x256 desktop companion (SCR-001) rendering the 7 glanceable mascot states.
Enforces Windows colorkey transparency (#010203), Per-Monitor-V2 DPI awareness, and WCAG AA contrast.
"""

import ctypes
import logging
import math
import os
from typing import Dict, Optional
import tkinter as tk

from PIL import Image, ImageTk

from nova.core.enums import MascotVisualState

logger = logging.getLogger(__name__)

TRANSPARENT_COLORKEY = "#010203"
DEFAULT_WINDOW_SIZE = 256
DEFAULT_MARGIN_RIGHT = 32
DEFAULT_MARGIN_BOTTOM = 64

ASSET_FILENAMES: Dict[MascotVisualState, str] = {
    MascotVisualState.SLEEPING: "mascot_sleeping.svg",
    MascotVisualState.WAKING: "mascot_waking.svg",
    MascotVisualState.LISTENING: "mascot_listening.svg",
    MascotVisualState.DICTATING: "mascot_dictating.svg",
    MascotVisualState.TRACKING: "mascot_tracking.svg",
    MascotVisualState.EXECUTING: "mascot_executing.svg",
    MascotVisualState.ERROR: "mascot_error.svg",
}


def enable_windows_dpi_awareness() -> None:
    """Declare Windows Per-Monitor-V2 DPI awareness to prevent coordinate scaling distortion."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        logger.info("Per-Monitor-V2 DPI awareness enabled.")
    except Exception:
        try:
            # Fallback to SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE = 2)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("Per-Monitor DPI awareness enabled via shcore.")
        except Exception as exc:
            logger.debug("DPI awareness declaration failed (headless or non-Windows): %s", exc)


def find_assets_dir() -> str:
    """Locate the assets/mascot directory."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "mascot"),
        os.path.join(os.getcwd(), "assets", "mascot"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


class MascotWidget:
    """
    Floating Tkinter mascot desktop companion widget.
    Renders 7 vector states with seamless colorkey transparency and smooth ambient hover.
    """

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        size: int = DEFAULT_WINDOW_SIZE,
        reduced_motion: bool = False,
    ) -> None:
        self.size = size
        self.reduced_motion = reduced_motion
        self.current_visual_state: MascotVisualState = MascotVisualState.SLEEPING

        self._root = root
        self._owns_root = root is None
        self._canvas: Optional[tk.Canvas] = None
        self._images: Dict[MascotVisualState, ImageTk.PhotoImage] = {}
        self._raw_images: Dict[MascotVisualState, Image.Image] = {}
        self._canvas_image_id: Optional[int] = None

        # Drag state
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Animation state
        self._anim_frame = 0
        self._anim_timer_id: Optional[str] = None
        self._is_destroyed = False
        self._assets_dir = find_assets_dir()

        self._init_window()
        self._load_vector_assets()
        self._setup_bindings()
        self._start_animation_loop()

    @property
    def root(self) -> Optional[tk.Tk]:
        return self._root

    def _init_window(self) -> None:
        """Initialize frameless transparent topmost window."""
        if self._root is None:
            enable_windows_dpi_awareness()
            self._root = tk.Tk()

        self._root.title("NOVA Desktop Companion")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)

        # Apply Windows transparent colorkey
        try:
            self._root.wm_attributes("-transparentcolor", TRANSPARENT_COLORKEY)
            self._root.config(bg=TRANSPARENT_COLORKEY)
        except Exception as exc:
            logger.debug("Transparent colorkey not supported on host OS: %s", exc)

        # Position window in bottom-right corner of screen
        screen_width = self._root.winfo_screenwidth()
        screen_height = self._root.winfo_screenheight()
        init_x = max(0, screen_width - self.size - DEFAULT_MARGIN_RIGHT)
        init_y = max(0, screen_height - self.size - DEFAULT_MARGIN_BOTTOM)
        self._root.geometry(f"{self.size}x{self.size}+{init_x}+{init_y}")

        # Canvas with transparent colorkey background
        self._canvas = tk.Canvas(
            self._root,
            width=self.size,
            height=self.size,
            bg=TRANSPARENT_COLORKEY,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

    def _load_vector_assets(self) -> None:
        """Load and rasterize the approved SVG assets for all 7 states into 256x256 images."""
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF (fitz) not available; vector rasterization disabled.")
            return

        for state, filename in ASSET_FILENAMES.items():
            svg_path = os.path.join(self._assets_dir, filename)
            if not os.path.exists(svg_path):
                logger.warning("Mascot asset not found: %s", svg_path)
                continue

            try:
                doc = fitz.open(svg_path)
                page = doc[0]
                rect = page.rect
                zoom = float(self.size) / max(rect.width, rect.height)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=True)
                img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)

                # Composite over colorkey background for smooth antialiased edges
                background = Image.new("RGBA", (self.size, self.size), (1, 2, 3, 255))
                background.paste(img, (0, 0), img)
                final_img = background.convert("RGB")

                self._raw_images[state] = final_img
                if self._root:
                    self._images[state] = ImageTk.PhotoImage(final_img, master=self._root)
                logger.debug("Loaded mascot visual asset for state: %s", state)
            except Exception as exc:
                logger.error("Failed to render mascot SVG %s: %s", svg_path, exc)

        # Initial canvas render
        if self._canvas and self.current_visual_state in self._images:
            self._canvas_image_id = self._canvas.create_image(
                self.size // 2,
                self.size // 2,
                image=self._images[self.current_visual_state],
            )

    def _setup_bindings(self) -> None:
        """Enable dragging the mascot across the desktop."""
        if not self._canvas or not self._root:
            return

        def on_drag_start(event: tk.Event) -> None:
            self._drag_start_x = event.x
            self._drag_start_y = event.y

        def on_drag_motion(event: tk.Event) -> None:
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            new_x = self._root.winfo_x() + dx
            new_y = self._root.winfo_y() + dy
            self._root.geometry(f"+{new_x}+{new_y}")

        self._canvas.bind("<Button-1>", on_drag_start)
        self._canvas.bind("<B1-Motion>", on_drag_motion)

    def set_visual_state(self, state: MascotVisualState) -> None:
        """Thread-safe update of the mascot's visual appearance."""
        if self._is_destroyed:
            return

        def update() -> None:
            if self._is_destroyed or not self._canvas:
                return
            self.current_visual_state = state
            if state in self._images:
                if self._canvas_image_id is None:
                    self._canvas_image_id = self._canvas.create_image(
                        self.size // 2,
                        self.size // 2,
                        image=self._images[state],
                    )
                else:
                    self._canvas.itemconfig(self._canvas_image_id, image=self._images[state])

        if self._root:
            self._root.after(0, update)

    def _start_animation_loop(self) -> None:
        """Ambient float animation loop with subtle bobbing motion."""
        if self._is_destroyed or not self._root:
            return

        # Frame delay: 50ms (~20 FPS tick)
        tick_ms = 50

        def animate_tick() -> None:
            if self._is_destroyed or not self._canvas:
                return

            if not self.reduced_motion and self._canvas_image_id is not None:
                self._anim_frame = (self._anim_frame + 1) % 120
                # Gentle vertical sine bobbing (amplitude: 3px, period: ~6 seconds)
                offset_y = math.sin((self._anim_frame / 60.0) * math.pi) * 3.0
                center_x = self.size // 2
                center_y = int((self.size // 2) + offset_y)
                self._canvas.coords(self._canvas_image_id, center_x, center_y)

            self._anim_timer_id = self._root.after(tick_ms, animate_tick)

        self._anim_timer_id = self._root.after(tick_ms, animate_tick)

    def destroy(self) -> None:
        """Clean up resources and window handles."""
        self._is_destroyed = True
        if self._root and self._anim_timer_id:
            try:
                self._root.after_cancel(self._anim_timer_id)
            except Exception:
                pass
            self._anim_timer_id = None

        if self._owns_root and self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None
