"""Continuous 'hey jarvis' wake-word detection.

Primary engine: openwakeword — an offline, real-time model that listens on
80 ms audio frames at 16 kHz and was trained specifically on the phrase
"hey jarvis". No network calls, no API keys, low CPU.

Fallback engine: an energy-gated loop over the existing SpeechRecognition /
Google stack, so the feature keeps working even when openwakeword isn't
installed. Speech-recognition calls are only made when the mic actually
hears sound (the library's energy-based VAD gates them), so the fallback
doesn't hammer the API during silence.
"""

import threading
import time

try:
    import numpy as _np
    from openwakeword.model import Model as _OWWModel
    OPENWAKEWORD_OK = True
except Exception:  # pragma: no cover - depends on user's environment
    OPENWAKEWORD_OK = False


class WakeWordListener:
    """Listens continuously for the wake word in a background thread.

    on_wake:   called (from the listener thread) when the wake word is heard.
               The mic is guaranteed to be free at that moment, so the
               callback can open it for a full command capture.
    is_paused: optional callable returning True while the assistant is busy
               speaking/processing, so it never wakes itself up on its own
               reply. The loop idles (draining audio) while paused.
    """

    def __init__(self, botname="jarvis", on_wake=None, is_paused=None,
                 threshold=0.5):
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
        if OPENWAKEWORD_OK:
            try:
                self._run_offline()
                return
            except Exception as e:
                print(f"[wake] offline engine failed ({e}); "
                      f"using online fallback")
        self._run_online()

    def _run_offline(self):
        """Listen with openwakeword in ~80 ms frames at 16 kHz.

        The mic stream is always closed BEFORE on_wake fires so the caller
        can immediately open the mic to capture the actual command.
        """
        import pyaudio
        oww = _OWWModel(inference_framework="onnx",
                        wakeword_models=["hey_jarvis"])
        pa = pyaudio.PyAudio()
        print("[wake] offline 'hey jarvis' listening (openwakeword)")
        cooldown = 0.0
        try:
            while self.running:
                try:
                    stream = pa.open(
                        format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=1280)
                except Exception:
                    raise   # outer finally owns pa.terminate()
                woke = False
                try:
                    while self.running:
                        if self._paused():
                            # drain the buffer while idle so it never overflows
                            try:
                                stream.read(1280, exception_on_overflow=False)
                            except Exception:
                                pass
                            time.sleep(0.1)
                            continue
                        data = stream.read(1280, exception_on_overflow=False)
                        frame = _np.frombuffer(data, dtype=_np.int16)
                        score = oww.predict(frame).get("hey_jarvis", 0.0)
                        if (score >= self.threshold
                                and time.time() >= cooldown):
                            # cooldown so JARVIS's own reply never re-triggers
                            cooldown = time.time() + 3.0
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
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        cooldown = 0.0
        print("[wake] online fallback listening (Google speech recognition)")
        while self.running:
            if self._paused():
                time.sleep(0.4)
                continue
            try:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.4)
                    audio = recognizer.listen(source, timeout=2,
                                              phrase_time_limit=2)
                if not self.running:
                    break
                if time.time() < cooldown:
                    continue
                text = ""
                try:
                    text = recognizer.recognize_google(
                        audio, language="en-in").lower()
                except Exception:
                    continue  # speech heard but not understood — not a wake
                if self._is_wake_text(text):
                    cooldown = time.time() + 4.0
                    self._fire()
            except Exception as e:
                print(f"[wake] online error: {e}")
                time.sleep(1.0)

    def _is_wake_text(self, text):
        """True when a transcript is ADDRESSED to the assistant.

        The name must lead the utterance ("hey jarvis ..." / "jarvis ..."),
        which avoids false wakes from ordinary speech that merely mentions
        the name somewhere mid-sentence.
        """
        t = (text or "").strip().lower().rstrip(".,!?")
        return (t.startswith("hey " + self.botname)
                or t.startswith(self.botname))

    def _fire(self):
        try:
            if self.on_wake:
                self.on_wake()
        except Exception as e:
            print(f"[wake] on_wake callback error: {e}")
