"""
Project NOVA - Semantic UI Navigation & Impulse Routing Coordinator
Orchestrates speech tokens, UI Automation crawler, high-contrast HUD overlay,
dual-axis crosshair scanner, continuous cursor glider, Win32 mouse driver,
and state-dependent acoustic impulse routing.
"""

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from nova.automation.crawler import UIAutomationCrawler, UIElementTarget
from nova.automation.shortcuts import SystemShortcutManager
from nova.core.enums import SystemEventType, SystemState
from nova.core.glider import ContinuousGlider
from nova.core.state_machine import StateMachine, SystemEvent
from nova.input.driver import InputDriver, get_virtual_desktop_bounds
from nova.input.scroll_controller import ScrollController
from nova.input.text_injector import TextInjector
from nova.speech.dictation_pipeline import DictationPipeline
from nova.ui.crosshair import CrosshairOverlay
from nova.ui.hud_overlay import HudOverlay
from nova.core.safety import ActionArbiter, GlobalHotkeyManager, SafetyCoordinator

logger = logging.getLogger(__name__)


class SpokenFeedback:
    """
    Non-blocking, local Windows SAPI5 spoken confirmation (Item 6).
    Maintains 100% offline-first execution (NFR-004, SEC-001).
    Integrates TM-04 software ducking gate to eliminate acoustic feedback loops.
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._speaking_count = 0

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking_count > 0

    def speak(self, text: str, on_done: Optional[Callable[[], None]] = None) -> None:
        if not self.enabled or not text:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return

        # 1. Synchronously engage speaking counter on caller thread to prevent audio pipeline race
        with self._lock:
            self._speaking_count += 1

        def _run() -> None:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                try:
                    # SVSFDefault = 0: Synchronous speech execution inside this background worker thread.
                    voice.Speak(text, 0)
                except Exception as exc:
                    logger.debug("SAPI5 speak execution error: %s", exc)
                finally:
                    time.sleep(0.2)  # 200ms room reverberation hangover window (TM-04)
                    with self._lock:
                        self._speaking_count = max(0, self._speaking_count - 1)
                    pythoncom.CoUninitialize()
                    if on_done:
                        try:
                            on_done()
                        except Exception as exc:
                            logger.debug("Error in SpokenFeedback on_done callback: %s", exc)
            except Exception as exc:
                logger.debug("SAPI5 worker thread error: %s", exc)
                with self._lock:
                    self._speaking_count = max(0, self._speaking_count - 1)
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

        clean_tag = "".join(c for c in text if c.isalnum())[:10]
        t = threading.Thread(target=_run, name=f"SAPI-{clean_tag}", daemon=True)
        t.start()


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
DEFAULT_NUDGE_STEP_PX = 65
MICRO_NUDGE_STEP_PX = 18
JUMP_NUDGE_STEP_PX = 160
MOMENTUM_EXPIRY_SECONDS = 1.2


class TagSnapCoordinator:
    """
    Subsystem coordinator managing 'Tag & Snap' (MOD-002) and
    'Acoustic Impulse Routing & Continuous Gliding' (MOD-003).
    """

    def __init__(
        self,
        state_machine: StateMachine,
        crawler: UIAutomationCrawler,
        hud: HudOverlay,
        driver: Optional[InputDriver] = None,
        crosshair: Optional[CrosshairOverlay] = None,
        glider: Optional[ContinuousGlider] = None,
        scroller: Optional[ScrollController] = None,
        text_injector: Optional[TextInjector] = None,
        dictation_pipeline: Optional[DictationPipeline] = None,
        shortcuts: Optional[SystemShortcutManager] = None,
        speech_feedback: Optional[SpokenFeedback] = None,
        safety_coordinator: Optional[SafetyCoordinator] = None,
        control_panel: Optional[object] = None,
        reduced_motion: bool = False,
        on_activate: Optional[Callable[[], None]] = None,
        on_deactivate: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state_machine = state_machine
        self.crawler = crawler
        self.hud = hud
        self.driver = driver or InputDriver()
        self.reduced_motion = reduced_motion
        self.shortcuts = shortcuts or SystemShortcutManager(driver=self.driver)
        self.on_activate_callback = on_activate
        self.on_deactivate_callback = on_deactivate


        self._lock = threading.RLock()
        self._current_pages: List[List[UIElementTarget]] = []
        self._current_page_idx: int = 0
        self._selected_target: Optional[UIElementTarget] = None
        self._action_generation: int = self.state_machine.current_generation
        self._dictation_action_generation: int = self.state_machine.current_generation
        self.speech_feedback = speech_feedback or SpokenFeedback(enabled=not getattr(self.driver, "headless", False))

        # Safety & Emergency Override Subsystem (MOD-006: FR-021, FR-022, FR-023, SEC-005)
        self.safety_coordinator = safety_coordinator or SafetyCoordinator(
            arbiter=getattr(self.state_machine, "arbiter", None),
            state_machine=self.state_machine,
            on_halt_feedback=self._on_safety_halt_feedback,
            headless=getattr(self.driver, "headless", False),
        )
        self.hotkey_manager = self.safety_coordinator.hotkey_manager

        # Kinetic Momentum Tracking for Voice Nudging
        self._last_nudge_dir: Optional[str] = None
        self._last_nudge_time: float = 0.0
        self._nudge_multiplier: float = 1.0

        # Crosshair Overlay (FR-018)
        hud_root = getattr(hud, "root", getattr(hud, "_root", None)) if hud else None
        self.crosshair = crosshair or CrosshairOverlay(
            root=hud_root,
            driver=self.driver,
            on_hit_complete=self._on_crosshair_hit_complete,
            snap_resolver=self._resolve_magnetic_snap,
        )
        if crosshair and getattr(crosshair, "snap_resolver", None) is None:
            self.crosshair.snap_resolver = self._resolve_magnetic_snap

        # Continuous Glider (FR-016, FR-017)
        self.glider = glider or ContinuousGlider(
            driver=self.driver,
            root=hud_root,
            on_halt=self._on_glider_boundary_halt,
        )
        if glider and getattr(glider, "on_halt", None) is None:
            self.glider.on_halt = self._on_glider_boundary_halt

        # Fluid Mouse Wheel Scroller (FR-019)
        self.scroller = scroller or ScrollController(root=hud_root, driver=self.driver)

        # Free-Text Dictation & Keyboard Injector (FR-020)
        self.text_injector = text_injector or TextInjector(driver=self.driver, state_machine=self.state_machine)
        self.dictation_pipeline = dictation_pipeline
        if self.dictation_pipeline:
            self._wire_dictation_pipeline()

        # Control Panel & Command Cheat Sheet Window
        self.control_panel = control_panel
        if self.control_panel is None and hud_root:
            try:
                from nova.ui.control_panel import ControlPanel
                self.control_panel = ControlPanel(
                    root=hud_root,
                    on_feedback_toggle=lambda enabled: setattr(self.speech_feedback, "enabled", enabled),
                )
            except Exception as exc:
                logger.debug("ControlPanel initialization skipped: %s", exc)

        # Register Subsystem Invalidation & Cancellation Hooks with Safety Arbiter (FR-022)
        self.safety_coordinator.register_cancellation_hook(lambda: self.dismiss_hud(bump_gen=False))
        self.safety_coordinator.register_cancellation_hook(lambda: self.crosshair.hide() if self.crosshair.is_visible else None)
        self.safety_coordinator.register_cancellation_hook(lambda: self.glider.stop_glide() if self.glider.is_gliding else None)
        self.safety_coordinator.register_cancellation_hook(lambda: self.scroller.stop_scroll() if self.scroller.is_scrolling else None)
        self.safety_coordinator.register_cancellation_hook(
            lambda: self.dictation_pipeline.stop_dictation(commit_pending=False)
            if (self.dictation_pipeline and self.dictation_pipeline.is_active)
            else None
        )
        self.safety_coordinator.register_cancellation_hook(
            lambda: self.control_panel.hide() if (getattr(self, "control_panel", None) and self.control_panel.is_visible) else None
        )
        self._pending_youtube_query = False
        self.safety_coordinator.register_cancellation_hook(
            lambda: setattr(self, "_pending_youtube_query", False)
        )

    def _on_safety_halt_feedback(self, source: str) -> None:
        """Provide spoken feedback upon vocal or physical emergency stops."""
        if source in ("VOCAL_HALT", "DICTATION_EMERGENCY_SPOTTER") or source.startswith("HOTKEY"):
            self.speech_feedback.speak("Halted")

    def start(self) -> None:
        """Start coordinator background safety handlers and global hotkeys."""
        self.safety_coordinator.start()

    def stop(self) -> None:
        """Stop coordinator and release global physical hotkeys (SEC-005)."""
        self.safety_coordinator.stop()

    def handle_activate(self) -> None:
        """Handle activate command: show mascot in STANDBY, requiring subsequent wake up."""
        logger.info("Handling system activate request.")
        if callable(getattr(self, "on_activate_callback", None)):
            try:
                self.on_activate_callback()
            except Exception as exc:
                logger.error("Error in on_activate_callback: %s", exc)

    def handle_deactivate(self) -> None:
        """Handle deactivate command: auto-sleep if active, close UI, hide mascot to background."""
        logger.info("Handling system deactivate request.")
        if getattr(self, "control_panel", None) and self.control_panel.is_visible:
            self.control_panel.hide()
        if self.hud.is_visible:
            self.dismiss_hud()
        if self.crosshair.is_visible:
            self.crosshair.hide()
        if self.glider.is_gliding:
            self.glider.stop_glide()
        if self.scroller.is_scrolling:
            self.scroller.stop_scroll()
        if self.dictation_pipeline and self.dictation_pipeline.is_active:
            self.dictation_pipeline.stop_dictation(commit_pending=False)

        current_state = self.state_machine.current_state
        if current_state != SystemState.STANDBY:
            self.state_machine.handle_event(
                SystemEvent(event_type=SystemEventType.DEACTIVATE_TRIGGERED)
            )

        if callable(getattr(self, "on_deactivate_callback", None)):
            try:
                self.on_deactivate_callback()
            except Exception as exc:
                logger.error("Error in on_deactivate_callback: %s", exc)


    def _on_glider_boundary_halt(self) -> None:
        """Invoked when continuous glider automatically halts at screen boundary."""
        with self._lock:
            if self.state_machine.current_state == SystemState.GLIDE_ACTIVE:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                logger.info("Transitioned state from GLIDE_ACTIVE to IDLE_ACTIVE on screen boundary halt.")

    def _wire_dictation_pipeline(self) -> None:
        """Wire callbacks between DictationPipeline, TextInjector, and StateMachine."""
        if not self.dictation_pipeline:
            return

        def _on_text(text: str) -> None:
            if getattr(self, "_pending_youtube_query", False):
                self._pending_youtube_query = False
                clean_query = self.shortcuts.sanitize_youtube_query(text)
                logger.info("Captured two-phase YouTube query via dictation: '%s'", clean_query)
                self.shortcuts.play_youtube(clean_query)
                if clean_query:
                    self.speech_feedback.speak(f"Searching YouTube for {clean_query}")
                else:
                    self.speech_feedback.speak("Opening YouTube")
                if self.dictation_pipeline and self.dictation_pipeline.is_active:
                    self.dictation_pipeline.stop_dictation(commit_pending=False)
                return

            self.text_injector.inject_text(text, action_generation=self._dictation_action_generation)

        def _on_complete() -> None:
            if getattr(self, "_pending_youtube_query", False):
                self._pending_youtube_query = False
                logger.info("Two-phase YouTube query timed out; opening YouTube homepage.")
                self.shortcuts.play_youtube("")
                self.speech_feedback.speak("Opening YouTube")
            if self.state_machine.current_state == SystemState.DICTATING:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

        def _on_halt() -> None:
            self.safety_coordinator.trigger_emergency_halt(source="DICTATION_EMERGENCY_SPOTTER", reset_to_standby=False)
            if self.state_machine.current_state == SystemState.DICTATING:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

        def _on_click() -> None:
            if self.state_machine.current_state == SystemState.DICTATING:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
            self.trigger_direct_click()

        self.dictation_pipeline.on_text_ready = _on_text
        self.dictation_pipeline.on_dictation_complete = _on_complete
        self.dictation_pipeline.on_emergency_halt = _on_halt
        self.dictation_pipeline.on_click_command = _on_click

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

    def _resolve_magnetic_snap(self, x: int, y: int, max_radius: int = 65) -> Optional[Tuple[int, int]]:
        """
        Resolves nearest actionable CTA centroid to laser intersection (x, y)
        within max_radius for Magnetic CTA Snapping.
        """
        with self._lock:
            target = self.crawler.find_nearest_target(x, y, max_radius=max_radius)
            if target is not None:
                return (target.centroid_x, target.centroid_y)
            return None

    def nudge_cursor(self, direction: str, magnitude_px: Optional[int] = None) -> bool:
        """
        Discrete voice directional nudging in IDLE_ACTIVE with kinetic momentum acceleration.
        Moves the physical mouse cursor along direction ('up', 'down', 'left', 'right').
        If magnitude_px is not specified, applies kinetic momentum stacking:
        1st step: 65px (1.0x), 2nd step: 130px (2.0x), 3rd+ step: 230px (3.5x).
        Pausing for >1.2s resets back to 1.0x baseline.
        Clamps coordinates to virtual desktop boundaries.
        """
        with self._lock:
            now = time.time()
            cur_x, cur_y = self.driver.get_cursor_pos()
            vx, vy, v_max_x, v_max_y = get_virtual_desktop_bounds()

            if magnitude_px is None:
                # Kinetic momentum stacking on repeated commands in same direction within 1.2s
                if direction == self._last_nudge_dir and (now - self._last_nudge_time) < MOMENTUM_EXPIRY_SECONDS:
                    self._nudge_multiplier = min(3.5, self._nudge_multiplier + 1.0)
                else:
                    self._nudge_multiplier = 1.0
                dist = int(round(DEFAULT_NUDGE_STEP_PX * self._nudge_multiplier))
            else:
                dist = magnitude_px
                self._nudge_multiplier = 1.0

            self._last_nudge_dir = direction
            self._last_nudge_time = now

            dx, dy = 0, 0
            if direction == "up":
                dy = -dist
            elif direction == "down":
                dy = dist
            elif direction == "left":
                dx = -dist
            elif direction == "right":
                dx = dist
            else:
                return False

            new_x = max(vx, min(v_max_x - 1, cur_x + dx))
            new_y = max(vy, min(v_max_y - 1, cur_y + dy))

            self.driver.set_cursor_pos(new_x, new_y)
            logger.info(
                "Voice Nudge: Moved cursor %s by %d px to (%d, %d) (momentum: %.1fx).",
                direction,
                dist,
                new_x,
                new_y,
                self._nudge_multiplier,
            )
            return True

    def _on_crosshair_hit_complete(self, x: int, y: int) -> None:
        """Callback when crosshair finishes phase 2 click."""
        with self._lock:
            if self.state_machine.current_state == SystemState.CROSSHAIR_ACTIVE:
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

    def handle_impulse(self) -> bool:
        """
        State-dependent non-verbal impulse routing (FR-015, FR-11b):
        - STANDBY: Suppressed (ignored).
        - DICTATING: Suppressed (ignored).
        - IDLE_ACTIVE: Instant Left Mouse Click at current cursor.
        - TRACKING: If target aimed, fires target click; otherwise direct in-place click.
        - GLIDE_ACTIVE: Atomic HALT_GLIDE_AND_CLICK, transitions to IDLE_ACTIVE.
        - CROSSHAIR_ACTIVE:
            Phase 1: Locks Y coordinate, initiates vertical sweep. Suppresses OS click.
            Phase 2: Locks X coordinate, snaps to (X, Y), executes Left Click, transitions to IDLE_ACTIVE.
        """
        with self._lock:
            if self.speech_feedback.is_speaking:
                logger.debug("Impulse suppressed: TTS speech feedback active (plosive gate).")
                return False

            current_state = self.state_machine.current_state
            logger.debug("Coordinator handling impulse in state: %s", current_state)

            # 0. Active Continuous Scroll: Halt on Mouth Click (FR-019 / FR-015)
            if self.scroller.is_scrolling:
                self.scroller.stop_scroll()
                return True

            # 1. STANDBY: Suppressed
            if current_state == SystemState.STANDBY:
                logger.debug("Impulse ignored: system in STANDBY.")
                return False

            # 2. DICTATING: Suppressed (prevent mouth sounds from clicking fields)
            if current_state == SystemState.DICTATING:
                logger.debug("Impulse ignored: system in DICTATING.")
                return False

            # 3. IDLE_ACTIVE: Suppressed (user requested removal of accidental in-place mouth clicks)
            if current_state == SystemState.IDLE_ACTIVE:
                logger.debug("Impulse ignored in IDLE_ACTIVE: in-place click disarmed.")
                return False

            # 4. TRACKING: Execute click only on explicitly aimed/selected target (suppress blind click)
            if current_state == SystemState.TRACKING:
                if self.hud.is_visible and self._selected_target is not None:
                    return self.execute_target_click()
                logger.debug("Impulse ignored in TRACKING: no target selected.")
                return False

            # 5. GLIDE_ACTIVE: Clean halt without mouse click (user requested removal of halt-and-click)
            if current_state == SystemState.GLIDE_ACTIVE:
                self.glider.stop_glide()
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                logger.info("Continuous glider halted via mouth click (click suppressed).")
                return True

            # 6. CROSSHAIR_ACTIVE: Multi-Phase Scanner Intercept
            if current_state == SystemState.CROSSHAIR_ACTIVE:
                if self.crosshair.phase == 1:
                    self.crosshair.lock_y()
                    return True
                elif self.crosshair.phase == 2:
                    self.crosshair.hit_and_click()
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return True

            return False

    def handle_speech_phrase(self, phrase: str) -> bool:
        """
        Processes recognized speech utterances related to target snapping,
        crosshairs, continuous gliding, and directional steering.
        Returns True if the utterance was handled by the coordinator.
        """
        phrase = phrase.strip().lower()
        logger.debug("Coordinator evaluating phrase: '%s'", phrase)

        with self._lock:
            tokens = phrase.split()
            if not tokens:
                return False

            current_state = self.state_machine.current_state

            # Two-Phase YouTube Query Pending Handling
            if getattr(self, "_pending_youtube_query", False):
                if any(t in ("halt", "cancel", "stop", "close", "dismiss") for t in tokens):
                    self._pending_youtube_query = False
                    if self.dictation_pipeline and self.dictation_pipeline.is_active:
                        self.dictation_pipeline.stop_dictation(commit_pending=False)
                    self.speech_feedback.speak("Halted")
                    return True
                self._pending_youtube_query = False
                query = self.shortcuts.sanitize_youtube_query(phrase)
                self.shortcuts.play_youtube(query)
                if query:
                    self.speech_feedback.speak(f"Searching YouTube for {query}")
                else:
                    self.speech_feedback.speak("Opening YouTube")
                if self.dictation_pipeline and self.dictation_pipeline.is_active:
                    self.dictation_pipeline.stop_dictation(commit_pending=False)
                return True

            # 0. System Desktop Shortcuts & Window Controls (FR-020, SEC-004)
            # Prioritize "close window" to disambiguate from HUD badge dismissal "close"
            shortcut_executed = False
            if "close window" in phrase or ("close" in tokens and "window" in tokens):
                shortcut_executed = self.shortcuts.close_window()
            elif "switch window" in phrase or ("switch" in tokens and "window" in tokens):
                shortcut_executed = self.shortcuts.switch_window()
            elif "show desktop" in phrase or ("show" in tokens and "desktop" in tokens) or phrase == "desktop":
                shortcut_executed = self.shortcuts.show_desktop()
            elif "open browser" in phrase or phrase == "browser":
                shortcut_executed = self.shortcuts.launch_browser()
                if shortcut_executed:
                    self.speech_feedback.speak("Opening browser")
            elif "open paint" in phrase or phrase == "paint":
                shortcut_executed = self.shortcuts.launch_paint()
                if shortcut_executed:
                    self.speech_feedback.speak("Opening paint")
            elif "open explorer" in phrase or "open this pc" in phrase or phrase in ("explorer", "this pc"):
                shortcut_executed = self.shortcuts.launch_explorer()
                if shortcut_executed:
                    self.speech_feedback.speak("Opening explorer")
            elif "open youtube" in phrase or phrase == "youtube":
                shortcut_executed = self.shortcuts.play_youtube("")
                if shortcut_executed:
                    self.speech_feedback.speak("Opening YouTube")
            elif "play on youtube" in phrase or "search on youtube" in phrase or "on youtube" in phrase or ("play" in tokens and "on youtube" in phrase):
                query = self.shortcuts.sanitize_youtube_query(phrase)
                if query and query != "[unk]":
                    shortcut_executed = self.shortcuts.play_youtube(query)
                    if shortcut_executed:
                        self.speech_feedback.speak(f"Searching YouTube for {query}")
                else:
                    # Two-Phase interaction: Ask user for query and arm unconstrained capture
                    self._pending_youtube_query = True
                    def _arm_query_capture() -> None:
                        if self.dictation_pipeline and not self.dictation_pipeline.is_active:
                            self.dictation_pipeline.start_dictation()
                            self.dictation_pipeline.reset_grace_timer()
                    self.speech_feedback.speak("What would you like to search for?", on_done=_arm_query_capture)
                    shortcut_executed = True

            if shortcut_executed:
                if current_state == SystemState.DICTATING:
                    if self.dictation_pipeline:
                        self.dictation_pipeline.stop_dictation(commit_pending=False)
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                return True

            # Activate & Deactivate Lifecycle Commands
            if phrase == "activate" or "activate" in tokens:
                self.handle_activate()
                return True
            if phrase == "deactivate" or "deactivate" in tokens:
                self.handle_deactivate()
                return True

            # Control Panel / Menu Commands
            if phrase in ("menu", "show menu", "help", "commands"):
                if getattr(self, "control_panel", None):
                    self.control_panel.show()
                    self.speech_feedback.speak("Menu")
                    return True
            if phrase in ("close menu", "hide menu"):
                if getattr(self, "control_panel", None) and self.control_panel.is_visible:
                    self.control_panel.hide()
                    return True

            # 1. Two-Phase Voice Dictation In-Flight Commands (FR-020)
            # Evaluated BEFORE generic dismissal to ensure "done", "stop", "cancel" inside dictation
            # are routed to dictation pipeline rather than triggering emergency halt.
            if current_state == SystemState.DICTATING:
                if any(t in ("stop", "done", "cancel", "exit") for t in tokens):
                    if self.dictation_pipeline:
                        self.dictation_pipeline.stop_dictation(commit_pending=False)
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    if "done" in tokens:
                        self.speech_feedback.speak("Done")
                    return True
                if any(t in ("click", "left click") for t in tokens) or phrase == "click":
                    if self.dictation_pipeline:
                        self.dictation_pipeline.stop_dictation(commit_pending=True)
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return self.trigger_direct_click()
                if "enter" in tokens:
                    if self.dictation_pipeline:
                        self.dictation_pipeline.stop_dictation(commit_pending=True)
                    self.text_injector.press_key("enter")
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return True
                if any(t in ("backspace", "delete") for t in tokens) or "back space" in phrase:
                    self.text_injector.press_key("backspace")
                    return True
                if "youtube" in tokens and any(t in ("play", "open", "search") for t in tokens):
                    if self.dictation_pipeline:
                        self.dictation_pipeline.stop_dictation(commit_pending=False)
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    query = self.shortcuts.sanitize_youtube_query(phrase)
                    return self.shortcuts.play_youtube(query)

            # 2. Dismissal / Close / Emergency (FR-021, FR-022)
            dismissal_words = ("halt", "cancel", "dismiss", "close", "closed", "done", "clear", "exit", "hide")
            if any(t in dismissal_words for t in tokens) or any(k in phrase for k in ("close tag", "close tags", "hide tag", "hide tags", "clear tag", "clear tags")):
                if getattr(self, "control_panel", None) and self.control_panel.is_visible:
                    self.control_panel.hide()
                is_emergency = any(t in ("halt", "cancel") for t in tokens)
                self.safety_coordinator.trigger_emergency_halt(
                    source="VOCAL_HALT" if is_emergency else "VOCAL_DISMISS",
                    reset_to_standby=False,
                )
                if current_state in (SystemState.GLIDE_ACTIVE, SystemState.CROSSHAIR_ACTIVE, SystemState.DICTATING):
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                return True

            # 3. Fluid Mouse Wheel Scrolling (FR-019)
            if self.scroller.is_scrolling:
                if any(t in ("stop", "halt") for t in tokens):
                    self.scroller.stop_scroll()
                    return True
                # Only steer scroller if not in crosshair or glide mode
                if current_state not in (SystemState.CROSSHAIR_ACTIVE, SystemState.GLIDE_ACTIVE):
                    if "up" in tokens or "scroll up" in phrase:
                        self.scroller.set_direction("up")
                        return True
                    if "down" in tokens or "scroll down" in phrase:
                        self.scroller.set_direction("down")
                        return True
                    if any(t in ("faster", "fast") for t in tokens):
                        self.scroller.modulate_speed(1.5)
                        return True
                    if any(t in ("slower", "slow") for t in tokens):
                        self.scroller.modulate_speed(0.65)
                        return True
            else:
                if "scroll down" in phrase or phrase == "scroll":
                    self.scroller.start_scroll(direction="down")
                    return True
                if "scroll up" in phrase:
                    self.scroller.start_scroll(direction="up")
                    return True

            # 4. Dictation Mode Entry (FR-020)
            if any(t in ("type", "dictate") for t in tokens):
                if current_state in (SystemState.IDLE_ACTIVE, SystemState.TRACKING):
                    if self.hud.is_visible:
                        self.dismiss_hud()
                    self._dictation_action_generation = self.state_machine.current_generation
                    self.state_machine.transition_to(SystemState.DICTATING)
                    if self.dictation_pipeline:
                        self.dictation_pipeline.start_dictation()
                    self.speech_feedback.speak(
                        "Dictate",
                        on_done=lambda: self.dictation_pipeline.reset_grace_timer() if self.dictation_pipeline else None,
                    )
                    return True


            # 4. Directional Steering (FR-017, FR-13):
            # Only in GLIDE_ACTIVE or CROSSHAIR_ACTIVE
            if current_state in (SystemState.GLIDE_ACTIVE, SystemState.CROSSHAIR_ACTIVE):
                dir_cmd = None
                for token in tokens:
                    if token in ("left", "right", "up", "down"):
                        dir_cmd = token
                        break
                if not dir_cmd:
                    for d in ("go left", "go right", "go up", "go down"):
                        if d in phrase:
                            dir_cmd = d.replace("go ", "")
                            break

                if dir_cmd:
                    if current_state == SystemState.GLIDE_ACTIVE:
                        self.glider.set_heading_direction(dir_cmd)
                        self.glider.start_glide(autonomous=True)
                        return True
                    elif current_state == SystemState.CROSSHAIR_ACTIVE:
                        if self.crosshair.set_sweep_direction(dir_cmd):
                            return True

            # 3. Crosshair Mode Controls (FR-018)
            if current_state == SystemState.CROSSHAIR_ACTIVE:
                # Spoken speed adjustments
                for token in tokens:
                    if token == "slow":
                        self.crosshair.set_sweep_speed(100.0)
                        return True
                    elif token == "fast":
                        self.crosshair.set_sweep_speed(320.0)
                        return True
                    elif token == "normal":
                        self.crosshair.set_sweep_speed(180.0)
                        return True

                # Any confirmation word in Phase 1 locks Y
                if self.crosshair.phase == 1 and any(t in ("lock", "freeze", "stop", "click", "hit", "mark") for t in tokens):
                    self.crosshair.lock_y()
                    return True
                # Any confirmation word in Phase 2 snaps and clicks
                if self.crosshair.phase == 2 and any(t in ("hit", "click", "mark", "lock", "freeze", "stop") for t in tokens):
                    self.crosshair.hit_and_click()
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return True

            # 4. Glider Mode Controls (FR-016)
            if current_state == SystemState.GLIDE_ACTIVE:
                if any(t in ("stop", "halt") for t in tokens):
                    self.glider.stop_glide()
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return True
                if any(t in ("hit", "click", "mark", "lock") for t in tokens):
                    self.glider.halt_and_click(button="left")
                    self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
                    return True
                # Suppress other vocalizations in GLIDE_ACTIVE to protect sustained vowel hums from triggering tags
                logger.debug("Utterance '%s' suppressed in GLIDE_ACTIVE to preserve continuous glide.", phrase)
                return True

            # 5. Crosshair Trigger Command (FR-018)
            if "cross hair" in phrase or any(t in ("crosshair", "scanner", "laser") for t in tokens):
                return self.trigger_crosshair_scan()

            # 6. Glider / Canvas Mode Trigger (FR-016)
            if any(t in ("glide", "canvas", "draw", "move") for t in tokens):
                direction = None
                for d in ("left", "right", "up", "down"):
                    if d in tokens:
                        direction = d
                        break
                return self.trigger_glide_mode(direction=direction)

            # 7. Tag / Scan Command (FR-006)
            if any(t in ("tag", "scan") for t in tokens):
                return self.trigger_tag_scan()

            # 8. Pagination Navigation (FR-007)
            if any(t in ("next", "more") for t in tokens):
                return self.page_next()
            if any(t in ("back", "previous") for t in tokens):
                return self.page_previous()

            # 9. Voice Directional Nudging in IDLE_ACTIVE (Kinetic Momentum & Chained Multipliers)
            if current_state == SystemState.IDLE_ACTIVE:
                if phrase == "enter":
                    self.text_injector.press_key("enter")
                    return True
                if phrase in ("backspace", "delete", "back space"):
                    self.text_injector.press_key("backspace")
                    return True

                # Disambiguate spoken click commands from directional nudges
                is_click_action = any(c in phrase for c in ("click", "double", "triple", "middle"))
                dirs = [t for t in tokens if t in ("up", "down", "left", "right")]
                if dirs and not is_click_action:
                    d = dirs[0]
                    is_nudge = any(t in ("nudge", "step", "move", "tap", "jump", "far", "big", "little", "bit") for t in tokens)
                    # When HUD is visible and no explicit nudge prefix, let bare "right" arm modifier (FR-012)
                    if d == "right" and self.hud.is_visible and not is_nudge:
                        pass
                    else:
                        # Count chained repetitions of the same direction (e.g. "up up up")
                        repeat_count = sum(1 for t in dirs if t == d)

                        if any(t in ("nudge", "tap", "little", "bit") for t in tokens):
                            step_size = MICRO_NUDGE_STEP_PX * repeat_count
                            return self.nudge_cursor(d, magnitude_px=step_size)
                        elif any(t in ("jump", "far", "big") for t in tokens):
                            step_size = JUMP_NUDGE_STEP_PX * repeat_count
                            return self.nudge_cursor(d, magnitude_px=step_size)
                        else:
                            # Standard step: if chained in single phrase (e.g. "up up"), multiply directly;
                            # otherwise pass magnitude_px=None to engage kinetic momentum stacking!
                            if repeat_count > 1:
                                return self.nudge_cursor(d, magnitude_px=DEFAULT_NUDGE_STEP_PX * repeat_count)
                            return self.nudge_cursor(d, magnitude_px=None)

            # 10. Spoken Clicks & Action Modifiers (FR-010, FR-012)
            has_double = "double" in tokens or "double click" in phrase or "double-click" in phrase
            has_right = "right click" in phrase or ("right" in tokens and "click" in tokens) or (self.hud.is_visible and "right" in tokens and len(tokens) == 1)
            has_triple = "triple" in tokens or "triple click" in phrase
            has_middle = "middle" in tokens or "middle click" in phrase

            if has_triple:
                self.driver.arm_modifier("triple")
            elif has_double:
                self.driver.arm_modifier("double")
            elif has_middle:
                self.driver.arm_modifier("middle")
            elif has_right:
                self.driver.arm_modifier("right")

            # Extract digit if present
            digit = None
            for token in tokens:
                if token in SPOKEN_DIGIT_MAP:
                    digit = SPOKEN_DIGIT_MAP[token]
                    break

            is_click_action = (
                "click" in tokens
                or "double click" in phrase
                or "right click" in phrase
                or "middle click" in phrase
                or "triple click" in phrase
            )

            # 11. Compound Shortcut: "<click_action> <digit>" (Instant Snap & Click)
            if is_click_action and digit is not None:
                if self.hud.is_visible:
                    if self.aim_at_target_badge(digit):
                        return self.execute_target_click()
                    return False

            # 12. Direct Click or Confirmation Click on Aimed Target
            if is_click_action:
                if self.hud.is_visible and self._selected_target is not None:
                    return self.execute_target_click()
                return self.trigger_direct_click()

            # If only modifier was spoken without digit or click (e.g. spoken ahead of time)
            if (has_double or has_right or has_triple or has_middle) and digit is None:
                logger.info("Spoken modifier armed; waiting for click or target digit.")
                return True

            # 13. Single-Digit Aiming (Option 1: Aim then Click)
            if digit is not None and self.hud.is_visible:
                return self.aim_at_target_badge(digit)

        return False

    def trigger_crosshair_scan(self) -> bool:
        """Initiate dual-axis crosshair scanner (FR-018)."""
        with self._lock:
            current_state = self.state_machine.current_state
            if current_state == SystemState.STANDBY:
                logger.debug("Cannot trigger crosshair while in STANDBY state.")
                return False

            if self.hud.is_visible:
                logger.info("Crosshair trigger requested while HUD is visible; prioritizing safe HUD dismissal.")
                self.dismiss_hud()
                return True

            self.state_machine.transition_to(SystemState.CROSSHAIR_ACTIVE)
            self.crosshair.start()
            return True

    def trigger_glide_mode(self, direction: Optional[str] = None) -> bool:
        """Enter continuous glide mode (FR-016)."""
        with self._lock:
            current_state = self.state_machine.current_state
            if current_state == SystemState.STANDBY:
                logger.debug("Cannot trigger glide while in STANDBY state.")
                return False

            if self.hud.is_visible:
                self.dismiss_hud()

            self.state_machine.transition_to(SystemState.GLIDE_ACTIVE)
            if direction:
                self.glider.set_heading_direction(direction)
                self.glider.start_glide(autonomous=True)
            else:
                self.glider.start_glide(autonomous=False)
            return True

    def trigger_tag_scan(self) -> bool:
        """Query foreground window UI controls and project HUD overlay badges (FR-006)."""
        with self._lock:
            current_state = self.state_machine.current_state
            if current_state in (SystemState.STANDBY, SystemState.GLIDE_ACTIVE, SystemState.CROSSHAIR_ACTIVE):
                logger.debug("Cannot trigger tag scan while in state: %s", current_state)
                return False

            if self.crosshair.is_visible:
                self.crosshair.hide()

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
            if self.speech_feedback:
                self.speech_feedback.speak("Tagging")
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
            self._action_generation = self.state_machine.current_generation
            logger.info("Aimed cursor at Target %d (%d, %d). Badges active.", digit, target.centroid_x, target.centroid_y)
            return True

    def select_target_badge(self, digit: int) -> bool:
        """Compatibility helper: aims at target badge (Option 1)."""
        return self.aim_at_target_badge(digit)

    def execute_target_click(self) -> bool:
        """
        Two-step Flow Step 2 (Fire):
        1. Validate selected target
        2. Verify generation hasn't changed (prevents stale clicks on halt/dismissal)
        3. Transition state machine to EXECUTING
        4. Dispatch mouse click with active modifier (left/right/double/triple/middle)
        5. Re-validate and transition state back to TRACKING (HUD stays visible for sequential clicks)
        """
        with self._lock:
            if not self._selected_target:
                return self.trigger_direct_click()

            if self.state_machine.current_generation != self._action_generation:
                logger.warning("Action dropped: generation changed (halt or dismissal during dispatch).")
                return False

            target = self._selected_target
            is_valid = self.crawler.revalidate_target(target, tolerance_px=5)
            if not is_valid:
                logger.warning("Target re-validation failed before click dispatch.")
                self.dismiss_hud()
                return False

            self.state_machine.transition_to(SystemState.EXECUTING)
            if self.state_machine.current_generation != self._action_generation:
                logger.warning("Action dropped: generation changed during execution transition.")
                return False

            modifier = self.driver.get_active_modifier()
            button = "right" if modifier == "right" else ("middle" if modifier == "middle" else "left")
            click_count = 3 if modifier == "triple" else (2 if modifier == "double" else 1)

            self.driver.click(button=button, click_count=click_count)
            self.driver.disarm_modifier()

            # State returns to TRACKING so badges remain usable
            self.state_machine.transition_to(SystemState.TRACKING)
            logger.info("Executed %s click (x%d) on Target %d (%d, %d). Tags remain active.", button, click_count, target.target_id, target.centroid_x, target.centroid_y)
            return True

    def trigger_direct_click(self) -> bool:
        """Direct in-place click at current cursor position (FR-010)."""
        with self._lock:
            gen_start = self.state_machine.current_generation
            self.state_machine.transition_to(SystemState.EXECUTING)
            if self.state_machine.current_generation != gen_start:
                logger.warning("Direct click dropped: generation changed during transition.")
                return False

            modifier = self.driver.get_active_modifier()
            button = "right" if modifier == "right" else ("middle" if modifier == "middle" else "left")
            click_count = 3 if modifier == "triple" else (2 if modifier == "double" else 1)

            self.driver.click(button=button, click_count=click_count)
            self.driver.disarm_modifier()
            self.state_machine.transition_to(SystemState.IDLE_ACTIVE)
            logger.info("Executed in-place %s click (x%d).", button, click_count)
            return True

    def dismiss_hud(self, bump_gen: bool = True) -> None:
        """Dismiss HUD overlay and clean up target state."""
        with self._lock:
            if bump_gen:
                self.state_machine.bump_generation(reason="DISMISS_HUD")
            self.hud.hide()
            self.driver.disarm_modifier()
            self._current_pages = []
            self._current_page_idx = 0
            self._selected_target = None
            if self.state_machine.current_state in (SystemState.TRACKING, SystemState.EXECUTING):
                self.state_machine.transition_to(SystemState.IDLE_ACTIVE)

    def destroy(self) -> None:
        """Clean up sub-components and cancel active timers."""
        with self._lock:
            if hasattr(self, "scroller") and self.scroller:
                try:
                    self.scroller.destroy()
                except Exception:
                    pass
            if hasattr(self, "glider") and self.glider:
                try:
                    self.glider.destroy()
                except Exception:
                    pass
            if hasattr(self, "crosshair") and self.crosshair:
                try:
                    self.crosshair.destroy()
                except Exception:
                    pass
            if hasattr(self, "hud") and self.hud:
                try:
                    self.hud.destroy()
                except Exception:
                    pass
