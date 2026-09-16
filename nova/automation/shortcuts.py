"""
Project NOVA - System Intent Routing & Desktop Shortcuts Subsystem (MOD-005)
Implements whitelisted desktop utility launcher, YouTube search query sanitizer,
and window management shortcuts (FR-020, SEC-001, SEC-004, PRIV-002).
"""

import logging
import os
import re
import subprocess
import urllib.parse
import webbrowser
from typing import Callable, List, Optional

from nova.input.driver import InputDriver

logger = logging.getLogger(__name__)

# Disallowed characters for shell parameter sanitization (SEC-004)
DISALLOWED_SHELL_CHARS_RE = re.compile(r'[\x00-\x1f\x7f;&|`$<>]')
DISALLOWED_EXPLORER_PATH_RE = re.compile(r'[\x00-\x1f\x7f;&|`$<>"\']')

# Standard browser installation candidate paths on Windows
BROWSER_CANDIDATE_PATHS = [
    # Microsoft Edge
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"Microsoft\Edge\Application\msedge.exe"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"Microsoft\Edge\Application\msedge.exe"),
    # Google Chrome
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"Google\Chrome\Application\chrome.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"Google\Chrome\Application\chrome.exe"),
]


class SystemShortcutManager:
    """
    Subsystem manager for rapid execution of desktop utility shortcuts,
    sanitized media queries, and window navigation (FR-020, SEC-004).
    """

    def __init__(
        self,
        driver: Optional[InputDriver] = None,
        browser_launcher: Optional[Callable[[List[str]], None]] = None,
        explorer_launcher: Optional[Callable[[List[str]], None]] = None,
        paint_launcher: Optional[Callable[[List[str]], None]] = None,
        url_opener: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.driver = driver or InputDriver()
        self._browser_launcher = browser_launcher
        self._explorer_launcher = explorer_launcher
        self._paint_launcher = paint_launcher
        self._url_opener = url_opener

    def find_browser_executable(self) -> Optional[str]:
        """Discover Edge or Chrome binary path for pre-warmed accessibility launching."""
        for path in BROWSER_CANDIDATE_PATHS:
            if os.path.exists(path):
                return path
        return None

    def launch_browser(self, url: Optional[str] = None) -> bool:
        """
        Launch default web browser pre-warmed with --force-renderer-accessibility (FR-020).
        This ensures Chromium exposes DOM elements to Windows UI Automation out-of-the-box.
        """
        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https"):
                logger.warning("Rejected non-HTTP URL for browser launch: '%s'", url)
                return False

        browser_exe = self.find_browser_executable()

        cmd = [browser_exe, "--force-renderer-accessibility"] if browser_exe else None
        if cmd and url:
            cmd.append(url)

        if cmd:
            try:
                if self._browser_launcher:
                    self._browser_launcher(cmd)
                else:
                    subprocess.Popen(cmd, shell=False)
                logger.info("Launched browser via executable '%s' with accessibility flag.", browser_exe)
                return True
            except Exception as exc:
                logger.warning("Failed to launch browser executable '%s': %s. Falling back to default handler.", browser_exe, exc)

        # Fallback to standard Python webbrowser module
        target_url = url or "https://www.google.com"
        try:
            if self._url_opener:
                self._url_opener(target_url)
            else:
                webbrowser.open(target_url)
            logger.info("Launched browser via standard URL handler: '%s'", target_url)
            return True
        except Exception as exc:
            logger.error("Failed to launch browser via URL handler: %s", exc)
            return False

    def launch_paint(self) -> bool:
        """Launch Windows Paint (mspaint.exe) (FR-020)."""
        cmd = ["mspaint.exe"]
        try:
            if self._paint_launcher:
                self._paint_launcher(cmd)
            else:
                subprocess.Popen(cmd, shell=False)
            logger.info("Launched Windows Paint.")
            return True
        except Exception as exc:
            logger.error("Failed to launch Paint: %s", exc)
            return False

    def launch_explorer(self, folder: str = "shell:MyComputerFolder") -> bool:
        """Launch Windows Explorer (explorer.exe) at This PC / specified folder (FR-020)."""
        # Validate folder argument to prevent parameter injection
        cleaned_folder = folder.strip()
        if DISALLOWED_EXPLORER_PATH_RE.search(cleaned_folder):
            logger.warning("Rejected unsafe folder parameter for Explorer: '%s'", folder)
            cleaned_folder = "shell:MyComputerFolder"

        cmd = ["explorer.exe", cleaned_folder]
        try:
            if self._explorer_launcher:
                self._explorer_launcher(cmd)
            else:
                subprocess.Popen(cmd, shell=False)
            logger.info("Launched Windows Explorer with target '%s'.", cleaned_folder)
            return True
        except Exception as exc:
            logger.error("Failed to launch Windows Explorer: %s", exc)
            return False

    @staticmethod
    def sanitize_youtube_query(raw_query: str) -> str:
        """
        Sanitize user spoken query against command injection and control characters (SEC-004).
        Strips conversational prefixes ('hey', 'hey nova', 'please'), command openers ('play on youtube',
        'search on youtube', 'open youtube'), speech [unk] artifact tokens, and trailing 'on youtube' clauses.
        """
        if not raw_query:
            return ""

        # Remove [unk] or <unk> speech recognition artifact tokens
        clean = re.sub(r'\[\s*unk\s*\]|<\s*unk\s*>', ' ', raw_query, flags=re.IGNORECASE)

        # Remove control chars and shell metacharacters (SEC-004)
        clean = DISALLOWED_SHELL_CHARS_RE.sub(" ", clean)

        # Strip surrounding quotes and whitespace
        clean = clean.strip().strip("'\"")

        # Strip conversational prefixes: "hey nova", "wake up nova", "hey", "nova", "please", "can you"
        clean = re.sub(r'^(?:hey\s+nova|wake\s+up\s+nova|hey|nova|please|can\s+you)\s+', '', clean, flags=re.IGNORECASE)

        # Strip command triggers: "play on youtube", "search on youtube", "open youtube", "on youtube", "search youtube", "youtube", "play", "search"
        clean = re.sub(
            r'^(?:play\s+on\s+you\s*tube|search\s+on\s+you\s*tube|open\s+you\s*tube|on\s+you\s*tube|search\s+you\s*tube|you\s*tube|play|search)(?:\s+|$)',
            '',
            clean,
            flags=re.IGNORECASE,
        )

        # Strip leading "for "
        clean = re.sub(r'^for\s+', '', clean, flags=re.IGNORECASE)

        # Strip trailing "on youtube", "in youtube", "on you tube", "youtube"
        clean = re.sub(r'(?:\s+|^)(?:on|in)?\s*you\s*tube$', '', clean, flags=re.IGNORECASE)

        # Strip any leftover [unk] tokens
        clean = re.sub(r'\[\s*unk\s*\]|<\s*unk\s*>', ' ', clean, flags=re.IGNORECASE)

        # Collapse repeated whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def play_youtube(self, query: str = "") -> bool:
        """
        Open YouTube search results for sanitized query string (FR-020, SEC-004).
        If query is empty, opens YouTube homepage.
        """
        clean_query = self.sanitize_youtube_query(query)

        if clean_query:
            encoded = urllib.parse.quote_plus(clean_query)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
        else:
            target_url = "https://www.youtube.com"

        # Verify target URL conforms strictly to HTTPS youtube.com domain (SEC-004)
        parsed = urllib.parse.urlparse(target_url)
        if parsed.scheme != "https" or parsed.netloc not in ("www.youtube.com", "youtube.com"):
            logger.error("Security violation: Generated invalid YouTube URL '%s'", target_url)
            return False

        try:
            if self._url_opener:
                self._url_opener(target_url)
            else:
                self.launch_browser(target_url)
            logger.info("Dispatched YouTube search for query: '%s' -> %s", clean_query, target_url)
            return True
        except Exception as exc:
            logger.error("Failed to open YouTube URL: %s", exc)
            return False

    def switch_window(self) -> bool:
        """Dispatch Alt+Tab hotkey to switch active foreground application (FR-020)."""
        try:
            self.driver.press_hotkey("alt", "tab")
            logger.info("Executed Alt+Tab window switch.")
            return True
        except Exception as exc:
            logger.error("Failed to execute Alt+Tab window switch: %s", exc)
            return False

    def close_window(self) -> bool:
        """Dispatch Alt+F4 hotkey to close active foreground window (FR-020)."""
        try:
            self.driver.press_hotkey("alt", "f4")
            logger.info("Executed Alt+F4 window close.")
            return True
        except Exception as exc:
            logger.error("Failed to execute Alt+F4 window close: %s", exc)
            return False

    def show_desktop(self) -> bool:
        """Dispatch Win+D hotkey to toggle display of the desktop (FR-020)."""
        try:
            self.driver.press_hotkey("win", "d")
            logger.info("Executed Win+D show desktop.")
            return True
        except Exception as exc:
            logger.error("Failed to execute Win+D show desktop: %s", exc)
            return False
