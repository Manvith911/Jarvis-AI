"""Regression tests for the GUI worker (ui/gui.py).

Only plain QObject signal wiring is exercised — no QApplication, no audio
hardware, no windows are created.
"""

import unittest
from unittest.mock import MagicMock

from ui.gui import AssistantWorker


class FakeTTS:
    interrupted = False

    def speak(self, text):
        pass

    def is_busy(self):
        return False


def _make_worker():
    assistant = MagicMock()
    assistant.username = "tester"
    assistant.history = []
    assistant.is_processing = False
    assistant.tts = FakeTTS()
    assistant.summarize_and_save_history = MagicMock()
    return AssistantWorker(assistant), assistant


class FarewellTests(unittest.TestCase):
    def test_goodbye_replies_without_error(self):
        """'bye' must end the session with a friendly reply.

        The old code referenced self.worker (a MainWindow-only attribute)
        from inside the worker, which raised AttributeError and surfaced the
        catch-all "Yikes, something went wrong on my end" error.
        """
        worker, _ = _make_worker()
        errors, replies = [], []
        worker.error.connect(lambda m: errors.append(m))
        worker.line.connect(
            lambda t, tag: replies.append((tag, t)) if tag == "ai" else None)
        worker.process("bye")
        self.assertFalse(errors)
        self.assertTrue(
            any("See ya" in t for tag, t in replies if tag == "ai"))

    def test_conversation_mode_ends_on_goodbye(self):
        worker, _ = _make_worker()
        worker._mic_convo = True
        worker.process("goodbye")
        self.assertFalse(worker._mic_convo)

    def test_goodbye_disarms_wake_word_listener(self):
        """Saying goodbye must stop the 'hey jarvis' listener too — the HUD
        should not keep listening after the session ends."""
        worker, _ = _make_worker()
        fake_wake = MagicMock()
        worker.wake_active = True
        worker.wake = fake_wake
        worker.process("bye")
        self.assertFalse(worker.wake_active)
        fake_wake.stop.assert_called_once()
        self.assertIsNone(worker.wake)


if __name__ == "__main__":
    unittest.main()
