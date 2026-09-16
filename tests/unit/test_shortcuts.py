"""
Project NOVA - Unit Tests for System Shortcuts & Media Routing (MOD-005)
Verifies:
- FR-020: Application launching (Browser with accessibility flag, Paint, Explorer)
- SEC-004: YouTube query parameter sanitization & command injection prevention
- FR-020: Window management hotkeys (Alt+Tab, Alt+F4, Win+D)
"""

import unittest
from unittest.mock import MagicMock

from nova.automation.shortcuts import SystemShortcutManager
from nova.input.driver import InputDriver


class TestSystemShortcuts(unittest.TestCase):
    def setUp(self):
        self.driver = InputDriver(headless=True)
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

    # -------------------------------------------------------------------------
    # 1. YouTube Query Sanitization Tests (SEC-004)
    # -------------------------------------------------------------------------

    def test_sanitize_youtube_query_basic(self):
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("play bohemian rhapsody on youtube"),
            "bohemian rhapsody",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("search lofi hip hop in youtube"),
            "lofi hip hop",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("play jazz"),
            "jazz",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("on youtube"),
            "",
        )

    def test_sanitize_youtube_query_unk_and_prefixes(self):
        """Conversational prefixes ('hey', 'wake up'), [unk] tokens, and command prefixes are stripped."""
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("hey play on youtube [unk]"),
            "",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("hey play lofi beats [unk]"),
            "lofi beats",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("hey nova search jazz music on youtube"),
            "jazz music",
        )
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("play on youtube <unk>"),
            "",
        )
        # Verify fallback to home url when query reduces to empty
        res = self.shortcuts.play_youtube("hey play on youtube [unk]")
        self.assertTrue(res)
        self.assertEqual(self.opened_urls[-1], "https://www.youtube.com")

    def test_sanitize_youtube_query_injection_prevention(self):
        """Disallowed shell characters (;&|`$<>) and control chars are stripped (SEC-004)."""
        # Semicolon command separator
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("lofi beats; calc.exe"),
            "lofi beats calc.exe",
        )
        # Background job / pipeline
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("song & notepad.exe | dir"),
            "song notepad.exe dir",
        )
        # Variable substitution & backticks
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("`whoami` $PATH <file>"),
            "whoami PATH file",
        )
        # Null bytes and control characters
        self.assertEqual(
            self.shortcuts.sanitize_youtube_query("jazz\x00music\r\nstream"),
            "jazz music stream",
        )

    def test_play_youtube_query_url_encoding(self):
        res = self.shortcuts.play_youtube("lo-fi hip hop & relaxing beats")
        self.assertTrue(res)
        self.assertEqual(len(self.opened_urls), 1)
        self.assertEqual(
            self.opened_urls[0],
            "https://www.youtube.com/results?search_query=lo-fi+hip+hop+relaxing+beats",
        )

    def test_play_youtube_empty_query_opens_home(self):
        res = self.shortcuts.play_youtube("")
        self.assertTrue(res)
        self.assertEqual(len(self.opened_urls), 1)
        self.assertEqual(self.opened_urls[0], "https://www.youtube.com")

    # -------------------------------------------------------------------------
    # 2. Application Launching Tests (FR-020)
    # -------------------------------------------------------------------------

    def test_launch_browser_with_accessibility_flag(self):
        self.shortcuts.find_browser_executable = MagicMock(return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        res = self.shortcuts.launch_browser()
        self.assertTrue(res)
        self.assertEqual(len(self.launched_browser_cmds), 1)
        self.assertEqual(
            self.launched_browser_cmds[0],
            [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--force-renderer-accessibility"],
        )

    def test_launch_browser_with_url(self):
        self.shortcuts.find_browser_executable = MagicMock(return_value=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        res = self.shortcuts.launch_browser("https://www.google.com")
        self.assertTrue(res)
        self.assertEqual(
            self.launched_browser_cmds[0],
            [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--force-renderer-accessibility", "https://www.google.com"],
        )

    def test_launch_browser_rejects_unsafe_scheme(self):
        """Non-HTTP schemes (file://, javascript:, cmd:) are blocked (SEC-004)."""
        res = self.shortcuts.launch_browser("file:///C:/Windows/System32/cmd.exe")
        self.assertFalse(res)
        self.assertEqual(len(self.launched_browser_cmds), 0)

    def test_launch_paint(self):
        res = self.shortcuts.launch_paint()
        self.assertTrue(res)
        self.assertEqual(self.launched_paint_cmds[0], ["mspaint.exe"])

    def test_launch_explorer_default(self):
        res = self.shortcuts.launch_explorer()
        self.assertTrue(res)
        self.assertEqual(self.launched_explorer_cmds[0], ["explorer.exe", "shell:MyComputerFolder"])

    def test_launch_explorer_sanitizes_unsafe_folder(self):
        res = self.shortcuts.launch_explorer("C:\\Users;&calc.exe")
        self.assertTrue(res)
        # Unsafe folder parameter rejected; safely defaults to shell:MyComputerFolder
        self.assertEqual(self.launched_explorer_cmds[0], ["explorer.exe", "shell:MyComputerFolder"])

    def test_launch_explorer_allows_valid_windows_path(self):
        """Standard Windows paths with backslashes must be accepted and launched."""
        res = self.shortcuts.launch_explorer(r"C:\Users\Cyber_bot\Documents")
        self.assertTrue(res)
        self.assertEqual(self.launched_explorer_cmds[-1], ["explorer.exe", r"C:\Users\Cyber_bot\Documents"])


    # -------------------------------------------------------------------------
    # 3. Window Management Hotkey Tests (FR-020)
    # -------------------------------------------------------------------------

    def test_switch_window_dispatches_alt_tab(self):
        res = self.shortcuts.switch_window()
        self.assertTrue(res)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<ALT+TAB>")

    def test_close_window_dispatches_alt_f4(self):
        res = self.shortcuts.close_window()
        self.assertTrue(res)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<ALT+F4>")

    def test_show_desktop_dispatches_win_d(self):
        res = self.shortcuts.show_desktop()
        self.assertTrue(res)
        self.assertEqual(self.driver.injected_keystrokes[-1], "<WIN+D>")


if __name__ == "__main__":
    unittest.main()
