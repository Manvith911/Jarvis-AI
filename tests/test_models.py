import importlib
import os
import unittest

import ollama_streaming


class ModelConfigTests(unittest.TestCase):
    """MODEL / BIG_MODEL come from the environment (or .env) via decouple."""

    def setUp(self):
        self._backup = {k: os.environ.get(k) for k in ("MODEL", "BIG_MODEL")}
        os.environ.pop("MODEL", None)
        os.environ.pop("BIG_MODEL", None)

    def tearDown(self):
        for k, v in self._backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _reload(self):
        importlib.reload(ollama_streaming)
        return ollama_streaming

    def test_defaults_when_unset(self):
        o = self._reload()
        self.assertEqual(o.DEFAULT_MODEL, "qwen3:1.7b")
        self.assertEqual(o.BIG_MODEL, "qwen3:1.7b")

    def test_model_override_propagates_to_big(self):
        os.environ["MODEL"] = "qwen3:4b"
        o = self._reload()
        self.assertEqual(o.DEFAULT_MODEL, "qwen3:4b")
        # BIG_MODEL falls back to MODEL when not set
        self.assertEqual(o.BIG_MODEL, "qwen3:4b")

    def test_big_model_override_wins(self):
        os.environ["MODEL"] = "qwen3:4b"
        os.environ["BIG_MODEL"] = "qwen3:14b"
        o = self._reload()
        self.assertEqual(o.DEFAULT_MODEL, "qwen3:4b")
        self.assertEqual(o.BIG_MODEL, "qwen3:14b")

    def test_empty_big_model_falls_back(self):
        os.environ["MODEL"] = "qwen3:4b"
        os.environ["BIG_MODEL"] = ""
        o = self._reload()
        self.assertEqual(o.BIG_MODEL, "qwen3:4b")


if __name__ == "__main__":
    unittest.main()
