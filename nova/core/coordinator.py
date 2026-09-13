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
        self._selected_target: Optional[UIElementTarget] = None

    @property
    def current_page_index(self) -> int:
        with self._lock:
            return self._current_page_idx

    @property
    def total_pages(self) -> int:
        with self._lock:
            return len(self._current_pages)

    @property
    def selected_target(self) -> Optional[UIElementTarget]:
        with self._lock:
            return self._selected_target

    def handle_speech_phrase(self, phrase: str) -> bool:
        """
        Processes recognized speech utterances related to target snapping and navigation.
        Returns True if the utterance was handled by the coordinator.
        """
        phrase = phrase.strip().lower()
        logger.debug("Coordinator evaluating phrase: '%s'", phrase)

        with self._lock:
            tokens = phrase.split()
            if not tokens:
                return False

            # 1. Dismissal / Close (FR-021)
            if any(t in ("halt", "cancel", "dismiss", "close", "done") for t in tokens):
                self.dismiss_hud()
                return True

            # 2. Tag / Scan Command (FR-006)
            if any(t in ("tag", "scan") for t in tokens):
                return self.trigger_tag_scan()

            # 3. Pagination Navigation (FR-007)
            if any(t in ("next", "more") for t in tokens):
                return self.page_next()
            if any(t in ("back", "previous") for t in tokens):
                return self.page_previous()

            # 4. Action Modifiers (FR-012)
            has_double = "double" in tokens
            has_right = "right" in tokens
            if has_double:
                self.driver.arm_modifier("double")
            elif has_right:
                self.driver.arm_modifier("right")

            # 5. Extract digit if present
            digit = None
            for token in tokens:
                if token in SPOKEN_DIGIT_MAP:
                    digit = SPOKEN_DIGIT_MAP[token]
                    break

            # 6. Compound Shortcut: "click <digit>" or "<modifier> click <digit>" (Instant Snap & Click)
            if "click" in tokens and digit is not None:
                if self.hud.is_visible:
                    if self.aim_at_target_badge(digit):
                        return self.execute_target_click()
                    return False

            # 7. Direct Click or Confirmation Click on Aimed Target
            if "click" in tokens:
                if self.hud.is_visible and self._selected_target is not None:
                    return self.execute_target_click()
                return self.trigger_direct_click()

            # If only modifier was spoken without digit or click
            if (has_double or has_right) and digit is None:
                return True

            # 8. Single-Digit Aiming (Option 1: Aim then Click)
            if digit is not None and self.hud.is_visible:
                return self.aim_at_target_badge(digit)

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
            self._selected_target = None

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
            self._selected_target = None
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
            self._selected_target = None
            self.driver.disarm_modifier()  # FR-007: Pagination resets pending modifiers
            page_targets = self._current_pages[self._current_page_idx]
            self.hud.show_targets(page_targets, self._current_page_idx, len(self._current_pages))
            return True

    def aim_at_target_badge(self, digit: int) -> bool:
        """
        Two-step Flow Step 1 (Aim):
        1. Locate target on current page
        2. Lock badge visual highlight (amber)
        3. Pre-glide target re-validation (FR-011)
        4. 78ms non-blocking cursor glide to target centroid (FR-009)
        5. Store _selected_target; HUD remains active for confirmation or re-aiming
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

            # Pre-glide target re-validation (FR-011)
            is_valid = self.crawler.revalidate_target(target, tolerance_px=5)
            if not is_valid:
                logger.warning(
                    "Action aborted: Target %d failed pre-aim re-validation (moved or window changed).",
                    digit,
                )
                self.dismiss_hud()
                return False

            # Lock visual badge highlight (amber)
            self.hud.highlight_target(digit)

            # Glide cursor to target centroid
            self.driver.glide_to(
                target.centroid_x,
                target.centroid_y,
                steps=5,
                reduced_motion=self.reduced_motion,
            )

            self._selected_target = target
            logger.info("Aimed cursor at Target %d (%d, %d). Badges active.", digit, target.centroid_x, target.centroid_y)
            return True

    def select_target_badge(self, digit: int) -> bool:
        """Compatibility helper: aims at target badge (Option 1)."""
        return self.aim_at_target_badge(digit)

    def execute_target_click(self) -> bool:
        """
        Two-step Flow Step 2 (Fire):
        1. Validate selected target
        2. Transition state machine to EXECUTING
        3. Dispatch mouse click with active modifier (left/right/double)
        4. Re-validate and transition state back to TRACKING (HUD stays visible for sequential clicks!)
        """
        with self._lock:
            if not self._selected_target:
                return self.trigger_direct_click()

            target = self._selected_target
            is_valid = self.crawler.revalidate_target(target, tolerance_px=5)
            if not is_valid:
                logger.warning("Target re-validation failed before click dispatch.")
                self.dismiss_hud()
                return False

            self.state_machine.transition_to(SystemState.EXECUTING)
            modifier = self.driver.get_active_modifier()
            button = "right" if modifier == "right" else "left"
            click_count = 2 if modifier == "double" else 1

            self.driver.click(button=button, click_count=click_count)
            self.driver.disarm_modifier()

            # State returns to TRACKING so badges remain usable!
            self.state_machine.transition_to(SystemState.TRACKING)
            logger.info("Executed %s click (x%d) on Target %d (%d, %d). Tags remain active.", button, click_count, target.target_id, target.centroid_x, target.centroid_y)
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
            self._selected_target = None
            if self.state_machine.current_state in (SystemState.TRACKING, SystemState.EXECUTING):
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
