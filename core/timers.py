"""Timers & reminders for J.A.R.V.I.S.

``TimerManager`` is a tiny daemon thread that fires messages after a delay —
no cloud, no services. Parsers turn natural phrases like "set a timer for 10
minutes", "10 minute timer", "remind me to call dad in 5 minutes" and
"remind me at 5 pm to stretch" into (message, seconds) pairs.

Usage:
    timers = TimerManager(on_fire=lambda msg: speak(msg))
    timers.add(600, "Reminder: stretch your legs!")
    timers.add_until(hour=17, minute=0, ampm="pm", message="Time to leave!")
"""

import re
import threading
import time
from datetime import datetime

_UNIT_RE = r"(?:sec(?:ond)?s?|s|min(?:ute)?s?|m|hour(?:s)?|hrs?|h)"

# "set a timer for 10 minutes", "timer 30 seconds", "set timer 5 min"
_TIMER_AFTER_RE = re.compile(
    r"\b(?:set\s+(?:a\s+|an\s+)?)?(?:timer|stopwatch)\s*(?:for|of)?\s*"
    r"(\d+)\s*(" + _UNIT_RE + r")\b", re.IGNORECASE)

# "10 minute timer", "30 second timer"
_TIMER_BEFORE_RE = re.compile(
    r"\b(\d+)\s*(" + _UNIT_RE + r")\s*(?:timer|stopwatch)\b", re.IGNORECASE)

# "remind me to <task> in N minutes" / "remind me in N minutes to <task>"
_REMIND_IN_RE = [
    re.compile(
        r"\bremind\s+me\s+(?:to\s+)?(.+?)\s+in\s+(\d+)\s*(" + _UNIT_RE +
        r")\b", re.IGNORECASE),
    re.compile(
        r"\bremind\s+me\s+in\s+(\d+)\s*(" + _UNIT_RE + r")\s+(?:to\s+)?"
        r"(.+?)\s*$", re.IGNORECASE),
]

# "remind me to <task> at 5 pm" / "remind me at 5:30 pm to <task>"
_REMIND_AT_RE = [
    re.compile(
        r"\bremind\s+me\s+(?:to\s+)?(.+?)\s+at\s+(\d{1,2})(?::(\d{2}))?"
        r"\s*(am|pm)?\b", re.IGNORECASE),
    re.compile(
        r"\bremind\s+me\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+"
        r"(?:to\s+)?(.+?)\s*$", re.IGNORECASE),
]

# "remind me in 10 minutes" (no task -> generic message)
_REMIND_IN_BARE_RE = re.compile(
    r"\bremind\s+me\s+in\s+(\d+)\s*(" + _UNIT_RE + r")\b", re.IGNORECASE)

# bare time replies to "when should I remind you?": "in 10 minutes",
# "at 5:30 pm", "5 pm"
_TIME_AT_RE = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_TIME_DUR_RE = re.compile(
    r"\b(?:in\s+|after\s+)?(\d+)\s*(" + _UNIT_RE + r")\b", re.IGNORECASE)
_TIME_CLOCK_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)


def _to_seconds(num, unit):
    """'10', 'minutes' -> 600."""
    u = (unit or "").lower().rstrip("s")
    n = int(num)
    if u in ("s", "sec", "second"):
        return n
    if u in ("m", "min", "minute"):
        return n * 60
    if u in ("h", "hr", "hour", "hrs"):
        return n * 3600
    return n * 60  # safe default: minutes


def parse_timer_command(text):
    """Parse 'set a timer for 10 minutes'. Returns (seconds, raw_unit) or
    None when no timer is mentioned."""
    t = (text or "").strip()
    if not t:
        return None
    m = _TIMER_AFTER_RE.search(t) or _TIMER_BEFORE_RE.search(t)
    if not m:
        return None
    return _to_seconds(m.group(1), m.group(2)), m.group(2)


def seconds_until(hour, minute=0, ampm=None):
    """Seconds from now until the next occurrence of the given clock time
    (rolls to tomorrow if that time already passed today)."""
    h = int(hour)
    if ampm:
        ap = ampm.strip().lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
    now = datetime.now()
    target = now.replace(hour=h, minute=int(minute), second=0, microsecond=0)
    delta = (target - now).total_seconds()
    if delta <= 0:
        delta += 86400
    return delta


def parse_reminder_command(text):
    """Parse a 'remind me ...' phrase.

    Returns (task, seconds): task is the reminder text ('' when the user
    only said a time), seconds is how long until it fires. Returns None when
    the phrase isn't a reminder.
    """
    t = (text or "").strip()
    if not t or "remind" not in t.lower():
        return None

    # order 1: "remind me to <task> in N minutes"
    m = _REMIND_IN_RE[0].search(t)
    if m:
        task, num, unit = m.group(1), m.group(2), m.group(3)
        return task.strip().strip(".,!?"), _to_seconds(num, unit)
    # order 2: "remind me in N minutes to <task>"
    m = _REMIND_IN_RE[1].search(t)
    if m:
        num, unit, task = m.group(1), m.group(2), m.group(3)
        return task.strip().strip(".,!?"), _to_seconds(num, unit)

    # order 1: "remind me to <task> at 5 pm"
    m = _REMIND_AT_RE[0].search(t)
    if m:
        task = m.group(1)
        hour, minute, ampm = m.group(2), m.group(3) or 0, m.group(4)
        return (task.strip().strip(".,!?") or "",
                seconds_until(hour, minute, ampm))
    # order 2: "remind me at 5:30 pm to <task>"
    m = _REMIND_AT_RE[1].search(t)
    if m:
        hour, minute, ampm = m.group(1), m.group(2) or 0, m.group(3)
        task = m.group(4)
        return (task.strip().strip(".,!?") or "",
                seconds_until(hour, minute, ampm))

    # "remind me in 10 minutes" with no task
    m = _REMIND_IN_BARE_RE.search(t)
    if m:
        return "", _to_seconds(m.group(1), m.group(2))

    # "remind me" with no time at all — the caller asks for the time
    return None


def parse_time_reply(text):
    """Parse a spoken time answer like 'in 10 minutes', '30 seconds' or
    'at 5:30 pm' into seconds. Returns None when no time is recognized."""
    t = (text or "").strip()
    if not t:
        return None
    m = _TIME_AT_RE.search(t)
    if m:
        return seconds_until(m.group(1), m.group(2) or 0, m.group(3))
    m = _TIME_DUR_RE.search(t)
    if m:
        return _to_seconds(m.group(1), m.group(2))
    m = _TIME_CLOCK_RE.search(t)
    if m:
        return seconds_until(m.group(1), m.group(2) or 0, m.group(3))
    return None


def format_duration(seconds):
    """'10 minutes', '1 hour and 5 minutes' — for speaking out loud."""
    s = int(round(float(seconds)))  # never truncate 599.9s into '9 minutes'
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''}"
    m = s // 60
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''}"
    h, rem = divmod(m, 60)
    if rem:
        return (f"{h} hour{'s' if h != 1 else ''} and "
                f"{rem} minute{'s' if rem != 1 else ''}")
    return f"{h} hour{'s' if h != 1 else ''}"


class TimerManager:
    """Fires messages after delays from a single daemon thread."""

    def __init__(self, on_fire=None):
        self.on_fire = on_fire or (lambda message: None)
        self._items = []          # (due_monotonic, message)
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def add(self, seconds, message):
        """Fire ``message`` after ``seconds`` (float/int)."""
        with self._lock:
            self._items.append((time.monotonic() + max(0.0, float(seconds)),
                                str(message)))

    def add_until(self, hour, minute=0, ampm=None, message=""):
        """Remind at the next occurrence of a clock time."""
        self.add(seconds_until(hour, minute, ampm), message)

    def list(self):
        """[(seconds_remaining, message), ...] sorted soonest first."""
        with self._lock:
            now = time.monotonic()
            items = sorted((due - now, msg) for due, msg in self._items)
        return [(max(0.0, s), msg) for s, msg in items]

    def cancel_all(self):
        with self._lock:
            self._items.clear()

    def _run(self):
        while True:
            time.sleep(0.5)
            due_now = []
            with self._lock:
                now = time.monotonic()
                keep = []
                for due, msg in self._items:
                    if now >= due:
                        due_now.append(msg)
                    else:
                        keep.append((due, msg))
                self._items = keep
            for msg in due_now:
                try:
                    self.on_fire(msg)
                except Exception as e:  # never let a timer kill the thread
                    print(f"[timers] fire error: {e}")
