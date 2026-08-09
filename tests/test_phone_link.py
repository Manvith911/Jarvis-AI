import os
import re
import time
import types
import unittest
from unittest.mock import patch

from _bootstrap import FakeTTS

import phone_link


class FakeAssistant:
    """Minimal stand-in for PersonalizedAssistant: no Ollama, no audio."""

    def __init__(self, command_mode=False):
        self.is_processing = False
        self.history = []
        self.username = "tester"
        self.botname = "JARVIS"
        self.model = "qwen3:1.7b"
        self.tts = FakeTTS()
        self.ollama = types.SimpleNamespace(model=self.model)
        self.command_mode = command_mode
        self.summarize_called = False

    def handle_command(self, query):
        if self.command_mode:
            self.tts.speak("It's nice out.")
            return True
        return False

    def generate_reply(self, question, speak=True, paced=True):
        for token in ("hi ", "there ", "friend!"):
            yield token

    def summarize_and_save_history(self):
        self.summarize_called = True


def collect(server, message, session="s1"):
    return "".join(server._chat_stream(message, session))


class LanIpTests(unittest.TestCase):
    def test_lan_ip_looks_like_an_ip(self):
        ip = phone_link.get_lan_ip()
        self.assertRegex(ip, r"^\d{1,3}(\.\d{1,3}){3}$")

    def test_url_https_by_default(self):
        # the phone link serves HTTPS (self-signed) so the phone browser
        # can use its microphone for voice input
        self.assertTrue(phone_link.get_phone_url().startswith("https://"))

    def test_url_http_when_https_off(self):
        self.assertTrue(
            phone_link.get_phone_url(https=False).startswith("http://"))


class CertTests(unittest.TestCase):
    def test_ssl_context_creates_cached_cert(self):
        ctx = phone_link.ensure_ssl_context()
        if ctx is None:
            self.skipTest("cryptography not installed")
        cert_path, key_path = ctx
        self.assertTrue(os.path.exists(cert_path))
        self.assertTrue(os.path.exists(key_path))
        # the cert must cover the current LAN IP so browsers accept it
        self.assertTrue(
            phone_link._cert_contains_ip(cert_path, phone_link.get_lan_ip()))

    def test_phone_link_server_enables_https(self):
        s = phone_link.PhoneLinkServer(FakeAssistant())
        if s.ssl_context is None:
            self.skipTest("cryptography not installed")
        self.assertTrue(s.ssl_enabled)
        self.assertTrue(s.url.startswith("https://"))


class QrTests(unittest.TestCase):
    def test_qr_png_bytes(self):
        png = phone_link.make_qr_png("http://192.168.1.5:5080")
        self.assertIsNotNone(png)
        self.assertTrue(png.startswith(b"\x89PNG"))


class ChatHandlerTests(unittest.TestCase):
    def make_server(self, command_mode=False):
        return phone_link.PhoneLinkServer(FakeAssistant(command_mode))

    def test_plain_chat_streams_reply(self):
        s = self.make_server()
        with patch("phone_link.is_online", return_value=True):
            text = collect(s, "hello")
        self.assertEqual(text, "hi there friend!")
        self.assertFalse(s.assistant.is_processing)
        self.assertEqual(s.assistant.history[-2:],
                         ["User: hello", "AI: hi there friend!"])

    def test_command_replies_with_announcement(self):
        s = self.make_server(command_mode=True)
        text = collect(s, "weather")
        self.assertEqual(text, "It's nice out.")

    def test_command_reply_is_phone_only(self):
        """Phone requests must not reach the desktop speaker."""
        s = self.make_server(command_mode=True)
        collect(s, "weather")
        # FakeTTS records every 'spoken' message — it must stay empty
        self.assertEqual(s.assistant.tts.messages, [])

    def test_chat_request_is_phone_only(self):
        """AI chat must stream with speak=False (phone-only reply)."""
        s = self.make_server()
        real = s.assistant.generate_reply
        calls = {}

        def recorder(question, speak=True, paced=True):
            calls["speak"] = speak
            calls["paced"] = paced
            yield from real(question, speak, paced)

        with patch("phone_link.is_online", return_value=True), \
             patch.object(s.assistant, "generate_reply", recorder):
            text = collect(s, "hello")
        self.assertEqual(text, "hi there friend!")
        self.assertFalse(calls["speak"])

    def test_chat_forwards_pre_reply_announcement_to_phone(self):
        """Notices like 'give me a sec' (spoken during prompt build) are
        sent to the phone instead of the desktop speaker."""
        s = self.make_server()
        real = s.assistant.generate_reply

        def gen_with_announce(question, speak=True, paced=True):
            s.assistant.tts.speak("Give me a sec — looking that up for you!")
            yield from real(question, speak, paced)

        with patch("phone_link.is_online", return_value=True), \
             patch.object(s.assistant, "generate_reply", gen_with_announce):
            text = collect(s, "hello")
        self.assertTrue(text.startswith("Give me a sec"))
        self.assertIn("hi there friend!", text)
        # nothing leaked to the desktop speaker
        self.assertEqual(s.assistant.tts.messages, [])

    def test_busy_yields_busy_message(self):
        s = self.make_server()
        s.assistant.is_processing = True
        text = collect(s, "hello")
        self.assertIn("One sec", text)

    def test_empty_message(self):
        s = self.make_server()
        text = collect(s, "   ")
        self.assertIn("Say something", text)

    def test_bye_never_exits(self):
        s = self.make_server()
        with patch.object(s.assistant, "summarize_and_save_history") as summ:
            text = collect(s, "bye")
        self.assertIn("See ya", text)
        self.assertIn("User: bye", s.assistant.history)
        time.sleep(0.05)
        summ.assert_called_once()
        self.assertFalse(s.assistant.is_processing)

    def test_wikipedia_followup(self):
        s = self.make_server()
        with patch("phone_link.have_internet", return_value=True), \
             patch("phone_link.search_on_wikipedia",
                   return_value="Albert Einstein was a physicist."):
            q1 = collect(s, "wikipedia")
            self.assertIn("What should I look up", q1)
            q2 = collect(s, "einstein")
        self.assertIn("Wikipedia says", q2)
        self.assertNotIn("s1", s.followups)

    def test_offline_wikipedia_followup(self):
        s = self.make_server()
        with patch("phone_link.have_internet", return_value=False):
            q1 = collect(s, "wikipedia")
            self.assertIn("What should I look up", q1)
            q2 = collect(s, "einstein")
        self.assertIn("offline", q2)

    def test_youtube_followup(self):
        s = self.make_server()
        with patch("phone_link.have_internet", return_value=True), \
             patch("phone_link.play_on_youtube") as play, \
             patch("phone_link.is_online", return_value=True):
            q1 = collect(s, "youtube")
            self.assertIn("jam to", q1)
            q2 = collect(s, "despacito")
        play.assert_called_once_with("despacito")
        self.assertIn("Playing despacito", q2)

    def test_deep_marker_swaps_and_restores_model(self):
        s = self.make_server()
        with patch("phone_link.is_online", return_value=True), \
             patch("phone_link.BIG_MODEL", "qwen3:14b"):
            text = collect(s, "ULTRATHINK: explain black holes")
        self.assertEqual(text, "hi there friend!")
        self.assertEqual(s.assistant.ollama.model, "qwen3:1.7b")

    def test_handler_error_is_friendly(self):
        s = self.make_server()
        with patch.object(s.assistant, "generate_reply",
                          side_effect=RuntimeError("boom")), \
             patch("phone_link.is_online", return_value=True):
            text = collect(s, "hello")
        self.assertIn("went wrong", text)
        self.assertFalse(s.assistant.is_processing)

    def test_stop_after_start(self):
        # port 0 = ephemeral, so the test never collides with a running HUD
        s = phone_link.PhoneLinkServer(FakeAssistant(), port=0)
        self.assertTrue(s.start())
        self.assertTrue(s.is_running)
        s.stop()
        self.assertFalse(s.is_running)


class FlaskRouteTests(unittest.TestCase):
    def setUp(self):
        self.server = phone_link.PhoneLinkServer(FakeAssistant())
        self.client = self.server.app.test_client()

    def test_index_serves_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("J.A.R.V.I.S.", r.get_data(as_text=True))
        self.assertIn("/api/chat", r.get_data(as_text=True))

    def test_status_json(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(r.get_json()["botname"], "JARVIS")

    def test_chat_endpoint(self):
        with patch("phone_link.is_online", return_value=True):
            r = self.client.post("/api/chat",
                                 json={"message": "hello", "session": "t"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("friend", r.get_data(as_text=True))

    def test_chat_endpoint_empty_message(self):
        r = self.client.post("/api/chat", json={"message": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Say something", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
