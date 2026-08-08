"""Shared helpers for the test suite.

Puts the project root on ``sys.path`` (so ``import main`` works no matter
how the tests are launched) and provides a silent fake TTS so no audio or
real devices are touched during tests.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class FakeTTS:
    """Records everything 'spoken'; never touches audio hardware."""

    def __init__(self):
        self.messages = []

    def speak(self, text):
        self.messages.append(text)

    def is_busy(self):
        return False


def make_assistant():
    """A PersonalizedAssistant with a fake TTS and no personal memory, so
    tests are deterministic and never read/write the user's real files."""
    import main
    a = main.PersonalizedAssistant("qwen3:1.7b", "JARVIS", "", tts=FakeTTS())
    a.memory = {}
    a.username = "tester"
    return a
