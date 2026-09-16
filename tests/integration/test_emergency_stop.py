"""
Project NOVA - Integration Tests for Safety & Emergency Override Subsystem (MOD-006)
Verifies:
1. Vocal emergency stop ('halt', 'cancel') across all active interaction modes (FR-021).
2. Monotonic generation-gated action execution discarding stale in-flight clicks (FR-022).
3. Secondary global physical emergency stop via Win32 RegisterHotKey (Escape, Ctrl+Shift+Q) (FR-023).
4. Clean hotkey unregistration and resource deallocation on shutdown (SEC-005).
5. Parallel isolated emergency spotter during unconstrained dictation (FR-021, SRS.md FR-19).
"""

import threading
import time
import tkinter as tk
import unittest
from unittest.mock import MagicMock

from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.automation.shortcuts import SystemShortcutManager
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemEventType, SystemState
from nova.core.glider import ContinuousGlider
from nova.core.safety import ActionArbiter, GlobalHotkeyManager, SafetyCoordinator
from nova.core.state_machine import StateMachine, SystemEvent
from nova.input.driver import InputDriver
from nova.input.scroll_controller import ScrollController
from nova.input.text_injector import TextInjector
from nova.speech.dictation_pipeline import DictationPipeline
from nova.ui.crosshair import CrosshairOverlay
from nova.ui.hud_overlay import HudOverlay


class TestEmergencyStopIntegration(unittest.TestCase):
    """Integration test suite for Project NOVA MOD-006 Safety & Emergency Override."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.arbiter = ActionArbiter(initial_generation=0)
        self.sm = StateMachine(initial_state=SystemState.IDLE_ACTIVE, arbiter=self.arbiter)
        self.driver = InputDriver(headless=True)
        self.crawler = UIAutomationCrawler()

        # Seed synthetic mock controls for UI Automation
        targets = [
            UIElementTarget(
                target_id=1,
                title="Submit",
                control_type="Button",
                bounding_box=(200, 300, 280, 330),
                centroid_x=240,
                centroid_y=315,
                page_index=0,
                window_handle=12345,
            ),
            UIElementTarget(
                target_id=2,
                title="Cancel",
                control_type="Button",
                bounding_box=(300, 300, 380, 330),
                centroid_x=340,
                centroid_y=315,
                page_index=0,
                window_handle=12345,
            ),
        ]
        self.crawler.set_synthetic_targets([targets])

        self.hud = HudOverlay(root=self.root)
        self.crosshair = CrosshairOverlay(root=self.root, driver=self.driver)
        self.glider = ContinuousGlider(driver=self.driver, root=self.root)
        self.scroller = ScrollController(root=self.root, driver=self.driver)
        self.text_injector = TextInjector(driver=self.driver, state_machine=self.sm)
        self.dictation_pipeline = DictationPipeline(model_path="non_existent_path")
        self.shortcuts = SystemShortcutManager(driver=self.driver)

        self.coordinator = TagSnapCoordinator(
            state_machine=self.sm,
            crawler=self.crawler,
            hud=self.hud,
            driver=self.driver,
            crosshair=self.crosshair,
            glider=self.glider,
            scroller=self.scroller,
            text_injector=self.text_injector,
            dictation_pipeline=self.dictation_pipeline,
            shortcuts=self.shortcuts,
            reduced_motion=True,
        )

    def tearDown(self):
        self.coordinator.stop()
        try:
            self.hud.destroy()
        except Exception:
            pass
        try:
            self.crosshair.destroy()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_vocal_halt_during_crosshair_scan_dismisses_and_resets(self):
        """FR-021: Spoken 'halt' dismisses active crosshair scan and resets state."""
        self.coordinator.handle_speech_phrase("crosshair")
        self.root.update()
        self.assertEqual(self.sm.current_state, SystemState.CROSSHAIR_ACTIVE)
        self.assertTrue(self.crosshair.is_visible)

        gen_before = self.coordinator.safety_coordinator.arbiter.current_generation

        # Issue vocal halt
        self.coordinator.handle_speech_phrase("halt")
        self.root.update()

        self.assertFalse(self.crosshair.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertGreater(self.coordinator.safety_coordinator.arbiter.current_generation, gen_before)

    def test_vocal_cancel_during_continuous_gliding_halts_motion(self):
        """FR-021: Spoken 'cancel' halts glider motion and bumps generation."""
        self.coordinator.handle_speech_phrase("glide")
        self.root.update()
        self.assertEqual(self.sm.current_state, SystemState.GLIDE_ACTIVE)
        self.assertTrue(self.glider.is_gliding)

        gen_before = self.coordinator.safety_coordinator.arbiter.current_generation

        # Issue vocal cancel
        self.coordinator.handle_speech_phrase("cancel")
        self.root.update()

        self.assertFalse(self.glider.is_gliding)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        self.assertGreater(self.coordinator.safety_coordinator.arbiter.current_generation, gen_before)

    def test_physical_escape_hotkey_dismisses_hud_and_resets_to_standby(self):
        """FR-023, SEC-005: Physical Escape hotkey forces immediate reset to STANDBY."""
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        gen_before = self.coordinator.safety_coordinator.arbiter.current_generation

        # Simulate global physical Escape hotkey
        self.coordinator.hotkey_manager.simulate_hotkey("escape")
        self.root.update()

        self.assertFalse(self.hud.is_visible)
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)
        self.assertEqual(self.coordinator.safety_coordinator.arbiter.current_generation, gen_before + 1)

    def test_physical_ctrl_shift_q_hotkey_halts_scroller_and_resets_to_standby(self):
        """FR-023: Global Ctrl+Shift+Q hotkey halts fluid scrolling and forces STANDBY."""
        self.coordinator.handle_speech_phrase("scroll down")
        self.root.update()
        self.assertTrue(self.scroller.is_scrolling)

        gen_before = self.coordinator.safety_coordinator.arbiter.current_generation

        # Simulate global physical Ctrl+Shift+Q hotkey
        self.coordinator.hotkey_manager.simulate_hotkey("ctrl_shift_q")
        self.root.update()

        self.assertFalse(self.scroller.is_scrolling)
        self.assertEqual(self.sm.current_state, SystemState.STANDBY)
        self.assertEqual(self.coordinator.safety_coordinator.arbiter.current_generation, gen_before + 1)

    def test_dictation_emergency_halt_spotted_in_parallel_drops_pending_text(self):
        """FR-021, PRIV-002: Parallel emergency spotter halts dictation without injecting text."""
        self.coordinator.handle_speech_phrase("type")
        self.root.update()
        self.assertEqual(self.sm.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        # Trigger emergency halt via dictation spotter callback
        if self.dictation_pipeline.on_emergency_halt:
            self.dictation_pipeline.on_emergency_halt()

        self.root.update()
        self.assertFalse(self.dictation_pipeline.is_active)
        self.assertEqual(self.sm.current_state, SystemState.IDLE_ACTIVE)
        # Verify no text was injected
        self.assertEqual(len(self.driver.injected_keystrokes), 0)

    def test_generation_gated_action_execution_discards_stale_click(self):
        """FR-022: In-flight click carrying stale generation is dropped without SendInput."""
        # 1. Arm Tag mode
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # 2. Capture stale generation id before dispatch
        stale_gen = self.coordinator.safety_coordinator.arbiter.current_generation

        # 3. An emergency halt occurs before click execution reaches SendInput
        self.coordinator.safety_coordinator.trigger_emergency_halt(source="EMERGENCY_OVERRIDE")
        self.root.update()

        # 4. Verify that an action dispatched with stale generation is rejected by arbiter
        self.assertFalse(self.coordinator.safety_coordinator.arbiter.is_valid(stale_gen))
        self.assertEqual(len(self.driver.injected_clicks), 0)

    def test_clean_shutdown_and_unregistration(self):
        """SEC-005: Clean shutdown deallocates hotkeys and terminates message loop."""
        self.coordinator.start()
        self.assertTrue(self.coordinator.hotkey_manager.is_running)

        self.coordinator.stop()
        self.assertFalse(self.coordinator.hotkey_manager.is_running)
        self.assertEqual(len(self.coordinator.hotkey_manager._registered_ids), 0)


if __name__ == "__main__":
    unittest.main()
