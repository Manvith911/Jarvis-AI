"""End-to-end check of the local STT pipeline.

Flow exercised (exactly what J.A.R.V.I.S. does at runtime):
    SAPI5 speaks a phrase  ->  saved as 16 kHz mono WAV
    ->  wrapped in speech_recognition.AudioData
    ->  core.stt.transcribe_local() (faster-whisper, no Google)

Run with the project Python (the same one that runs the HUD):
    python tests/stt_check.py

Exit code 0 = the local engine loaded and transcribed correctly.
Needs: faster-whisper installed (already in requirements.txt), a SAPI5
voice (Windows) and internet for the one-time model download (~75 MB base).
"""

import os
import sys
import tempfile
import wave

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def speak_to_wav(text, path):
    """Speak ``text`` through the Windows SAPI5 voice into a WAV file."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    # SAFT16kHz16BitMono = 4, SSFMCreateForWrite = 3
    stream.Format.Type = 4
    stream.Open(path, 3)
    voice.AudioOutputStream = stream
    voice.Speak(text)
    stream.Close()


def wav_to_audiodata(path):
    import speech_recognition as sr
    with wave.open(path, "rb") as w:
        frames = w.readframes(w.getnframes())
        return sr.AudioData(frames, w.getframerate(), w.getsampwidth())


def main():
    phrase = "Hello Jarvis, what is the weather today?"

    from core.stt import local_available, transcribe_local

    print("[1/3] Loading local whisper model (downloads once on first use)...")
    ok = local_available()
    print(f"      local engine available: {ok}")
    if not ok:
        print("FAIL: faster-whisper model could not be loaded.")
        return 1

    print(f"[2/3] Speaking through SAPI5: {phrase!r}")
    tmp = os.path.join(tempfile.gettempdir(), "jarvis_stt_check.wav")
    try:
        speak_to_wav(phrase, tmp)
    except Exception as e:
        print(f"FAIL: could not render speech to WAV: {e}")
        return 1
    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        print("FAIL: WAV file is empty.")
        return 1
    print(f"      WAV written: {os.path.getsize(tmp)} bytes")

    print("[3/3] Transcribing with local whisper (no Google)...")
    audio = wav_to_audiodata(tmp)
    text = transcribe_local(audio)
    print(f"      transcript: {text!r}")

    if not text:
        print("FAIL: nothing was transcribed.")
        return 1
    low = text.lower()
    if "jarvis" not in low or "weather" not in low:
        print(f"FAIL: transcript doesn't match the phrase ({phrase!r}).")
        return 1
    print("PASS: local speech-to-text works end-to-end, fully offline "
          "(Google was never involved).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
