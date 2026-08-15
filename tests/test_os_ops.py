"""Tests for functions/os_ops.py helpers — no real apps launched."""

import unittest
from unittest.mock import patch

from functions.os_ops import (
    normalize_url, open_notepad, parse_open_command, set_mute,
)


class NormalizeUrlTests(unittest.TestCase):
    def test_bare_name_gets_dot_com(self):
        self.assertEqual(normalize_url("github"), "https://github.com")

    def test_domain_stays_https(self):
        self.assertEqual(normalize_url("github.com"), "https://github.com")

    def test_www_prefix(self):
        self.assertEqual(normalize_url("www.x.io"), "https://www.x.io")

    def test_full_url_unchanged(self):
        self.assertEqual(normalize_url("http://a.com/x"),
                         "http://a.com/x")
        self.assertEqual(normalize_url("https://a.com/x"),
                         "https://a.com/x")

    def test_host_with_port(self):
        """'localhost:3000' must not become 'localhost:3000.com'."""
        self.assertEqual(normalize_url("localhost:3000"),
                         "https://localhost:3000")

    def test_path_without_dot(self):
        self.assertEqual(normalize_url("github.com/foo"),
                         "https://github.com/foo")


class OpenNotepadTests(unittest.TestCase):
    def test_open_notepad_does_not_block(self):
        """Popen, never run() — run() would block until Notepad closes."""
        with patch("functions.os_ops.sp.Popen") as popen:
            open_notepad()
        popen.assert_called_once()
        # the launch target is the first positional argument
        self.assertIn("notepad", popen.call_args[0][0].lower())


class ParseOpenCommandTests(unittest.TestCase):
    def test_open_in_browser(self):
        self.assertEqual(parse_open_command("open github in brave"),
                         ("app", "github", "brave"))

    def test_search_in_browser(self):
        self.assertEqual(
            parse_open_command("search for best laptops in chrome"),
            ("search", "best laptops", "chrome"))

    def test_google_query_in_browser_strips_trailing_google(self):
        """'search for X on google in chrome' must search for X, not
        'X on google'."""
        self.assertEqual(
            parse_open_command("search for einstein on google in chrome"),
            ("search", "einstein", "chrome"))
        self.assertEqual(parse_open_command("google einstein in brave"),
                         ("search", "einstein", "brave"))

    def test_empty_search_target_is_not_a_command(self):
        """'search on google in firefox' has nothing to search — it must
        not become a silent no-op command."""
        self.assertIsNone(parse_open_command("search on google in firefox"))

    def test_play_youtube_is_not_an_open_command(self):
        self.assertIsNone(parse_open_command("play despacito on youtube"))

    def test_politeness_is_stripped(self):
        self.assertEqual(parse_open_command("can you open notepad"),
                         ("app", "notepad", None))


class SetMuteTests(unittest.TestCase):
    def test_set_mute_falls_back_to_toggle_without_pycaw(self):
        """Without pycaw, set_mute must degrade to the mute media key."""
        import sys
        with patch.dict(sys.modules,
                        {"pycaw.pycaw": None, "comtypes": None}), \
                patch("functions.os_ops.toggle_mute",
                      return_value=True) as tm:
            self.assertTrue(set_mute(True))
        tm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
