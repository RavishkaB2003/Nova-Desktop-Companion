"""
Project NOVA - Unit Tests for UI Automation Crawler
"""

import unittest
from nova.automation.crawler import (
    DEFAULT_PAGE_SIZE,
    REVALIDATE_TOLERANCE_PX,
    UIAutomationCrawler,
    UIElementTarget,
)


class TestUIAutomationCrawler(unittest.TestCase):
    def setUp(self):
        self.crawler = UIAutomationCrawler(page_size=DEFAULT_PAGE_SIZE)

    def test_constants(self):
        self.assertEqual(DEFAULT_PAGE_SIZE, 9)
        self.assertEqual(REVALIDATE_TOLERANCE_PX, 5)

    def test_synthetic_injection_and_pagination(self):
        # Create 22 synthetic targets -> should produce 3 pages (9 + 9 + 4)
        synthetic_pages = []
        total_targets = 22
        page_size = 9

        for p_idx in range(3):
            page = []
            count = min(page_size, total_targets - (p_idx * page_size))
            for i in range(1, count + 1):
                page.append(
                    UIElementTarget(
                        target_id=i,
                        title=f"Button {i}",
                        control_type="ButtonControl",
                        bounding_box=(100 * i, 100, 100 * i + 80, 140),
                        centroid_x=100 * i + 40,
                        centroid_y=120,
                        page_index=p_idx,
                        window_handle=12345,
                    )
                )
            synthetic_pages.append(page)

        self.crawler.set_synthetic_targets(synthetic_pages)
        pages = self.crawler.query_foreground_elements()

        self.assertEqual(len(pages), 3)
        self.assertEqual(len(pages[0]), 9)
        self.assertEqual(len(pages[1]), 9)
        self.assertEqual(len(pages[2]), 4)

        # Check target IDs are 1..9 on each page
        for page in pages:
            for idx, item in enumerate(page, start=1):
                self.assertEqual(item.target_id, idx)

    def test_revalidate_synthetic_target(self):
        target = UIElementTarget(
            target_id=1,
            title="Submit",
            control_type="ButtonControl",
            bounding_box=(100, 100, 200, 140),
            centroid_x=150,
            centroid_y=120,
            page_index=0,
            window_handle=9999,
        )
        self.crawler.set_synthetic_targets([[target]])
        self.assertTrue(self.crawler.revalidate_target(target, tolerance_px=5))

    def test_traverse_control_bounds_and_offscreen_filtering(self):
        """Crawler filters out off-screen controls, foreign monitor bounds, and huge container backgrounds."""
        class MockRect:
            def __init__(self, left, top, right, bottom):
                self.left = left
                self.top = top
                self.right = right
                self.bottom = bottom

        class MockControl:
            def __init__(self, name, ctype, rect, is_offscreen=False, children=None):
                self.Name = name
                self.ControlTypeName = ctype
                self.BoundingRectangle = rect
                self.IsOffscreen = is_offscreen
                self._children = children or []

            def GetChildren(self):
                return self._children

        win_rect = (100, 100, 800, 600)

        # 1. Valid button inside window
        btn_valid = MockControl("OK", "ButtonControl", MockRect(150, 150, 250, 190))
        # 2. Control outside window (e.g. secondary monitor)
        btn_off_mon = MockControl("Hidden", "ButtonControl", MockRect(2500, 50, 2600, 90))
        # 3. Offscreen control
        btn_offscreen = MockControl("Invisible", "ButtonControl", MockRect(200, 200, 300, 240), is_offscreen=True)
        # 4. Massive window background container (>88% of window area)
        pane_huge = MockControl("MainPane", "PaneControl", MockRect(100, 100, 790, 590))

        root_ctrl = MockControl("Window", "WindowControl", MockRect(100, 100, 800, 600), children=[btn_valid, btn_off_mon, btn_offscreen, pane_huge])

        acc = []
        self.crawler._traverse_control(root_ctrl, hwnd=123, depth=0, accumulator=acc, win_rect=win_rect)

        # Only the valid button should be accumulated
        self.assertEqual(len(acc), 1)
        self.assertEqual(acc[0].title, "OK")

    def test_cta_filtering_and_container_exclusion(self):
        """Verify containers, unclickable data items, and disabled controls are excluded, while action-pattern controls are included."""
        class MockRect:
            def __init__(self, left, top, right, bottom):
                self.left = left
                self.top = top
                self.right = right
                self.bottom = bottom

        class MockPatternControl:
            def __init__(self, name, ctype, rect, has_invoke=False, is_enabled=True, children=None):
                self.Name = name
                self.ControlTypeName = ctype
                self.BoundingRectangle = rect
                self.IsOffscreen = False
                self.IsEnabled = is_enabled
                self._has_invoke = has_invoke
                self._children = children or []

            def GetChildren(self):
                return self._children

            def GetInvokePattern(self):
                return True if self._has_invoke else None

            def GetTogglePattern(self):
                return None

            def GetSelectionItemPattern(self):
                return None

        win_rect = (0, 0, 1000, 800)

        # 1. Container ToolBarControl (should NOT be tagged, but its children should)
        btn_inside_bar = MockPatternControl("Save", "ButtonControl", MockRect(20, 20, 80, 50))
        toolbar = MockPatternControl("Standard Toolbar", "ToolBarControl", MockRect(10, 10, 300, 60), children=[btn_inside_bar])

        # 2. Static HeaderItemControl without invoke (should be excluded)
        static_header = MockPatternControl("Date Modified", "HeaderItemControl", MockRect(100, 100, 200, 130))

        # 3. Interactive HeaderItemControl with invoke (e.g. Sort column, should be included)
        sort_header = MockPatternControl("Sort Name", "HeaderItemControl", MockRect(210, 100, 310, 130), has_invoke=True)

        # 4. Static DataItemControl without pattern (e.g. unclickable cell, should be excluded)
        static_cell = MockPatternControl("12 KB", "DataItemControl", MockRect(100, 150, 200, 180))

        # 5. Interactive DataItemControl with invoke (e.g. actionable row/cell, should be included)
        action_cell = MockPatternControl("Open File", "DataItemControl", MockRect(210, 150, 310, 180), has_invoke=True)

        # 6. Disabled ButtonControl (should be excluded)
        disabled_btn = MockPatternControl("Disabled Gray", "ButtonControl", MockRect(400, 150, 480, 180), is_enabled=False)

        root = MockPatternControl("Root", "WindowControl", MockRect(0, 0, 1000, 800), children=[
            toolbar, static_header, sort_header, static_cell, action_cell, disabled_btn
        ])

        acc = []
        self.crawler._traverse_control(root, hwnd=999, depth=0, accumulator=acc, win_rect=win_rect)

        # Expected: btn_inside_bar, sort_header, action_cell (3 items)
        # Excluded: toolbar (container), static_header (no pattern), static_cell (no pattern), disabled_btn (disabled)
        titles = [t.title for t in acc]
        self.assertEqual(len(acc), 3)
        self.assertIn("Save", titles)
        self.assertIn("Sort Name", titles)
        self.assertIn("Open File", titles)
        self.assertNotIn("Standard Toolbar", titles)
        self.assertNotIn("Date Modified", titles)
        self.assertNotIn("12 KB", titles)
        self.assertNotIn("Disabled Gray", titles)

    def test_priority_deduplication(self):
        """ButtonControl upgrades a generic CustomControl at overlapping coordinates."""
        class MockRect:
            def __init__(self, left, top, right, bottom):
                self.left = left
                self.top = top
                self.right = right
                self.bottom = bottom

        class MockCtrl:
            def __init__(self, name, ctype, rect, has_invoke=True, children=None):
                self.Name = name
                self.ControlTypeName = ctype
                self.BoundingRectangle = rect
                self.IsOffscreen = False
                self.IsEnabled = True
                self._has_invoke = has_invoke
                self._children = children or []

            def GetChildren(self):
                return self._children

            def GetInvokePattern(self):
                return True if self._has_invoke else None

            def GetTogglePattern(self):
                return None

            def GetSelectionItemPattern(self):
                return None

        # A CustomControl wrapper around a ButtonControl at essentially the same position
        btn = MockCtrl("Submit Form", "ButtonControl", MockRect(100, 100, 180, 140))
        custom_wrapper = MockCtrl("Wrapper", "CustomControl", MockRect(98, 98, 182, 142), children=[btn])

        root = MockCtrl("App", "WindowControl", MockRect(0, 0, 1000, 800), children=[custom_wrapper])

        acc = []
        self.crawler._traverse_control(root, hwnd=1, depth=0, accumulator=acc, win_rect=(0, 0, 1000, 800))

        self.assertEqual(len(acc), 1)
        self.assertEqual(acc[0].control_type, "ButtonControl")
        self.assertEqual(acc[0].title, "Submit Form")

    def test_find_nearest_target_containment_and_radius(self):
        """Verify find_nearest_target finds direct containment and nearby CTA within radius."""
        target = UIElementTarget(
            target_id=1,
            title="Save",
            control_type="ButtonControl",
            bounding_box=(100, 100, 200, 140),
            centroid_x=150,
            centroid_y=120,
            page_index=0,
            window_handle=123,
        )
        self.crawler.set_synthetic_targets([[target]])

        # 1. Direct hit inside bounding box (120, 110)
        found = self.crawler.find_nearest_target(120, 110, max_radius=65)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "Save")

        # 2. Near hit within 65px radius (170, 150 -> distance ~36px from centroid 150, 120)
        found_near = self.crawler.find_nearest_target(170, 150, max_radius=65)
        self.assertIsNotNone(found_near)
        self.assertEqual(found_near.title, "Save")

        # 3. Far miss beyond 65px (e.g. 300, 300)
        found_far = self.crawler.find_nearest_target(300, 300, max_radius=65)
        self.assertIsNone(found_far)

    def test_find_nearest_target_radial_probe(self):
        """Tier 1: Radial probe finds interactive button via ControlFromPoint."""
        from unittest.mock import patch, MagicMock

        mock_ctrl = MagicMock()
        mock_ctrl.ControlTypeName = "ButtonControl"
        mock_ctrl.Name = "Web Submit"
        mock_ctrl.NativeWindowHandle = 999

        mock_rect = MagicMock()
        mock_rect.left = 400
        mock_rect.top = 200
        mock_rect.right = 500
        mock_rect.bottom = 240
        mock_ctrl.BoundingRectangle = mock_rect

        with patch("uiautomation.ControlFromPoint", return_value=mock_ctrl):
            # Probe near (440, 210)
            res = self.crawler.find_nearest_target_radial_probe(440, 210, max_radius=65)
            self.assertIsNotNone(res)
            self.assertEqual(res.title, "Web Submit")
            self.assertEqual(res.centroid_x, 450)
            self.assertEqual(res.centroid_y, 220)

    def test_find_nearest_target_visual_fallback(self):
        """Tier 2: When radial UIA probe returns None, visual contour fallback snaps to button."""
        from unittest.mock import patch

        self.crawler.clear_synthetic_targets()

        with patch.object(self.crawler, "find_nearest_target_radial_probe", return_value=None):
            with patch("nova.automation.vision.find_nearest_button_contour", return_value=(320, 180)):
                res = self.crawler.find_nearest_target(300, 175, max_radius=65)
                self.assertIsNotNone(res)
                self.assertEqual(res.centroid_x, 320)
                self.assertEqual(res.centroid_y, 180)
                self.assertEqual(res.title, "Visual Button")

    def test_image_and_text_control_web_tagging(self):
        """Crawler tags ImageControl icon buttons and TextControls with Click actions."""
        class MockRect:
            def __init__(self, left, top, right, bottom):
                self.left = left
                self.top = top
                self.right = right
                self.bottom = bottom

        class MockLegacyPattern:
            def __init__(self, action):
                self.DefaultAction = action

        class MockRichControl:
            def __init__(self, name, ctype, rect, action=""):
                self.Name = name
                self.ControlTypeName = ctype
                self.BoundingRectangle = rect
                self.IsOffscreen = False
                self.IsEnabled = True
                self._action = action

            def GetChildren(self):
                return []

            def GetInvokePattern(self):
                return None

            def GetLegacyIAccessiblePattern(self):
                return MockLegacyPattern(self._action) if self._action else None

        accumulator = []
        win_rect = (0, 0, 1000, 800)

        # 1. Named ImageControl (e.g. Search icon button)
        img_btn = MockRichControl("Search", "ImageControl", MockRect(50, 50, 80, 80))
        # 2. TextControl with DefaultAction='Click' (e.g. clickable link/tag)
        txt_link = MockRichControl("Learn More", "TextControl", MockRect(100, 50, 200, 80), action="Click")
        # 3. Static TextControl without action (should NOT be tagged)
        txt_static = MockRichControl("Normal paragraph text", "TextControl", MockRect(50, 120, 400, 150))

        self.crawler._traverse_control(img_btn, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)
        self.crawler._traverse_control(txt_link, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)
        self.crawler._traverse_control(txt_static, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)

        titles = [t.title for t in accumulator]
        self.assertIn("Search", titles)
        self.assertIn("Learn More", titles)
        self.assertNotIn("Normal paragraph text", titles)

    def test_deduplication_radius_allows_adjacent_buttons(self):
        """Deduplication at 14px allows adjacent toolbar buttons (18px apart) to both be tagged."""
        class MockRect:
            def __init__(self, left, top, right, bottom):
                self.left = left
                self.top = top
                self.right = right
                self.bottom = bottom

        class MockSimpleControl:
            def __init__(self, name, rect):
                self.Name = name
                self.ControlTypeName = "ButtonControl"
                self.BoundingRectangle = rect
                self.IsOffscreen = False
                self.IsEnabled = True

            def GetChildren(self):
                return []

            def GetInvokePattern(self):
                return True

        accumulator = []
        win_rect = (0, 0, 1000, 800)

        # Button 1: width 30px, centroid x=65
        btn1 = MockSimpleControl("Previous", MockRect(50, 50, 80, 80))
        # Button 2: 18px away, width 30px, centroid x=83 (dx=18 > 14px)
        btn2 = MockSimpleControl("Next", MockRect(98, 50, 128, 80))
        # Button 3: duplicate of btn1 within 5px (e.g. inner div wrapper)
        btn3_dup = MockSimpleControl("Previous Inner", MockRect(52, 52, 78, 78))

        self.crawler._traverse_control(btn1, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)
        self.crawler._traverse_control(btn2, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)
        self.crawler._traverse_control(btn3_dup, hwnd=1, depth=0, accumulator=accumulator, win_rect=win_rect)

        titles = [t.title for t in accumulator]
        self.assertEqual(len(accumulator), 2)
        self.assertIn("Previous", titles)
        self.assertIn("Next", titles)


if __name__ == "__main__":
    unittest.main()
