"""
Project NOVA - Windows UI Automation Tree Crawler
Queries accessible controls in the foreground window with <35ms latency budget (NFR-003).
Allocates paginated targets (FR-006, FR-007) and enforces pre-click target re-validation (FR-011).
"""

from dataclasses import dataclass
import logging
import math
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 9
MAX_TRAVERSAL_DEPTH = 6
MIN_CONTROL_WIDTH_PX = 10
MIN_CONTROL_HEIGHT_PX = 10
REVALIDATE_TOLERANCE_PX = 5


@dataclass(frozen=True)
class UIElementTarget:
    """Represents an actionable semantic UI control on screen."""
    target_id: int  # Single digit (1..9) on the active page
    title: str
    control_type: str
    bounding_box: Tuple[int, int, int, int]  # (left, top, right, bottom)
    centroid_x: int
    centroid_y: int
    page_index: int
    window_handle: int
    native_element: Optional[Any] = None


class UIAutomationCrawler:
    """
    Crawls Windows UI Automation accessibility tree to identify actionable elements.
    Supports real desktop inspection via uiautomation / pywin32, and synthetic injection for tests.
    """

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        self.page_size = page_size
        self._synthetic_pages: Optional[List[List[UIElementTarget]]] = None

    def set_synthetic_targets(self, pages: List[List[UIElementTarget]]) -> None:
        """Inject synthetic UI target pages for deterministic unit testing."""
        self._synthetic_pages = pages

    def clear_synthetic_targets(self) -> None:
        """Clear synthetic targets to resume live desktop crawling."""
        self._synthetic_pages = None

    def query_foreground_elements(self) -> List[List[UIElementTarget]]:
        """
        Query actionable controls from the current foreground window.
        Returns a list of pages, each containing up to 9 UIElementTarget instances.
        """
        if self._synthetic_pages is not None:
            return self._synthetic_pages

        try:
            import win32gui
            import uiautomation as auto

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindow(hwnd):
                logger.debug("No active foreground window found for UI Automation query.")
                return []

            ctrl = auto.ControlFromHandle(hwnd)
            if not ctrl:
                logger.debug("Failed to acquire UI Automation control from HWND %s", hwnd)
                return []

            raw_targets: List[UIElementTarget] = []
            self._traverse_control(ctrl, hwnd, depth=0, accumulator=raw_targets)

            # Paginate into batches of up to page_size (1..9)
            pages: List[List[UIElementTarget]] = []
            for page_idx in range(0, math.ceil(len(raw_targets) / self.page_size) or 1):
                slice_start = page_idx * self.page_size
                slice_end = slice_start + self.page_size
                page_raw = raw_targets[slice_start:slice_end]
                if not page_raw:
                    break

                page_targets: List[UIElementTarget] = []
                for digit_idx, item in enumerate(page_raw, start=1):
                    page_targets.append(
                        UIElementTarget(
                            target_id=digit_idx,
                            title=item.title,
                            control_type=item.control_type,
                            bounding_box=item.bounding_box,
                            centroid_x=item.centroid_x,
                            centroid_y=item.centroid_y,
                            page_index=page_idx,
                            window_handle=item.window_handle,
                            native_element=item.native_element,
                        )
                    )
                pages.append(page_targets)

            logger.info("Crawled %d actionable elements across %d page(s).", len(raw_targets), len(pages))
            return pages

        except Exception as exc:
            logger.error("Error during UI Automation tree crawl: %s", exc)
            return []

    def _traverse_control(
        self,
        ctrl: Any,
        hwnd: int,
        depth: int,
        accumulator: List[UIElementTarget],
    ) -> None:
        """Recursive bounded tree traversal collecting clickable controls."""
        if depth > MAX_TRAVERSAL_DEPTH:
            return

        try:
            rect = ctrl.BoundingRectangle
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            # Only consider elements with valid, visible dimensions
            if width >= MIN_CONTROL_WIDTH_PX and height >= MIN_CONTROL_HEIGHT_PX:
                ctype = getattr(ctrl, "ControlTypeName", "")
                name = getattr(ctrl, "Name", "") or ""

                # Target clickable and actionable control types
                interactive_types = {
                    "ButtonControl",
                    "MenuItemControl",
                    "HyperlinkControl",
                    "CheckBoxControl",
                    "RadioButtonControl",
                    "EditControl",
                    "TabItemControl",
                    "ListItemControl",
                    "TreeItemControl",
                    "ComboBoxControl",
                    "SplitButtonControl",
                }

                if ctype in interactive_types or (hasattr(ctrl, "GetInvokePattern") and ctrl.GetInvokePattern()):
                    cx = rect.left + (width // 2)
                    cy = rect.top + (height // 2)
                    accumulator.append(
                        UIElementTarget(
                            target_id=len(accumulator) + 1,
                            title=name[:40],
                            control_type=ctype,
                            bounding_box=(rect.left, rect.top, rect.right, rect.bottom),
                            centroid_x=cx,
                            centroid_y=cy,
                            page_index=0,
                            window_handle=hwnd,
                            native_element=ctrl,
                        )
                    )

            # Traverse children
            for child in ctrl.GetChildren():
                self._traverse_control(child, hwnd, depth + 1, accumulator)

        except Exception as exc:
            logger.debug("Skipping unreadable control node at depth %d: %s", depth, exc)

    def revalidate_target(
        self,
        target: UIElementTarget,
        tolerance_px: int = REVALIDATE_TOLERANCE_PX,
    ) -> bool:
        """
        Pre-click stale target guard (FR-011).
        Verifies that the target's foreground window is still active and that the element
        centroid hasn't moved beyond tolerance_px.
        """
        if self._synthetic_pages is not None:
            # Synthetic validation logic for automated tests
            return True

        try:
            import win32gui

            current_hwnd = win32gui.GetForegroundWindow()
            if current_hwnd != target.window_handle:
                logger.warning(
                    "Stale target guard: Foreground window changed from %s to %s",
                    target.window_handle,
                    current_hwnd,
                )
                return False

            # Verify element position has not shifted
            if target.native_element is not None:
                rect = target.native_element.BoundingRectangle
                current_cx = rect.left + ((rect.right - rect.left) // 2)
                current_cy = rect.top + ((rect.bottom - rect.top) // 2)
                dx = abs(current_cx - target.centroid_x)
                dy = abs(current_cy - target.centroid_y)
                distance = math.hypot(dx, dy)
                if distance > tolerance_px:
                    logger.warning(
                        "Stale target guard: Target moved by %.1fpx (tolerance=%dpx)",
                        distance,
                        tolerance_px,
                    )
                    return False

            return True
        except Exception as exc:
            logger.error("Failed to revalidate UI target: %s", exc)
            return False
