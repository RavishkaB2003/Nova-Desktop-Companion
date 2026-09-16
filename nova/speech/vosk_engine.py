"""
Project NOVA - Offline Speech Recognition Engine
Vosk Kaldi-based streaming speech processor for continuous wake-word and command spotting.
Operates 100% locally with zero cloud egress (NFR-004, SEC-001, PRIV-001).
"""

import json
import logging
import os
import sys
import threading
import time
from typing import Callable, List, Optional

from nova.audio.capture import AudioCaptureManager
from nova.core.enums import SystemEventType
from nova.core.state_machine import SystemEvent

logger = logging.getLogger(__name__)

DEFAULT_GRAMMAR = [
    "wake up nova", "hey nova", "wake up", "nova", "activate", "deactivate",
    "go to sleep", "sleep", "halt", "cancel", "done", "close", "closed", "dismiss", "stop",
    "close tag", "close tags", "clear", "exit", "hide", "hide tags",
    "tag", "scan", "click", "double click", "right click", "middle click", "triple click", "double", "right",
    "next", "more", "back", "previous",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "cross hair", "scanner", "laser", "lock", "hit", "mark", "freeze",
    "slow", "fast", "normal",
    "scroll down", "scroll up", "scroll", "faster", "slower",
    "type", "dictate", "enter", "delete", "back space", "space",
    "glide", "canvas", "draw", "move", "start",
    "left", "up", "down", "go right", "go left", "go up", "go down",
    "nudge", "step", "tap", "jump",
    "nudge up", "nudge down", "nudge left", "nudge right",
    "jump up", "jump down", "jump left", "jump right",
    "step up", "step down", "step left", "step right",
    "open browser", "browser", "open paint", "paint", "open explorer", "open this pc", "explorer",
    "open youtube", "play on youtube", "on youtube", "youtube",
    "switch window", "close window", "show desktop",
    "menu", "show menu", "help", "commands", "close menu",
    "[unk]",
]
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_DEBOUNCE_SECONDS = 0.25
DEFAULT_CONFIDENCE_THRESHOLD = 0.65



def find_default_model_path() -> Optional[str]:
    """Search common local paths for the downloaded Vosk model across source and frozen environments."""
    candidates = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "models", "vosk-model-small-en-us-0.15"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "models", "vosk-model-small-en-us-0.15"))
        candidates.append(os.path.join(exe_dir, "_internal", "models", "vosk-model-small-en-us-0.15"))

    candidates.extend([
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "vosk-model-small-en-us-0.15"),
        os.path.join(os.getcwd(), "models", "vosk-model-small-en-us-0.15"),
    ])
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
        on_speech_activity: Optional[Callable[[], None]] = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.sample_rate = sample_rate
        self.grammar = grammar or DEFAULT_GRAMMAR
        self.on_event = on_event
        self.on_speech_activity = on_speech_activity
        self.debounce_seconds = debounce_seconds
        self.confidence_threshold = confidence_threshold

        self._resolved_model_path = model_path or find_default_model_path()
        self._model = None
        self._recognizer = None
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_trigger_time: float = 0.0
        self._last_phrase: str = ""
        self._dictation_pipeline: Optional[object] = None
        self._lock = threading.RLock()

        self._init_recognizer()

    def set_dictation_pipeline(self, pipeline: Optional[object]) -> None:
        """Attach a DictationPipeline instance for unconstrained speech transcription (FR-020)."""
        with self._lock:
            self._dictation_pipeline = pipeline

    def _init_recognizer(self) -> None:
        """Initialize the Vosk model and Kaldi recognizer if model path exists."""
        if not self._resolved_model_path or not os.path.exists(self._resolved_model_path):
            logger.warning(
                "Vosk model path not found (%s). Engine operating in mock/synthetic mode.",
                self._resolved_model_path,
            )
            return

        try:
            if getattr(sys, "frozen", False):
                exe_dir = os.path.dirname(sys.executable)
                for cand in [
                    os.path.join(exe_dir, "_internal", "vosk"),
                    os.path.join(exe_dir, "vosk"),
                    getattr(sys, "_MEIPASS", ""),
                ]:
                    if cand and os.path.exists(cand):
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(cand)
                            except Exception:
                                pass
                        os.environ["PATH"] = cand + os.pathsep + os.environ.get("PATH", "")

            import vosk
            # Suppress verbose Vosk C-level logs if not debugging
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(self._resolved_model_path)
            self._recognizer = vosk.KaldiRecognizer(
                self._model,
                self.sample_rate,
                json.dumps(self.grammar),
            )
            if hasattr(self._recognizer, "SetWords"):
                try:
                    self._recognizer.SetWords(True)
                except Exception:
                    pass
            logger.info("Vosk Kaldi speech recognizer initialized successfully.")
        except Exception as exc:
            logger.error("Failed to initialize Vosk model: %s", exc)
            self._model = None
            self._recognizer = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def model(self) -> Optional[object]:
        """Expose loaded Vosk model for shared recognizer instances."""
        with self._lock:
            return self._model

    def reset(self) -> None:
        """Reset Kaldi recognizer internal state and discard buffered partial hypotheses (TM-04)."""
        with self._lock:
            if self._recognizer:
                try:
                    self._recognizer.Reset()
                except Exception:
                    pass

    def process_pcm_chunk(self, chunk: bytes) -> Optional[str]:
        """
        Feed a raw 16kHz mono 16-bit PCM chunk into the recognizer.
        Returns recognized phrase text if a complete utterance or instant partial match is detected.
        """
        if not chunk or not self._recognizer:
            return None

        with self._lock:
            # Delegate directly to unconstrained dictation pipeline when active (FR-020)
            if self._dictation_pipeline and getattr(self._dictation_pipeline, "is_active", False):
                if self.on_speech_activity:
                    self.on_speech_activity()
                return self._dictation_pipeline.process_pcm_chunk(chunk)

            try:
                if self._recognizer.AcceptWaveform(chunk):
                    result_json = json.loads(self._recognizer.Result())
                    text = result_json.get("text", "").strip().lower()
                    if text:
                        if text == "[unk]":
                            logger.debug("Discarding out-of-vocabulary [unk] token.")
                            return None

                        # Word-level confidence gating
                        word_items = result_json.get("result", [])
                        if word_items and self.confidence_threshold > 0.0:
                            confidences = [float(w.get("conf", 1.0)) for w in word_items if "conf" in w]
                            if confidences:
                                avg_conf = sum(confidences) / len(confidences)
                                if avg_conf < self.confidence_threshold:
                                    logger.info(
                                        "Rejected low-confidence speech '%s' (conf=%.2f < threshold=%.2f)",
                                        text, avg_conf, self.confidence_threshold,
                                    )
                                    return None

                        if self.on_speech_activity:
                            self.on_speech_activity()
                        self._handle_recognized_text(text)
                        return text
                else:
                    partial_json = json.loads(self._recognizer.PartialResult())
                    partial_text = partial_json.get("partial", "").strip().lower()
                    if partial_text and partial_text != "[unk]":
                        if self.on_speech_activity:
                            self.on_speech_activity()
                        # Instant trigger on partial matches reserved strictly for emergency halts, complete wake phrases, and crosshair locks
                        words = partial_text.split()
                        if any(w in words for w in ["halt", "stop"]):
                            logger.info("Instant emergency halt phrase recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
                        # Check deactivate BEFORE activate to prevent subphrase hijacking
                        if "deactivate" in words:
                            logger.info("Instant deactivate command recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
                        if "activate" in words:
                            logger.info("Instant activate command recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
                        if any(w in partial_text for w in ["wake up nova", "hey nova", "wake up"]):
                            logger.info("Instant wake word recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
                        # Instant trigger for crosshair lock / hit confirmation tokens (FR-018):
                        # Bypasses Kaldi's 500-800ms silence wait, eliminating overshoot while laser sweeps.
                        if any(w in words for w in ["lock", "hit", "freeze", "mark"]):
                            logger.info("Instant crosshair lock confirmation recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
                        # Instant trigger for spoken click commands (FR-010, FR-012):
                        # Bypasses Kaldi's 500-800ms silence wait so spoken clicks fire instantaneously
                        if words == ["click"] or partial_text in ("click", "double click", "right click", "middle click"):
                            logger.info("Instant spoken click command recognized: '%s'", partial_text)
                            self._handle_recognized_text(partial_text)
                            self._recognizer.Reset()
                            return partial_text
            except Exception as exc:
                logger.error("Error during speech recognition decoding: %s", exc)
        return None

    def _handle_recognized_text(self, text: str) -> None:
        """Dispatches typed events based on recognized keywords with smart per-phrase debounce."""
        now = time.monotonic()
        clean_text = text.strip().lower()

        is_same_phrase = (clean_text == self._last_phrase)
        required_debounce = self.debounce_seconds if is_same_phrase else 0.05

        if (now - self._last_trigger_time) < required_debounce:
            logger.debug("Debounced recognition event for phrase: '%s' (same=%s)", text, is_same_phrase)
            return

        self._last_trigger_time = now
        self._last_phrase = clean_text
        logger.info("Speech recognized utterance: '%s'", text)

        words = clean_text.split()
        event: Optional[SystemEvent] = None
        # Exact token matching for commands
        if "deactivate" in words:
            event = SystemEvent(
                event_type=SystemEventType.DEACTIVATE_TRIGGERED,
                payload={"phrase": text},
            )
        elif "activate" in words:
            event = SystemEvent(
                event_type=SystemEventType.ACTIVATE_TRIGGERED,
                payload={"phrase": text},
            )
        elif clean_text in ("wake up nova", "hey nova", "wake up") or words == ["nova"] or any(clean_text.startswith(p + " ") for p in ("wake up nova", "hey nova", "wake up")):
            event = SystemEvent(
                event_type=SystemEventType.WAKE_WORD_DETECTED,
                payload={"phrase": text},
            )
        elif clean_text in ("go to sleep", "sleep") or (words and words[0] in ("go", "sleep") and "sleep" in words):
            event = SystemEvent(
                event_type=SystemEventType.SLEEP_TRIGGERED,
                payload={"phrase": text},
            )
        elif any(w in words for w in ["halt", "cancel"]):
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
