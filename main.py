import threading
import time
import requests
import re
import pyttsx3
import speech_recognition as sr
from decouple import config
from datetime import datetime
import os
import sys

# Windows console: print emoji/unicode without crashing
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# pythonw.exe (silent autostart) has NO console, so sys.stdout/stderr are
# None there and any print() would crash the app. Send them to a log file
# (truncated each launch) so silent failures stay diagnosable; if the log
# can't be opened, fall back to devnull rather than crash at import.
if sys.stdout is None or sys.stderr is None:
    _sink = None
    try:
        _log_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "jarvis_autostart.log")
        _sink = open(_log_path, "w", encoding="utf-8")
    except Exception:
        pass
    if _sink is None:
        _sink = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _sink
    if sys.stderr is None:
        sys.stderr = _sink

from ollama_streaming import StreamingOllama, BIG_MODEL, split_deep_marker
from ai_memory import (
    apply_facts, clear_memory, confirmation_text, extract_facts,
    load_memory, memory_snippet, memory_summary, save_memory,
)
from functions.online_ops import (
    find_my_ip, get_city_from_ip, get_latest_news, get_random_joke,
    get_weather_report, play_on_youtube,
    search_on_wikipedia, search_on_google
)
from functions.os_ops import (
    open_application, open_in_browser, parse_open_command,
    search_url, strip_politeness, take_screenshot
)

HISTORY_FILE = "ai_conversation_history.txt"

def load_history():
    """Read saved conversation history."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def append_history(summary):
    """Append summary to history file."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(summary.strip() + "\n\n")


_CITY_RE = re.compile(
    r"(?:weather|temperature)\s+(?:in|at|for)\s+(.+?)\s*$",
    re.IGNORECASE,
)


def parse_city_from_query(query):
    """Pull a city out of 'weather in london today' or "what's the weather
    today in new york". Returns None when no city is mentioned."""
    m = _CITY_RE.search(query or "")
    if not m:
        return None
    city = m.group(1).strip()
    # drop trailing words that aren't part of the city name
    city = re.sub(
        r"\b(today|right now|now|please|tomorrow|this week|this afternoon|"
        r"this evening|tonight|currently)\b.*$",
        "", city, flags=re.IGNORECASE).strip()
    return city or None

class Speech:
    """Text-to-speech system (SAPI5 via win32com, pyttsx3 as fallback)."""

    def __init__(self):
        self.is_speaking = False
        self.speech_lock = threading.Lock()
        self.tts_available = False
        self._sapi = None
        self._engine = None
        try:
            from speech_engine import SapiSpeech, strip_for_speech
            self._sapi = SapiSpeech(rate=1)
            if self._sapi.ok:
                self.tts_available = True
                print("TTS ready")
                return
            print(f"SAPI5 unavailable ({self._sapi.error}); trying pyttsx3...")
        except Exception as e:
            print(f"TTS init error: {e}")
        # fallback: pyttsx3 (on some systems only the first utterance
        # produces audio — the SAPI5 path above is preferred)
        try:
            import pyttsx3
            self._engine = pyttsx3.init('sapi5')
            self._engine.setProperty('rate', 180)
            self._engine.setProperty('volume', 1.0)
            voices = self._engine.getProperty('voices')
            if voices and len(voices) > 1:
                self._engine.setProperty('voice', voices[-1].id)
            self.tts_available = True
            print("TTS ready")
        except Exception as e:
            print(f"TTS failed: {e}")
            self.tts_available = False

    def speak(self, text):
        if not text or not text.strip():
            return
        with self.speech_lock:
            if not self.tts_available:
                print(f"TTS unavailable. Text: {text}")
                return
            try:
                self.is_speaking = True
                print(f"Speaking: {text}")
                if self._sapi is not None:
                    self._sapi.speak(text)
                else:
                    self._engine.say(strip_for_speech(text))
                    self._engine.runAndWait()
            except Exception as e:
                print(f"TTS error: {e}")
            finally:
                self.is_speaking = False

    def is_busy(self):
        return self.is_speaking

class PersonalizedAssistant:
    def __init__(self, model_name, botname, history_text):
        self.botname = botname
        self.tts = Speech()
        self.is_processing = False
        self.model = model_name
        self.ollama = StreamingOllama(model=self.model)
        self.history = []
        self.history_text = history_text
        # Persistent personal memory — facts the user shared in past chats
        # (name, interests, favorites...) override the .env fallback name.
        self.memory = load_memory()
        mem_name = self.memory.get("name")
        self.username = mem_name or config('USER', default='Friend')
        # FRIENDLY, CASUAL, HELPFUL PROMPT
        self.prompt_template = (
            f"{self.history_text}\n"
            "You are {botname}, an AI assistant who is also a friendly sidekick for {username}. "
            "The person talking to you is the user, and their name is {username}. "
            "Be warm, casual, and supportive—like a buddy who always has their back. "
            "Your tone should be fun, easygoing, and helpful, not too formal or robotic. "
            "Keep your answers short (1-2 sentences), unless more detail is needed. Don't be afraid to add a little personality, a joke, or a friendly comment now and then. "
            "IMPORTANT: when the user asks about themselves (like \"who am I\" or \"what is my name\"), "
            "answer about the USER ({username}) — never describe yourself for those questions. "
            "Only describe yourself when they ask \"who are you\".\n"
            "{memory}\n"
            "{ongoing}\nUser: {question}\nAI:"
        )

    def listen(self):
        if self.is_processing:
            return None
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        with sr.Microphone() as source:
            print('Listening...')
            try:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=5)
                print('Recognizing...')
                query = recognizer.recognize_google(audio, language='en-in')
                print(f"You said: {query}")
                return query.lower()
            except sr.WaitTimeoutError:
                print("Timeout")
            except sr.UnknownValueError:
                print("Didn't understand audio")
                self.tts.speak("Sorry, I couldn't catch that. Mind saying it again?")
            except Exception as e:
                print(f"Recognition error: {e}")
        return None

    def build_prompt(self, question):
        """Build the full prompt for a question, adding Google context when requested."""
        ongoing = "\n".join(self.history[-6:])

        # Google context addition
        google_context = ""
        if question.lower().startswith("google ") or question.lower().startswith("search on google"):
            google_query = question.partition(" ")[2] if question.lower().startswith("google ") else question.partition("search on google")[2].strip()
            self.speak("Give me a sec, googling that for you...")
            google_results = search_on_google(google_query)
            google_context = f"\n[Google info about '{google_query}']:\n{google_results}\n"

        return self.prompt_template.format(
            botname=self.botname,
            username=self.username,
            memory=memory_snippet(self.memory),
            ongoing=ongoing + google_context,
            question=question
        )

    def generate_reply(self, question, speak=True, paced=True):
        """Yield reply tokens one at a time, speaking them in sentence chunks.

        A generator so callers (CLI, GUI) can stream tokens as they arrive.
        Speech starts as soon as a phrase or sentence forms: the buffer flushes
        on sentence punctuation (period / exclamation / question), on softer
        breaks (commas, semicolons, colons, dashes, newlines) once a minimum
        length is reached, or after ``max_chunk`` characters so a long run of
        unpunctuated text never delays audio for long. When ``paced`` is True
        the generator waits for each chunk to finish speaking (good for the
        CLI); set it to False when another thread owns the speech queue so
        tokens flow at model speed.
        """
        prompt = self.build_prompt(question)
        buffer = ""
        hard_ends = {".", "!", "?"}
        soft_ends = {",", ";", ":", "\n", "\u2014", "\u2013"}  # , ; : newline — –
        min_chunk = 14     # don't speak tiny fragments like "Okay," alone
        max_chunk = 100    # force a flush so audio never lags far behind

        def speak_chunk(chunk):
            self.tts.speak(chunk)
            if paced:
                while self.tts.is_busy():
                    time.sleep(0.07)

        def flush(force=False):
            nonlocal buffer
            chunk = buffer.strip()
            buffer = ""
            if chunk and (force or len(chunk) >= min_chunk):
                speak_chunk(chunk)

        for token in self.ollama.generate_stream(prompt):
            print(token, end="", flush=True)
            yield token
            if speak:
                buffer += token
                last = buffer[-1] if buffer else ""
                if last in hard_ends:
                    flush(force=True)          # complete sentence — always speak
                elif last in soft_ends and len(buffer) >= min_chunk:
                    flush()                    # natural pause, long enough
                elif len(buffer) >= max_chunk:
                    flush(force=True)          # long run — don't stall audio
        if speak and buffer.strip():
            flush(force=True)

    def chat(self, question):
        """Stream reply and speak by sentence or chunk.

        A question prefixed with ULTRATHINK (e.g. "ULTRATHINK: explain X")
        is answered by the bigger model and switched back afterwards.
        """
        self.is_processing = True
        old_model = self.ollama.model
        question, deep = split_deep_marker(question)
        if deep and old_model != BIG_MODEL:
            self.ollama.model = BIG_MODEL
            self.speak("Ultra Think mode on — big brain engaged!")
        print(f"\n{self.botname}: ", end="", flush=True)
        try:
            reply = "".join(self.generate_reply(question, speak=True))
        finally:
            self.ollama.model = old_model
        self.history.append(f"User: {question}")
        self.history.append(f"AI: {reply.strip()}")
        self.is_processing = False

    def speak(self, text):
        print(f"{self.botname}: {text}")
        self.tts.speak(text)

    def wait_for_speech_completion(self):
        while self.tts.is_busy():
            time.sleep(0.1)

    def weather_report(self, query=None):
        """Report the weather for a city mentioned in the query, or the
        location detected from the public IP. Never fails hard: a key-free
        wttr.in fallback answers even with no API keys configured."""
        try:
            self.is_processing = True
            city = parse_city_from_query(query) if query else None
            if not city:
                city = get_city_from_ip()
            weather, temperature, feels_like = get_weather_report(city)
            place = city or "your area"
            # get_weather_report already includes the ℃ symbol
            report = (f"It's {temperature} in {place} and feels like "
                      f"{feels_like}. {weather.capitalize()} vibes today!")
            self.speak(report)
        except Exception as e:
            self.speak("Oops, couldn't get the weather right now. Blame the clouds!")
            print(f"Weather error: {e}")
        finally:
            self.is_processing = False

    def _handle_open_command(self, kind, target, browser):
        """Execute a parsed open/search command with spoken feedback."""
        where = f" in {browser}" if browser else ""
        if kind == "search":
            target = (target or "").strip()
            if not target:
                return
            self.speak(f"Searching for {target}{where} — hold on!")
            ok = open_in_browser(search_url(target), browser)
            if not ok:
                self.speak(
                    f"Couldn't find {browser} on this machine. Check your install?")
            return
        # kind == "app": an application or a website
        self.speak(f"Opening {target}{where} — on it!")
        ok = open_application(target, browser)
        if not ok:
            self.speak(f"Hmm, I couldn't find {target} on this machine.")

    def summarize_and_save_history(self):
        """Summarize conversation and save to file."""
        if not self.history:
            return
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        summary_prompt = (
            "Summarize the following chat in a chill, friendly way (3-5 lines), and start with the date/time (YYYY-MM-DD HH:MM):\n"
            f"Date: {date_str}\n"
            + "\n".join(self.history[-12:])
        )
        summary = ""
        for token in self.ollama.generate_stream(summary_prompt):
            summary += token
        summary_with_date = f"{date_str} - {summary.strip()}"
        append_history(summary_with_date)
        print(f"\n[History saved]\n{summary_with_date}\n")

    def handle_command(self, query):
        """Handle non-chat commands. Return True if handled, else False."""
        lowered = (query or "").lower()

        # 0. identity questions — the small local model often describes ITSELF
        # when asked "who am I", so answer these directly from the user's name.
        idq = strip_politeness(lowered)
        if re.search(
            r"\bwho (am|i am)\b|\bwhat('s| is) my name\b|"
            r"do you know (who i am|my name)|tell me my name",
            idq,
            flags=re.IGNORECASE,
        ):
            self.speak(
                f"You're {self.username}, of course! My favourite human. "
                f"Anything for you, {self.username}?"
            )
            return True

        # 0b. personal memory — recall or wipe the facts JARVIS knows
        if re.search(
            r"what do you know about me|what do you remember about me|"
            r"do you remember (me|my name)",
            idq,
        ):
            self.speak(memory_summary(self.memory))
            return True

        # forget command — but never fire on negated phrasings like
        # "don't forget about me" (that's an ordinary chat message)
        if not re.search(
            r"\b(don't|dont|do not|never)\s+forget\b", idq
        ):
            if re.search(
                r"\bforget everything\b|\bclear (your|the) memory\b|"
                r"\berase (your|the) memory\b|\bforget about me\b",
                idq,
            ):
                if clear_memory():
                    self.memory = {}
                    self.speak("Memory wiped! I know nothing about you again. "
                               "Refreshing!")
                else:
                    self.speak("Couldn't clear my memory. Try again?")
                return True

        # 1. natural-language launcher: "open github in brave",
        #    "search for best laptops in chrome", "can you open notepad"...
        parsed = parse_open_command(lowered)
        if parsed:
            try:
                self._handle_open_command(*parsed)
            except Exception as e:
                print(f"Open command error: {e}")
                self.speak("Couldn't open that. My bad!")
            return True

        # 2. fixed quick commands
        commands = {
            'ip address': (lambda: self.speak(
                f'Your IP Address is {find_my_ip()} (don\'t worry, I won\'t leak it!)'), None),
            'my ip': (lambda: self.speak(
                f'Your IP Address is {find_my_ip()} (don\'t worry, I won\'t leak it!)'), None),
            'weather': (lambda: self.weather_report(query), None),
            'joke': (lambda: self.speak(get_random_joke()), None),
            'news': (self.report_news, None),
            'screenshot': (take_screenshot, "Screenshot time! Hold still..."),
        }
        for key, (func, announce) in commands.items():
            if key in lowered:
                if announce:
                    self.speak(announce)
                try:
                    func()
                except Exception as e:
                    self.speak(f"Couldn't run that command: {key}. My bad!")
                    print(f"Command error ({key}): {e}")
                return True

        # 3. "play <song> on youtube" -> play it right away (no follow-up Q)
        clean = strip_politeness(query)
        if re.match(r"^(please\s+)?play\s+", clean, flags=re.IGNORECASE):
            video = re.sub(r"^(please\s+)?play\s+", "", clean,
                           flags=re.IGNORECASE)
            video = re.sub(r"\s+(on\s+)?youtube\s*$", "", video).strip()
            if video and video.lower() != clean.lower():
                self.speak(f"Playing {video} on YouTube—enjoy!")
                play_on_youtube(video)
                return True

        if 'wikipedia' in lowered:
            self.speak('What should I look up on Wikipedia, friend?')
            self.wait_for_speech_completion()
            search_query = self.listen()
            if search_query:
                try:
                    results = search_on_wikipedia(search_query)
                    short_result = results[:200] + "..." if len(results) > 200 else results
                    self.speak(f"Wikipedia says: {short_result}")
                except Exception as e:
                    self.speak("Wikipedia's not playing nice right now.")
            return True

        if 'youtube' in lowered:
            self.speak('What do you want to jam to on YouTube?')
            self.wait_for_speech_completion()
            video = self.listen()
            if video:
                self.speak(f"Playing {video} on YouTube—enjoy!")
                play_on_youtube(video)
            return True

        if 'bye' in lowered or 'goodbye' in lowered:
            self.speak(f'See ya, {self.username}! Ping me anytime!')
            self.summarize_and_save_history()
            time.sleep(2)
            exit(0)

        # 6. personal memory — learn facts the user shares ("my name is X",
        #    "i like football") and save them for future sessions. Runs last
        #    so every real command above takes precedence.
        learned = extract_facts(idq)
        if learned:
            applied = apply_facts(self.memory, learned)
            if applied:
                save_memory(self.memory)
                if self.memory.get("name"):
                    self.username = self.memory["name"]
                self.speak(confirmation_text(applied))
            else:
                # nothing new (already known, or at the interest cap) —
                # acknowledge instead of silence
                self.speak("Got it!")
            return True

        return False

    def report_news(self):
        try:
            self.speak("Let me grab some news headlines for you...")
            news = get_latest_news()
            if news:
                self.speak(f"Here's one: {news[0]}")
        except Exception as e:
            self.speak("Couldn't fetch news. I blame the internet goblins!")

if __name__ == '__main__':
    # The Desktop HUD is the only interface now — running `python main.py`
    # pops up the HUD (gui.py) instead of the old terminal voice loop.
    from gui import main as gui_main
    gui_main()