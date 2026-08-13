"""Tests for core/stt.py (local whisper with Google fallback) and the
barge-in stop-phrase matcher in core/assistant.py."""

import unittest
from unittest.mock import MagicMock, patch

import core.stt as stt
from core.assistant import is_stop_phrase


class LocalSttTests(unittest.TestCase):
    def test_transcribe_local_none_without_model(self):
        """No local engine -> transcribe_local returns None (no crash)."""
        with patch.object(stt, "_load_model", return_value=None):
            self.assertIsNone(stt.transcribe_local(MagicMock()))

    def test_transcribe_local_uses_model(self):
        """A working local model transcribes the audio samples."""
        fake_model = MagicMock()
        seg = MagicMock()
        seg.text = "Hello world"
        fake_model.transcribe.return_value = ([seg], None)
        audio = MagicMock()
        audio.get_raw_data.return_value = b"\x00\x00" * 1600  # ~0.05s silence
        with patch.object(stt, "_load_model", return_value=fake_model):
            self.assertEqual(stt.transcribe_local(audio), "Hello world")

    def test_transcribe_local_boosts_quiet_audio(self):
        """Low-level (quiet) speech is amplified before reaching whisper,
        and short-command tuning flags are passed through."""
        import numpy as np
        import struct
        fake_model = MagicMock()
        seg = MagicMock()
        seg.text = "hi"
        fake_model.transcribe.return_value = ([seg], None)
        # ~0.2s of quiet speech: int16 samples peaking around 0.02 (quiet)
        quiet = struct.pack("<%dh" % 3200, *([600] * 3200))
        audio = MagicMock()
        audio.get_raw_data.return_value = quiet
        with patch.object(stt, "_load_model", return_value=fake_model):
            self.assertEqual(stt.transcribe_local(audio), "hi")
        args, kwargs = fake_model.transcribe.call_args
        samples = args[0]
        # 600/32768 ~= 0.018 -> boosted by the capped gain, well above 0.03
        self.assertGreater(float(np.max(np.abs(samples))), 0.03)
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertIn("voice command", kwargs["initial_prompt"])

    def test_transcribe_falls_back_to_google(self):
        """Local says nothing -> recognizer.recognize_google is used."""
        audio = MagicMock()
        recognizer = MagicMock()
        recognizer.recognize_google.return_value = "hey jarvis"
        with patch.object(stt, "transcribe_local", return_value=None):
            self.assertEqual(stt.transcribe(audio, recognizer), "hey jarvis")
        recognizer.recognize_google.assert_called_once()

    def test_transcribe_prefers_local(self):
        """Local result wins; Google is not even called."""
        audio = MagicMock()
        recognizer = MagicMock()
        with patch.object(stt, "transcribe_local",
                          return_value="hello there"):
            self.assertEqual(stt.transcribe(audio, recognizer),
                             "hello there")
        recognizer.recognize_google.assert_not_called()

    def test_transcribe_total_failure_returns_none(self):
        audio = MagicMock()
        recognizer = MagicMock()
        recognizer.recognize_google.side_effect = Exception("no network")
        with patch.object(stt, "transcribe_local", return_value=None):
            self.assertIsNone(stt.transcribe(audio, recognizer))


class StopPhraseTests(unittest.TestCase):
    def test_accepts_stop_phrases(self):
        for phrase in ("stop", "stop it", "stop that", "stop talking",
                       "shut up", "be quiet", "quiet", "cancel",
                       "cancel that", "enough", "that's enough",
                       "cut it out", "silence", "hush"):
            self.assertTrue(is_stop_phrase(phrase), phrase)

    def test_tolerates_punctuation_and_case(self):
        self.assertTrue(is_stop_phrase(" Stop! "))
        self.assertTrue(is_stop_phrase("SHUT UP"))
        self.assertTrue(is_stop_phrase("stop, please"))

    def test_rejects_ordinary_speech(self):
        for phrase in ("stop the car", "what time is it", "play despacito",
                       "stopwatch", "stoplight", "i love you",
                       "stop being so loud", ""):
            self.assertFalse(is_stop_phrase(phrase), phrase)

    def test_rejects_empty(self):
        self.assertFalse(is_stop_phrase(None))
        self.assertFalse(is_stop_phrase("   "))


if __name__ == "__main__":
    unittest.main()
