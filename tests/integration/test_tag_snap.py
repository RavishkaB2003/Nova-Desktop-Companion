"""
Project NOVA - Integration Tests for Semantic UI Target Navigation (Tag & Snap)
Verifies end-to-end coordination across speech tokens, state machine, crawler, HUD, and mouse driver.
"""

import tkinter as tk
import unittest
from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemState
from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver
from nova.ui.hud_overlay import HudOverlay


class TestTagSnapIntegration(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        self.crawler = UIAutomationCrawler(page_size=9)
        self.hud = HudOverlay(root=self.root)
        self.driver = InputDriver(headless=True)

        self.coordinator = TagSnapCoordinator(
            state_machine=self.sm,
            crawler=self.crawler,
            hud=self.hud,
            driver=self.driver,
            reduced_motion=False,
        )

        # Build 15 synthetic targets across 2 pages
        targets_p1 = [
            UIElementTarget(
                target_id=i,
                title=f"Button {i}",
                control_type="ButtonControl",
                bounding_box=(100 * i, 100, 100 * i + 80, 140),
                centroid_x=100 * i + 40,
                centroid_y=120,
                page_index=0,
                window_handle=777,
            )
            for i in range(1, 10)
        ]
        targets_p2 = [
            UIElementTarget(
                target_id=i,
                title=f"Link {i}",
                control_type="HyperlinkControl",
                bounding_box=(100 * i, 200, 100 * i + 80, 240),
                centroid_x=100 * i + 40,
                centroid_y=220,
                page_index=1,
                window_handle=777,
            )
            for i in range(1, 7)
        ]
        self.crawler.set_synthetic_targets([targets_p1, targets_p2])

    def tearDown(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.hud.destroy()
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    def test_end_to_end_tag_and_snap_flow(self):
        # 1. Trigger "tag"
        handled = self.coordinator.handle_speech_phrase("tag")
        self.root.update()

        self.assertTrue(handled)
        self.assertEqual(self.sm.current_state, SystemState.TRACKING)
        self.assertTrue(self.hud.is_visible)
        self.assertEqual(self.coordinator.current_page_index, 0)
        self.assertEqual(self.coordinator.total_pages, 2)

        # 2. Test pagination: "next"
        self.coordinator.handle_speech_phrase("next")
        self.root.update()
        self.assertEqual(self.coordinator.current_page_index, 1)

        # 3. Test pagination: "back"
        self.coordinator.handle_speech_phrase("back")
        self.root.update()
        self.assertEqual(self.coordinator.current_page_index, 0)

        # 4. Arm modifier "double"
        self.coordinator.handle_speech_phrase("double")

        # 5. Select digit "3"
        handled_digit = self.coordinator.handle_speech_phrase("3")
        self.root.update()

        self.assertTrue(handled_digit)
        # End state returns to IDLE_ACTIVE
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.hud.is_visible)

        # Verify cursor glide reached Target 3 centroid (340, 120)
        self.assertTrue(len(self.driver.injected_glides) > 0)
        self.assertEqual(self.driver.injected_glides[-1], (340, 120))

        # Verify double-click was dispatched
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0], (340, 120, "left", 2))

    def test_stale_target_revalidation_guard(self):
        # Trigger "tag"
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertEqual(self.sm.current_state, SystemState.TRACKING)

        # Mock crawler to simulate stale target (element moved / window switched)
        self.crawler.revalidate_target = lambda target, tolerance_px=5: False

        # Attempt to select digit "4"
        handled = self.coordinator.handle_speech_phrase("4")
        self.root.update()

        # Action must be aborted (FR-011)
        self.assertFalse(handled)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.hud.is_visible)
        # Zero clicks should have been dispatched
        self.assertEqual(len(self.driver.injected_clicks), 0)

    def test_direct_in_place_click(self):
        self.coordinator.handle_speech_phrase("click")
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][2], "left")

    def test_emergency_halt_dismissal(self):
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        self.coordinator.handle_speech_phrase("halt")
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)


if __name__ == "__main__":
    unittest.main()
