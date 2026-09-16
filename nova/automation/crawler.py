"""
Project NOVA - Windows UI Automation Tree Crawler
Queries accessible controls in the foreground window with <35ms latency budget (NFR-003).
Allocates paginated targets (FR-006, FR-007) and enforces pre-click target re-validation (FR-011).
"""

import atexit
from dataclasses import dataclass
import logging
import math
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 9
MAX_TRAVERSAL_DEPTH = 18
MAX_TARGET_ACCUMULATION = 54
MIN_CONTROL_WIDTH_PX = 12
MIN_CONTROL_HEIGHT_PX = 12
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


def wake_chromium_accessibility(hwnd: int) -> None:
    """
    Chromium/Electron applications (VS Code, Chrome, Edge, Slack, Teams) keep their
    internal accessibility DOM tree dormant by default to save resources.
    Calling AccessibleObjectFromWindow with OBJID_CLIENT and asserting SPI_SETSCREENREADER
    signals Chromium to initialize BrowserAccessibilityManager and expose all web controls.
    """
    try:
        import ctypes
        from ctypes import wintypes
        oleacc = ctypes.windll.oleacc

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_byte * 8),
            ]

        IID_IAccessible = GUID(
            0x618736E0, 0x3C3D, 0x11CF, (ctypes.c_byte * 8)(0x81, 0x0C, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71)
        )
        p_acc = ctypes.c_void_p()
        oleacc.AccessibleObjectFromWindow(hwnd, -4, ctypes.byref(IID_IAccessible), ctypes.byref(p_acc))

        # Assert Windows screen reader flag to activate Chromium renderer accessibility
        try:
            SPI_SETSCREENREADER = 0x0047
            SPIF_SENDCHANGE = 0x0002
            ctypes.windll.user32.SystemParametersInfoW(SPI_SETSCREENREADER, 1, 0, SPIF_SENDCHANGE)
        except Exception:
            pass
    except Exception as exc:
        logger.debug("Chromium accessibility wake-up notification skipped: %s", exc)


class UIAutomationCrawler:
    """
    Crawls Windows UI Automation accessibility tree to identify actionable elements.
    Supports real desktop inspection via uiautomation / pywin32, and synthetic injection for tests.
    """

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        self.page_size = page_size
        self._synthetic_pages: Optional[List[List[UIElementTarget]]] = None
        self._last_crawled_targets: List[UIElementTarget] = []
        self._original_screenreader_flag: Optional[int] = None

        # Query and preserve original Windows screen reader flag, then assert for Chromium DOM activation
        try:
            import ctypes
            from ctypes import wintypes
            is_active = wintypes.BOOL()
            # SPI_GETSCREENREADER = 0x0046
            if ctypes.windll.user32.SystemParametersInfoW(0x0046, 0, ctypes.byref(is_active), 0):
                self._original_screenreader_flag = 1 if is_active.value else 0

            # SPI_SETSCREENREADER = 0x0047, SPIF_SENDCHANGE = 0x0002
            ctypes.windll.user32.SystemParametersInfoW(0x0047, 1, 0, 2)
            atexit.register(self.restore_system_accessibility_flags)
        except Exception as exc:
            logger.debug("SystemParametersInfoW screen reader flag init skipped: %s", exc)

    def restore_system_accessibility_flags(self) -> None:
        """
        Restores the Windows SPI_SETSCREENREADER system accessibility flag to its
        initial state on shutdown, ensuring host system accessibility settings
        are completely preserved without persistent side effects.
        """
        if self._original_screenreader_flag is not None:
            try:
                import ctypes
                # SPI_SETSCREENREADER = 0x0047, SPIF_SENDCHANGE = 0x0002
                ctypes.windll.user32.SystemParametersInfoW(
                    0x0047, self._original_screenreader_flag, 0, 2
                )
                logger.info(
                    "Restored Windows SPI_SETSCREENREADER to original state: %d",
                    self._original_screenreader_flag,
                )
            except Exception as exc:
                logger.debug("Failed to restore SPI_SETSCREENREADER flag: %s", exc)

    def set_synthetic_targets(self, pages: List[List[UIElementTarget]]) -> None:
        """Inject synthetic UI target pages for deterministic unit testing."""
        self._synthetic_pages = pages
        self._last_crawled_targets = [t for p in pages for t in p]

    def clear_synthetic_targets(self) -> None:
        """Clear synthetic targets to resume live desktop crawling."""
        self._synthetic_pages = None
        self._last_crawled_targets = []

    def query_foreground_elements(self) -> List[List[UIElementTarget]]:
        """
        Query actionable controls from the current foreground window.
        Returns a list of pages, each containing up to 9 UIElementTarget instances.
        """
        if self._synthetic_pages is not None:
            return self._synthetic_pages

        try:
            import os
            import win32gui
            import win32process
            import win32con
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                my_pid = os.getpid()
                hwnd = win32gui.GetForegroundWindow()
                if hwnd and win32gui.IsWindow(hwnd):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == my_pid:
                        # Foreground window belongs to Nova (mascot/HUD); inspect underlying application in Z-order
                        curr = win32gui.GetWindow(win32gui.GetDesktopWindow(), win32con.GW_CHILD)
                        while curr:
                            if win32gui.IsWindowVisible(curr) and not win32gui.IsIconic(curr):
                                _, win_pid = win32process.GetWindowThreadProcessId(curr)
                                if win_pid != my_pid:
                                    cls = win32gui.GetClassName(curr)
                                    if cls not in ("Progman", "WorkerW", "Shell_TrayWnd"):
                                        rect = win32gui.GetWindowRect(curr)
                                        if (rect[2] - rect[0] > 100) and (rect[3] - rect[1] > 100):
                                            hwnd = curr
                                            break
                            curr = win32gui.GetWindow(curr, win32con.GW_HWNDNEXT)

                if not hwnd or not win32gui.IsWindow(hwnd):
                    logger.debug("No active foreground window found for UI Automation query.")
                    return []

                # Signal Chromium/Electron to activate its accessibility tree
                wake_chromium_accessibility(hwnd)

                win_rect = None
                try:
                    if hwnd and win32gui.IsWindow(hwnd):
                        win_rect = win32gui.GetWindowRect(hwnd)
                except Exception:
                    pass

                ctrl = auto.ControlFromHandle(hwnd)
                if not ctrl:
                    logger.debug("Failed to acquire UI Automation control from HWND %s", hwnd)
                    return []

                raw_targets: List[UIElementTarget] = []
                self._traverse_control(ctrl, hwnd, depth=0, accumulator=raw_targets, win_rect=win_rect)

                # Sort actionable targets in visual reading order (top-to-bottom, left-to-right)
                raw_targets.sort(key=lambda t: (t.centroid_y // 45, t.centroid_x))

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

                self._last_crawled_targets = [t for p in pages for t in p]
                logger.info("Crawled %d actionable elements across %d page(s).", len(raw_targets), len(pages))
                return pages

        except Exception as exc:
            logger.error("Error during UI Automation tree crawl: %s", exc)
            return []

    def _find_nearest_in_candidates(
        self, x: int, y: int, candidates: List[UIElementTarget], max_radius: int
    ) -> Optional[UIElementTarget]:
        """Finds closest target from an explicit list of UIElementTarget candidates."""
        if not candidates:
            return None
        best_target: Optional[UIElementTarget] = None
        min_dist = float("inf")
        for t in candidates:
            left, top, right, bottom = t.bounding_box
            if left <= x <= right and top <= y <= bottom:
                return t
            dist = math.hypot(t.centroid_x - x, t.centroid_y - y)
            if dist < min_dist:
                min_dist = dist
                best_target = t
        if min_dist <= max_radius:
            return best_target
        return None

    def find_nearest_target_radial_probe(
        self, x: int, y: int, max_radius: int = 65
    ) -> Optional[UIElementTarget]:
        """
        Tier 1: Direct OS hit-testing via UIAutomation.ControlFromPoint.
        Probes concentric points in a radial grid around (x, y) to query Chromium/Edge/Win32
        hit-test tree directly in <2ms, bypassing top-down window crawling.
        """
        try:
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                probe_offsets = [
                    (0, 0),
                    (0, -20), (0, 20), (-20, 0), (20, 0),
                    (-20, -20), (20, -20), (-20, 20), (20, 20),
                    (0, -45), (0, 45), (-45, 0), (45, 0),
                ]

                strict_interactive = {
                    "ButtonControl",
                    "CheckBoxControl",
                    "HyperlinkControl",
                    "RadioButtonControl",
                    "ComboBoxControl",
                    "TabItemControl",
                    "MenuItemControl",
                    "ListItemControl",
                    "SplitButtonControl",
                    "EditControl",
                }

                best_target: Optional[UIElementTarget] = None
                min_dist = float("inf")
                seen_rects = set()

                for dx, dy in probe_offsets:
                    px, py = x + dx, y + dy
                    try:
                        ctrl = auto.ControlFromPoint(px, py)
                    except Exception:
                        continue

                    if not ctrl:
                        continue

                    target_ctrl = None
                    ctype = getattr(ctrl, "ControlTypeName", "")
                    if ctype in strict_interactive:
                        target_ctrl = ctrl
                    else:
                        # Inspect parent hierarchy up to 3 levels for text/image/div elements inside buttons
                        try:
                            parent = ctrl.GetParentControl()
                            depth = 0
                            while parent and depth < 3:
                                ptype = getattr(parent, "ControlTypeName", "")
                                if ptype in strict_interactive:
                                    target_ctrl = parent
                                    break
                                elif (hasattr(parent, "GetInvokePattern") and parent.GetInvokePattern()) or (
                                    hasattr(parent, "GetTogglePattern") and parent.GetTogglePattern()
                                ):
                                    target_ctrl = parent
                                    break
                                parent = parent.GetParentControl()
                                depth += 1
                        except Exception:
                            pass

                    if not target_ctrl:
                        continue

                    try:
                        rect = getattr(target_ctrl, "BoundingRectangle", None)
                        if not rect:
                            continue

                        rect_tuple = (rect.left, rect.top, rect.right, rect.bottom)
                        if rect_tuple in seen_rects:
                            continue
                        seen_rects.add(rect_tuple)

                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        if width < 8 or height < 8 or width > 600 or height > 200:
                            continue

                        cx = rect.left + (width // 2)
                        cy = rect.top + (height // 2)

                        if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                            dist = 0.0
                        else:
                            dist = math.hypot(cx - x, cy - y)

                        if dist < min_dist and dist <= max_radius:
                            min_dist = dist
                            tname = (getattr(target_ctrl, "Name", "") or "").strip()
                            t_type = getattr(target_ctrl, "ControlTypeName", "ButtonControl").replace("Control", "")
                            best_target = UIElementTarget(
                                target_id=0,
                                title=tname or t_type,
                                control_type=t_type,
                                bounding_box=rect_tuple,
                                centroid_x=cx,
                                centroid_y=cy,
                                page_index=0,
                                window_handle=getattr(target_ctrl, "NativeWindowHandle", 0) or 0,
                                native_element=target_ctrl,
                            )
                            if dist == 0.0:
                                return best_target
                    except Exception:
                        continue

                return best_target
        except Exception as exc:
            logger.debug("Radial point UIA probing skipped: %s", exc)
            return None

    def find_nearest_target(self, x: int, y: int, max_radius: int = 65) -> Optional[UIElementTarget]:
        """
        Finds the closest actionable CTA to screen coordinates (x, y) within max_radius
        using a 4-tier gravity well:
        1. Synthetic target injection (for deterministic unit testing).
        2. Tier 1: Radial UIA Point Probing (auto.ControlFromPoint) across web & desktop.
        3. Tier 2: Real-time OpenCV Visual Contour Detector (for canvas/custom UI).
        4. Tier 3: Cached Foreground Targets (_last_crawled_targets).
        5. Tier 4: Fallback to None (click at raw laser reticle).
        """
        # Deterministic synthetic injection for unit tests
        if self._synthetic_pages is not None:
            candidates = [t for p in self._synthetic_pages for t in p]
            return self._find_nearest_in_candidates(x, y, candidates, max_radius)

        # Tier 1: Radial UIA Point Probing
        target = self.find_nearest_target_radial_probe(x, y, max_radius)
        if target is not None:
            return target

        # Tier 2: OpenCV Visual Contour Detector
        try:
            from nova.automation.vision import find_nearest_button_contour

            visual_centroid = find_nearest_button_contour(x, y, max_radius=max_radius)
            if visual_centroid is not None:
                vcx, vcy = visual_centroid
                return UIElementTarget(
                    target_id=0,
                    title="Visual Button",
                    control_type="Button",
                    bounding_box=(vcx - 16, vcy - 12, vcx + 16, vcy + 12),
                    centroid_x=vcx,
                    centroid_y=vcy,
                    page_index=0,
                    window_handle=0,
                )
        except Exception as exc:
            logger.debug("Visual contour detection fallback skipped: %s", exc)

        # Tier 3: Cached Foreground Targets
        if self._last_crawled_targets:
            return self._find_nearest_in_candidates(x, y, self._last_crawled_targets, max_radius)

        return None

    def _traverse_control(
        self,
        ctrl: Any,
        hwnd: int,
        depth: int,
        accumulator: List[UIElementTarget],
        win_rect: Optional[Tuple[int, int, int, int]] = None,
    ) -> None:
        """Recursive bounded tree traversal collecting clickable controls."""
        if depth > MAX_TRAVERSAL_DEPTH or len(accumulator) >= MAX_TARGET_ACCUMULATION:
            return

        # 1. Safely inspect current node without letting property errors abort tree traversal
        try:
            is_offscreen = False
            try:
                is_offscreen = bool(getattr(ctrl, "IsOffscreen", False))
            except Exception:
                pass

            # Ignore explicitly disabled controls (non-actionable)
            try:
                if hasattr(ctrl, "IsEnabled") and not ctrl.IsEnabled:
                    is_offscreen = True
            except Exception:
                pass

            rect = getattr(ctrl, "BoundingRectangle", None) if not is_offscreen else None
            if rect:
                width = rect.right - rect.left
                height = rect.bottom - rect.top

                if width >= MIN_CONTROL_WIDTH_PX and height >= MIN_CONTROL_HEIGHT_PX:
                    cx = rect.left + (width // 2)
                    cy = rect.top + (height // 2)

                    valid_bounds = True
                    if win_rect is not None:
                        w_left, w_top, w_right, w_bottom = win_rect
                        w_w = max(1, w_right - w_left)
                        w_h = max(1, w_bottom - w_top)

                        # Discard controls whose centroid falls outside the active window
                        if not (w_left <= cx <= w_right and w_top <= cy <= w_bottom):
                            valid_bounds = False
                        # Discard outer window background containers (>65% width and >45% height)
                        elif width >= int(w_w * 0.65) and height >= int(w_h * 0.45):
                            valid_bounds = False

                    # Reject controls with unreasonably massive button dimensions
                    if width > 900 and height > 450:
                        valid_bounds = False

                    if valid_bounds:
                        ctype = getattr(ctrl, "ControlTypeName", "")
                        name = (getattr(ctrl, "Name", "") or "").strip()

                        # Non-actionable container types to filter out completely
                        container_types = {
                            "WindowControl",
                            "PaneControl",
                            "GroupControl",
                            "TitleBarControl",
                            "ScrollBarControl",
                            "ToolBarControl",
                            "MenuBarControl",
                            "MenuControl",
                            "ListControl",
                            "TreeControl",
                            "DataGridControl",
                            "TableControl",
                            "HeaderControl",
                            "TabControl",
                            "StatusBarControl",
                            "SeparatorControl",
                        }

                        if ctype not in container_types:
                            # Inherent CTA controls that are always clickable
                            strict_interactive_types = {
                                "ButtonControl",
                                "MenuItemControl",
                                "HyperlinkControl",
                                "CheckBoxControl",
                                "RadioButtonControl",
                                "EditControl",
                                "TabItemControl",
                                "ComboBoxControl",
                                "SplitButtonControl",
                            }

                            item_types = {
                                "ListItemControl",
                                "TreeItemControl",
                            }

                            conditional_types = {
                                "CustomControl",
                                "DataItemControl",
                                "HeaderItemControl",
                            }

                            clickable_actions = {"Click", "Press", "Jump", "Select", "Execute", "Double Click"}

                            has_action = False
                            if ctype in strict_interactive_types:
                                has_action = True
                            elif ctype == "ImageControl":
                                # ImageControl is actionable if named (icon buttons like search/cart/close) or exposes an invoke/legacy pattern
                                legacy_action = ""
                                if hasattr(ctrl, "GetLegacyIAccessiblePattern"):
                                    try:
                                        p = ctrl.GetLegacyIAccessiblePattern()
                                        if p:
                                            legacy_action = getattr(p, "DefaultAction", "") or ""
                                    except Exception:
                                        pass
                                has_action = bool(name) or legacy_action in clickable_actions or (hasattr(ctrl, "GetInvokePattern") and bool(ctrl.GetInvokePattern()))
                            elif ctype == "TextControl":
                                # TextControl is actionable if it exposes an invoke pattern or clickable legacy action
                                legacy_action = ""
                                if hasattr(ctrl, "GetLegacyIAccessiblePattern"):
                                    try:
                                        p = ctrl.GetLegacyIAccessiblePattern()
                                        if p:
                                            legacy_action = getattr(p, "DefaultAction", "") or ""
                                    except Exception:
                                        pass
                                has_action = legacy_action in clickable_actions or (hasattr(ctrl, "GetInvokePattern") and bool(ctrl.GetInvokePattern()))
                            elif ctype in item_types:
                                has_action = bool(name) or (hasattr(ctrl, "GetSelectionItemPattern") and bool(ctrl.GetSelectionItemPattern())) or (hasattr(ctrl, "GetInvokePattern") and bool(ctrl.GetInvokePattern()))
                            elif ctype in conditional_types:
                                # DataItem, HeaderItem, and CustomControl
                                legacy_action = ""
                                if hasattr(ctrl, "GetLegacyIAccessiblePattern"):
                                    try:
                                        p = ctrl.GetLegacyIAccessiblePattern()
                                        if p:
                                            legacy_action = getattr(p, "DefaultAction", "") or ""
                                    except Exception:
                                        pass
                                has_action = (
                                    legacy_action in clickable_actions
                                    or (hasattr(ctrl, "GetInvokePattern") and bool(ctrl.GetInvokePattern()))
                                    or (hasattr(ctrl, "GetTogglePattern") and bool(ctrl.GetTogglePattern()))
                                    or (hasattr(ctrl, "GetSelectionItemPattern") and bool(ctrl.GetSelectionItemPattern()))
                                )
                            elif hasattr(ctrl, "GetInvokePattern") and bool(ctrl.GetInvokePattern()):
                                has_action = True
                            elif hasattr(ctrl, "GetTogglePattern") and bool(ctrl.GetTogglePattern()):
                                has_action = True
                            else:
                                if hasattr(ctrl, "GetLegacyIAccessiblePattern"):
                                    try:
                                        p = ctrl.GetLegacyIAccessiblePattern()
                                        if p and getattr(p, "DefaultAction", "") in clickable_actions:
                                            has_action = True
                                    except Exception:
                                        pass

                            if has_action:
                                # Overlapping badge deduplication within 14px (matching 32x21px badges)
                                overlapping_idx = None
                                for idx, t in enumerate(accumulator):
                                    if abs(t.centroid_x - cx) < 14 and abs(t.centroid_y - cy) < 14:
                                        overlapping_idx = idx
                                        break

                                if overlapping_idx is not None:
                                    existing = accumulator[overlapping_idx]
                                    # If new control is a more specific strict CTA and existing was generic, prioritize strict CTA
                                    if ctype in strict_interactive_types and existing.control_type not in strict_interactive_types:
                                        accumulator[overlapping_idx] = UIElementTarget(
                                            target_id=existing.target_id,
                                            title=name[:40] or existing.title,
                                            control_type=ctype,
                                            bounding_box=(rect.left, rect.top, rect.right, rect.bottom),
                                            centroid_x=cx,
                                            centroid_y=cy,
                                            page_index=0,
                                            window_handle=hwnd,
                                            native_element=ctrl,
                                        )
                                else:
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
        except Exception:
            pass

        if len(accumulator) >= MAX_TARGET_ACCUMULATION:
            return

        # 2. Independently traverse children so container errors never prune the subtree
        try:
            for child in ctrl.GetChildren():
                self._traverse_control(child, hwnd, depth + 1, accumulator, win_rect)
                if len(accumulator) >= MAX_TARGET_ACCUMULATION:
                    break
        except Exception as exc:
            logger.debug("Skipping unreadable child nodes at depth %d: %s", depth, exc)

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
            import os
            import win32gui
            import win32process
            import uiautomation as auto

            with auto.UIAutomationInitializerInThread():
                current_hwnd = win32gui.GetForegroundWindow()
                if current_hwnd and win32gui.IsWindow(current_hwnd):
                    _, cur_pid = win32process.GetWindowThreadProcessId(current_hwnd)
                    if cur_pid == os.getpid():
                        # HUD or mascot window is active, consider target window still valid
                        current_hwnd = target.window_handle

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
