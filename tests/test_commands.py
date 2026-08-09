import unittest
from unittest.mock import patch

from _bootstrap import make_assistant


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.assistant = make_assistant()

    def test_identity_question(self):
        self.assertTrue(self.assistant.handle_command("who am i"))
        self.assertIn("tester", " ".join(self.assistant.tts.messages).lower())

    def test_memory_recall(self):
        self.assistant.memory = {"name": "alice", "interests": ["chess"]}
        self.assertTrue(self.assistant.handle_command("what do you know about me"))
        self.assertIn("alice", " ".join(self.assistant.tts.messages).lower())

    def test_learns_fact_without_touching_real_memory(self):
        with patch("core.assistant.save_memory") as save:
            self.assertTrue(
                self.assistant.handle_command("my name is testperson"))
        save.assert_called_once()
        self.assertEqual(self.assistant.memory.get("name"), "testperson")

    def test_offline_weather(self):
        with patch("core.assistant.have_internet", return_value=False):
            self.assertTrue(self.assistant.handle_command("weather"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_offline_news(self):
        with patch("core.assistant.have_internet", return_value=False):
            self.assertTrue(self.assistant.handle_command("news"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_offline_joke(self):
        with patch("core.assistant.have_internet", return_value=False):
            self.assertTrue(self.assistant.handle_command("joke"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_offline_youtube(self):
        with patch("core.assistant.have_internet", return_value=False):
            self.assertTrue(
                self.assistant.handle_command("play despacito on youtube"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_offline_wikipedia(self):
        with patch("core.assistant.have_internet", return_value=False):
            self.assertTrue(self.assistant.handle_command("wikipedia"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_offline_ip(self):
        # find_my_ip returns None when offline (short-circuits on the
        # module's connectivity check) - the command must say so gracefully
        with patch("core.assistant.find_my_ip", return_value=None):
            self.assertTrue(self.assistant.handle_command("my ip"))
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_screenshot_announces_saved(self):
        with patch("core.assistant.take_screenshot",
                   return_value="C:/fake/screenshot.png"):
            self.assertTrue(self.assistant.handle_command("screenshot"))
        self.assertIn("screenshot saved",
                      " ".join(self.assistant.tts.messages).lower())

    def test_screenshot_failure(self):
        with patch("core.assistant.take_screenshot", return_value=None):
            self.assertTrue(self.assistant.handle_command("screenshot"))
        self.assertIn("failed",
                      " ".join(self.assistant.tts.messages).lower())

    def test_plain_chat_not_a_command(self):
        self.assertFalse(self.assistant.handle_command("how are you"))

    def test_listen_returns_none_without_mic(self):
        """A missing/broken microphone must never raise — just return None."""
        with patch("core.assistant.sr.Microphone",
                   side_effect=OSError("no microphone")):
            self.assertIsNone(self.assistant.listen())


if __name__ == "__main__":
    unittest.main()
