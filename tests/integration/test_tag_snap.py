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
            self.coordinator.destroy()
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

        # 5. Aim at digit "3" (Option 1: Two-step Aim-then-Click)
        handled_digit = self.coordinator.handle_speech_phrase("3")
        self.root.update()

        self.assertTrue(handled_digit)
        # Option 1: HUD remains visible after aiming so user can confirm or re-aim
        self.assertTrue(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.TRACKING)

        # Verify cursor glide reached Target 3 centroid (340, 120)
        self.assertTrue(len(self.driver.injected_glides) > 0)
        self.assertEqual(self.driver.injected_glides[-1], (340, 120))

        # 6. Confirm click with "click"
        handled_click = self.coordinator.handle_speech_phrase("click")
        self.root.update()
        self.assertTrue(handled_click)

        # Verify double-click was dispatched at (340, 120)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0], (340, 120, "left", 2))
        # HUD stays active for sequential actions
        self.assertTrue(self.hud.is_visible)

        # 7. Dismiss HUD with "done"
        self.coordinator.handle_speech_phrase("done")
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

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

    def test_prefixed_and_compound_speech_commands(self):
        # 1. "hey tag" prefix handling (user reported bug)
        handled = self.coordinator.handle_speech_phrase("hey tag")
        self.root.update()
        self.assertTrue(handled)
        self.assertEqual(self.sm.current_state, SystemState.TRACKING)
        self.assertTrue(self.hud.is_visible)

        # 2. "cancel that" dismissal
        handled_cancel = self.coordinator.handle_speech_phrase("cancel that")
        self.root.update()
        self.assertTrue(handled_cancel)
        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

        # 3. "scan" variant
        self.coordinator.handle_speech_phrase("nova scan")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # 4. "right click 2" compound command (instant aim + click)
        handled_right_click = self.coordinator.handle_speech_phrase("right click 2")
        self.root.update()
        self.assertTrue(handled_right_click)
        self.assertTrue(self.hud.is_visible)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][2], "right")

        # 5. Dismiss with "close"
        self.coordinator.handle_speech_phrase("close")
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

    def test_option_1_aim_then_click_sequential(self):
        # Trigger tag
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # 1. Aim at target 1 (moves cursor, highlights badge, tags stay visible)
        self.assertTrue(self.coordinator.handle_speech_phrase("1"))
        self.root.update()
        self.assertTrue(self.hud.is_visible)
        self.assertEqual(self.driver.injected_glides[-1], (140, 120))
        self.assertEqual(len(self.driver.injected_clicks), 0)

        # 2. Re-aim to target 2 before clicking
        self.assertTrue(self.coordinator.handle_speech_phrase("2"))
        self.root.update()
        self.assertTrue(self.hud.is_visible)
        self.assertEqual(self.driver.injected_glides[-1], (240, 120))
        self.assertEqual(len(self.driver.injected_clicks), 0)

        # 3. Fire click on target 2
        self.assertTrue(self.coordinator.handle_speech_phrase("click"))
        self.root.update()
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[-1], (240, 120, "left", 1))
        # Tags remain visible for next action!
        self.assertTrue(self.hud.is_visible)

        # 4. Aim to target 5 and right click
        self.assertTrue(self.coordinator.handle_speech_phrase("5"))
        self.root.update()
        self.assertEqual(self.driver.injected_glides[-1], (540, 120))
        self.assertTrue(self.coordinator.handle_speech_phrase("right"))
        self.assertTrue(self.coordinator.handle_speech_phrase("click"))
        self.root.update()
        self.assertEqual(len(self.driver.injected_clicks), 2)
        self.assertEqual(self.driver.injected_clicks[-1], (540, 120, "right", 1))
        self.assertTrue(self.hud.is_visible)

        # 5. Dismiss with "done"
        self.assertTrue(self.coordinator.handle_speech_phrase("done"))
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

    def test_spoken_double_click_direct(self):
        """Direct spoken 'double click' executes left double-click in place and disarms modifier."""
        self.driver.set_cursor_pos(300, 400)
        handled = self.coordinator.handle_speech_phrase("double click")
        self.assertTrue(handled)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[-1], (300, 400, "left", 2))
        # Verify modifier was consumed and disarmed
        self.assertIsNone(self.driver.get_active_modifier())

    def test_spoken_right_click_direct_does_not_nudge(self):
        """Direct spoken 'right click' executes right click in place and NEVER nudges cursor right."""
        self.driver.set_cursor_pos(300, 400)
        handled = self.coordinator.handle_speech_phrase("right click")
        self.assertTrue(handled)
        # Position should NOT have moved to (365, 400)
        self.assertEqual(self.driver.get_cursor_pos(), (300, 400))
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[-1], (300, 400, "right", 1))

    def test_spoken_middle_and_triple_clicks_direct(self):
        """Direct spoken 'middle click' and 'triple click' execute accurately."""
        self.driver.set_cursor_pos(500, 500)
        self.assertTrue(self.coordinator.handle_speech_phrase("middle click"))
        self.assertEqual(self.driver.injected_clicks[-1], (500, 500, "middle", 1))

        self.assertTrue(self.coordinator.handle_speech_phrase("triple click"))
        self.assertEqual(self.driver.injected_clicks[-1], (500, 500, "left", 3))

    def test_spoken_close_dismisses_hud_without_laser(self):
        """Spoken 'close', 'close tag', 'clear' dismiss HUD cleanly without starting crosshair laser."""
        # 1. Open tags
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # 2. Say "close"
        handled = self.coordinator.handle_speech_phrase("close")
        self.root.update()
        self.assertTrue(handled)
        self.assertFalse(self.hud.is_visible)
        self.assertFalse(self.coordinator.crosshair.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)

        # 3. Test "close tag"
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)
        self.assertTrue(self.coordinator.handle_speech_phrase("close tag"))
        self.root.update()
        self.assertFalse(self.hud.is_visible)
        self.assertFalse(self.coordinator.crosshair.is_visible)

    def test_crosshair_call_while_hud_visible_dismisses_hud_safely(self):
        """Spoken crosshair trigger while HUD badges are active safely dismisses HUD instead of opening laser."""
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # Spurious crosshair trigger while tags are displayed
        handled = self.coordinator.handle_speech_phrase("laser")
        self.root.update()
        self.assertTrue(handled)
        self.assertFalse(self.hud.is_visible)
        self.assertFalse(self.coordinator.crosshair.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)


if __name__ == "__main__":
    unittest.main()
