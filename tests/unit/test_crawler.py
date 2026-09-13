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


if __name__ == "__main__":
    unittest.main()
