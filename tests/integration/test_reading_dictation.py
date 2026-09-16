"""
Integration tests for Project NOVA Reading, Scrolling & Free-Text Dictation (MOD-004)
Verifies end-to-end interaction across:
- FR-019: Fluid mouse wheel continuous scrolling via voice commands ("scroll down", "scroll up")
- FR-016 / FR-019: Dynamic speed modulation ("faster", "slower")
- FR-015 / FR-019: Instant halting via voice ("stop", "halt") and acoustic mouth clicks
- FR-020: Two-phase voice dictation ("type", "dictate") -> DICTATING state -> text injection into active controls
- FR-020: Spoken punctuation parsing, whitespace cleanup, and capitalization
- FR-021 / FR-022: Emergency cancellation ("halt", "cancel") and generation-gated stale text suppression
- PRIV-002: Ephemeral in-memory processing with zero persistent transcription files
"""

import json
import tkinter as tk
import unittest
from unittest.mock import MagicMock

from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemState
from nova.core.glider import ContinuousGlider
from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver, WHEEL_DELTA
from nova.input.scroll_controller import ScrollController
from nova.input.text_injector import TextInjector
from nova.speech.dictation_pipeline import DictationPipeline
from nova.ui.crosshair import CrosshairOverlay
from nova.ui.hud_overlay import HudOverlay


class MockCrawler(UIAutomationCrawler):
    def __init__(self, targets=None):
        super().__init__()
        self._targets = targets or [
            UIElementTarget(1, "Input Field", "Edit", (100, 100, 300, 140), 200, 120, 0, 1234),
        ]
        self._last_crawled_targets = list(self._targets)

    def query_foreground_elements(self):
        self._last_crawled_targets = list(self._targets)
        return [self._targets]

    def revalidate_target(self, target, tolerance_px=5):
        return True


class TestReadingDictationIntegration(unittest.TestCase):
    """End-to-end integration test suite for MOD-004."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.state_machine = StateMachine(initial_state=SystemState.IDLE_ACTIVE)
        self.crawler = MockCrawler()
        self.driver = InputDriver(headless=True)
        self.hud = HudOverlay(root=self.root)
        self.crosshair = CrosshairOverlay(root=self.root, driver=self.driver)
        self.glider = ContinuousGlider(driver=self.driver, root=self.root)
        self.scroller = ScrollController(root=self.root, driver=self.driver, tick_ms=25)
        self.text_injector = TextInjector(driver=self.driver, state_machine=self.state_machine)
        self.dictation_pipeline = DictationPipeline(model_path="non_existent_path")

        self.coordinator = TagSnapCoordinator(
            state_machine=self.state_machine,
            crawler=self.crawler,
            hud=self.hud,
            driver=self.driver,
            crosshair=self.crosshair,
            glider=self.glider,
            scroller=self.scroller,
            text_injector=self.text_injector,
            dictation_pipeline=self.dictation_pipeline,
        )

    def tearDown(self):
        try:
            self.coordinator.destroy()
            if self.dictation_pipeline.is_active:
                self.dictation_pipeline.stop_dictation(commit_pending=False)
            self.root.update_idletasks()
            self.root.destroy()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 1. Continuous Scrolling Tests (FR-019, FR-016, FR-015)
    # -------------------------------------------------------------------------

    def test_scroll_down_start_and_voice_halt(self):
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.scroller.is_scrolling)

        # Spoken phrase: "scroll down"
        handled = self.coordinator.handle_speech_phrase("scroll down")
        self.assertTrue(handled)
        self.assertTrue(self.scroller.is_scrolling)
        self.assertEqual(self.scroller.direction, "down")

        # Execute 2 scroll ticks (default base delta is 15 units, gentle reading pacing)
        self.scroller.step()
        self.scroller.step()
        self.assertEqual(len(self.driver.injected_scrolls), 2)
        self.assertEqual(self.driver.injected_scrolls[0], -15)
        self.assertEqual(self.driver.injected_scrolls[1], -15)

        # Voice halt: "stop"
        handled_stop = self.coordinator.handle_speech_phrase("stop")
        self.assertTrue(handled_stop)
        self.assertFalse(self.scroller.is_scrolling)

    def test_scroll_speed_modulation(self):
        self.coordinator.handle_speech_phrase("scroll")
        self.assertTrue(self.scroller.is_scrolling)
        self.assertEqual(self.scroller.current_speed, 15.0)

        # "faster" -> 1.5x speed (22.5)
        self.coordinator.handle_speech_phrase("faster")
        self.assertEqual(self.scroller.current_speed, 22.5)

        # "slower" -> 0.65x speed (22.5 * 0.65 = 14.625)
        self.coordinator.handle_speech_phrase("slower")
        self.assertAlmostEqual(self.scroller.current_speed, 14.625, places=2)

        self.scroller.stop_scroll()

    def test_scroll_up_and_mouth_click_instant_halt(self):
        """Mouth click (impulse) immediately halts continuous scrolling without firing mouse click (FR-019/FR-015)."""
        self.coordinator.handle_speech_phrase("scroll up")
        self.assertTrue(self.scroller.is_scrolling)
        self.assertEqual(self.scroller.direction, "up")

        self.scroller.step()
        self.assertEqual(self.driver.injected_scrolls[-1], 15)

        # Non-verbal acoustic mouth click arrives
        handled_click = self.coordinator.handle_impulse()
        self.assertTrue(handled_click)

        # Scroller stopped immediately
        self.assertFalse(self.scroller.is_scrolling)

        # Verify NO extraneous mouse clicks were injected
        self.assertEqual(len(self.driver.injected_clicks), 0)

    # -------------------------------------------------------------------------
    # 2. Two-Phase Free-Text Dictation Tests (FR-020, PRIV-002)
    # -------------------------------------------------------------------------

    def test_dictation_flow_type_text_commit(self):
        # Spoken phrase: "type"
        handled = self.coordinator.handle_speech_phrase("type")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        # Simulate ASR recognition
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "hello nova period please enter text"})
        self.dictation_pipeline._recognizer = mock_rec

        # Feed audio chunk
        self.dictation_pipeline.process_pcm_chunk(b"\x00" * 3200)

        # Verify text was formatted and injected via Win32 InputDriver
        self.assertEqual(
            self.driver.injected_keystrokes,
            ["Hello nova. Please enter text "],
        )

        # Conclude dictation via "done"
        self.coordinator.handle_speech_phrase("done")
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)

    def test_dictation_enter_and_backspace_controls(self):
        self.coordinator.handle_speech_phrase("dictate")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        # Backspace in dictation mode
        self.coordinator.handle_speech_phrase("backspace")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<BACKSPACE>")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        # Enter commits and exits dictation mode
        self.coordinator.handle_speech_phrase("enter")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<ENTER>")
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

    def test_mouth_clicks_suppressed_in_dictating_state(self):
        """Mouth sounds must NOT click controls while dictating (FR-013)."""
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        impulse_handled = self.coordinator.handle_impulse()
        self.assertFalse(impulse_handled)
        self.assertEqual(len(self.driver.injected_clicks), 0)

        self.coordinator.handle_speech_phrase("cancel")

    def test_emergency_halt_during_dictation_drops_stale_text(self):
        """Emergency halt bumps generation; subsequent late text is dropped (FR-021, FR-022)."""
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        stale_gen = self.coordinator._dictation_action_generation

        # Emergency halt spoken
        self.coordinator.handle_speech_phrase("halt")
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)
        self.assertGreater(self.state_machine.current_generation, stale_gen)

        # If a late worker tries to inject with the stale generation
        injected = self.text_injector.inject_text("late orphan text", action_generation=stale_gen)
        self.assertFalse(injected)
        self.assertEqual(len(self.driver.injected_keystrokes), 0)

    def test_spoken_click_during_dictation_exits_and_clicks(self):
        """Spoken 'click' while in DICTATING state must exit dictation and fire mouse click immediately."""
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        # Spoken "click"
        handled = self.coordinator.handle_speech_phrase("click")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)
        self.assertEqual(len(self.driver.injected_clicks), 1)
        self.assertEqual(self.driver.injected_clicks[0][2], "left")

    def test_dictation_stream_click_phrase_exits_and_clicks(self):
        """If ASR decodes 'click' inside dictation audio stream, it must exit and click."""
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "click"})
        self.dictation_pipeline._recognizer = mock_rec

        self.dictation_pipeline.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)
        self.assertEqual(len(self.driver.injected_clicks), 1)

    def test_delete_and_back_space_commands(self):
        """'delete' and 'back space' must inject backspace keystrokes in both DICTATING and IDLE_ACTIVE states."""
        # Test in DICTATING mode
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        self.coordinator.handle_speech_phrase("delete")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<BACKSPACE>")

        self.coordinator.handle_speech_phrase("back space")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<BACKSPACE>")

        # Exit dictation
        self.coordinator.handle_speech_phrase("done")
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)

        # Test in IDLE_ACTIVE mode
        self.coordinator.handle_speech_phrase("delete")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<BACKSPACE>")

        self.coordinator.handle_speech_phrase("back space")
        self.assertEqual(self.driver.injected_keystrokes[-1], "<BACKSPACE>")

    def test_dictation_multi_sentence_continuous_streaming(self):
        """Verify dictation does not stop halfway when user pauses or speaks natural vocabulary."""
        # Enter dictation mode
        handled = self.coordinator.handle_speech_phrase("dictate")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)

        mock_rec = MagicMock()
        self.dictation_pipeline._recognizer = mock_rec

        # Clause 1: Initial sentence
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "hello world period"})
        self.dictation_pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIn("Hello world. ", self.driver.injected_keystrokes)
        # Verify dictation is STILL ACTIVE (did not exit halfway!)
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        # Clause 2: Natural vocabulary containing "cancel"
        mock_rec.Result.return_value = json.dumps({"text": "please cancel my appointment period"})
        self.dictation_pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIn("Please cancel my appointment. ", self.driver.injected_keystrokes)
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        # Clause 3: Conclusion with "done"
        mock_rec.Result.return_value = json.dumps({"text": "thank you done"})
        self.dictation_pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIn("Thank you ", self.driver.injected_keystrokes)
        # Session now cleanly concluded
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)


if __name__ == "__main__":
    unittest.main()

