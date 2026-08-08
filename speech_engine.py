"""
SAPI5 speech engine (Windows) — a reliable drop-in for pyttsx3.

Why not pyttsx3? On many Windows systems pyttsx3's ``runAndWait()`` only
produces audio for the *first* utterance per engine instance — every
subsequent call returns instantly and silently. Driving SAPI5 directly via
win32com and calling ``SpVoice.Speak()`` in synchronous mode blocks until
each phrase is actually spoken, which is reliable for streaming TTS.

Usage (create one instance on each thread that speaks):
    speech = SapiSpeech(rate=1)
    if speech.ok:
        speech.speak("Hello there!")
"""

import re

try:
    import pythoncom
    import win32com.client
    _COM_OK = True
except Exception:
    _COM_OK = False

# SAPI5 reads emoji and pictographs out loud as long descriptions ("smiling
# face with smiling eyes", "black heart", "black right-pointing triangle",
# ...). Strip those — plus markdown markers and ASCII smilies — before
# speaking so only real words reach audio.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # emojis & pictographs (faces, animals, food...)
    "\U00002600-\U000027BF"   # misc symbols & dingbats (☀ ★ ♥ ⚠ ✈ ...)
    "\U00002190-\U000021FF"   # arrows (← → ↑ ↓ ...)
    "\U00002300-\U000023FF"   # misc technical (⏰ ⌚ ...)
    "\U000025A0-\U000025FF"   # geometric shapes (▶ ■ ◆ ● ...)
    "\U00002B00-\U00002BFF"   # arrows & math symbols (⬅ ⬆ ⬇ ⭕ ...)
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flag emojis)
    "\U0000FE0F"              # variation selector-16 (emoji presentation)
    "\U0001F3FB-\U0001F3FF"   # skin-tone modifiers
    "\U0000200D"              # zero-width joiner
    "]+"
)
_SMILEY_RE = re.compile(r"(?i)[:;=]-?[)DdPpOo/\\*\[\]]+|[:;=]-?\(|</3")
_MD_RE = re.compile(r"[*_`~]+")
_WS_RE = re.compile(r"\s+")


def strip_for_speech(text):
    """Clean text before it reaches the speech engine.

    Removes emoji/pictographs (which SAPI reads as words like "smiling face
    with smiling eyes"), ASCII smilies (``:)``, ``:D``), and markdown
    emphasis markers (``**bold**``, backticks) so the assistant only speaks
    the actual words.
    """
    if not text:
        return ""
    cleaned = _EMOJI_RE.sub(" ", text)
    cleaned = _SMILEY_RE.sub(" ", cleaned)
    cleaned = _MD_RE.sub(" ", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip()


class SapiSpeech:
    """Thin, reliable SAPI5 text-to-speech wrapper."""

    def __init__(self, rate=1):
        self.ok = False
        self.error = "win32com (pywin32) is not installed"
        if not _COM_OK:
            return
        try:
            pythoncom.CoInitialize()
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
            self._voice.Volume = 100
            self._voice.Rate = rate
            self._pick_voice()
            self.ok = True
            self.error = None
        except Exception as e:
            self.error = str(e)

    def _pick_voice(self):
        """Prefer Microsoft David / Zira / Hazel / Mark, else the first."""
        try:
            voices = self._voice.GetVoices()
            n = voices.Count
            for pref in ("david", "zira", "hazel", "mark"):
                for i in range(n):
                    if pref in voices.Item(i).GetDescription().lower():
                        self._voice.Voice = voices.Item(i)
                        return
            if n > 0:
                self._voice.Voice = voices.Item(0)
        except Exception:
            pass

    def speak(self, text):
        """Speak synchronously — returns once the phrase has been spoken."""
        clean = strip_for_speech(text)
        if not self.ok or not clean:
            return
        self._voice.Speak(clean)

    def purge(self):
        """Stop current speech and clear anything queued (SAPI5)."""
        try:
            # SVSFlagsAsync | SVSFPurgeBeforeSpeak
            self._voice.Speak("", 1 | 8)
        except Exception:
            pass
