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

    def test_casual_mentions_do_not_trigger_quick_commands(self):
        """Statements that merely mention a keyword must stay chat:
        'newspaper' contains 'news', 'weatherman' contains 'weather'..."""
        for phrase in ("i read the newspaper this morning",
                       "what about the weatherman",
                       "this weather is nice",
                       "the weather is nice today",
                       "you're a joke"):
            with self.subTest(phrase=phrase):
                self.assertFalse(self.assistant.handle_command(phrase))

    def test_quick_command_requests_still_fire(self):
        with patch.object(self.assistant, "report_news") as news:
            self.assertTrue(self.assistant.handle_command("what's the news"))
            news.assert_called_once()
        with patch("core.assistant.get_random_joke") as joke:
            self.assertTrue(self.assistant.handle_command("tell me some jokes"))
            joke.assert_called_once()
        with patch("core.assistant.take_screenshot", return_value="x"):
            self.assertTrue(self.assistant.handle_command("take a screenshot"))

    def test_generate_reply_streams_unencodable_tokens(self):
        """Model tokens the console can't encode (emoji) must never crash."""
        self.assistant.ollama.generate_stream = \
            lambda prompt: iter(["Hi", "😊"])
        reply = "".join(self.assistant.generate_reply(
            "hello", speak=False, paced=False))
        self.assertEqual(reply, "Hi😊")

    def test_speak_handles_unencodable_chars(self):
        """℃/emoji must print safely (cp1252 consoles) and still be spoken."""
        self.assistant.speak("It's 23℃ in bengaluru 😊")
        self.assertIn("23℃", " ".join(self.assistant.tts.messages))

    def test_listen_returns_none_without_mic(self):
        """A missing/broken microphone must never raise — just return None."""
        with patch("core.assistant.sr.Microphone",
                   side_effect=OSError("no microphone")):
            self.assertIsNone(self.assistant.listen())


if __name__ == "__main__":
    unittest.main()
