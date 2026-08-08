"""Persistent personal memory for J.A.R.V.I.S.

The user can tell JARVIS things about themselves — "my name is Alice",
"I like football", "my favourite colour is blue" — and those facts are saved
to ``ai_memory.json`` so they survive restarts. Known facts are injected into
the system prompt so every reply feels personal and remembered.

Facts are extracted with lightweight regexes (no model needed, works offline
with the tiny local models). Extraction only fires on explicit statements, so
ordinary chat like "what is my name" is unaffected.
"""

import json
import os
import re

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "ai_memory.json")

# ---------------------------------------------------------------------------
# Fact extraction patterns. Each (key, [regexes]) — regexes are matched with
# re.search, IGNORECASE; the first capturing group is the value.
# ---------------------------------------------------------------------------

_NAME_RE = [
    r"\bmy name (?:is|'s)\s+([a-z][a-z' -]{0,30})",
    r"\bcall me\s+([a-z][a-z' -]{0,30})",
    r"\bi(?:'m| am)\s+called\s+([a-z][a-z' -]{0,30})",
]

_INTEREST_RE = [
    r"\bi\s+(?:really\s+|totally\s+|kind of\s+|also\s+)?"
    r"(?:like|love|enjoy|adore)\s+([a-z0-9][a-z0-9 ,&'-]{0,40})",
    r"\bi(?:'m| am)\s+(?:really\s+)?into\s+([a-z0-9][a-z0-9 ,&'-]{0,40})",
    r"\bi(?:'m| am)\s+(?:a\s+|a big\s+)?fan of\s+([a-z0-9][a-z0-9 ,&'-]{0,40})",
    r"\bmy\s+(?:hobbies|hobby)\s+(?:are|is)\s+([a-z0-9][a-z0-9 ,&'-]{0,40})",
]

_FAVORITE_THINGS = {
    "color", "colour", "food", "movie", "film", "song", "band", "artist",
    "show", "game", "team", "book", "sport", "subject", "place", "animal",
    "season", "drink",
}
_FAVORITE_RE = [
    r"\bmy\s+(?:favorite|favourite)\s+(\w+)\s+is\s+"
    r"([a-z0-9][a-z0-9 ,&'-]{0,40})",
]

_OCCUPATION_RE = [
    r"\bi(?:'m| am)\s+a\s+(student|teacher|engineer|developer|programmer|"
    r"doctor|nurse|lawyer|designer|artist|musician|writer|chef|cook|manager|"
    r"analyst|researcher|scientist|pilot|driver|police|soldier|actor|athlete|"
    r"accountant|consultant|entrepreneur|freelancer)\b",
    r"\bi\s+work\s+as\s+(?:a\s+|an\s+)?([a-z][a-z ]{0,20})\b",
]

_LOCATION_RE = [
    r"\bi(?:'m| am)\s+from\s+([a-z][a-z -]{0,30})",
    r"\bi\s+live in\s+([a-z][a-z -]{0,30})",
    r"\bi\s+stay in\s+([a-z][a-z -]{0,30})",
]

_BIRTHDAY_RE = [
    r"\bmy\s+birthday\s+is\s+([a-z0-9 ,/-]{3,40})",
]

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def load_memory():
    """Read the memory file. Returns {} on any error (fresh start)."""
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_memory(mem):
    """Persist the memory dict to disk (best-effort)."""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[memory] could not save: {e}")


def clear_memory():
    """Delete the memory file. Returns True on success."""
    try:
        os.remove(MEMORY_FILE)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"[memory] could not clear: {e}")
        return False


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Values that aren't real interests ("i love you", "i like this")
_INTEREST_STOPWORDS = {"you", "this", "that", "it", "them", "us",
                       "him", "her", "me"}

# Bounds so the memory can never grow without limit:
#  - the JSON file keeps at most this many distinct interests
#  - only this many interests are injected into the model prompt
#  - the injected memory line is hard-truncated at this many characters
MAX_STORED_INTERESTS = 50
MAX_PROMPT_INTERESTS = 10
MAX_SNIPPET_CHARS = 600


def _clean_value(value):
    """Trim punctuation / trailing fluff from a captured value."""
    v = (value or "").strip()
    v = re.sub(r"[.,;!?]+$", "", v).strip()
    v = re.sub(r"\s+(please|thanks|thank you|plz)\s*$", "", v,
               flags=re.I).strip()
    return v


def extract_facts(text):
    """Return [(key, value), ...] facts stated in ``text``.

    Matches are lowercased. Name and single-valued facts keep the first
    match; interests accumulate every distinct match.
    """
    t = (text or "").lower()
    facts = []

    # name (first match only)
    for pat in _NAME_RE:
        m = re.search(pat, t)
        if m:
            val = _clean_value(m.group(1)).strip("' ")
            if val and val.lower() not in _INTEREST_STOPWORDS:
                facts.append(("name", val))
            break

    # interests (may be several; "football and coding" splits into two)
    for pat in _INTEREST_RE:
        for m in re.finditer(pat, t):
            val = _clean_value(m.group(1))
            if not val:
                continue
            val = re.sub(r"^(?:to|about)\s+", "", val).strip()  # "like to play"
            # drop a trailing platform mention: "play despacito on youtube"
            val = re.sub(r"\s+on\s+(youtube|spotify|netflix|amazon\s*prime)\s*$",
                         "", val, flags=re.I).strip()
            for piece in re.split(r"\s+(?:and|&)\s+|\s*,\s*", val):
                piece = piece.strip()
                if piece and piece.lower() not in _INTEREST_STOPWORDS:
                    facts.append(("interests", piece))

    # favorites: "my favorite <thing> is <value>"
    for pat in _FAVORITE_RE:
        m = re.search(pat, t)
        if m:
            thing = m.group(1).lower()
            if thing == "colour":
                thing = "color"
            if thing in _FAVORITE_THINGS:
                val = _clean_value(m.group(2))
                if val:
                    facts.append((f"favorite_{thing}", val))
            break

    # occupation
    for pat in _OCCUPATION_RE:
        m = re.search(pat, t)
        if m:
            val = _clean_value(m.group(1))
            if val:
                facts.append(("occupation", val))
            break

    # location
    for pat in _LOCATION_RE:
        m = re.search(pat, t)
        if m:
            val = _clean_value(m.group(1))
            if val:
                facts.append(("location", val))
            break

    # birthday
    for pat in _BIRTHDAY_RE:
        m = re.search(pat, t)
        if m:
            val = _clean_value(m.group(1))
            if val:
                facts.append(("birthday", val))
            break

    return facts


def apply_facts(mem, facts):
    """Merge extracted facts into the memory dict.

    Returns the list of facts that were actually new/changed, so the caller
    can confirm them to the user.
    """
    mem = mem if isinstance(mem, dict) else {}
    applied = []
    for key, val in facts:
        if key == "interests":
            existing = mem.setdefault("interests", [])
            # cap the stored list so the file can't grow forever
            if (val not in existing
                    and len(existing) < MAX_STORED_INTERESTS):
                existing.append(val)
                applied.append((key, val))
        else:
            if mem.get(key) != val:
                mem[key] = val
                applied.append((key, val))
    return applied


# ---------------------------------------------------------------------------
# Prompt / speech snippets
# ---------------------------------------------------------------------------


def memory_snippet(mem):
    """A line for the system prompt describing known facts ('' if none)."""
    mem = mem or {}
    parts = []
    name = mem.get("name")
    if name:
        parts.append(f"name is {name}")
    for key, val in mem.items():
        if key == "name":
            continue
        if key == "interests":
            if val:
                shown = val[:MAX_PROMPT_INTERESTS]
                more = len(val) - len(shown)
                text = ", ".join(shown)
                if more > 0:
                    text += f" (+{more} more)"
                parts.append("interests: " + text)
        elif key.startswith("favorite_"):
            parts.append(f"favorite {key[len('favorite_'):]}: {val}")
        else:
            parts.append(f"{key.replace('_', ' ')}: {val}")
    if not parts:
        return ""
    text = ("Facts you know about the user (weave them in naturally when "
            "relevant): " + "; ".join(parts) + ".")
    # hard cap: never let the injected line eat the model's context window
    if len(text) > MAX_SNIPPET_CHARS:
        text = text[:MAX_SNIPPET_CHARS].rstrip() + "..."
    return text


def memory_summary(mem):
    """A spoken summary of what JARVIS remembers about the user."""
    mem = mem or {}
    if not mem:
        return ("I don't know much about you yet. Tell me your name, your "
                "hobbies, or what you like!")
    parts = []
    name = mem.get("name")
    if name:
        parts.append(f"your name is {name}")
    for key, val in mem.items():
        if key == "name":
            continue
        if key == "interests":
            if val:
                parts.append("you like " + ", ".join(val))
        elif key.startswith("favorite_"):
            parts.append(f"your favourite {key[len('favorite_'):]} is {val}")
        else:
            parts.append(f"your {key.replace('_', ' ')} is {val}")
    return "Here's what I remember about you: " + ", ".join(parts) + "."


def confirmation_text(facts):
    """A short friendly confirmation for facts that were just saved."""
    msgs = []
    for key, val in facts:
        if key == "name":
            msgs.append(f"Nice to meet you, {val.title()}! I'll remember that.")
        elif key == "interests":
            msgs.append(f"Cool — I'll remember you like {val}.")
        elif key == "favorite_color":
            msgs.append(f"Nice — {val} is a great colour pick!")
        elif key == "occupation":
            msgs.append(f"A {val}? Nice, noted!")
        elif key == "location":
            msgs.append(f"Nice — {val}! Noted.")
        elif key == "birthday":
            msgs.append("Got it — I'll remember your birthday!")
        elif key.startswith("favorite_"):
            msgs.append(f"{val.title()}? Noted!")
        else:
            msgs.append(f"Got it — {val}. Noted!")
    return " ".join(msgs)
