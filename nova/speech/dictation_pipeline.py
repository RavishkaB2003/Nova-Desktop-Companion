"""
Project NOVA - Unconstrained Voice Dictation Pipeline
Implements two-phase voice dictation with unconstrained Kaldi language model (FR-020),
silence-pause detection (>800ms), and parallel emergency halt spotting (FR-021).
Operates 100% locally with zero persistent user transcription logging (PRIV-002).
"""

import json
import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

from nova.speech.vosk_engine import find_default_model_path

logger = logging.getLogger(__name__)

DEFAULT_SILENCE_TIMEOUT_S = 3.0  # 3.0s silence pause before auto-committing dictation sentence
DEFAULT_ARMING_GRACE_PERIOD_S = 1.5  # 1.5s grace window to prevent false triggers from wake/trigger acoustics & TTS


class DictationPipeline:
    """
    Manages unconstrained speech recognition during SystemState.DICTATING.
    Transcribes free-form speech and triggers text injection callbacks upon utterance completion.
    """

    def __init__(
        self,
        model: Optional[object] = None,
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
        silence_timeout_s: float = DEFAULT_SILENCE_TIMEOUT_S,
        arming_grace_period_s: float = DEFAULT_ARMING_GRACE_PERIOD_S,
        on_text_ready: Optional[Callable[[str], None]] = None,
        on_dictation_complete: Optional[Callable[[], None]] = None,
        on_emergency_halt: Optional[Callable[[], None]] = None,
        on_click_command: Optional[Callable[[], None]] = None,
    ) -> None:
        self.model = model
        self.model_path = model_path or (find_default_model_path() if model is None else None)
        self.sample_rate = sample_rate
        self.silence_timeout_s = silence_timeout_s
        self.arming_grace_period_s = arming_grace_period_s
        self.on_text_ready = on_text_ready
        self.on_dictation_complete = on_dictation_complete
        self.on_emergency_halt = on_emergency_halt
        self.on_click_command = on_click_command

        self._lock = threading.RLock()
        self._model = None
        self._recognizer = None
        self._is_active = False
        self._has_spoken = False
        self._last_speech_time: float = 0.0
        self._accumulated_text: str = ""
        self._start_time: float = 0.0

        self._init_recognizer()

    def _init_recognizer(self) -> None:
        """Initialize unconstrained Vosk Kaldi recognizer."""
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
            vosk.SetLogLevel(-1)

            if self.model is not None:
                self._model = self.model
                self._recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)
                logger.info("Unconstrained Vosk dictation recognizer initialized with shared model.")
                return

            if not self.model_path or not os.path.exists(self.model_path):
                logger.warning("Vosk model path not found for dictation (%s). Operating in mock mode.", self.model_path)
                return

            self._model = vosk.Model(self.model_path)
            # Unconstrained recognizer: NO grammar constraint passed
            self._recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)
            logger.info("Unconstrained Vosk dictation recognizer initialized successfully.")
        except Exception as exc:
            logger.error("Failed to initialize dictation recognizer: %s", exc)
            self._model = None
            self._recognizer = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._is_active

    def start_dictation(self) -> None:
        """Arm the dictation pipeline to process incoming audio chunks."""
        with self._lock:
            self._is_active = True
            self._has_spoken = False
            self._start_time = time.monotonic()
            self._last_speech_time = self._start_time
            self._accumulated_text = ""
            if self._recognizer:
                try:
                    self._recognizer.Reset()
                except Exception:
                    pass
            logger.info("Dictation pipeline armed (unconstrained ASR active).")

    def reset_grace_timer(self) -> None:
        """Reset arming grace period timer to now (e.g. after TTS feedback audio un-mutes)."""
        with self._lock:
            self._start_time = time.monotonic()
            self._last_speech_time = self._start_time
            logger.debug("Dictation grace period timer reset to current monotonic time.")


    def stop_dictation(self, commit_pending: bool = True) -> Optional[str]:
        """
        Disarm dictation pipeline and optionally commit any buffered uncommitted text.
        """
        with self._lock:
            if not self._is_active:
                return None

            self._is_active = False
            final_text = ""

            if commit_pending and self._recognizer:
                try:
                    res_json = json.loads(self._recognizer.FinalResult())
                    final_text = res_json.get("text", "").strip()
                except Exception:
                    pass

            if not final_text and self._accumulated_text:
                final_text = self._accumulated_text.strip()

            if final_text and self.on_text_ready:
                self.on_text_ready(final_text)

            if self.on_dictation_complete:
                self.on_dictation_complete()

            logger.info("Dictation pipeline stopped. Final text committed: '%s'", final_text)
            return final_text

    def process_pcm_chunk(self, chunk: bytes) -> Optional[str]:
        """
        Feed audio chunk into unconstrained dictation recognizer.
        Detects emergency halts, silence auto-commit, and completed sentences.
        """
        if not chunk:
            return None

        with self._lock:
            if not self._is_active:
                return None

            now = time.monotonic()
            start_time = getattr(self, "_start_time", 0.0)
            in_grace_period = (now - start_time) < getattr(self, "arming_grace_period_s", DEFAULT_ARMING_GRACE_PERIOD_S)

            if not self._recognizer:
                return None

            try:
                if self._recognizer.AcceptWaveform(chunk):
                    res_json = json.loads(self._recognizer.Result())
                    text = res_json.get("text", "").strip()
                    if text:
                        self._has_spoken = True
                        self._last_speech_time = now
                        words = text.lower().split()
                        logger.debug("Dictation clause recognized: %d words", len(words))

                        # 1. Isolated Emergency Halt (FR-021, SRS.md FR-19):
                        # ONLY trigger if the full utterance is strictly "halt" or "cancel" alone.
                        # Sentences containing those words as vocabulary (e.g. "please cancel my order") transcribe normally.
                        if words in (["halt"], ["cancel"]):
                            if not in_grace_period:
                                logger.info("Isolated emergency halt spotted during dictation: '%s'", text)
                                self.stop_dictation(commit_pending=False)
                                if self.on_emergency_halt:
                                    self.on_emergency_halt()
                                return None
                            else:
                                logger.debug("Discarding isolated halt/cancel utterance during arming grace period.")
                                return None

                        # 2. Isolated Click Command (FR-010, FR-020)
                        if words in (["click"], ["left", "click"], ["double", "click"], ["right", "click"]):
                            logger.info("Click command spotted during dictation: '%s'", text)
                            self.stop_dictation(commit_pending=False)
                            if self.on_click_command:
                                self.on_click_command()
                            return None

                        # 3. Explicit Session Conclusion ("done", "stop", "stop dictation")
                        if words in (["stop", "dictation"], ["done", "typing"], ["stop", "typing"], ["stop"], ["done"]):
                            self.stop_dictation(commit_pending=False)
                            return None

                        if words and words[-1] in ("stop", "done"):
                            # Filter the terminating keyword and finalize
                            cleaned_words = [w for w in words[:-1]]
                            clean_text = " ".join(cleaned_words)
                            if clean_text and self.on_text_ready:
                                self.on_text_ready(clean_text)
                            self.stop_dictation(commit_pending=False)
                            return clean_text

                        # 4. Continuous phrase streaming:
                        # Immediately dispatch recognized clause into target field and STAY ACTIVE
                        if self.on_text_ready:
                            self.on_text_ready(text)
                            self._accumulated_text = ""
                        return text
                else:
                    part_json = json.loads(self._recognizer.PartialResult())
                    partial_text = part_json.get("partial", "").strip().lower()
                    if partial_text:
                        self._has_spoken = True
                        self._last_speech_time = now

                        part_words = partial_text.split()

                        # Isolated click command spotter during dictation
                        if part_words in (["click"], ["left", "click"], ["double", "click"], ["right", "click"]):
                            logger.info("Instant click spotted in partial dictation: '%s'", partial_text)
                            self.stop_dictation(commit_pending=False)
                            if self.on_click_command:
                                self.on_click_command()
                            return None

                        if partial_text in ("stop dictation", "stop typing", "done typing"):
                            self.stop_dictation(commit_pending=False)
                            return None

                # Silence timeout check: if user spoke and has been silent for >= silence_timeout_s
                if self._has_spoken and (now - self._last_speech_time) >= self.silence_timeout_s:

                    logger.info("Dictation silence timeout (%.2fs) elapsed. Auto-committing sentence.", self.silence_timeout_s)
                    self.stop_dictation(commit_pending=True)
                    return None

            except Exception as exc:
                logger.error("Error processing dictation PCM chunk: %s", exc)

            return None
