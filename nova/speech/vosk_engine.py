"""
Project NOVA - Offline Speech Recognition Engine
Vosk Kaldi-based streaming speech processor for continuous wake-word and command spotting.
Operates 100% locally with zero cloud egress (NFR-004, SEC-001, PRIV-001).
"""

import json
import logging
import os
import threading
import time
from typing import Callable, List, Optional

from nova.audio.capture import AudioCaptureManager
from nova.core.enums import SystemEventType
from nova.core.state_machine import SystemEvent

logger = logging.getLogger(__name__)

DEFAULT_GRAMMAR = [
    "hey nova", "wake up", "nova", "sleep", "halt", "cancel",
    "tag", "scan", "click", "double", "right",
    "next", "more", "back", "previous",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "[unk]",
]
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_DEBOUNCE_SECONDS = 0.25


def find_default_model_path() -> Optional[str]:
    """Search common local paths for the downloaded Vosk model."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "vosk-model-small-en-us-0.15"),
        os.path.join(os.getcwd(), "models", "vosk-model-small-en-us-0.15"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


class VoskSpeechEngine:
    """
    Offline streaming Kaldi speech recognition engine.
    Consumes ephemeral PCM audio chunks and triggers typed system events.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        grammar: Optional[List[str]] = None,
        on_event: Optional[Callable[[SystemEvent], None]] = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        self.sample_rate = sample_rate
        self.grammar = grammar or DEFAULT_GRAMMAR
        self.on_event = on_event
        self.debounce_seconds = debounce_seconds

        self._resolved_model_path = model_path or find_default_model_path()
        self._model = None
        self._recognizer = None
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_trigger_time: float = 0.0
        self._lock = threading.RLock()

        self._init_recognizer()

    def _init_recognizer(self) -> None:
        """Initialize the Vosk model and Kaldi recognizer if model path exists."""
        if not self._resolved_model_path or not os.path.exists(self._resolved_model_path):
            logger.warning(
                "Vosk model path not found (%s). Engine operating in mock/synthetic mode.",
                self._resolved_model_path,
            )
            return

        try:
            import vosk
            # Suppress verbose Vosk C-level logs if not debugging
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(self._resolved_model_path)
            self._recognizer = vosk.KaldiRecognizer(
                self._model,
                self.sample_rate,
                json.dumps(self.grammar),
            )
            logger.info("Vosk Kaldi speech recognizer initialized successfully.")
        except Exception as exc:
            logger.error("Failed to initialize Vosk model: %s", exc)
            self._model = None
            self._recognizer = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def process_pcm_chunk(self, chunk: bytes) -> Optional[str]:
        """
        Feed a raw 16kHz mono 16-bit PCM chunk into the recognizer.
        Returns recognized phrase text if a complete utterance boundary is detected.
        """
        if not chunk or not self._recognizer:
            return None

        with self._lock:
            try:
                if self._recognizer.AcceptWaveform(chunk):
                    result_json = json.loads(self._recognizer.Result())
                    text = result_json.get("text", "").strip().lower()
                    if text:
                        self._handle_recognized_text(text)
                        return text
            except Exception as exc:
                logger.error("Error during speech recognition decoding: %s", exc)
        return None

    def _handle_recognized_text(self, text: str) -> None:
        """Dispatches typed events based on recognized keywords with debounce enforcement."""
        now = time.monotonic()
        if (now - self._last_trigger_time) < self.debounce_seconds:
            logger.debug("Debounced recognition event for phrase: '%s'", text)
            return

        self._last_trigger_time = now
        logger.info("Speech recognized utterance: '%s'", text)

        event: Optional[SystemEvent] = None
        if any(w in text for w in ["hey nova", "wake up", "nova"]):
            event = SystemEvent(
                event_type=SystemEventType.WAKE_WORD_DETECTED,
                payload={"phrase": text},
            )
        elif "sleep" in text:
            event = SystemEvent(
                event_type=SystemEventType.SLEEP_TRIGGERED,
                payload={"phrase": text},
            )
        elif any(w in text for w in ["halt", "cancel"]):
            event = SystemEvent(
                event_type=SystemEventType.EMERGENCY_HALT,
                payload={"phrase": text},
            )
        else:
            event = SystemEvent(
                event_type=SystemEventType.COMMAND_DETECTED,
                payload={"phrase": text},
            )

        if event and self.on_event:
            try:
                self.on_event(event)
            except Exception as exc:
                logger.exception("Error in speech engine event callback: %s", exc)

    def start(self, audio_manager: AudioCaptureManager) -> bool:
        """Start the background stream processing worker thread."""
        with self._lock:
            if self._is_running:
                return True

            self._is_running = True
            self._worker_thread = threading.Thread(
                target=self._processing_loop,
                args=(audio_manager,),
                name="VoskSpeechWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("Speech recognition worker thread started.")
            return True

    def stop(self) -> None:
        """Stop the speech recognition worker thread."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("Speech recognition worker thread stopped.")

    def _processing_loop(self, audio_manager: AudioCaptureManager) -> None:
        """Continuously pulls PCM chunks from the audio manager and feeds the recognizer."""
        while self.is_running:
            chunk = audio_manager.get_chunk(timeout=0.1)
            if chunk:
                self.process_pcm_chunk(chunk)
