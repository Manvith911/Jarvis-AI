import unittest
from unittest.mock import patch

from _bootstrap import make_assistant

FAKE_RESULTS = "Einstein was a physicist."


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.assistant = make_assistant()

    def test_factual_question_injects_web_results(self):
        with patch("core.assistant.have_internet", return_value=True), \
                patch("core.assistant.search_on_google",
                      return_value=FAKE_RESULTS) as search:
            prompt = self.assistant.build_prompt("who is einstein")
        search.assert_called_once()
        self.assertIn("[Web info about 'who is einstein']:", prompt)
        self.assertIn(FAKE_RESULTS, prompt)

    def test_casual_question_does_not_search(self):
        with patch("core.assistant.have_internet", return_value=True), \
                patch("core.assistant.search_on_google") as search:
            self.assistant.build_prompt("how are you")
        search.assert_not_called()

    def test_identity_question_does_not_search(self):
        with patch("core.assistant.have_internet", return_value=True), \
                patch("core.assistant.search_on_google") as search:
            self.assistant.build_prompt("who are you")
        search.assert_not_called()

    def test_offline_factual_question_injects_nothing(self):
        with patch("core.assistant.have_internet", return_value=False), \
                patch("core.assistant.search_on_google") as search:
            prompt = self.assistant.build_prompt("tell me about einstein")
        search.assert_not_called()
        self.assertNotIn("[Web info about 'tell me about einstein']:", prompt)

    def test_offline_explicit_google_speaks_notice(self):
        with patch("core.assistant.have_internet", return_value=False), \
                patch("core.assistant.search_on_google") as search:
            prompt = self.assistant.build_prompt("google einstein")
        search.assert_not_called()
        self.assertNotIn("[Web info about 'einstein']:", prompt)
        self.assertIn("offline", " ".join(self.assistant.tts.messages).lower())

    def test_question_with_braces_is_safe(self):
        prompt = self.assistant.build_prompt("what is a python dict {}")
        self.assertIn("{}", prompt)

    def test_remembered_history_is_included(self):
        self.assistant.history = ["User: hello", "AI: hi there"]
        prompt = self.assistant.build_prompt("how are you")
        self.assertIn("User: hello", prompt)

    def test_generate_reply_friendly_when_ollama_down(self):
        """An Ollama failure must produce a friendly reply, never a raw
        '[streaming error: ...]' token."""
        # Import the class through core.assistant (the exact binding its
        # except clause catches) so this stays valid even if core.ollama
        # gets reloaded by another test module mid-suite.
        from core.assistant import OllamaError
        with patch.object(self.assistant.ollama, "generate_stream",
                          side_effect=OllamaError("offline")), \
                patch("core.assistant.check_model",
                      return_value=("offline", None)):
            reply = "".join(
                self.assistant.generate_reply("hello", speak=False))
        self.assertIn("Ollama", reply)
        self.assertNotIn("streaming error", reply)

    def test_generate_reply_hints_missing_model(self):
        from core.assistant import OllamaError
        with patch.object(self.assistant.ollama, "generate_stream",
                          side_effect=OllamaError("404")), \
                patch("core.assistant.check_model",
                      return_value=("model-missing", ["llama3"])):
            reply = "".join(
                self.assistant.generate_reply("hello", speak=False))
        self.assertIn("ollama pull", reply)


if __name__ == "__main__":
    unittest.main()
