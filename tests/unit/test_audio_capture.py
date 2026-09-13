"""
Project NOVA - Unit Tests for Ephemeral Audio Capture
"""

import unittest
from nova.audio.capture import (
    AudioCaptureManager,
    BLOCK_SIZE_SAMPLES,
    CHANNELS,
    QUEUE_MAX_SIZE,
    SAMPLE_RATE_HZ,
)


class TestAudioCapture(unittest.TestCase):
    def setUp(self):
        self.mgr = AudioCaptureManager()

    def tearDown(self):
        self.mgr.stop()

    def test_default_acoustic_constants(self):
        self.assertEqual(SAMPLE_RATE_HZ, 16000)
        self.assertEqual(CHANNELS, 1)
        self.assertEqual(BLOCK_SIZE_SAMPLES, 1600)  # 100ms
        self.assertEqual(QUEUE_MAX_SIZE, 50)

    def test_initial_state(self):
        self.assertFalse(self.mgr.is_running)
        self.assertIsNone(self.mgr.get_chunk(timeout=0.01))

    def test_synthetic_injection_and_retrieval(self):
        dummy_chunk = b"\x00\x00" * 1600
        self.mgr.inject_synthetic_chunk(dummy_chunk)
        retrieved = self.mgr.get_chunk(timeout=0.1)
        self.assertEqual(retrieved, dummy_chunk)
        self.assertIsNone(self.mgr.get_chunk(timeout=0.01))

    def test_queue_overflow_drop_oldest_policy(self):
        # Fill queue to maximum capacity
        for i in range(QUEUE_MAX_SIZE):
            chunk = i.to_bytes(2, "little") * 1600
            self.mgr.inject_synthetic_chunk(chunk)

        # Inject one more chunk; should drop oldest chunk (index 0)
        new_chunk = (999).to_bytes(2, "little") * 1600
        self.mgr.inject_synthetic_chunk(new_chunk)

        # First retrieved chunk should be index 1, not index 0
        first_retrieved = self.mgr.get_chunk(timeout=0.05)
        expected_chunk_1 = (1).to_bytes(2, "little") * 1600
        self.assertEqual(first_retrieved, expected_chunk_1)

    def test_privacy_draining_on_stop(self):
        dummy_chunk = b"\x01\x02" * 1600
        self.mgr.inject_synthetic_chunk(dummy_chunk)
        self.mgr.stop()
        # PRIV-001: Audio queue must be completely drained on stop
        self.assertIsNone(self.mgr.get_chunk(timeout=0.01))


if __name__ == "__main__":
    unittest.main()
