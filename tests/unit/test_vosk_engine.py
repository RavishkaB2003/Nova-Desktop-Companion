"""
Project NOVA - Unit Tests for Vosk Speech Engine
"""

import time
import unittest
from nova.audio.capture import AudioCaptureManager
from nova.core.enums import SystemEventType
from nova.speech.vosk_engine import VoskSpeechEngine


class TestVoskEngine(unittest.TestCase):
    def test_keyword_event_dispatch_wake(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )

        engine._handle_recognized_text("hey nova")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.WAKE_WORD_DETECTED)
        self.assertEqual(events[0].payload, {"phrase": "hey nova"})

    def test_keyword_event_dispatch_sleep(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )

        engine._handle_recognized_text("sleep")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.SLEEP_TRIGGERED)

    def test_keyword_event_dispatch_halt(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )

        engine._handle_recognized_text("halt")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.EMERGENCY_HALT)

    def test_debounce_suppression(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.5,
        )

        # First trigger
        engine._handle_recognized_text("hey nova")
        self.assertEqual(len(events), 1)

        # Immediate second trigger within debounce window
        engine._handle_recognized_text("hey nova")
        self.assertEqual(len(events), 1)

        # Wait until debounce window expires
        time.sleep(0.55)
        engine._handle_recognized_text("hey nova")
        self.assertEqual(len(events), 2)

    def test_worker_thread_lifecycle(self):
        audio_mgr = AudioCaptureManager()
        engine = VoskSpeechEngine(model_path="non_existent_path")

        self.assertFalse(engine.is_running)
        self.assertTrue(engine.start(audio_mgr))
        self.assertTrue(engine.is_running)

        engine.stop()
        self.assertFalse(engine.is_running)


if __name__ == "__main__":
    unittest.main()
