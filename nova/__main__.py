"""
Project NOVA - Main Desktop Companion Daemon Entrypoint
Unites audio capture, offline speech recognition, state machine coordination,
audio ducking, and the transparent Tkinter mascot UI.
"""

import argparse
import logging
import signal
import tkinter as tk
from typing import Optional

from nova.audio.capture import AudioCaptureManager
from nova.audio.ducking import AudioDuckingManager, play_audio_chime
from nova.core.enums import SystemEventType, SystemState
from nova.core.state_machine import StateMachine, SystemEvent
from nova.speech.vosk_engine import VoskSpeechEngine
from nova.ui.mascot import MascotWidget, enable_windows_dpi_awareness

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
    ) -> None:
        self.debug = debug
        self.reduced_motion = reduced_motion
        self.model_path = model_path

        self._configure_logging()
        logger.info("Initializing Project NOVA Desktop Companion...")

        # Core subsystems
        self.state_machine = StateMachine(initial_state=SystemState.STANDBY)
        self.ducking_manager = AudioDuckingManager()
        self.audio_manager = AudioCaptureManager(on_error=self._on_audio_error)
        self.speech_engine = VoskSpeechEngine(
            model_path=self.model_path,
            on_event=self._on_speech_event,
        )

        # Tkinter UI
        enable_windows_dpi_awareness()
        self.root = tk.Tk()
        self.mascot = MascotWidget(
            root=self.root,
            reduced_motion=self.reduced_motion,
        )

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

    def _on_speech_event(self, event: SystemEvent) -> None:
        logger.debug("Speech event received by coordinator: %s", event)
        self.state_machine.handle_event(event)

    def _bind_state_transitions(self) -> None:
        """Subscribe coordinator logic to state changes."""
        def on_state_change(old_state: SystemState, new_state: SystemState) -> None:
            logger.info("State transition: %s -> %s", old_state, new_state)

            # Update Mascot visual appearance
            self.mascot.set_visual_state(self.state_machine.current_visual_state)

            # Audio ducking gate (FR-005)
            if new_state in (SystemState.LISTENING, SystemState.DICTATING):
                self.ducking_manager.duck()
            else:
                self.ducking_manager.unduck()

            # Audio chime feedback (FR-004)
            if old_state == SystemState.STANDBY and new_state in (SystemState.WAKING, SystemState.IDLE_ACTIVE):
                play_audio_chime("wake")
            elif new_state == SystemState.STANDBY and old_state != SystemState.STANDBY:
                play_audio_chime("sleep")
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

    def start(self) -> None:
        """Start background processing loops and enter the GUI event loop."""
        logger.info("Starting audio capture and speech recognition worker...")
        self.audio_manager.start()
        self.speech_engine.start(self.audio_manager)

        logger.info("Project NOVA is active and listening for wake words.")
        self.root.mainloop()

    def stop(self) -> None:
        """Stop all background workers and restore host system audio."""
        logger.info("Stopping Project NOVA subsystems...")
        self.speech_engine.stop()
        self.audio_manager.stop()
        self.ducking_manager.unduck()
        self.mascot.destroy()
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = NovaApp(
        debug=args.debug,
        reduced_motion=args.reduced_motion,
        model_path=args.model_path,
    )
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
