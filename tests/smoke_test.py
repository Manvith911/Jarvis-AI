"""J.A.R.V.I.S. smoke test — every command handler, fully mocked, zero crashes.

Runs the whole command surface (online AND offline branches) plus the core
chat flows with network, audio, TTS, browser and memory all mocked, to prove
the assistant can never crash on any of its own commands. No real mic,
speakers, internet or files are touched.

Run it with:
    ollama_assistant_env\\Scripts\\python.exe tests/smoke_test.py

Exit code is 0 when every check passes, 1 otherwise.
"""

import json
import os
import sys
from contextlib import ExitStack
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.assistant import PersonalizedAssistant, parse_city_from_query
from core.ollama import OllamaError, split_deep_marker


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeResp:
    """requests.get stand-in."""

    def __init__(self, payload=None, text="", status=200):
        self._payload = payload if payload is not None else {}
        self.text = text
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeStreamResp(FakeResp):
    """requests.post (streaming) stand-in for /api/generate."""

    def iter_lines(self):
        for chunk in ("Hello ", "there, ", "friend!"):
            yield json.dumps({"response": chunk}).encode("utf-8")
        yield json.dumps({"response": "", "done": True}).encode("utf-8")


class FakeTTS:
    """Records every 'spoken' message; never touches audio hardware."""

    def __init__(self):
        self.messages = []

    def speak(self, text):
        self.messages.append(text)

    def is_busy(self):
        return False


def fake_get(url, *args, **kwargs):
    """Benign offline answer for any GET the smoke run might still hit."""
    return FakeResp(status=200, text="ok")


def fake_post(url, *args, **kwargs):
    if "/api/generate" in url:
        return FakeStreamResp()
    return FakeResp(status=200)


# ---------------------------------------------------------------------------
# Tiny assert helpers + runner
# ---------------------------------------------------------------------------
def _expect_true(v):
    assert v is True, f"expected True, got {v!r}"


def _expect_false(v):
    assert v is False, f"expected False, got {v!r}"


def _expect_none(v):
    assert v is None, f"expected None, got {v!r}"


def _expect_in(text, needle):
    assert needle in text, f"{needle!r} not found in {text[:140]!r}"


def _expect_not_in(text, needle):
    assert needle not in text, f"{needle!r} unexpectedly found in {text[:140]!r}"


def _expect_eq(got, want):
    assert got == want, f"expected {want!r}, got {got!r}"


FAILURES = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as e:
        FAILURES.append(name)
        print(f"  FAIL  {name}\n        {type(e).__name__}: {e}")


def main():
    print("J.A.R.V.I.S. smoke test — every command, fully mocked, zero crashes\n")
    with ExitStack() as stack:
        # -- global network safety net: nothing may touch the real internet --
        stack.enter_context(mock.patch("requests.get", side_effect=fake_get))
        stack.enter_context(mock.patch("requests.post", side_effect=fake_post))

        # -- no real files / audio / TTS / browser / exit --------------------
        stack.enter_context(mock.patch("core.assistant.load_memory",
                                       return_value={}))
        stack.enter_context(mock.patch("core.assistant.save_memory"))
        stack.enter_context(mock.patch("core.assistant.clear_memory",
                                       return_value=True))
        stack.enter_context(mock.patch("core.assistant.append_history"))
        stack.enter_context(mock.patch("core.assistant.time.sleep"))
        stack.enter_context(mock.patch("builtins.exit"))

        # -- online features: canned happy answers ---------------------------
        stack.enter_context(mock.patch("core.assistant.have_internet",
                                       return_value=True))
        stack.enter_context(mock.patch("core.assistant.find_my_ip",
                                       return_value="203.0.113.7"))
        stack.enter_context(mock.patch("core.assistant.get_city_from_ip",
                                       return_value="Mumbai"))
        stack.enter_context(mock.patch("core.assistant.get_weather_report",
                                       return_value=("Sunny", "30C", "32C")))
        stack.enter_context(mock.patch("core.assistant.get_random_joke",
                                       return_value="Why so serious?"))
        stack.enter_context(mock.patch("core.assistant.get_latest_news",
                                       return_value=["Headline one"]))
        stack.enter_context(mock.patch("core.assistant.search_on_wikipedia",
                                       return_value="Albert Einstein was a "
                                                     "physicist."))
        stack.enter_context(mock.patch("core.assistant.search_on_google",
                                       return_value="Some web results here."))
        stack.enter_context(mock.patch("core.assistant.open_application",
                                       return_value=True))
        stack.enter_context(mock.patch("core.assistant.open_in_browser",
                                       return_value=True))
        stack.enter_context(mock.patch("core.assistant.take_screenshot",
                                       return_value="C:/fake/shot.png"))
        stack.enter_context(mock.patch("core.assistant.play_on_youtube"))
        stack.enter_context(mock.patch("core.assistant.check_model",
                                       return_value=("ok", ["qwen3:1.7b"])))

        a = PersonalizedAssistant("qwen3:1.7b", "JARVIS", "", tts=FakeTTS())
        a.memory = {}
        a.username = "smoketest"

        # -- mic failure: the real listen() must return None, never raise ----
        with mock.patch("core.assistant.sr.Microphone",
                        side_effect=OSError("no microphone")):
            check("listen() returns None when there is no mic",
                  lambda: _expect_none(a.listen()))

        # follow-up answers for the wikipedia / youtube commands
        a.listen = lambda: "einstein"

        def fake_stream(prompt):
            for token in ("Hello ", "there, ", "friend!"):
                yield token

        stack.enter_context(mock.patch.object(a.ollama, "generate_stream",
                                              side_effect=fake_stream))

        # ---- 1. every command handler --------------------------------------
        commands = [
            ("who am i", "identity"),
            ("what do you know about me", "memory recall"),
            ("forget everything", "forget memory"),
            ("open notepad", "open an app"),
            ("open github in brave", "open a website in a browser"),
            ("search for best laptops", "web search in a browser"),
            ("my ip", "IP address"),
            ("weather", "weather"),
            ("joke", "joke"),
            ("news", "news"),
            ("screenshot", "screenshot"),
            ("play despacito on youtube", "play on YouTube"),
            ("wikipedia", "Wikipedia follow-up"),
            ("youtube", "YouTube follow-up"),
            ("my name is smoketest", "learn a personal fact"),
            ("bye", "farewell (must not exit the process)"),
        ]
        for query, label in commands:
            check(f"handle_command: {label} ({query!r})",
                  lambda q=query: _expect_true(a.handle_command(q)))

        check("plain chat is not treated as a command",
              lambda: _expect_false(a.handle_command("how are you")))

        # ---- 2. prompt building --------------------------------------------
        # NOTE: the system prompt itself mentions "[Web info about ...]" in
        # its instructions, so assert on the injected web results text.
        check("build_prompt injects web info for factual questions",
              lambda: _expect_in(a.build_prompt("who is einstein"),
                                 "Some web results here."))
        check("build_prompt skips web search for casual chat",
              lambda: _expect_not_in(a.build_prompt("how are you"),
                                     "Some web results here."))

        # ---- 3. streaming replies ------------------------------------------
        check("generate_reply streams a reply",
              lambda: _expect_eq(
                  "".join(a.generate_reply("hi", speak=False)),
                  "Hello there, friend!"))

        with mock.patch.object(a.ollama, "generate_stream",
                               side_effect=OllamaError("offline")), \
                mock.patch("core.assistant.check_model",
                           return_value=("offline", None)):
            check("generate_reply is friendly when Ollama is down",
                  lambda: _expect_in(
                      "".join(a.generate_reply("hi", speak=False)), "Ollama"))

        # ---- 4. offline branch ---------------------------------------------
        with mock.patch("core.assistant.have_internet", return_value=False), \
                mock.patch("core.assistant.find_my_ip", return_value=None):
            for query in ("weather", "joke", "news", "my ip",
                          "play despacito on youtube", "wikipedia", "youtube"):
                check(f"offline branch: {query!r}",
                      lambda q=query: _expect_true(a.handle_command(q)))

        # ---- 5. helpers + sanity -------------------------------------------
        check("split_deep_marker",
              lambda: _expect_eq(
                  split_deep_marker("ULTRATHINK: explain black holes"),
                  ("explain black holes", True)))
        check("parse_city_from_query",
              lambda: _expect_eq(
                  parse_city_from_query("weather in london today"), "london"))
        check("the assistant actually produced spoken replies",
              lambda: _expect_true(len(a.tts.messages) > 0))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("ALL CHECKS PASSED — J.A.R.V.I.S. handled every command "
          "with zero crashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
