"""Tests for the wake-word transcript matcher (no audio hardware touched)."""

import unittest

from core.wake_word import WakeWordListener


class WakeTextTests(unittest.TestCase):
    def make(self, botname="jarvis"):
        return WakeWordListener(botname=botname)

    def test_exact_hey(self):
        self.assertTrue(self.make()._is_wake_text("hey jarvis"))

    def test_plain_name(self):
        self.assertTrue(self.make()._is_wake_text("jarvis"))

    def test_name_with_followup_command(self):
        self.assertTrue(
            self.make()._is_wake_text("hey jarvis what's the weather"))

    def test_punctuation_and_caps(self):
        self.assertTrue(self.make()._is_wake_text("Hey, Jarvis!"))

    def test_filler_prefix(self):
        self.assertTrue(self.make()._is_wake_text("okay hey jarvis"))

    def test_fuzzy_transcriptions(self):
        """Google often mangles the name — those must still wake JARVIS."""
        w = self.make()
        self.assertTrue(w._is_wake_text("hey jarvish"))
        self.assertTrue(w._is_wake_text("hey jervis"))
        self.assertTrue(w._is_wake_text("hey jarvisss"))

    def test_name_buried_after_filler(self):
        self.assertTrue(self.make()._is_wake_text("hey there jarvis"))

    def test_empty_transcript(self):
        self.assertFalse(self.make()._is_wake_text(""))
        self.assertFalse(self.make()._is_wake_text("   "))

    def test_not_a_wake(self):
        w = self.make()
        self.assertFalse(w._is_wake_text("hey siri"))
        self.assertFalse(w._is_wake_text("hello there"))
        self.assertFalse(w._is_wake_text("what's the weather"))
        self.assertFalse(w._is_wake_text("okay google"))

    def test_custom_botname(self):
        w = WakeWordListener(botname="alexa")
        self.assertTrue(w._is_wake_text("hey alexa"))
        self.assertFalse(w._is_wake_text("hey jarvis"))


if __name__ == "__main__":
    unittest.main()
