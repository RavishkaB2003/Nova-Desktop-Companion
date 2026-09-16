"""
Project NOVA - Unit Tests for Unconstrained Voice Dictation Pipeline (FR-020, FR-021, PRIV-002)
"""

import json
import time
import unittest
from unittest.mock import MagicMock
from nova.speech.dictation_pipeline import DictationPipeline


class TestDictationPipeline(unittest.TestCase):
    def test_mock_mode_when_model_missing(self):
        pipeline = DictationPipeline(model_path="non_existent_path")
        self.assertFalse(pipeline.is_active)
        pipeline.start_dictation()
        self.assertTrue(pipeline.is_active)
        pipeline.stop_dictation()
        self.assertFalse(pipeline.is_active)

    def test_full_recognition_dispatches_text(self):
        received_text = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_text_ready=lambda t: received_text.append(t),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "testing dictation pipeline"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertEqual(res, "testing dictation pipeline")
        self.assertEqual(received_text, ["testing dictation pipeline"])
        self.assertTrue(pipeline.is_active)

    def test_emergency_halt_in_full_result_triggers_halt_callback(self):
        halt_called = []
        received_text = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            arming_grace_period_s=0.0,
            on_text_ready=lambda t: received_text.append(t),
            on_emergency_halt=lambda: halt_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "halt"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIsNone(res)
        self.assertEqual(len(halt_called), 1)
        self.assertEqual(len(received_text), 0)
        # Pipeline should be auto-stopped
        self.assertFalse(pipeline.is_active)

    def test_speculative_partial_result_does_not_halt_dictation(self):
        """Speculative partial hypotheses (e.g. 'cancel' or 'halt' intermediate guess) must NOT trip emergency halt."""
        halt_called = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            arming_grace_period_s=0.0,
            on_emergency_halt=lambda: halt_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        mock_rec.PartialResult.return_value = json.dumps({"partial": "cancel"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIsNone(res)
        self.assertEqual(len(halt_called), 0)
        self.assertTrue(pipeline.is_active)

    def test_reset_grace_timer(self):
        """reset_grace_timer re-anchors grace period start time to now."""
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            arming_grace_period_s=1.5,
        )
        pipeline.start_dictation()
        pipeline._start_time = time.monotonic() - 2.0  # Expired
        pipeline.reset_grace_timer()
        # Should now be within grace period again
        self.assertLess(time.monotonic() - pipeline._start_time, 0.5)


    def test_emergency_halt_during_grace_period_suppressed(self):
        """During the arming grace window, acoustic residue does not trip emergency halt."""
        halt_called = []
        received_text = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            arming_grace_period_s=1.5,
            on_text_ready=lambda t: received_text.append(t),
            on_emergency_halt=lambda: halt_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "halt"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        # Feed chunk immediately (within 1.5s grace window)
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        # Halt was suppressed by grace window
        self.assertEqual(len(halt_called), 0)
        self.assertTrue(pipeline.is_active)

    def test_natural_sentence_containing_cancel_is_not_halted(self):
        """SRS.md FR-19: Sentences containing 'cancel' as vocabulary transcribe normally."""
        halt_called = []
        received_text = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            arming_grace_period_s=0.0,
            on_text_ready=lambda t: received_text.append(t),
            on_emergency_halt=lambda: halt_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "please cancel my dentist appointment"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertEqual(res, "please cancel my dentist appointment")
        self.assertEqual(received_text, ["please cancel my dentist appointment"])
        self.assertEqual(len(halt_called), 0)
        self.assertTrue(pipeline.is_active)

    def test_continuous_dictation_multiple_phrases(self):
        """User can dictate multiple clauses/sentences without session premature exit."""
        received_text = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_text_ready=lambda t: received_text.append(t),
        )

        mock_rec = MagicMock()
        pipeline._recognizer = mock_rec
        pipeline.start_dictation()

        # Clause 1
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "first sentence"})
        pipeline.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(received_text[-1], "first sentence")
        self.assertTrue(pipeline.is_active)

        # Clause 2
        mock_rec.Result.return_value = json.dumps({"text": "second sentence"})
        pipeline.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(received_text[-1], "second sentence")
        self.assertTrue(pipeline.is_active)

        # Clause 3 concludes with 'done'
        mock_rec.Result.return_value = json.dumps({"text": "third sentence done"})
        pipeline.process_pcm_chunk(b"\x00" * 3200)
        self.assertEqual(received_text[-1], "third sentence")
        self.assertFalse(pipeline.is_active)

    def test_stop_command_at_end_of_utterance(self):
        received_text = []
        completed = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_text_ready=lambda t: received_text.append(t),
            on_dictation_complete=lambda: completed.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "enter address stop"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertEqual(res, "enter address")
        self.assertEqual(received_text, ["enter address"])
        self.assertEqual(len(completed), 1)
        self.assertFalse(pipeline.is_active)

    def test_silence_auto_commit(self):
        completed = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            silence_timeout_s=0.1,  # 100ms for fast test
            on_dictation_complete=lambda: completed.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        mock_rec.PartialResult.return_value = json.dumps({"partial": "speaking"})
        mock_rec.FinalResult.return_value = json.dumps({"text": "speaking final"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        pipeline.process_pcm_chunk(b"\x00" * 3200)
        self.assertTrue(pipeline.is_active)

        # Wait past silence timeout
        time.sleep(0.15)
        # Feed next silent chunk
        mock_rec.PartialResult.return_value = json.dumps({"partial": ""})
        pipeline.process_pcm_chunk(b"\x00" * 3200)

        # Pipeline should have auto-committed and stopped
        self.assertFalse(pipeline.is_active)
        self.assertEqual(len(completed), 1)

    def test_click_command_in_full_result_triggers_click_callback(self):
        click_called = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_click_command=lambda: click_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "click"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIsNone(res)
        self.assertEqual(len(click_called), 1)
        self.assertFalse(pipeline.is_active)

    def test_click_command_in_partial_result_triggers_click_callback(self):
        click_called = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_click_command=lambda: click_called.append(True),
        )

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = False
        mock_rec.PartialResult.return_value = json.dumps({"partial": "click"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIsNone(res)
        self.assertEqual(len(click_called), 1)
        self.assertFalse(pipeline.is_active)

    def test_shared_model_initialization(self):
        mock_model = MagicMock()
        with unittest.mock.patch("vosk.KaldiRecognizer") as mock_rec_cls:
            pipeline = DictationPipeline(model=mock_model)
            self.assertEqual(pipeline._model, mock_model)
    def test_grace_period_halt_does_not_type_halt(self):
        """Halt spoken during 1.5s grace period must be discarded, not typed into target (F-08)."""
        received = []
        pipeline = DictationPipeline(
            model_path="non_existent_path",
            on_text_ready=lambda t: received.append(t),
        )
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = json.dumps({"text": "halt"})
        pipeline._recognizer = mock_rec

        pipeline.start_dictation()  # Grace period active
        res = pipeline.process_pcm_chunk(b"\x00" * 3200)

        self.assertIsNone(res)
        self.assertEqual(len(received), 0)  # "Halt" was NOT dispatched to editor
        self.assertTrue(pipeline.is_active)  # Remains active


if __name__ == "__main__":
    unittest.main()

