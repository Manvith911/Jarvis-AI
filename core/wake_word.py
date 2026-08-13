"""Continuous 'hey jarvis' wake-word detection.

Primary engine: openwakeword — an offline, real-time model that listens on
80 ms audio frames at 16 kHz and was trained specifically on the phrase
"hey jarvis". No per-use network calls, no API keys, low CPU.

A fresh ``pip install openwakeword`` ships WITHOUT the pretrained model
files, and the installed openwakeword version never auto-downloads them —
so the offline engine would crash on startup and silently fall back to the
online engine. :func:`_ensure_wake_model` downloads the small (~1.2 MB)
``hey_jarvis`` ONNX model straight from the official openwakeword release
to the exact path the library looks for (once, then it's cached forever).

Fallback engine: an energy-gated loop over the existing SpeechRecognition /
Google stack, so the feature keeps working even when openwakeword isn't
installed or the model can't be downloaded (e.g. first run offline).
Speech-recognition calls are only made when the mic actually hears sound
(the library's energy-based VAD gates them), so the fallback doesn't hammer
the API during silence. Unlike the old version, the fallback matches the
wake phrase *fuzzily* — Google frequently mis-transcribes "hey jarvis" as
"hey jarvish", "hey jervis", "okay jarvis", etc. — so a wake is never
missed just because the transcript isn't spelled perfectly.
"""

import difflib
import re
import threading
import time

try:
    import numpy as _np
    from openwakeword.model import Model as _OWWModel
    OPENWAKEWORD_OK = True
except Exception:  # pragma: no cover - depends on user's environment
    OPENWAKEWORD_OK = False

# Google sometimes injects a filler word before the wake name ("hey jarvis",
# "okay jarvis", "listen jarvis"...). These are stripped before the name
# match so a perfectly-heard wake is never missed.
_FILLER_WORDS = {
    "hey", "hi", "hay", "he", "hei", "h", "y", "ok", "okay", "o kay", "oh",
    "a", "uh", "um", "yo", "listen", "so", "and", "can", "could", "please",
}

# Minimum similarity (difflib ratio) between the leading word and the bot
# name for it to count as a wake. Google mangles "jarvis" in many ways
# ("jarvish", "jervis", "jarvees"...); 0.7 catches those while rejecting
# unrelated words like "siri", "google", "hey there".
_NAME_SIMILARITY = 0.70

# How long after a wake JARVIS's own reply can never re-trigger it.
_WAKE_COOLDOWN = 3.0

# openwakeword model we use (trained on "hey jarvis").
_WAKE_MODEL = "hey_jarvis"


# Feature-extractor models the openwakeword preprocessor ALSO needs (they
# live in the same GitHub release as the wake-word models but are not
# shipped with the pip package on this platform).
_FEATURE_MODELS = ("melspectrogram.onnx", "embedding_model.onnx")


def _ensure_wake_model(model_name=_WAKE_MODEL):
    """Make sure the openwakeword model files exist on disk (download once).

    openwakeword resolves pretrained models by name to files next to the
    package (``openwakeword/resources/models/...``). A fresh install does
    not ship those files and this openwakeword version does not download
    them automatically, which makes the offline wake-word engine crash and
    silently fall back to the slower online engine. This downloads the wake
    word model AND the mel-spectrogram / embedding feature extractors from
    the official openwakeword release, to the exact paths the library looks
    for. Returns True when the wake-word model is available.
    """
    try:
        import os
        import re

        import requests
        from openwakeword import MODELS
        meta = MODELS.get(model_name)
        if not meta:
            print(f"[wake] unknown wake-word model '{model_name}'")
            return False
        # we use the onnx runtime, so swap the tflite path/URL for onnx
        target = meta["model_path"].replace(".tflite", ".onnx")
        urls = [meta["download_url"].replace(".tflite", ".onnx")]
        # the preprocessor needs the feature extractors from the same release
        m = re.search(r"/releases/download/([^/]+)/", meta["download_url"])
        tag = m.group(1) if m else "v0.5.1"
        for feat in _FEATURE_MODELS:
            urls.append(
                "https://github.com/dscripka/openWakeWord/releases/download/"
                f"{tag}/{feat}")
        model_dir = os.path.dirname(target)
        os.makedirs(model_dir, exist_ok=True)
        for url in urls:
            file_path = os.path.join(model_dir, url.rsplit("/", 1)[-1])
            if os.path.exists(file_path):
                continue
            print(f"[wake] downloading {os.path.basename(file_path)}...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)
            print(f"[wake] {os.path.basename(file_path)} ready "
                  f"({os.path.getsize(file_path)} bytes)")
        return os.path.exists(target)
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[wake] could not prepare offline model: {e}")
        return False


class WakeWordListener:
    """Listens continuously for the wake word in a background thread.

    on_wake:   called (from the listener thread) when the wake word is heard.
               The mic is guaranteed to be free at that moment, so the
               callback can open it for a full command capture.
    is_paused: optional callable returning True while the assistant is busy
               speaking/processing, so it never wakes itself up on its own
               reply. The loop idles (mic closed) while paused.
    threshold: openwakeword detection score (0.0–1.0). Lower = more
               sensitive (a few more false wakes), higher = stricter.
    """

    def __init__(self, botname="jarvis", on_wake=None, is_paused=None,
                 threshold=0.4):
        self.botname = (botname or "jarvis").lower()
        self.on_wake = on_wake
        self.is_paused = is_paused or (lambda: False)
        self.threshold = float(threshold)
        self.running = False
        self._thread = None

    # -- lifecycle ----------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    @property
    def active(self):
        return self.running

    # -- internals ----------------------------------------------------
    def _paused(self):
        try:
            return bool(self.is_paused())
        except Exception:
            return False

    def _run(self):
        if OPENWAKEWORD_OK and _ensure_wake_model():
            try:
                self._run_offline()
                return
            except Exception as e:
                print(f"[wake] offline engine failed ({e}); "
                      f"using online fallback")
        self._run_online()

    def _run_offline(self):
        """Listen with openwakeword in ~80 ms frames at 16 kHz.

        The mic stream is opened only while actually listening for the wake
        word and closed BEFORE on_wake fires, so the caller can immediately
        open the mic to capture the actual command (no two streams fighting
        over the same device).
        """
        import pyaudio
        oww = _OWWModel(inference_framework="onnx",
                        wakeword_models=[_WAKE_MODEL])
        pa = pyaudio.PyAudio()
        print("[wake] offline 'hey jarvis' listening (openwakeword)")
        cooldown = 0.0
        try:
            while self.running:
                # while the assistant is busy, release the mic entirely
                while self.running and self._paused():
                    time.sleep(0.08)
                if not self.running:
                    break
                try:
                    stream = pa.open(
                        format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=1280)
                except Exception:
                    raise   # outer finally owns pa.terminate()
                woke = False
                try:
                    while self.running and not self._paused():
                        data = stream.read(1280, exception_on_overflow=False)
                        frame = _np.frombuffer(data, dtype=_np.int16)
                        score = oww.predict(frame).get(_WAKE_MODEL, 0.0)
                        if (score >= self.threshold
                                and time.time() >= cooldown):
                            # cooldown so JARVIS's own reply never re-triggers
                            cooldown = time.time() + _WAKE_COOLDOWN
                            woke = True
                            break
                finally:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if woke and self.running:
                    self._fire()   # mic is free now
        finally:
            pa.terminate()

    def _run_online(self):
        """Energy-gated fallback using Google speech recognition."""
        import speech_recognition as sr
        from core.stt import new_recognizer
        recognizer = new_recognizer()
        cooldown = 0.0
        print("[wake] online fallback listening (Google speech recognition)")
        while self.running:
            if self._paused():
                time.sleep(0.4)
                continue
            if time.time() < cooldown:
                # JARVIS may still be replying — don't burn API calls
                time.sleep(0.3)
                continue
            try:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.4)
                    recognizer.energy_threshold = max(
                        recognizer.energy_threshold, 60)
                    audio = recognizer.listen(source, timeout=2,
                                              phrase_time_limit=3)
                if not self.running:
                    break
                text = ""
                try:
                    from core.stt import transcribe
                    text = (transcribe(audio, recognizer,
                                       language="en-in") or "").lower()
                except Exception:
                    continue  # speech heard but not understood — not a wake
                if not text:
                    continue
                if self._is_wake_text(text):
                    cooldown = time.time() + 4.0
                    self._fire()
            except sr.WaitTimeoutError:
                # silence — no speech heard, completely normal; keep waiting
                pass
            except Exception as e:
                print(f"[wake] online error: {e}")
                time.sleep(1.0)

    def _normalize(self, text):
        """Lowercase, strip punctuation and collapse whitespace."""
        t = (text or "").lower()
        t = re.sub(r"[^a-z0-9 ]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _is_wake_text(self, text):
        """True when a transcript is ADDRESSED to the assistant.

        The name must lead the utterance ("hey jarvis ..." / "jarvis ...").
        Leading filler words are ignored, and the name itself is matched
        fuzzily (difflib) because Google frequently mis-transcribes it —
        "hey jarvish", "hey jervis", "hey jarvis?" should all wake JARVIS,
        while "hey siri" or ordinary chatter must not.
        """
        # normalize the botname the same way as the transcript, so
        # BOTNAME="J.A.R.V.I.S." still matches a spoken "jarvis"
        name = self._normalize(self.botname)
        t = self._normalize(text)
        if not t or not name:
            return False
        words = t.split()
        # a dotted botname like "J.A.R.V.I.S." normalizes to "j a r v i s"
        # (punctuation becomes spaces) — merge runs of single letters back
        # into one word so the name still matches a spoken "jarvis".
        merged = []
        i = 0
        while i < len(words):
            if (len(words[i]) == 1 and i + 1 < len(words)
                    and len(words[i + 1]) == 1):
                run = ""
                while i < len(words) and len(words[i]) == 1:
                    run += words[i]
                    i += 1
                merged.append(run)
            else:
                merged.append(words[i])
                i += 1
        words = merged
        while words and words[0] in _FILLER_WORDS:
            words.pop(0)
        if not words:
            return False
        first = words[0]
        # exact, prefix ("jarvis", "jarvis!") or fuzzy ("jarvish", "jervis")
        if first == name or first.startswith(name):
            return True
        if difflib.SequenceMatcher(None, name, first).ratio() >= _NAME_SIMILARITY:
            return True
        # "hey there jarvis" — the name buried one word deeper
        if len(words) > 1:
            second = words[1]
            if (second == name or second.startswith(name)
                    or difflib.SequenceMatcher(None, name, second).ratio()
                    >= _NAME_SIMILARITY):
                return True
        return False

    def _fire(self):
        try:
            if self.on_wake:
                self.on_wake()
        except Exception as e:
            print(f"[wake] on_wake callback error: {e}")
