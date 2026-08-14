import unittest
from types import SimpleNamespace
from unittest.mock import patch

import functions.online_ops as oo


class OnlineOpsTests(unittest.TestCase):
    def setUp(self):
        # force a fresh probe on every test
        oo._internet_cache["at"] = 0.0
        oo._internet_cache["result"] = None

    def test_online_detection(self):
        with patch.object(oo.requests, "get",
                          return_value=SimpleNamespace(status_code=204,
                                                       text="")):
            self.assertTrue(oo.have_internet())

    def test_offline_detection(self):
        with patch.object(oo.requests, "get",
                          side_effect=Exception("no network")):
            self.assertFalse(oo.have_internet())

    def test_result_is_cached(self):
        with patch.object(oo.requests, "get",
                          return_value=SimpleNamespace(status_code=204,
                                                       text="")) as get:
            self.assertTrue(oo.have_internet())
            first = get.call_count
            self.assertTrue(oo.have_internet())  # served from cache
            self.assertEqual(get.call_count, first)

    def test_find_my_ip_short_circuits_offline(self):
        with patch.object(oo, "have_internet", return_value=False):
            self.assertIsNone(oo.find_my_ip())

    def test_find_my_ip_online(self):
        with patch.object(oo, "have_internet", return_value=True), \
                patch.object(oo.requests, "get",
                             return_value=SimpleNamespace(status_code=200,
                                                          text="203.0.113.7")):
            # provider returns a plain IP
            self.assertEqual(oo.find_my_ip(), "203.0.113.7")

    # -- wikipedia (direct MediaWiki API) -----------------------------
    def _wiki_reply(self, pages):
        return {"query": {"pages": pages}}

    def test_wikipedia_returns_summary(self):
        with patch.object(oo.requests, "get") as get:
            get.return_value.json.return_value = self._wiki_reply({
                "1": {"index": 1, "title": "Albert Einstein",
                       "extract": "Albert Einstein was a German-born "
                                   "theoretical physicist."}})
            res = oo.search_on_wikipedia("einstein")
        self.assertIn("Einstein", res)

    def test_wikipedia_skips_disambiguation(self):
        """A disambiguation hit must not win over a real article."""
        with patch.object(oo.requests, "get") as get:
            get.return_value.json.return_value = self._wiki_reply({
                "1": {"index": 1, "title": "Java (disambiguation)",
                       "extract": "Java may refer to:",
                       "pageprops": {"disambiguation": ""}},
                "2": {"index": 2,
                       "title": "Java (programming language)",
                       "extract": "Java is a programming language."}})
            res = oo.search_on_wikipedia("java")
        self.assertEqual(res, "Java is a programming language.")

    def test_wikipedia_no_results_is_friendly(self):
        with patch.object(oo.requests, "get") as get:
            get.return_value.json.return_value = self._wiki_reply({})
            res = oo.search_on_wikipedia("zzz nonexistent topic")
        self.assertIn("Couldn't find", res)

    def test_wikipedia_api_error_is_friendly(self):
        with patch.object(oo.requests, "get",
                          side_effect=Exception("no network")):
            res = oo.search_on_wikipedia("einstein")
        self.assertIn("reachable", res)

    def test_wikipedia_empty_query(self):
        self.assertIn("topic", oo.search_on_wikipedia("   "))

    # -- jokes ---------------------------------------------------------
    def test_joke_returns_fallback_when_api_down(self):
        with patch.object(oo.requests, "get",
                          side_effect=Exception("down")):
            joke = oo.get_random_joke()
        self.assertTrue(joke.strip())

    def test_joke_returns_fallback_when_empty(self):
        with patch.object(oo.requests, "get") as get:
            get.return_value.json.return_value = {"joke": ""}
            self.assertTrue(oo.get_random_joke().strip())

    # -- news (key-free Google News RSS fallback) -----------------------
    RSS = ("<rss version=\"2.0\"><channel>"
           "<item><title>Headline one - The Hindu</title></item>"
           "<item><title>Headline two - Times of India</title></item>"
           "</channel></rss>")

    def test_news_falls_back_to_keyless_rss(self):
        """No API keys -> Google News RSS supplies the headlines, with the
        trailing publisher stripped."""
        with patch.object(oo, "GNEWS_API_KEY", ""), \
                patch.object(oo, "NEWS_API_KEY", ""), \
                patch.object(oo.requests, "get",
                             return_value=SimpleNamespace(status_code=200,
                                                          text=self.RSS)):
            news = oo.get_latest_news()
        self.assertEqual(news, ["Headline one", "Headline two"])

    def test_news_prefers_configured_api(self):
        """A configured GNews key wins over the key-free fallback."""
        with patch.object(oo, "GNEWS_API_KEY", "abc"), \
                patch.object(oo.requests, "get") as get:
            get.return_value.json.return_value = {
                "articles": [{"title": "API headline"}]}
            self.assertEqual(oo.get_latest_news(), ["API headline"])

    def test_news_returns_empty_when_all_sources_fail(self):
        with patch.object(oo, "GNEWS_API_KEY", ""), \
                patch.object(oo, "NEWS_API_KEY", ""), \
                patch.object(oo.requests, "get",
                             side_effect=Exception("no network")):
            self.assertEqual(oo.get_latest_news(), [])

    def test_parse_rss_titles_bad_xml(self):
        self.assertEqual(oo._parse_rss_titles("<not xml"), [])

    # -- youtube fallback ---------------------------------------------
    def test_play_on_youtube_falls_back_without_pywhatkit(self):
        """pywhatkit missing must not raise — open a YouTube search page."""
        import sys
        with patch.dict(sys.modules, {"pywhatkit": None}):
            with patch("webbrowser.open") as open_:
                oo.play_on_youtube("despacito")
        open_.assert_called_once()
        self.assertIn("youtube.com/results", open_.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
