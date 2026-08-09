import importlib
import os
import unittest

import core.ollama as ollama_streaming


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


class OllamaStreamErrorTests(unittest.TestCase):
    """generate_stream must raise OllamaError (never yield a raw error
    token), and check_model must diagnose offline / missing-model cases."""

    def test_generate_stream_raises_ollama_error(self):
        from unittest.mock import patch
        with patch("core.ollama.requests.post",
                   side_effect=Exception("connection refused")):
            gen = ollama_streaming.StreamingOllama(
                model="qwen3:1.7b").generate_stream("hi")
            with self.assertRaises(ollama_streaming.OllamaError):
                next(gen)

    def test_generate_stream_raises_on_http_error(self):
        from unittest.mock import MagicMock, patch
        import requests
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404", response=resp)
        with patch("core.ollama.requests.post", return_value=resp):
            gen = ollama_streaming.StreamingOllama(
                model="qwen3:1.7b").generate_stream("hi")
            with self.assertRaises(ollama_streaming.OllamaError):
                next(gen)

    def test_check_model_online(self):
        from unittest.mock import patch
        with patch("core.ollama.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {
                "models": [{"name": "qwen3:1.7b"}, {"name": "qwen3:4b"}]}
            self.assertEqual(
                ollama_streaming.check_model("qwen3:1.7b")[0], "ok")
            self.assertEqual(
                ollama_streaming.check_model("llama3")[0], "model-missing")

    def test_check_model_offline(self):
        from unittest.mock import patch
        with patch("core.ollama.requests.get",
                   side_effect=Exception("down")):
            self.assertEqual(
                ollama_streaming.check_model("qwen3:1.7b")[0], "offline")


if __name__ == "__main__":
    unittest.main()
