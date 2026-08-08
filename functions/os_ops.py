"""Local OS operations for J.A.R.V.I.S.

Launches apps, browsers and websites from natural-language commands like
"open github in brave" or "open discord".
"""

import glob
import os
import re
import subprocess as sp
import urllib.parse
from functools import lru_cache

# ---------------------------------------------------------------------------
# Browsers
# ---------------------------------------------------------------------------
BROWSER_CANDIDATES = {
    "brave": [
        r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "opera": [
        r"C:\Program Files\Opera\opera.exe",
        r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
    ],
}

# Common one-word websites so "open github" / "open youtube" resolve to the
# site even when no app with that name is installed.
KNOWN_SITES = {
    "github", "youtube", "google", "gmail", "facebook", "twitter", "x",
    "instagram", "linkedin", "reddit", "stackoverflow", "stackexchange",
    "whatsapp", "telegram", "netflix", "primevideo", "spotify", "amazon",
    "flipkart", "wikipedia", "yahoo", "bing", "twitch", "medium", "quora",
    "pinterest", "snapchat", "tiktok", "ebay", "paypal", "dropbox", "zoom",
    "slack", "notion", "figma", "canva", "codeforces", "leetcode", "hackerrank",
    "geeksforgeeks", "udemy", "coursera", "w3schools", "mdn", "stackoverflow",
    "chrome", "brave", "edge", "firefox", "opera",
}


def find_browser(browser):
    """Return the full path to an installed browser, or None."""
    name = (browser or "").strip().lower()
    if not name:
        return None
    for cand in BROWSER_CANDIDATES.get(name, []):
        cand = os.path.expandvars(cand)
        if os.path.exists(cand):
            return cand
    return None


def normalize_url(name):
    """Turn 'github', 'github.com', 'www.x.io' into a full https:// URL."""
    n = (name or "").strip().strip('"').strip("'")
    if n.startswith(("http://", "https://")):
        return n
    if n.startswith("www."):
        return "https://" + n
    if "." in n:
        return "https://" + n
    return "https://" + n + ".com"


def looks_like_url(name):
    n = (name or "").strip().lower()
    return (
        n.startswith(("http://", "https://", "www."))
        or "." in n
        or n in KNOWN_SITES
    )


def open_in_browser(url, browser=None):
    """Open a URL in the requested browser, or the system default.

    Returns True if a browser was launched, False if a specific browser was
    requested but not found.
    """
    url = normalize_url(url)
    exe = find_browser(browser)
    if exe:
        try:
            sp.Popen([exe, url])
            return True
        except Exception as e:
            print(f"[os_ops] could not launch {browser}: {e}")
    if browser:
        # A specific browser was asked for but isn't installed.
        return False
    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        print(f"[os_ops] could not open browser: {e}")
        return False


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
# name -> executable/base-name used when searching PATH / registry / Start Menu
NAME_ALIASES = {
    "visual studio code": "code",
    "vs code": "code",
    "vscode": "code",
    "command prompt": "cmd",
    "cmd": "cmd",
    "terminal": "wt",
    "windows terminal": "wt",
    "file explorer": "explorer",
    "explorer": "explorer",
    "calculator": "calc",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "control panel": "control",
    "task manager": "taskmgr",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "powershell": "powershell",
    "paint 3d": "paint3d",
    "snipping tool": "snippingtool",
}

# name -> Windows URI / special launch target (handled by os.startfile)
URI_TARGETS = {
    "camera": "microsoft.windows.camera:",
    "settings": "ms-settings:",
}


def open_camera():
    sp.run('start microsoft.windows.camera:', shell=True)


def open_notepad():
    sp.run('notepad.exe', shell=True)


def open_discord():
    """Launch Discord — via App Paths lookup, or the web app as fallback."""
    target = find_app("discord")
    if target:
        os.startfile(target)
        return True
    return open_in_browser("https://discord.com/app")


def open_cmd():
    os.system('start cmd')


def open_calculator():
    sp.Popen("calc.exe")


def take_screenshot():
    print("screenshot functionality is not implemented yet.")


@lru_cache(maxsize=1)
def _app_paths_registry():
    """{exe_name_lower: full_path} from the Windows 'App Paths' registry key."""
    out = {}
    try:
        import winreg
    except ImportError:
        return out

    def _scan(root):
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        try:
            with winreg.OpenKey(root, key) as k:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, sub) as sk:
                            val, _ = winreg.QueryValueEx(sk, None)
                            if val:
                                out[sub.lower()] = val
                    except OSError:
                        continue
        except OSError:
            pass

    try:
        _scan(winreg.HKEY_LOCAL_MACHINE)
        _scan(winreg.HKEY_CURRENT_USER)
    except Exception as e:
        print(f"[os_ops] registry scan failed: {e}")
    return out


def _where(exe_name):
    """Use Windows 'where' to find an executable on PATH."""
    try:
        r = sp.run(["where", exe_name], capture_output=True, text=True, timeout=6)
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.lower().endswith(".exe") and os.path.exists(line):
                return line
    except Exception:
        pass
    return None


def find_app(name):
    """Locate an installed app; returns a launch target (exe, .lnk, or URI).

    Search order: Windows URI targets -> PATH ('where') -> registry App Paths
    -> Start Menu shortcuts. Returns None when nothing is found.
    """
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in URI_TARGETS:
        return URI_TARGETS[key]
    key = NAME_ALIASES.get(key, key)
    if key.endswith(".exe"):
        key = key[:-4]

    # 1. exe on PATH
    exe = _where(key) or _where(key + ".exe")
    if exe:
        return exe

    # 2. registry App Paths
    reg = _app_paths_registry()
    for cand in (key + ".exe", key):
        hit = reg.get(cand.lower())
        if hit and os.path.exists(hit):
            return hit

    # 3. Start Menu shortcuts (*.lnk)
    bases = (
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    )
    for base in bases:
        if not os.path.isdir(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", f"*{key}*.lnk"),
                             recursive=True):
            return lnk
    return None


def open_application(name, browser=None):
    """Open an app or website from a natural-language name.

    Priority: built-in quick actions -> explicit URL -> installed app
    (PATH/registry/Start Menu) -> website fallback. This way "open chrome"
    launches the Chrome app while "open github" opens github.com.
    """
    n = (name or "").strip()
    if not n:
        return False
    low = n.lower()

    # 1. built-in quick actions (camera, cmd, calculator, discord, ...)
    if low in _BUILTIN_APPS:
        _BUILTIN_APPS[low]()
        return True

    # 2. explicit full URL / domain
    if n.startswith(("http://", "https://", "www.")) or "." in n:
        return open_in_browser(normalize_url(n), browser)

    # 3. an installed application with that name
    target = find_app(n)
    if target:
        try:
            os.startfile(target)
            return True
        except Exception as e:
            print(f"[os_ops] could not start {target}: {e}")

    # 4. known or single-word names are almost certainly websites
    if low in KNOWN_SITES or " " not in n:
        return open_in_browser(normalize_url(n), browser)
    return False


def _has_builtin(name):
    return name in _BUILTIN_APPS


_BUILTIN_APPS = {
    "camera": open_camera,
    "cmd": open_cmd,
    "command prompt": open_cmd,
    "calculator": open_calculator,
    "notepad": open_notepad,
    "discord": open_discord,
    "screenshot": take_screenshot,
}


# ---------------------------------------------------------------------------
# Natural-language command parsing ("open github in brave", "search X")
# ---------------------------------------------------------------------------
_BROWSER_WORDS = ("brave", "chrome", "edge", "firefox", "opera")
_COMMAND_PREFIXES = ("open ", "launch ", "start ", "search", "play ", "google ")


def looks_like_command(text):
    """True when the text is an 'open/search/play/...' style command."""
    low = (text or "").strip().lower()
    return low.startswith(_COMMAND_PREFIXES)


def strip_politeness(text):
    """Remove a leading 'can you / could you / please / hey jarvis ...'.

    Turns "can you open github in brave" into "open github in brave" so the
    command parser still catches it.
    """
    return re.sub(
        r"^\s*(?:can\s+you|could\s+you|will\s+you|would\s+you|"
        r"please|hey\s+jarvis|hey)[,\s]+",
        "", text or "", flags=re.I).strip()


def parse_open_command(query):
    """Parse 'open X [in <browser>]' / 'search Y [in <browser>]' commands.

    Returns (kind, target, browser) where kind is 'app' (open an app or
    website) or 'search' (open a web search). Returns None when the query is
    not an open/search command.
    """
    q = (query or "").strip()
    if not q:
        return None
    q = strip_politeness(q)
    low = q.lower()
    browser = None

    # strip a browser mention: "open github in brave", "... in the brave ..."
    for b in _BROWSER_WORDS:
        m = re.search(rf"\bin\s+(?:the\s+)?{b}\b", low)
        if m:
            browser = b
            q = (q[:m.start()] + q[m.end():]).strip()
            break
    # strip a trailing "in (the) browser"
    m = re.search(r"\b(?:in\s+)?(?:the\s+)?browser\s*$", q.lower())
    if m:
        q = q[:m.start()].strip()
    low = q.lower()

    # "google X" / "search on google X" without a browser -> chat flow answers
    # via DuckDuckGo; with a browser -> open the search in that browser.
    m = re.match(
        r"^(?:google\b|search\s+(?:on\s+)?(?:google|the\s+web|web)\b)\s*(.*)$",
        q, flags=re.I)
    if m:
        if not browser:
            return None
        return "search", m.group(1).strip(), browser

    if low.startswith("search"):
        target = re.sub(r"^search\s+(?:for\s+)?", "", q, flags=re.I).strip()
        if target:
            return "search", target, browser
        return None

    if low.startswith(("open", "launch", "start ")):
        target = re.sub(r"^(?:open|launch|start)\s+", "", q, flags=re.I).strip()
        if target:
            # drop trailing pleasantries and a leading "the"
            target = re.sub(r"\b(?:please|now)\s*$", "", target).strip()
            target = re.sub(r"^the\s+", "", target).strip()
            return "app", target, browser
        return None

    return None


def search_url(query):
    """Build a DuckDuckGo search URL (free, no API key)."""
    return "https://duckduckgo.com/?q=" + urllib.parse.quote(query)
