"""
Unit tests for NOVA Digital Signal Processing Subsystem (MOD-003)
Verifies:
- FR-013: Sub-25ms acoustic impulse click detection (3-8kHz, <25ms duration, >18dB SNR)
- FR-014: Plosive acoustic gating (150ms mute on spoken token)
- FR-016: Voiced vowel pitch autocorrelation tracking (r_max >= 0.65, >150ms sustain)
- NFR-001: Sub-25ms DSP processing latency
"""

import time
import unittest
import numpy as np

from nova.audio.dsp import (
    AcousticImpulseDetector,
    VoicedPitchTracker,
    design_bandpass_filter,
)


def generate_transient(
    duration_ms: float = 10.0,
    center_freq_hz: float = 5000.0,
    sample_rate: int = 16000,
    amplitude: float = 20000.0,
) -> bytes:
    """Generate synthetic high-frequency transient burst (tongue pop / lip click)."""
    n_samples = int((duration_ms / 1000.0) * sample_rate)
    t = np.linspace(0, duration_ms / 1000.0, n_samples, endpoint=False)
    # Hann window envelope for sharp attack and quick decay
    window = np.hanning(n_samples)
    carrier = np.sin(2 * np.pi * center_freq_hz * t)
    signal = amplitude * window * carrier
    # Pad to standard chunk size (1600 samples = 100ms at 16kHz)
    padded = np.zeros(1600, dtype=np.float32)
    start = 100
    padded[start : start + n_samples] = signal
    return padded.astype(np.int16).tobytes()


def generate_voiced_vowel(
    duration_ms: float = 100.0,
    pitch_hz: float = 150.0,
    sample_rate: int = 16000,
    amplitude: float = 10000.0,
) -> bytes:
    """Generate synthetic voiced vowel waveform with fundamental and harmonics."""
    n_samples = int((duration_ms / 1000.0) * sample_rate)
    t = np.linspace(0, duration_ms / 1000.0, n_samples, endpoint=False)
    # Harmonic series characteristic of human voiced vowels
    signal = (
        amplitude * np.sin(2 * np.pi * pitch_hz * t)
        + 0.5 * amplitude * np.sin(2 * np.pi * 2 * pitch_hz * t)
        + 0.25 * amplitude * np.sin(2 * np.pi * 3 * pitch_hz * t)
    )
    return signal.astype(np.int16).tobytes()


class TestAcousticImpulseDetector(unittest.TestCase):
    """Test suite for AcousticImpulseDetector (FR-013, FR-014, NFR-001)."""

    def setUp(self):
        self.impulse_fired = False
        self.impulse_count = 0

        def on_impulse():
            self.impulse_fired = True
            self.impulse_count += 1

        self.detector = AcousticImpulseDetector(
            sample_rate=16000,
            snr_threshold_db=18.0,
            max_duration_ms=25.0,
            plosive_gate_ms=150.0,
            on_impulse=on_impulse,
        )

    def test_filter_design(self):
        """Verify 2nd-order Butterworth bandpass filter coefficients (3kHz - 8kHz)."""
        sos = design_bandpass_filter(3000, 7999, 16000, order=2)
        self.assertIsNotNone(sos)
        self.assertEqual(sos.shape, (2, 6))

    def test_detect_mouth_click_transient(self):
        """FR-013: Sharp high-frequency transient (>18dB SNR, <25ms) triggers impulse."""
        # Establish calm noise floor first
        silence = np.zeros(1600, dtype=np.int16).tobytes()
        self.detector.process_pcm_chunk(silence)

        # Generate a 12ms click centered at 5kHz
        click_chunk = generate_transient(duration_ms=12.0, center_freq_hz=5000.0, amplitude=25000.0)
        detected = self.detector.process_pcm_chunk(click_chunk)

        self.assertTrue(detected)
        self.assertTrue(self.impulse_fired)
        self.assertEqual(self.impulse_count, 1)

    def test_reject_low_amplitude_noise(self):
        """Quiet noise (< 18dB above noise floor) must NOT trigger impulse."""
        noise = (np.random.randn(1600) * 10.0).astype(np.int16).tobytes()
        detected = self.detector.process_pcm_chunk(noise)
        self.assertFalse(detected)
        self.assertFalse(self.impulse_fired)

    def test_reject_low_frequency_voice_or_rumble(self):
        """Low-frequency sound (200Hz) filtered out by 3-8kHz bandpass filter."""
        # 200Hz tone with high amplitude
        t = np.linspace(0, 0.1, 1600, endpoint=False)
        low_freq = (25000.0 * np.sin(2 * np.pi * 200.0 * t)).astype(np.int16).tobytes()

        detected = self.detector.process_pcm_chunk(low_freq)
        self.assertFalse(detected)
        self.assertFalse(self.impulse_fired)

    def test_reject_sustained_tone_exceeding_duration(self):
        """Tones sustained > 25ms (e.g. whistle or voiced sibilant) must be rejected."""
        # 80ms tone at 4kHz
        t = np.linspace(0, 0.1, 1600, endpoint=False)
        sustained = (20000.0 * np.sin(2 * np.pi * 4000.0 * t)).astype(np.int16).tobytes()

        detected = self.detector.process_pcm_chunk(sustained)
        self.assertFalse(detected)
        self.assertFalse(self.impulse_fired)

    def test_plosive_acoustic_gating(self):
        """FR-014: Gating suppresses impulse detection for 150ms after spoken token."""
        click_chunk = generate_transient(duration_ms=10.0, center_freq_hz=5500.0, amplitude=25000.0)

        # Notify speech recognized -> activates plosive gate
        self.detector.notify_speech_detected(duration_ms=150.0)
        self.assertTrue(self.detector.is_gated)

        # Click arriving during gate must be suppressed
        detected = self.detector.process_pcm_chunk(click_chunk)
        self.assertFalse(detected)
        self.assertFalse(self.impulse_fired)

        # Wait for gate to expire (>150ms)
        time.sleep(0.16)
        self.assertFalse(self.detector.is_gated)

        # Now click must be detected
        detected_after = self.detector.process_pcm_chunk(click_chunk)
        self.assertTrue(detected_after)
        self.assertTrue(self.impulse_fired)

    def test_dsp_latency_budget(self):
        """NFR-001: Total DSP processing latency per chunk must be <= 25ms (typically < 2ms)."""
        click_chunk = generate_transient(duration_ms=10.0, center_freq_hz=5000.0, amplitude=25000.0)

        t0 = time.perf_counter()
        self.detector.process_pcm_chunk(click_chunk)
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Must be well below 25ms budget
        self.assertLess(t_elapsed_ms, 25.0)


class TestVoicedPitchTracker(unittest.TestCase):
    """Test suite for VoicedPitchTracker (FR-016)."""

    def setUp(self):
        self.glide_started = False
        self.glide_stopped = False
        self.ticks = []

        def on_start():
            self.glide_started = True

        def on_tick(dt):
            self.ticks.append(dt)

        def on_stop():
            self.glide_stopped = True

        self.tracker = VoicedPitchTracker(
            sample_rate=16000,
            correlation_threshold=0.65,
            min_sustain_ms=150.0,
            on_glide_start=on_start,
            on_glide_tick=on_tick,
            on_glide_stop=on_stop,
        )

    def test_disarmed_by_default(self):
        """Tracker must remain inactive when not armed."""
        self.assertFalse(self.tracker.is_armed)
        vowel_chunk = generate_voiced_vowel(duration_ms=100.0, pitch_hz=160.0)
        result = self.tracker.process_pcm_chunk(vowel_chunk)
        self.assertFalse(result)
        self.assertFalse(self.glide_started)

    def test_sustained_voiced_vowel_triggers_glide(self):
        """FR-016: Sustaining pitch r_max >= 0.65 for >150ms triggers continuous glide."""
        self.tracker.arm()
        self.assertTrue(self.tracker.is_armed)

        # Generate 160Hz voiced vowel chunks (50ms chunks = 800 samples)
        chunk1 = generate_voiced_vowel(duration_ms=50.0, pitch_hz=160.0)

        # Feed consecutive chunks to exceed 150ms sustain threshold
        self.tracker.process_pcm_chunk(chunk1)
        time.sleep(0.06)
        self.tracker.process_pcm_chunk(chunk1)
        time.sleep(0.06)
        self.tracker.process_pcm_chunk(chunk1)
        time.sleep(0.06)
        self.tracker.process_pcm_chunk(chunk1)

        self.assertTrue(self.glide_started)
        self.assertGreater(len(self.ticks), 0)

    def test_unvoiced_noise_halts_glide(self):
        """Unvoiced noise does not trigger glide and halts active glide."""
        self.tracker.arm()
        noise = (np.random.randn(800) * 100.0).astype(np.int16).tobytes()

        # Simulate active glide
        self.tracker._is_gliding = True

        # Process unvoiced chunks with >100ms silence
        self.tracker.process_pcm_chunk(noise)
        time.sleep(0.12)
        self.tracker.process_pcm_chunk(noise)

        self.assertTrue(self.glide_stopped)
        self.assertFalse(self.tracker._is_gliding)


if __name__ == "__main__":
    unittest.main()
