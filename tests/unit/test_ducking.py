"""
Project NOVA - Unit Tests for Audio Ducking Manager and Chime Feedback
"""

import unittest
from nova.audio.ducking import AudioDuckingManager, play_audio_chime


class TestAudioDucking(unittest.TestCase):
    def setUp(self):
        self.mgr = AudioDuckingManager(duck_ratio=0.25)

    def tearDown(self):
        self.mgr.unduck()

    def test_initial_state(self):
        self.assertFalse(self.mgr.is_ducked)

    def test_duck_and_unduck_cycle(self):
        # Initial volume
        initial_vol = self.mgr.get_current_volume()

        # Duck audio
        success_duck = self.mgr.duck()
        self.assertTrue(success_duck)
        self.assertTrue(self.mgr.is_ducked)

        if initial_vol is not None and initial_vol > 0.05:
            ducked_vol = self.mgr.get_current_volume()
            self.assertIsNotNone(ducked_vol)
            self.assertLess(ducked_vol, initial_vol)

        # Unduck audio
        success_unduck = self.mgr.unduck()
        self.assertTrue(success_unduck)
        self.assertFalse(self.mgr.is_ducked)

        if initial_vol is not None:
            restored_vol = self.mgr.get_current_volume()
            self.assertAlmostEqual(restored_vol, initial_vol, places=2)

    def test_idempotent_ducking(self):
        self.mgr.duck()
        vol_after_first_duck = self.mgr.get_current_volume()

        # Calling duck again should not further reduce volume
        self.mgr.duck()
        vol_after_second_duck = self.mgr.get_current_volume()

        if vol_after_first_duck is not None and vol_after_second_duck is not None:
            self.assertAlmostEqual(vol_after_first_duck, vol_after_second_duck, places=2)

    def test_idempotent_unducking(self):
        # Calling unduck when not ducked should succeed as a no-op
        self.assertTrue(self.mgr.unduck())
        self.assertFalse(self.mgr.is_ducked)

    def test_play_audio_chime(self):
        # Synchronous chime calls should execute without exception
        self.assertTrue(play_audio_chime("wake", async_play=False))
        self.assertTrue(play_audio_chime("sleep", async_play=False))
        self.assertTrue(play_audio_chime("error", async_play=False))
        self.assertTrue(play_audio_chime("acknowledge", async_play=False))


if __name__ == "__main__":
    unittest.main()
