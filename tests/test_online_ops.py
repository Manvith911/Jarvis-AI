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


if __name__ == "__main__":
    unittest.main()
