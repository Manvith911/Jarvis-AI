"""Ensure the local Ollama server is running before J.A.R.V.I.S. needs it.

J.A.R.V.I.S. launches at Windows startup (autostart), but Ollama's tray app
is NOT started by Windows automatically - so the first thing the HUD does is
make sure the server is up, starting it if needed and waiting until it
answers. This module is pure-Python and dependency-light so both the HUD
(gui.py) and the CLI (main.py) can use it.
"""

import os
import subprocess
import time
from shutil import which

import requests

OLLAMA_URL = "http://localhost:11434"
READY_TIMEOUT = 60  # seconds to wait for the server to come up after launch

# Standard install locations for the Ollama app / server on Windows.
OLLAMA_CANDIDATES = [
    r"%LOCALAPPDATA%\Programs\Ollama\ollama app.exe",
    r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
    r"C:\Program Files\Ollama\ollama app.exe",
    r"C:\Program Files\Ollama\ollama.exe",
]

# Windows: don't pop a console window when spawning the server.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def is_online(timeout=1.5):
    """True when the Ollama server responds on the default port."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def find_ollama_exe():
    """Full path to an installed Ollama executable, or None."""
    for cand in OLLAMA_CANDIDATES:
        p = os.path.expandvars(cand)
        if os.path.exists(p):
            return p
    return which("ollama")


def start_ollama():
    """Launch the Ollama server detached. Returns True if a launch was
    attempted, False if no Ollama executable could be found."""
    exe = find_ollama_exe()
    if exe is None:
        print("[ollama] executable not found - install it from ollama.com")
        return False
    try:
        # The tray app starts the server itself; the CLI needs `serve`.
        if os.path.basename(exe).lower() == "ollama app.exe":
            subprocess.Popen([exe], creationflags=CREATE_NO_WINDOW)
        else:
            subprocess.Popen([exe, "serve"], creationflags=CREATE_NO_WINDOW)
        return True
    except Exception as e:
        print(f"[ollama] could not start server: {e}")
        return False


def ensure_ollama(timeout=READY_TIMEOUT, on_status=None):
    """Block until the Ollama server is online, starting it if needed.

    Safe to call repeatedly (no-op when the server is already up), so both
    the HUD startup sequence and the per-message check can share it.

    ``on_status(msg)`` is invoked (from the calling thread) with progress
    messages. Returns True when the server is online, False on failure.
    """
    if is_online():
        if on_status:
            on_status("Ollama is already running.")
        return True
    if on_status:
        on_status("Ollama is offline - starting it...")
    if not start_ollama():
        if on_status:
            on_status("Couldn't find Ollama. Install it from ollama.com and try again.")
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_online():
            if on_status:
                on_status("Ollama is online - all systems go.")
            return True
        time.sleep(1)
    if on_status:
        on_status("Ollama is taking long to start - check the Ollama tray icon.")
    return False
