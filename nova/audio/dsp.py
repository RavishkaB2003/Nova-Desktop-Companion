"""
Project NOVA - Acoustic Digital Signal Processing Subsystem
Provides sub-25ms acoustic impulse click detection (FR-013, NFR-001),
plosive acoustic gating (FR-014), and continuous voiced vowel pitch tracking (FR-016).
Enforces PRIV-001: In-memory ephemeral processing with zero disk writes.
"""

import logging
import time
from typing import Callable, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Constants for impulse detection (FR-013)
DEFAULT_SAMPLE_RATE = 16000
BANDPASS_LOW_HZ = 3000.0
BANDPASS_HIGH_HZ = 7999.0
DEFAULT_SNR_THRESHOLD_DB = 18.0
DEFAULT_MAX_DURATION_MS = 25.0
DEFAULT_PLOSIVE_GATE_MS = 150.0

# Constants for voiced pitch tracking (FR-016)
PITCH_MIN_HZ = 80.0
PITCH_MAX_HZ = 350.0
DEFAULT_PITCH_CORRELATION_THRESHOLD = 0.65
DEFAULT_MIN_SUSTAIN_MS = 150.0


def design_bandpass_filter(
    lowcut: float = BANDPASS_LOW_HZ,
    highcut: float = BANDPASS_HIGH_HZ,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    order: int = 2,
) -> Optional[np.ndarray]:
    """
    Precompute Second-Order Sections (SOS) bandpass filter (3kHz - 8kHz) using scipy.
    Returns SOS matrix, or None if scipy is unavailable.
    """
    try:
        from scipy.signal import butter
        nyquist = 0.5 * sample_rate
        low = max(100.0, lowcut) / nyquist
        high = min(nyquist - 1.0, highcut) / nyquist
        sos = butter(order, [low, high], btype="bandpass", output="sos")
        return sos
    except Exception as exc:
        logger.warning("scipy.signal.butter unavailable for DSP filter: %s", exc)
        return None


class AcousticImpulseDetector:
    """
    Sub-25ms acoustic impulse detector for mouth clicks and tongue pops (FR-013, NFR-001).
    Applies 3-8kHz bandpass filtering, dynamic noise floor estimation,
    transient SNR ratio gating (>18dB), transient duration check (<25ms),
    and plosive acoustic gating (FR-014).
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        snr_threshold_db: float = DEFAULT_SNR_THRESHOLD_DB,
        max_duration_ms: float = DEFAULT_MAX_DURATION_MS,
        min_spectral_ratio: float = 0.25,
        plosive_gate_ms: float = DEFAULT_PLOSIVE_GATE_MS,
        on_impulse: Optional[Callable[[], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.snr_threshold_db = snr_threshold_db
        self.max_duration_ms = max_duration_ms
        self.min_spectral_ratio = min_spectral_ratio
        self.plosive_gate_ms = plosive_gate_ms
        self.on_impulse = on_impulse

        self._sos = design_bandpass_filter(
            lowcut=BANDPASS_LOW_HZ,
            highcut=BANDPASS_HIGH_HZ,
            sample_rate=self.sample_rate,
            order=2,
        )

        # Dynamic noise floor tracker (exponential moving average in RMS)
        self._noise_floor_rms = 50.0
        self._noise_alpha = 0.05  # Slow adaptation
        self._gated_until: float = 0.0
        self._last_impulse_time: float = 0.0
        self._refractory_period_s = 0.10  # 100ms debounce between clicks

    def notify_speech_detected(self, duration_ms: Optional[float] = None) -> None:
        """
        Plosive acoustic gating (FR-014): Mute impulse detector for 150ms
        following spoken word recognition to suppress plosive false positives.
        """
        gate_ms = duration_ms if duration_ms is not None else self.plosive_gate_ms
        self._gated_until = time.monotonic() + (gate_ms / 1000.0)
        logger.debug("Plosive gate engaged for %.1f ms", gate_ms)

    @property
    def is_gated(self) -> bool:
        """Check if plosive acoustic gate is currently active."""
        return time.monotonic() < self._gated_until

    def process_pcm_chunk(self, chunk: bytes) -> bool:
        """
        Ingests a 16-bit mono PCM buffer, filters high-frequency transients,
        and fires on_impulse if criteria are satisfied.
        Returns True if an impulse was detected and triggered.
        """
        if not chunk:
            return False

        now = time.monotonic()
        # Check plosive gate
        if now < self._gated_until:
            return False

        # Debounce refractory period
        if (now - self._last_impulse_time) < self._refractory_period_s:
            return False

        # Convert raw PCM int16 to float32 numpy array
        signal = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if len(signal) == 0:
            return False

        # Apply 3kHz - 8kHz bandpass filter
        if self._sos is not None:
            try:
                from scipy.signal import sosfilt
                filtered = sosfilt(self._sos, signal)
            except Exception:
                filtered = signal
        else:
            filtered = signal

        # Calculate peak amplitude and RMS energy of chunk
        peak_val = np.max(np.abs(filtered))
        chunk_rms = np.sqrt(np.mean(filtered ** 2) + 1e-9)

        # Adapt noise floor if signal is at calm baseline
        if peak_val < (self._noise_floor_rms * 3.0):
            self._noise_floor_rms = (
                self._noise_alpha * chunk_rms
                + (1.0 - self._noise_alpha) * self._noise_floor_rms
            )
            self._noise_floor_rms = max(10.0, self._noise_floor_rms)

        # FR-013: High-frequency spectral concentration (3kHz - 8kHz)
        raw_energy = np.mean(signal ** 2) + 1e-9
        filtered_energy = np.mean(filtered ** 2) + 1e-9
        spectral_ratio = filtered_energy / raw_energy

        if spectral_ratio < self.min_spectral_ratio:
            return False

        # Compute SNR ratio in dB relative to dynamic noise floor
        snr_db = 20.0 * np.log10((peak_val + 1e-9) / (self._noise_floor_rms + 1e-9))

        if snr_db < self.snr_threshold_db:
            return False

        # Verify transient duration (<25ms)
        # 25ms in samples = (max_duration_ms / 1000.0) * sample_rate
        max_samples = int((self.max_duration_ms / 1000.0) * self.sample_rate)
        half_peak = peak_val * 0.5
        above_indices = np.where(np.abs(filtered) >= half_peak)[0]

        if len(above_indices) > 0:
            transient_span = above_indices[-1] - above_indices[0] + 1
            if transient_span > max_samples:
                # Sustained tone or wide noise burst, reject
                return False

        # Valid impulse qualified
        self._last_impulse_time = now
        logger.info(
            "Acoustic impulse detected! SNR: %.1f dB (floor: %.1f, peak: %.1f)",
            snr_db,
            self._noise_floor_rms,
            peak_val,
        )

        if self.on_impulse:
            try:
                self.on_impulse()
            except Exception as exc:
                logger.exception("Error in impulse callback: %s", exc)

        return True


class VoicedPitchTracker:
    """
    Continuous voiced vowel pitch tracker (FR-016).
    Computes Normalized Autocorrelation Function (NACF) in the human pitch
    range (80Hz - 350Hz) to detect sustained voiced vocalizations (r_max >= 0.65, >150ms)
    for continuous cursor gliding in canvas mode.
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        min_pitch_hz: float = PITCH_MIN_HZ,
        max_pitch_hz: float = PITCH_MAX_HZ,
        correlation_threshold: float = DEFAULT_PITCH_CORRELATION_THRESHOLD,
        min_sustain_ms: float = DEFAULT_MIN_SUSTAIN_MS,
        on_glide_start: Optional[Callable[[], None]] = None,
        on_glide_tick: Optional[Callable[[float], None]] = None,
        on_glide_stop: Optional[Callable[[], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.min_pitch_hz = min_pitch_hz
        self.max_pitch_hz = max_pitch_hz
        self.correlation_threshold = correlation_threshold
        self.min_sustain_ms = min_sustain_ms

        self.on_glide_start = on_glide_start
        self.on_glide_tick = on_glide_tick
        self.on_glide_stop = on_glide_stop

        # Lag bounds for pitch search
        self.min_lag = int(self.sample_rate / self.max_pitch_hz)
        self.max_lag = int(self.sample_rate / self.min_pitch_hz)

        self._is_armed = False
        self._is_gliding = False
        self._voiced_duration_s = 0.0
        self._unvoiced_duration_s = 0.0
        self._last_process_time: float = 0.0

    @property
    def is_armed(self) -> bool:
        return self._is_armed

    def arm(self) -> None:
        """Arm pitch tracker (active strictly in GLIDE_ACTIVE)."""
        self._is_armed = True
        self._voiced_duration_s = 0.0
        self._unvoiced_duration_s = 0.0
        self._is_gliding = False
        self._last_process_time = time.monotonic()
        logger.debug("Voiced pitch tracker armed for gliding.")

    def disarm(self) -> None:
        """Disarm pitch tracker and halt any active glide."""
        if self._is_gliding and self.on_glide_stop:
            try:
                self.on_glide_stop()
            except Exception as exc:
                logger.exception("Error in glide stop callback: %s", exc)

        self._is_armed = False
        self._is_gliding = False
        self._voiced_duration_s = 0.0
        self._unvoiced_duration_s = 0.0
        logger.debug("Voiced pitch tracker disarmed.")

    def compute_nacf_peak(self, signal: np.ndarray) -> Tuple[float, float]:
        """
        Compute peak Normalized Autocorrelation (r_max) and corresponding pitch (Hz)
        within the fundamental frequency window [80Hz, 350Hz].
        """
        n = len(signal)
        if n <= self.max_lag:
            return 0.0, 0.0

        # Energy of signal
        total_energy = np.sum(signal ** 2)
        if total_energy < 1e-4:
            return 0.0, 0.0

        best_r = 0.0
        best_lag = 0

        # Search lags in [min_lag, max_lag]
        for lag in range(self.min_lag, min(self.max_lag + 1, n // 2)):
            seg1 = signal[: n - lag]
            seg2 = signal[lag:n]
            denom = np.sqrt(np.sum(seg1 ** 2) * np.sum(seg2 ** 2)) + 1e-9
            r = float(np.sum(seg1 * seg2) / denom)
            if r > best_r:
                best_r = r
                best_lag = lag

        pitch_hz = (self.sample_rate / best_lag) if best_lag > 0 else 0.0
        return best_r, pitch_hz

    def process_pcm_chunk(self, chunk: bytes) -> bool:
        """
        Processes audio chunk when armed. Tracks sustained voiced vowel duration.
        Returns True if glide is actively running.
        """
        if not self._is_armed or not chunk:
            return False

        now = time.monotonic()
        dt = (now - self._last_process_time) if self._last_process_time > 0 else 0.02
        self._last_process_time = now

        signal = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        r_max, pitch = self.compute_nacf_peak(signal)

        is_voiced = r_max >= self.correlation_threshold

        if is_voiced:
            self._voiced_duration_s += dt
            self._unvoiced_duration_s = 0.0

            if self._voiced_duration_s >= (self.min_sustain_ms / 1000.0):
                if not self._is_gliding:
                    self._is_gliding = True
                    logger.info("Vowel glide triggered! Pitch: %.1f Hz, r_max: %.2f", pitch, r_max)
                    if self.on_glide_start:
                        self.on_glide_start()

                if self.on_glide_tick:
                    self.on_glide_tick(dt)
        else:
            self._unvoiced_duration_s += dt
            # If silence/unvoiced persists > 100ms, stop glide
            if self._unvoiced_duration_s > 0.10:
                self._voiced_duration_s = 0.0
                if self._is_gliding:
                    self._is_gliding = False
                    logger.info("Vowel glide halted (unvoiced frame).")
                    if self.on_glide_stop:
                        self.on_glide_stop()

        return self._is_gliding
