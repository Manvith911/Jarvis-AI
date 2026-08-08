import unittest
from unittest.mock import patch

from _bootstrap import make_assistant

FAKE_RESULTS = "Einstein was a physicist."


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.assistant = make_assistant()

    def test_factual_question_injects_web_results(self):
        with patch("main.have_internet", return_value=True), \
                patch("main.search_on_google",
                      return_value=FAKE_RESULTS) as search:
            prompt = self.assistant.build_prompt("who is einstein")
        search.assert_called_once()
        self.assertIn("[Web info about 'who is einstein']:", prompt)
        self.assertIn(FAKE_RESULTS, prompt)

    def test_casual_question_does_not_search(self):
        with patch("main.have_internet", return_value=True), \
                patch("main.search_on_google") as search:
            self.assistant.build_prompt("how are you")
        search.assert_not_called()

    def test_identity_question_does_not_search(self):
        with patch("main.have_internet", return_value=True), \
                patch("main.search_on_google") as search:
            self.assistant.build_prompt("who are you")
        search.assert_not_called()

    def test_offline_factual_question_injects_nothing(self):
        with patch("main.have_internet", return_value=False), \
                patch("main.search_on_google") as search:
            prompt = self.assistant.build_prompt("tell me about einstein")
        search.assert_not_called()
        self.assertNotIn("[Web info about 'tell me about einstein']:", prompt)

    def test_offline_explicit_google_speaks_notice(self):
        with patch("main.have_internet", return_value=False), \
                patch("main.search_on_google") as search:
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


if __name__ == "__main__":
    unittest.main()
