"""
Project NOVA - System Tray Icon Component
Provides Windows taskbar notification area presence (pystray) when NOVA runs
in background or dormant mode. Enables user to activate/deactivate the mascot,
toggle the control panel, or shut down cleanly.
"""

import logging
import os
import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def create_default_tray_image(size: int = 64) -> Image.Image:
    """Create a high-contrast fallback NOVA mascot icon (cyan & obsidian)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circular background (Obsidian #0A0E17) with Cyan border (#00F0FF)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(10, 14, 23, 255),
        outline=(0, 240, 255, 255),
        width=3,
    )

    # Stylized glowing eye dots (Cyan #00F0FF / Green #00FF9D)
    center_y = size // 2
    eye_radius = 4
    left_x = size // 2 - 10
    right_x = size // 2 + 10

    draw.ellipse(
        [left_x - eye_radius, center_y - eye_radius, left_x + eye_radius, center_y + eye_radius],
        fill=(0, 240, 255, 255),
    )
    draw.ellipse(
        [right_x - eye_radius, center_y - eye_radius, right_x + eye_radius, center_y + eye_radius],
        fill=(0, 255, 157, 255),
    )
    return img


def load_mascot_tray_image(size: int = 64) -> Image.Image:
    """Load and rasterize mascot_sleeping.svg if available, else generate fallback."""
    try:
        import fitz
        from nova.ui.mascot import find_assets_dir
        assets_dir = find_assets_dir()
        svg_path = os.path.join(assets_dir, "mascot_sleeping.svg")
        if os.path.exists(svg_path):
            doc = fitz.open(svg_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=144, alpha=True)
            img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
            return img.resize((size, size), Image.Resampling.LANCZOS)
    except Exception as exc:
        logger.debug("Mascot SVG rasterization for tray fallback: %s", exc)

    return create_default_tray_image(size=size)


class NovaTrayIcon:
    """
    Manages the Windows taskbar notification area (System Tray) icon.
    Operates in detached background thread.
    """

    def __init__(
        self,
        on_activate: Optional[Callable[[], None]] = None,
        on_deactivate: Optional[Callable[[], None]] = None,
        on_toggle_panel: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.on_toggle_panel = on_toggle_panel
        self.on_quit = on_quit

        self._icon: Optional[object] = None
        self._lock = threading.RLock()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def _menu_activate(self, icon=None, item=None) -> None:
        logger.info("Tray menu: Activate requested.")
        if self.on_activate:
            try:
                self.on_activate()
            except Exception as exc:
                logger.error("Error in tray on_activate: %s", exc)

    def _menu_deactivate(self, icon=None, item=None) -> None:
        logger.info("Tray menu: Deactivate requested.")
        if self.on_deactivate:
            try:
                self.on_deactivate()
            except Exception as exc:
                logger.error("Error in tray on_deactivate: %s", exc)

    def _menu_toggle_panel(self, icon=None, item=None) -> None:
        logger.info("Tray menu: Toggle Control Panel requested.")
        if self.on_toggle_panel:
            try:
                self.on_toggle_panel()
            except Exception as exc:
                logger.error("Error in tray on_toggle_panel: %s", exc)

    def _menu_quit(self, icon=None, item=None) -> None:
        logger.info("Tray menu: Quit requested.")
        self.stop()
        if self.on_quit:
            try:
                self.on_quit()
            except Exception as exc:
                logger.error("Error in tray on_quit: %s", exc)

    def start(self) -> bool:
        """Start the system tray icon on a background thread."""
        with self._lock:
            if self._is_running:
                return True

            try:
                import pystray

                image = load_mascot_tray_image(size=64)
                menu = pystray.Menu(
                    pystray.MenuItem("Activate Mascot", self._menu_activate, default=True),
                    pystray.MenuItem("Deactivate Mascot", self._menu_deactivate),
                    pystray.MenuItem("Control Panel", self._menu_toggle_panel),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Quit NOVA", self._menu_quit),
                )

                self._icon = pystray.Icon(
                    name="ProjectNOVA",
                    icon=image,
                    title="NOVA Desktop Companion",
                    menu=menu,
                )

                self._icon.run_detached()
                self._is_running = True
                logger.info("System tray icon started successfully.")
                return True
            except Exception as exc:
                logger.warning("Could not initialize system tray icon (headless or unsupported): %s", exc)
                self._icon = None
                self._is_running = False
                return False

    def update_title(self, title: str) -> None:
        """Update the tooltip text for the system tray icon."""
        with self._lock:
            if self._icon:
                try:
                    self._icon.title = title
                except Exception:
                    pass

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

            if self._icon:
                try:
                    self._icon.stop()
                except Exception as exc:
                    logger.debug("Error stopping tray icon: %s", exc)
                self._icon = None
                logger.info("System tray icon stopped.")
