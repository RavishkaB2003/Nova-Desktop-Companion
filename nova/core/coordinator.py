"""
Project NOVA - Semantic UI Navigation Coordinator
Orchestrates speech tokens, UI Automation crawler, high-contrast HUD overlay,
and Win32 mouse input driver with the central state machine.
"""

import logging
import threading
from typing import Dict, List, Optional

from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.core.enums import SystemState
from nova.core.state_machine import StateMachine
from nova.input.driver import InputDriver
from nova.ui.hud_overlay import HudOverlay

logger = logging.getLogger(__name__)

SPOKEN_DIGIT_MAP: Dict[str, int] = {
    "1": 1, "one": 1,
    "2": 2, "two": 2,
    "3": 3, "three": 3,
    "4": 4, "four": 4,
    "5": 5, "five": 5,
    "6": 6, "six": 6,
    "7": 7, "seven": 7,
    "8": 8, "eight": 8,
    "9": 9, "nine": 9,
}


class TagSnapCoordinator:
    """
    Subsystem coordinator managing the 'Tag & Snap' workflow (MOD-002).
    """

    def __init__(
        self,
        state_machine: StateMachine,
        crawler: UIAutomationCrawler,
        hud: HudOverlay,
        driver: InputDriver,
        reduced_motion: bool = False,
    ) -> None:
        self.state_machine = state_machine
        self.crawler = crawler
        self.hud = hud
        self.driver = driver
        self.reduced_motion = reduced_motion

        self._lock = threading.RLock()
        self._current_pages: List[List[UIElementTarget]] = []
        self._current_page_idx: int = 0

    @property
    def current_page_index(self) -> int:
        with self._lock:
            return self._current_page_idx

    @property
    def total_pages(self) -> int:
        with self._lock:
            return len(self._current_pages)

    def handle_speech_phrase(self, phrase: str) -> bool:
        """
        Processes recognized speech utterances related to target snapping and navigation.
        Returns True if the utterance was handled by the coordinator.
        """
        phrase = phrase.strip().lower()
        logger.debug("Coordinator evaluating phrase: '%s'", phrase)

        with self._lock:
            # 1. Tag / Scan Command (FR-006)
            if phrase in ("tag", "scan"):
                return self.trigger_tag_scan()

            # 2. Pagination Navigation (FR-007)
            if phrase in ("next", "more"):
                return self.page_next()
            if phrase in ("back", "previous"):
                return self.page_previous()

            # 3. Action Modifiers (FR-012)
            if phrase == "double":
                self.driver.arm_modifier("double")
                return True
            if phrase == "right":
                self.driver.arm_modifier("right")
                return True

            # 4. Direct In-Place Click (FR-010)
            if phrase == "click":
                return self.trigger_direct_click()

            # 5. Emergency Dismissal / Halt (FR-021)
            if phrase in ("halt", "cancel", "dismiss", "close"):
                self.dismiss_hud()
                return True

            # 6. Single-Digit Badge Selection (FR-007, FR-009, FR-011)
            for token in phrase.split():
                if token in SPOKEN_DIGIT_MAP:
                    digit = SPOKEN_DIGIT_MAP[token]
                    return self.select_target_badge(digit)

        return False

    def trigger_tag_scan(self) -> bool:
        """Query foreground window UI controls and project HUD overlay badges."""
        with self._lock:
            current_state = self.state_machine.current_state
            if current_state == SystemState.STANDBY:
                logger.debug("Cannot trigger tag scan while in STANDBY state.")
                return False

            pages = self.crawler.query_foreground_elements()
            if not pages:
                logger.info("No interactive accessible controls found in foreground window.")
                return False

            self._current_pages = pages
            self._current_page_idx = 0

            # Transition state machine to TRACKING
            self.state_machine.transition_to(SystemState.TRACKING)

            # Show HUD badges for Page 0
            page_targets = self._current_pages[0]
            self.hud.show_targets(page_targets, 0, len(self._current_pages))
            return True

    def page_next(self) -> bool:
        """Advance to the next page of badges (FR-007)."""
        with self._lock:
            if not self._current_pages or self._current_page_idx >= len(self._current_pages) - 1:
                return False

            self._current_page_idx += 1
            self.driver.disarm_modifier()  # FR-007: Pagination resets pending modifiers
            page_targets = self._current_pages[self._current_page_idx]
            self.hud.show_targets(page_targets, self._current_page_idx, len(self._current_pages))
            return True

    def page_previous(self) -> bool:
        """Return to the previous page of badges (FR-007)."""
        with self._lock:
            if not self._current_pages or self._current_page_idx <= 0:
                return False

            self._current_page_idx -= 1
            self.driver.disarm_modifier()  # FR-007: Pagination resets pending modifiers
            page_targets = self._current_pages[self._current_page_idx]
            self.hud.show_targets(page_targets, self._current_page_idx, len(self._current_pages))
            return True

    def select_target_badge(self, digit: int) -> bool:
        """
        Execute target selection:
        1. Lock badge visual highlight
        2. Pre-click target re-validation (FR-011)
        3. 78ms non-blocking cursor glide (FR-009)
        4. SendInput click dispatch with active modifier
        5. Dismiss HUD and restore IDLE_ACTIVE state
        """
        with self._lock:
            if not self._current_pages or not self.hud.is_visible:
                return False

            active_page = self._current_pages[self._current_page_idx]
            target: Optional[UIElementTarget] = None
            for t in active_page:
                if t.target_id == digit:
                    target = t
                    break

            if not target:
                logger.warning("No target found for badge digit %d on current page.", digit)
                return False

            # Lock visual badge highlight (amber)
            self.hud.highlight_target(digit)

            # Pre-click target re-validation (FR-011)
            is_valid = self.crawler.revalidate_target(target, tolerance_px=5)
            if not is_valid:
                logger.warning(
                    "Action aborted: Target %d failed pre-click re-validation (moved or window changed).",
                    digit,
                )
                self.dismiss_hud()
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                return False

            # Transition state machine to EXECUTING
            self.state_machine.transition_to(SystemState.EXECUTING)

            # Determine click action from active modifier (FR-012)
            modifier = self.driver.get_active_modifier()
            button = "right" if modifier == "right" else "left"
            click_count = 2 if modifier == "double" else 1

            # Execute 78ms non-blocking cursor glide to target centroid (FR-009)
            self.driver.glide_to(
                target.centroid_x,
                target.centroid_y,
                steps=5,
                reduced_motion=self.reduced_motion,
            )

            # Dispatch click
            self.driver.click(button=button, click_count=click_count)

            # Dismiss HUD and return to IDLE_ACTIVE
            self.dismiss_hud()
            self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
            return True

    def trigger_direct_click(self) -> bool:
        """Direct in-place click at current cursor position (FR-010)."""
        with self._lock:
            self.state_machine.transition_to(SystemState.EXECUTING)
            modifier = self.driver.get_active_modifier()
            button = "right" if modifier == "right" else "left"
            click_count = 2 if modifier == "double" else 1

            self.driver.click(button=button, click_count=click_count)
            self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
            return True

    def dismiss_hud(self) -> None:
        """Dismiss HUD overlay and clean up target state."""
        with self._lock:
            self.hud.hide()
            self.driver.disarm_modifier()
            self._current_pages = []
            self._current_page_idx = 0
            if self.state_machine.current_state == SystemState.TRACKING:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
