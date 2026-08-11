"""Local speech-to-text (faster-whisper) with a Google fallback.

J.A.R.V.I.S. can now transcribe your voice **fully offline** with
`faster-whisper` (CTranslate2-based, runs great on a laptop CPU with a small
model). Google's free speech API is only used when the local engine isn't
installed or can't be loaded — so the core voice loop finally works with no
internet at all.

Configure via .env:
    WHISPER_MODEL          tiny / base / small / medium (default: base)
    WHISPER_DEVICE         cpu / cuda / auto (default: auto)
    WHISPER_COMPUTE_TYPE   int8 / float16 / float32 (default: int8)
    WHISPER_LANGUAGE       en / hi / ... (default: en; '' = auto-detect)

The first transcription downloads the model (e.g. ~75 MB for "base") and
caches it forever. `faster-whisper` is an optional dependency — everything
keeps working (via Google) if it isn't installed.
"""

from decouple import config

WHISPER_MODEL = config("WHISPER_MODEL", default="base")
WHISPER_DEVICE = config("WHISPER_DEVICE", default="auto")
WHISPER_COMPUTE = config("WHISPER_COMPUTE_TYPE", default="int8")
WHISPER_LANGUAGE = config("WHISPER_LANGUAGE", default="en") or None

# faster-whisper is imported lazily and exactly once (the model load is
# heavy). These globals are guarded by _lock.
import threading

_lock = threading.Lock()
_model = None
_loaded = False


def _load_model():
    """Load the local whisper model once. Returns the model or None."""
    global _model, _loaded
    with _lock:
        if _loaded:
            return _model
        _loaded = True
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE,
                                  compute_type=WHISPER_COMPUTE)
            print(f"[stt] local whisper '{WHISPER_MODEL}' ready "
                  f"({WHISPER_DEVICE}/{WHISPER_COMPUTE})")
        except Exception as e:
            print(f"[stt] local whisper unavailable ({e}); "
                  "using Google speech-to-text")
            _model = None
        return _model


def local_available():
    """True when the local whisper engine is usable (loads it if needed)."""
    return _load_model() is not None


def transcribe_local(audio):
    """Transcribe a ``speech_recognition`` AudioData with local whisper.

    Returns the transcript string, or None when the engine is unavailable
    or nothing was understood. Never raises.
    """
    model = _load_model()
    if model is None:
        return None
    try:
        import numpy as np
        # 16 kHz mono int16 -> float32 [-1, 1] for whisper
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        samples /= 32768.0
        segments, _info = model.transcribe(
            samples, language=WHISPER_LANGUAGE, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None
    except Exception as e:
        print(f"[stt] local transcribe error: {e}")
        return None


def transcribe(audio, recognizer, language="en"):
    """Transcribe audio, preferring the local engine.

    Falls back to Google's recognizer when the local engine is missing or
    hears nothing. Returns the text or None on total failure — the caller
    decides what silence means. Never raises.
    """
    try:
        text = transcribe_local(audio)
        if text:
            return text
    except Exception:
        pass
    try:
        return recognizer.recognize_google(audio, language=language)
    except Exception:
        return None
