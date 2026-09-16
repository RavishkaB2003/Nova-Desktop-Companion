"""
Project NOVA - Main Desktop Companion Daemon Entrypoint
Unites audio capture, offline speech recognition, digital signal processing (transients & pitch),
state machine coordination, audio ducking, and the transparent Tkinter mascot & HUD UI.
"""

import argparse
import logging
import queue
import signal
import threading
import tkinter as tk
from typing import Optional

from nova.audio.capture import AudioCaptureManager
from nova.audio.dsp import AcousticImpulseDetector, VoicedPitchTracker
from nova.audio.ducking import AudioDuckingManager, is_chime_playing, play_audio_chime
from nova.automation.crawler import UIAutomationCrawler
from nova.automation.shortcuts import SystemShortcutManager
from nova.core.coordinator import TagSnapCoordinator
from nova.core.enums import SystemEventType, SystemState
from nova.core.state_machine import StateMachine, SystemEvent
from nova.input.driver import InputDriver
from nova.input.scroll_controller import ScrollController
from nova.input.text_injector import TextInjector
from nova.speech.dictation_pipeline import DictationPipeline
from nova.speech.vosk_engine import VoskSpeechEngine, find_default_model_path
from nova.ui.hud_overlay import HudOverlay
from nova.ui.mascot import MascotWidget, enable_windows_dpi_awareness
from nova.ui.tray import NovaTrayIcon

logger = logging.getLogger("nova")



class NovaApp:
    """
    Top-level application orchestrator managing lifecycles of core subsystems.
    """

    def __init__(
        self,
        debug: bool = False,
        reduced_motion: bool = False,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        self.debug = debug
        self.reduced_motion = reduced_motion
        self.model_path = model_path or find_default_model_path()
        self.device = device

        self._configure_logging()
        logger.info("Initializing Project NOVA Desktop Companion...")

        # Core state machine & audio ducking
        self.state_machine = StateMachine(initial_state=SystemState.STANDBY)
        self.ducking_manager = AudioDuckingManager()
        self.audio_manager = AudioCaptureManager(device=self.device, on_error=self._on_audio_error)

        # Tkinter UI
        enable_windows_dpi_awareness()
        self.root = tk.Tk()
        self.mascot = MascotWidget(
            root=self.root,
            reduced_motion=self.reduced_motion,
        )

        # Speech Engine & Dictation Pipeline (Shared Vosk Kaldi Model)
        self.speech_engine = VoskSpeechEngine(
            model_path=self.model_path,
            on_event=self._on_speech_event,
            on_speech_activity=self._on_speech_activity,
        )
        self.dictation_pipeline = DictationPipeline(
            model=self.speech_engine.model,
            model_path=self.model_path,
        )
        self.speech_engine.set_dictation_pipeline(self.dictation_pipeline)

        # UI Automation & Input Subsystems (MOD-002, MOD-003, MOD-004)
        self.crawler = UIAutomationCrawler()
        self.input_driver = InputDriver()
        self.hud = HudOverlay(root=self.root)
        self.scroll_controller = ScrollController(root=self.root, driver=self.input_driver)
        self.text_injector = TextInjector(driver=self.input_driver, state_machine=self.state_machine)
        self.shortcut_manager = SystemShortcutManager(driver=self.input_driver)

        # System Tray Icon (Background Daemon Presence)
        self.tray_icon = NovaTrayIcon(
            on_activate=lambda: self.root.after(0, self.activate_mascot),
            on_deactivate=lambda: self.root.after(0, self.deactivate_mascot),
            on_toggle_panel=lambda: self.root.after(
                0,
                lambda: self.coordinator.control_panel.toggle()
                if getattr(self.coordinator, "control_panel", None)
                else None,
            ),
            on_quit=lambda: self.root.after(0, self._shutdown),
        )

        self.coordinator = TagSnapCoordinator(
            state_machine=self.state_machine,
            crawler=self.crawler,
            hud=self.hud,
            driver=self.input_driver,
            scroller=self.scroll_controller,
            text_injector=self.text_injector,
            dictation_pipeline=self.dictation_pipeline,
            shortcuts=self.shortcut_manager,
            reduced_motion=self.reduced_motion,
            on_activate=lambda: self.root.after(0, self.activate_mascot),
            on_deactivate=lambda: self.root.after(0, self.deactivate_mascot),
        )
        if self.coordinator.control_panel:
            self.mascot.on_double_click = self.coordinator.control_panel.toggle

        # Start silently in background mode (visible via system tray icon in taskbar)
        self.mascot.hide()


        # DSP Subsystems (MOD-003)
        self.impulse_detector = AcousticImpulseDetector(
            on_impulse=self._on_acoustic_impulse,
        )
        self.pitch_tracker = VoicedPitchTracker(
            on_glide_tick=self._on_glide_tick,
            on_glide_stop=self._on_glide_stop,
        )

        self._is_running = False
        self._audio_thread: Optional[threading.Thread] = None
        self._speech_queue: queue.Queue = queue.Queue(maxsize=100)
        self._speech_thread: Optional[threading.Thread] = None

        self._bind_state_transitions()
        self._setup_shutdown_handlers()

    def _configure_logging(self) -> None:
        level = logging.DEBUG if self.debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] (%(threadName)s) %(name)s: %(message)s",
        )

    def _on_audio_error(self, exc: Exception) -> None:
        logger.error("Audio capture stream error reported: %s", exc)
        self.state_machine.handle_event(
            SystemEvent(event_type=SystemEventType.AUDIO_STREAM_ERROR)
        )

    def _on_speech_activity(self) -> None:
        """Plosive acoustic gating (FR-014): mute impulse detector on speech token."""
        self.impulse_detector.notify_speech_detected()

    def _on_acoustic_impulse(self) -> None:
        """Dispatches detected acoustic impulse to coordinator on GUI thread."""
        logger.info("Acoustic impulse detected in NovaApp.")
        if self.root:
            try:
                self.root.after(0, self.coordinator.handle_impulse)
            except Exception as exc:
                logger.warning("Could not dispatch impulse via root.after: %s", exc)

    def _on_glide_tick(self, dt: float) -> None:
        """Advances glider step on GUI thread."""
        if self.root:
            try:
                self.root.after(0, lambda: self.coordinator.glider.step(dt))
            except Exception as exc:
                logger.warning("Could not dispatch glide tick via root.after: %s", exc)

    def _on_glide_stop(self) -> None:
        """Called when voiced vowel ceases."""
        # Only stop glider if it was not started in autonomous cruise mode
        if not self.coordinator.glider.is_autonomous:
            self.coordinator.glider.stop_glide()

    def activate_mascot(self) -> None:
        """Pop up mascot from background tray into desktop STANDBY (sleeping appearance)."""
        logger.info("Activating mascot from background mode into STANDBY.")
        self.mascot.show()
        self.tray_icon.update_title("NOVA Desktop Companion (Mascot Active - Sleeping)")
        self.coordinator.speech_feedback.speak("Activated")

    def deactivate_mascot(self) -> None:
        """Auto-sleep if active, close control panel/overlays, and hide mascot to background tray."""
        logger.info("Deactivating mascot back to background mode.")
        if getattr(self.coordinator, "control_panel", None) and self.coordinator.control_panel.is_visible:
            self.coordinator.control_panel.hide()
        if self.hud.is_visible:
            self.coordinator.dismiss_hud()
        if self.coordinator.crosshair.is_visible:
            self.coordinator.crosshair.hide()
        if self.coordinator.glider.is_gliding:
            self.coordinator.glider.stop_glide()
        if self.scroll_controller.is_scrolling:
            self.scroll_controller.stop_scroll()
        if self.dictation_pipeline and self.dictation_pipeline.is_active:
            self.dictation_pipeline.stop_dictation(commit_pending=False)

        # Auto-sleep if awake
        if self.state_machine.current_state != SystemState.STANDBY:
            self.state_machine.handle_event(
                SystemEvent(event_type=SystemEventType.DEACTIVATE_TRIGGERED)
            )

        self.mascot.hide()
        self.tray_icon.update_title("NOVA Desktop Companion (Background Mode)")

    def _shutdown(self) -> None:
        """Perform orderly shutdown."""
        self.stop()
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

    def _on_speech_event(self, event: SystemEvent) -> None:
        logger.debug("Speech event received by coordinator: %s", event)

        def _dispatch() -> None:
            if event.event_type == SystemEventType.ACTIVATE_TRIGGERED:
                self.activate_mascot()
                return
            if event.event_type == SystemEventType.DEACTIVATE_TRIGGERED:
                self.deactivate_mascot()
                return
            if event.payload and "phrase" in event.payload:
                phrase = event.payload["phrase"]
                if self.coordinator.handle_speech_phrase(phrase):
                    return
            self.state_machine.handle_event(event)

        if self.root:
            try:
                self.root.after(0, _dispatch)
            except Exception:
                _dispatch()
        else:
            _dispatch()


    def _bind_state_transitions(self) -> None:
        """Subscribe coordinator logic to state changes."""
        def on_state_change(old_state: SystemState, new_state: SystemState) -> None:
            logger.info("State transition: %s -> %s", old_state, new_state)

            # Update Mascot visual appearance
            self.mascot.set_visual_state(self.state_machine.current_visual_state)

            # Arm / disarm pitch tracker strictly for GLIDE_ACTIVE (FR-016)
            if new_state == SystemState.GLIDE_ACTIVE:
                self.pitch_tracker.arm()
            else:
                self.pitch_tracker.disarm()

            # Audio ducking gate (FR-005)
            if new_state in (SystemState.LISTENING, SystemState.DICTATING):
                self.ducking_manager.duck()
            else:
                self.ducking_manager.unduck()

            # Clean audio buffer on entry into DICTATING to prevent trigger phrase spillover
            if new_state == SystemState.DICTATING:
                while not self._speech_queue.empty():
                    try:
                        self._speech_queue.get_nowait()
                    except queue.Empty:
                        break
                self.speech_engine.reset()

            # Audio chime feedback (FR-004) and SAPI5 spoken confirmation (Item 6)
            if old_state == SystemState.STANDBY and new_state in (SystemState.WAKING, SystemState.IDLE_ACTIVE):
                play_audio_chime("wake")
                self.coordinator.speech_feedback.speak("Ready")
            elif new_state == SystemState.STANDBY and old_state != SystemState.STANDBY:
                play_audio_chime("sleep")
                self.coordinator.speech_feedback.speak("Sleep")
            elif new_state == SystemState.ERROR:
                play_audio_chime("error")

        self.state_machine.subscribe(on_state_change)

    def _setup_shutdown_handlers(self) -> None:
        """Handle window close and SIGINT gracefully."""
        def shutdown() -> None:
            self.stop()
            if self.root:
                try:
                    self.root.quit()
                except Exception:
                    pass

        self.root.protocol("WM_DELETE_WINDOW", shutdown)

        def sig_handler(sig, frame) -> None:
            logger.info("Termination signal caught. Shutting down...")
            shutdown()

        try:
            signal.signal(signal.SIGINT, sig_handler)
            signal.signal(signal.SIGTERM, sig_handler)
        except Exception:
            pass

    def _audio_pipeline_loop(self) -> None:
        """
        Unified real-time audio pipeline thread.
        Distributes raw PCM chunks immediately to impulse detector (sub-25ms DSP, NFR-001)
        and voiced pitch tracker (autocorrelation).
        Asynchronously enqueues chunks for speech recognition to prevent Kaldi decode jitter.
        """
        logger.info("Audio pipeline processing loop started.")
        while self._is_running:
            try:
                chunk = self.audio_manager.get_chunk(timeout=0.05)
                if not chunk:
                    continue

                # Software Ducking Gate (TM-04 / FR-005):
                # Drop mic chunks while SAPI5 voice or audio chime is actively outputting sound through speakers
                # to completely prevent acoustic echo, self-triggering, and feedback loops.
                if self.coordinator.speech_feedback.is_speaking or is_chime_playing():
                    self.impulse_detector.notify_speech_detected()
                    self.speech_engine.reset()
                    continue

                # 1. Sub-25ms Acoustic Impulse Detection (FR-013, NFR-001)
                self.impulse_detector.process_pcm_chunk(chunk)

                # 2. Voiced Vowel Pitch Gliding (FR-016)
                self.pitch_tracker.process_pcm_chunk(chunk)

                # 3. Decoupled Speech Recognition Queue
                try:
                    self._speech_queue.put_nowait(chunk)
                except queue.Full:
                    pass
            except Exception as exc:
                logger.error("Error in audio pipeline loop: %s", exc)
                time.sleep(0.01)

    def _speech_worker_loop(self) -> None:
        """
        Asynchronous speech recognition worker thread.
        Consumes chunks decoupled from high-priority audio pipeline.
        """
        logger.info("Speech recognition worker loop started.")
        while self._is_running:
            try:
                chunk = self._speech_queue.get(timeout=0.05)
                self.speech_engine.process_pcm_chunk(chunk)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("Error in speech worker loop: %s", exc)

    def start(self) -> None:
        """Start background processing loops and enter the GUI event loop."""
        logger.info("Starting audio capture and pipeline worker...")
        self._is_running = True
        self.audio_manager.start()
        self.coordinator.start()
        self.tray_icon.start()

        self._audio_thread = threading.Thread(
            target=self._audio_pipeline_loop,
            name="NovaAudioPipeline",
            daemon=True,
        )
        self._audio_thread.start()

        self._speech_thread = threading.Thread(
            target=self._speech_worker_loop,
            name="NovaSpeechWorker",
            daemon=True,
        )
        self._speech_thread.start()

        logger.info("Project NOVA is active in background mode (tray icon listening for 'activate').")
        self.root.mainloop()

    def stop(self) -> None:
        """Stop all background workers and restore host system audio."""
        logger.info("Stopping Project NOVA subsystems...")
        self._is_running = False
        self.tray_icon.stop()
        if self._audio_thread and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=1.0)
            self._audio_thread = None

        if self._speech_thread and self._speech_thread.is_alive():
            self._speech_thread.join(timeout=1.0)
            self._speech_thread = None

        self.scroll_controller.stop_scroll()
        if self.dictation_pipeline and self.dictation_pipeline.is_active:
            self.dictation_pipeline.stop_dictation(commit_pending=False)
        self.speech_engine.stop()
        self.audio_manager.stop()
        self.ducking_manager.unduck()
        self.crawler.restore_system_accessibility_flags()
        self.coordinator.stop()
        self.coordinator.crosshair.destroy()
        self.mascot.destroy()
        self.hud.destroy()
        logger.info("All subsystems terminated cleanly.")



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project NOVA Assistive Desktop Companion")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument(
        "--reduced-motion",
        action="store_true",
        help="Disable ambient floating and motion animations (WCAG 2.2 AA)",
    )
    parser.add_argument("--model-path", type=str, default=None, help="Path to offline Vosk acoustic model")
    parser.add_argument("--device", type=str, default=None, help="Input microphone device ID or name substring")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = NovaApp(
        debug=args.debug,
        reduced_motion=args.reduced_motion,
        model_path=args.model_path,
        device=args.device,
    )
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
