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

    def test_different_keywords_not_debounced(self):
        """Different commands are not blocked by prior words (e.g. 'laser' then 'lock')."""
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.5,
        )

        engine._handle_recognized_text("laser")
        self.assertEqual(len(events), 1)

        time.sleep(0.06)
        engine._handle_recognized_text("lock")
        self.assertEqual(len(events), 2)

    def test_instant_partial_recognition_for_crosshair_lock_tokens(self):
        """Verify lock, hit, freeze, and mark trigger instantly on partial results and reset recognizer."""
        from unittest.mock import MagicMock
        import json

        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        engine._recognizer = mock_rec

        # 1. Test "lock" instant trigger
        mock_rec.PartialResult.return_value = json.dumps({"partial": "lock"})
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "lock")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[-1].event_type, SystemEventType.COMMAND_DETECTED)
        self.assertEqual(events[-1].payload, {"phrase": "lock"})
        mock_rec.Reset.assert_called()

        # 2. Test "hit" instant trigger
        time.sleep(0.1)
        mock_rec.Reset.reset_mock()
        mock_rec.PartialResult.return_value = json.dumps({"partial": "hit"})
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "hit")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].payload, {"phrase": "hit"})
        mock_rec.Reset.assert_called()

        # 3. Test non-instant word (e.g. "tag") is NOT triggered on partial
        mock_rec.Reset.reset_mock()
        mock_rec.PartialResult.return_value = json.dumps({"partial": "tag"})
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertIsNone(res)
        self.assertEqual(len(events), 2)  # No new event
        mock_rec.Reset.assert_not_called()

    def test_instant_partial_recognition_for_click_tokens(self):
        """Verify click, double click, right click trigger instantly on partial results."""
        from unittest.mock import MagicMock
        import json

        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        engine._recognizer = mock_rec

        # 1. "click"
        mock_rec.PartialResult.return_value = json.dumps({"partial": "click"})
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "click")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[-1].payload, {"phrase": "click"})
        mock_rec.Reset.assert_called()

        # 2. "double click"
        time.sleep(0.1)
        mock_rec.Reset.reset_mock()
        mock_rec.PartialResult.return_value = json.dumps({"partial": "double click"})
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "double click")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1].payload, {"phrase": "double click"})
        mock_rec.Reset.assert_called()

    def test_keyword_event_dispatch_activate(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )
        engine._handle_recognized_text("activate")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.ACTIVATE_TRIGGERED)
        self.assertEqual(events[0].payload, {"phrase": "activate"})

    def test_keyword_event_dispatch_deactivate(self):
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.1,
        )
        engine._handle_recognized_text("deactivate")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.DEACTIVATE_TRIGGERED)
        self.assertEqual(events[0].payload, {"phrase": "deactivate"})

    def test_low_confidence_rejection(self):
        """Utterances with average word confidence below threshold must be rejected."""
        from unittest.mock import MagicMock
        import json

        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            confidence_threshold=0.65,
        )
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        # Simulate a low-confidence false positive (e.g. noise mapped to 'sleep' with 0.35 confidence)
        mock_rec.Result.return_value = json.dumps({
            "text": "sleep",
            "result": [{"word": "sleep", "conf": 0.35}],
        })
        engine._recognizer = mock_rec

        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertIsNone(res)
        self.assertEqual(len(events), 0)

        # High confidence match (0.90) must pass
        mock_rec.Result.return_value = json.dumps({
            "text": "sleep",
            "result": [{"word": "sleep", "conf": 0.90}],
        })
        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "sleep")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.SLEEP_TRIGGERED)

    def test_sea_or_asleep_does_not_sleep(self):
        """Words like 'sea' or 'asleep' must NOT trigger SLEEP_TRIGGERED."""
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.0,
        )
        engine._handle_recognized_text("sea")
        self.assertEqual(events[-1].event_type, SystemEventType.COMMAND_DETECTED)
        engine._handle_recognized_text("asleep")
        self.assertEqual(events[-1].event_type, SystemEventType.COMMAND_DETECTED)

    def test_supernova_does_not_wake(self):
        """'supernova' must not trigger wake word detection."""
        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
            debounce_seconds=0.0,
        )
        engine._handle_recognized_text("supernova")
        self.assertEqual(events[-1].event_type, SystemEventType.COMMAND_DETECTED)

    def test_deactivate_partial_priority(self):
        """Partial result containing 'deactivate' must trigger DEACTIVATE_TRIGGERED, not ACTIVATE."""
        from unittest.mock import MagicMock
        import json

        events = []
        engine = VoskSpeechEngine(
            model_path="non_existent_path",
            on_event=lambda evt: events.append(evt),
        )
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        mock_rec.PartialResult.return_value = json.dumps({"partial": "deactivate"})
        engine._recognizer = mock_rec

        res = engine.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(res, "deactivate")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SystemEventType.DEACTIVATE_TRIGGERED)


if __name__ == "__main__":
    unittest.main()


