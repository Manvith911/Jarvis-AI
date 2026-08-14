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

import re

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


# Whisper's accuracy on short, quiet commands drops a lot when the input is
# barely audible or has no context. These tune the local engine for exactly
# that case (see transcribe_local below).
_WHISPER_INITIAL_PROMPT = (
    "The following is a short voice command spoken to a personal assistant:"
)

# --- anti-hallucination guards --------------------------------------------
# Whisper famously *hallucinates* when handed near-silent or noise-only
# audio: it invents plausible-sounding text out of nothing, and with an
# initial_prompt set it often echoes the prompt back verbatim ("The
# following is a short voice command spoken to a personal assistant...").
# That's how "random things" got heard when nothing was said. Every guard
# below exists to keep invented transcripts from ever becoming commands.

# A capture with a peak below this is effectively silence (int16 0.001 ≈
# -60 dBFS) — don't even hand it to whisper.
_MIN_SPEECH_PEAK = 0.001

# Segments whisper itself flags as "no speech" (high no_speech_prob means
# the text was invented over silence) or with an extreme compression ratio
# (the repetitive-loop hallucination signature) are dropped.
_NO_SPEECH_LIMIT = 0.6
_COMPRESSION_LIMIT = 2.4

# The exact fragment whisper echoes when it hallucinates the initial prompt.
_PROMPT_ECHO = re.sub(
    r"\s+", " ", _WHISPER_INITIAL_PROMPT.lower().strip(" :")
).strip()


def _normalize(text):
    """Lowercase and collapse whitespace for hallucination checks."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _is_hallucinated_segment(seg):
    """True when whisper's own confidence says a segment is invented."""
    # type-guarded: real faster-whisper segments expose plain floats, and
    # anything else (mocks, None, weird objects) is left alone
    try:
        no_speech = getattr(seg, "no_speech_prob", None)
        if isinstance(no_speech, (int, float)) and no_speech > _NO_SPEECH_LIMIT:
            return True
    except Exception:
        pass
    try:
        cr = getattr(seg, "compression_ratio", None)
        if isinstance(cr, (int, float)) and cr > _COMPRESSION_LIMIT:
            return True
    except Exception:
        pass
    return False


def _is_hallucinated_text(text):
    """True when a transcript smells like a whisper hallucination: an echo
    of the initial prompt, or a 4+ word phrase repeated verbatim (the
    classic whisper loop)."""
    t = _normalize(text)
    if not t:
        return True
    if _PROMPT_ECHO and _PROMPT_ECHO in t:
        return True
    words = t.split()
    for n in (4, 5):
        seen = set()
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if phrase in seen:
                return True
            seen.add(phrase)
    return False


def has_audible_speech(audio, min_peak=0.025):
    """True when the captured audio contains speech-like energy (as opposed
    to near-silence or ambient noise).

    Callers use this to decide whether a failed transcription means "say
    that again" (real speech, not understood) or "nothing was said" (stay
    quiet — ambient noise tripped the microphone). 0.025 (≈ -32 dBFS) sits
    comfortably above fan/HVAC-type noise (peak ~0.005–0.02) while staying
    well below even quiet human speech (peak ~0.03+), so noise never gets a
    spoken apology. This only gates the "nothing was understood" branch —
    quiet speech still gets the 4x boost before transcription.
    """
    try:
        import numpy as np
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = np.frombuffer(raw, dtype=np.int16)
        if not samples.size:
            return False
        peak = float(np.max(np.abs(samples))) / 32768.0
        return peak >= min_peak
    except Exception:
        return True  # can't tell — err on the side of asking again


def new_recognizer():
    """Build a speech_recognition Recognizer tuned for quiet speakers.

    The library's stock VAD calibrates its energy threshold with a very slow
    asymmetric average (damping 0.97) toward ``ambient * 1.5``, starting from
    a hardcoded 300. In practice the threshold barely moves during the short
    calibration window, so it sits far above quiet speech and soft commands
    are never heard at all (``listen()`` just times out).

    Lowering the ratio and damping makes the calibration converge close to
    the real noise floor in the ~0.5 s window, so normal AND quiet voices
    cross the threshold. Callers still call ``adjust_for_ambient_noise``
    before ``listen`` and may floor the result (see core/assistant.py).
    """
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 150
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_ratio = 1.2          # default 1.5
    recognizer.dynamic_energy_adjustment_damping = 0.6   # default 0.97
    return recognizer


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
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        # digital silence — whisper hallucinates on this, say nothing
        if peak < _MIN_SPEECH_PEAK:
            return None
        # Whisper expects normal-level audio; quiet speech (soft voices, mic
        # too far) reaches the model as a near-silent whisper and gets
        # misheard. Boost low-level input so the model hears it clearly,
        # capped so background noise isn't amplified into the transcript.
        if 0.0 < peak < 0.35:
            samples = samples * min(1.0 / peak, 4.0)
        segments, _info = model.transcribe(
            samples,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            # short isolated commands: don't let whisper condition on a
            # previous (empty) context, which causes hallucinated repeats
            condition_on_previous_text=False,
            # orient the model toward a short voice command — this noticeably
            # reduces mis-transcriptions of commands like "open chrome"
            initial_prompt=_WHISPER_INITIAL_PROMPT,
            # Silero VAD (bundled with faster-whisper) strips the non-speech
            # chunks that whisper loves to invent text over — the main fix
            # for "it heard something when I didn't say anything"
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        # drop segments whisper itself doubts, then reject transcripts that
        # still look like hallucinations (prompt echo / looping text)
        parts = []
        for seg in segments:
            if _is_hallucinated_segment(seg):
                continue
            parts.append(seg.text.strip())
        text = " ".join(parts).strip()
        if not text or _is_hallucinated_text(text):
            return None
        return text
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
