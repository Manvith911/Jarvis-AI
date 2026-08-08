import requests
import json

# Everyday model + the bigger model used when a question is marked with the
# ULTRATHINK keyword (e.g. "ULTRATHINK: explain black holes").
DEFAULT_MODEL = "qwen3:0.6b"
BIG_MODEL = "qwen3:1.7b"
DEEP_MARKER = "ultrathink"


def split_deep_marker(message):
    """Split off an ULTRATHINK marker from the start of a message.

    Returns (clean_message, is_deep). Questions marked like
    "ULTRATHINK: explain X" or "ULTRATHINK explain X" are routed to the
    bigger model. Matching is case-insensitive and only at the start, so
    ordinary questions that merely mention the word are unaffected.
    """
    m = (message or "").strip()
    low = m.lower()
    if low.startswith(DEEP_MARKER):
        rest = m[len(DEEP_MARKER):]
        if rest == "" or rest[0] in (":", " ", "\t"):
            return rest.lstrip(": \t").strip(), True
    return message, False


class StreamingOllama:
    def __init__(self, model=DEFAULT_MODEL, base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def generate_stream(self, prompt):
        url = f"{self.base_url}/api/generate"
        data = {"model": self.model, "prompt": prompt, "stream": True}
        try:
            response = requests.post(url, json=data, stream=True, timeout=120)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        part = json.loads(line.decode("utf-8"))
                        token = part.get("response", "")
                        if token:
                            yield token
                    except Exception:
                        continue
        except Exception as e:
            yield f"[streaming error: {e}]"