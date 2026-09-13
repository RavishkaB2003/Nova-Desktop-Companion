"""
Project NOVA - Low-Latency Ephemeral Audio Capture
Stream manager ingesting 16kHz mono 16-bit PCM via sounddevice into an in-memory buffer.
"""

import logging
import queue
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Standard acoustic parameters for Vosk speech model
SAMPLE_RATE_HZ = 16000
CHANNELS = 1
BLOCK_SIZE_SAMPLES = 1600  # 100ms chunks at 16kHz
DTYPE = "int16"
QUEUE_MAX_SIZE = 50  # 5 seconds maximum backlog before dropping oldest chunk


class AudioCaptureManager:
    """
    Manages continuous microphone stream capture into thread-safe ephemeral queues.
    Enforces PRIV-001: Zero disk persistence, RAM-only processing.
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE_HZ,
        block_size: int = BLOCK_SIZE_SAMPLES,
        channels: int = CHANNELS,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.on_error = on_error

        self._audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self._stream: Optional[Any] = None
        self._is_running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def _audio_callback(self, indata: bytes, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio stream callback executed on an audio driver thread."""
        if status:
            logger.debug("Audio input status flag: %s", status)

        try:
            # Convert or copy raw byte buffer
            chunk = bytes(indata)
            try:
                self._audio_queue.put_nowait(chunk)
            except queue.Full:
                # Discard oldest chunk to prioritize live, real-time speech
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    pass
                self._audio_queue.put_nowait(chunk)
        except Exception as err:
            logger.error("Unexpected error in audio callback: %s", err)
            if self.on_error:
                self.on_error(err)

    def start(self) -> bool:
        """Initialize and start the sounddevice RawInputStream."""
        with self._lock:
            if self._is_running:
                return True

            try:
                import sounddevice as sd

                self._stream = sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    channels=self.channels,
                    dtype=DTYPE,
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._is_running = True
                logger.info(
                    "Audio capture stream active: %d Hz, %d channel(s), blocksize=%d",
                    self.sample_rate,
                    self.channels,
                    self.block_size,
                )
                return True
            except Exception as err:
                logger.error("Failed to start sounddevice audio stream: %s", err)
                self._is_running = False
                if self.on_error:
                    self.on_error(err)
                return False

    def stop(self) -> None:
        """Stop and close the sounddevice stream."""
        with self._lock:
            if self._is_running:
                try:
                    if self._stream:
                        self._stream.stop()
                        self._stream.close()
                except Exception as err:
                    logger.debug("Error while closing audio stream: %s", err)
                finally:
                    self._stream = None
                    self._is_running = False
                    logger.info("Audio capture stream stopped.")

            # Drain queue to preserve privacy (PRIV-001)
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

    def get_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """Fetch the next available PCM chunk from the in-memory queue."""
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def inject_synthetic_chunk(self, chunk: bytes) -> None:
        """Helper method for headless automated testing and PCM simulation."""
        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            self._audio_queue.put_nowait(chunk)