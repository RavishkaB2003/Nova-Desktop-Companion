"""
Project NOVA - Integration Tests for System Intent Routing & Desktop Shortcuts (MOD-005)
Verifies end-to-end speech command coordination for:
- FR-020: Application launching ("open browser", "open paint", "open explorer", "open this pc")
- FR-020, SEC-004: Media searching ("play [query] on youtube", "open youtube")
- FR-020: Window management ("switch window", "close window", "show desktop")
- Disambiguation between "close window" (Alt+F4) and "close" (HUD dismissal)
"""

import tkinter as tk
import unittest
from unittest.mock import MagicMock

from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.automation.shortcuts import SystemShortcutManager
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemState
from nova.core.glider import ContinuousGlider
from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver
from nova.input.scroll_controller import ScrollController
from nova.input.text_injector import TextInjector
from nova.speech.dictation_pipeline import DictationPipeline
from nova.ui.crosshair import CrosshairOverlay
from nova.ui.hud_overlay import HudOverlay


class MockCrawler(UIAutomationCrawler):
    def __init__(self, targets=None):
        super().__init__()
        self._targets = targets or [
            UIElementTarget(1, "Button 1", "Button", (100, 100, 200, 140), 150, 120, 0, 1234),
        ]
        self._last_crawled_targets = list(self._targets)

    def query_foreground_elements(self):
        self._last_crawled_targets = list(self._targets)
        return [self._targets]

    def revalidate_target(self, target, tolerance_px=5):
        return True


class TestSystemShortcutsIntegration(unittest.TestCase):
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

        self.launched_browser_cmds = []
        self.launched_explorer_cmds = []
        self.launched_paint_cmds = []
        self.opened_urls = []

        self.shortcuts = SystemShortcutManager(
            driver=self.driver,
            browser_launcher=lambda cmd: self.launched_browser_cmds.append(cmd),
            explorer_launcher=lambda cmd: self.launched_explorer_cmds.append(cmd),
            paint_launcher=lambda cmd: self.launched_paint_cmds.append(cmd),
            url_opener=lambda url: self.opened_urls.append(url),
        )

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
            shortcuts=self.shortcuts,
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
    # 1. Application Launch Integration Tests (FR-020)
    # -------------------------------------------------------------------------

    def test_voice_command_open_browser(self):
        handled = self.coordinator.handle_speech_phrase("open browser")
        self.assertTrue(handled)
        self.assertTrue(len(self.launched_browser_cmds) > 0 or len(self.opened_urls) > 0)
        if self.launched_browser_cmds:
            self.assertIn("--force-renderer-accessibility", self.launched_browser_cmds[0])
        else:
            self.assertEqual(self.opened_urls[0], "https://www.google.com")

    def test_voice_command_open_paint(self):
        handled = self.coordinator.handle_speech_phrase("open paint")
        self.assertTrue(handled)
        self.assertEqual(len(self.launched_paint_cmds), 1)
        self.assertEqual(self.launched_paint_cmds[0], ["mspaint.exe"])

    def test_voice_command_open_explorer_and_this_pc(self):
        handled1 = self.coordinator.handle_speech_phrase("open explorer")
        self.assertTrue(handled1)
        self.assertEqual(self.launched_explorer_cmds[-1], ["explorer.exe", "shell:MyComputerFolder"])

        handled2 = self.coordinator.handle_speech_phrase("open this pc")
        self.assertTrue(handled2)
        self.assertEqual(self.launched_explorer_cmds[-1], ["explorer.exe", "shell:MyComputerFolder"])

    # -------------------------------------------------------------------------
    # 2. YouTube Search Voice Command Tests (FR-020, SEC-004)
    # -------------------------------------------------------------------------

    def test_voice_command_play_query_on_youtube(self):
        handled = self.coordinator.handle_speech_phrase("play bohemian rhapsody on youtube")
        self.assertTrue(handled)
        self.assertEqual(len(self.opened_urls), 1)
        self.assertEqual(
            self.opened_urls[0],
            "https://www.youtube.com/results?search_query=bohemian+rhapsody",
        )

    def test_voice_command_open_youtube_home(self):
        handled = self.coordinator.handle_speech_phrase("open youtube")
        self.assertTrue(handled)
        self.assertEqual(len(self.opened_urls), 1)
        self.assertEqual(self.opened_urls[0], "https://www.youtube.com")

    def test_youtube_command_during_dictation_mode(self):
        """Speaking a YouTube search during dictation exits dictation and executes search."""
        self.coordinator.handle_speech_phrase("type")
        self.assertEqual(self.state_machine.current_state, SystemState.DICTATING)
        self.assertTrue(self.dictation_pipeline.is_active)

        handled = self.coordinator.handle_speech_phrase("play jazz on youtube")
        self.assertTrue(handled)
        self.assertEqual(self.state_machine.current_state, SystemState.IDLE_ACTIVE)
        self.assertFalse(self.dictation_pipeline.is_active)
        self.assertEqual(
            self.opened_urls[0],
            "https://www.youtube.com/results?search_query=jazz",
        )

    def test_two_phase_youtube_query_flow(self):
        """Saying 'play on youtube' triggers query prompt, and subsequent phrase searches YouTube."""
        spoken_prompts = []
        self.coordinator.speech_feedback.speak = lambda text, on_done=None: (spoken_prompts.append(text), on_done() if on_done else None)

        # 1. User says "play on youtube" without a query
        handled = self.coordinator.handle_speech_phrase("play on youtube")
        self.assertTrue(handled)
        self.assertTrue(getattr(self.coordinator, "_pending_youtube_query", False))
        self.assertIn("What would you like to search for?", spoken_prompts)

        # 2. User says search phrase
        handled_query = self.coordinator.handle_speech_phrase("lofi hip hop beats")
        self.assertTrue(handled_query)
        self.assertFalse(getattr(self.coordinator, "_pending_youtube_query", False))
        self.assertEqual(len(self.opened_urls), 1)
        self.assertEqual(
            self.opened_urls[0],
            "https://www.youtube.com/results?search_query=lofi+hip+hop+beats",
        )

    def test_two_phase_youtube_query_cancel(self):
        """Saying 'cancel' or 'halt' while waiting for YouTube query safely halts."""
        spoken_prompts = []
        self.coordinator.speech_feedback.speak = lambda text, on_done=None: (spoken_prompts.append(text), on_done() if on_done else None)

        self.coordinator.handle_speech_phrase("play on youtube")
        self.assertTrue(getattr(self.coordinator, "_pending_youtube_query", False))

        handled_cancel = self.coordinator.handle_speech_phrase("cancel")
        self.assertTrue(handled_cancel)
        self.assertFalse(getattr(self.coordinator, "_pending_youtube_query", False))
        self.assertIn("Halted", spoken_prompts)
        self.assertEqual(len(self.opened_urls), 0)


    # -------------------------------------------------------------------------
    # 3. Window Management & Disambiguation Tests (FR-020)
    # -------------------------------------------------------------------------

    def test_voice_command_switch_window(self):
        handled = self.coordinator.handle_speech_phrase("switch window")
        self.assertTrue(handled)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<ALT+TAB>")

    def test_voice_command_show_desktop(self):
        handled = self.coordinator.handle_speech_phrase("show desktop")
        self.assertTrue(handled)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<WIN+D>")

    def test_close_window_vs_close_disambiguation(self):
        """
        'close window' executes Alt+F4.
        'close' dismisses HUD target badges and does NOT inject Alt+F4.
        """
        # 1. Open HUD tags
        self.coordinator.handle_speech_phrase("tag")
        self.root.update()
        self.assertTrue(self.hud.is_visible)

        # 2. Say "close window"
        handled_cw = self.coordinator.handle_speech_phrase("close window")
        self.assertTrue(handled_cw)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<ALT+F4>")
        # Tags remain visible because "close window" was targeted at the foreground app!
        self.assertTrue(self.hud.is_visible)

        # 3. Say "close" (should dismiss HUD without injecting Alt+F4)
        count_before = len([k for k in self.driver.injected_keystrokes if k == "<ALT+F4>"])
        handled_close = self.coordinator.handle_speech_phrase("close")
        self.root.update()
        self.assertTrue(handled_close)
        self.assertFalse(self.hud.is_visible)
        count_after = len([k for k in self.driver.injected_keystrokes if k == "<ALT+F4>"])
        self.assertEqual(count_before, count_after)


if __name__ == "__main__":
    unittest.main()
