"""Enable / disable J.A.R.V.I.S. at Windows startup.

The HUD's STARTUP toggle is the only interface. Two methods exist:

1. A Task Scheduler task ("JARVIS Assistant") firing at boot - preferred,
   but creating it needs administrator rights.
2. A Startup-folder shortcut that launches autostart.vbs at logon - no admin
   needed, so it always works as a fallback.

Everything runs silently (no console flashes) and is idempotent: enabling
first clears any old entries so J.A.R.V.I.S. never launches twice.
"""

import os
import subprocess

TASK_NAME = "JARVIS Assistant"
# The launcher scripts (autostart.vbs, enable_startup_task.ps1) live at the
# project root — this module sits one level down in utils/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VBS = os.path.join(BASE_DIR, "autostart.vbs")

_STARTUP_FOLDER = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
)
_SHORTCUT_NAME = "JARVIS Assistant.lnk"
_SHORTCUT = os.path.join(_STARTUP_FOLDER, _SHORTCUT_NAME)

# Windows: never show a console window for helper commands.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(args, timeout=30):
    """Run a command silently; return (returncode, combined_output)."""
    try:
        p = subprocess.run(
            args, capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


def task_exists():
    rc, _ = _run(["schtasks", "/Query", "/TN", TASK_NAME])
    return rc == 0


def shortcut_exists():
    try:
        return os.path.exists(_SHORTCUT)
    except Exception:
        return False


def autostart_enabled():
    """True when either autostart method is currently active."""
    return task_exists() or shortcut_exists()


def _create_shortcut():
    """Create the Startup-folder shortcut (no admin needed)."""
    try:
        os.makedirs(_STARTUP_FOLDER, exist_ok=True)
    except Exception:
        pass
    if not os.path.isdir(_STARTUP_FOLDER):
        return False
    ps = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{_SHORTCUT}');"
        "$s.TargetPath = \"$env:windir\\System32\\wscript.exe\";"
        f"$s.Arguments = '\"{VBS}\"';"
        f"$s.WorkingDirectory = '{BASE_DIR}';"
        "$s.Description = 'J.A.R.V.I.S. AI Assistant - silent autostart';"
        "$s.Save()"
    )
    _run([
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-Command", ps,
    ])
    return shortcut_exists()


def enable_autostart():
    """Turn on start-at-boot. Returns (ok, message)."""
    # Clear old entries first so J.A.R.V.I.S. never launches twice.
    disable_autostart()

    # Method 1 (preferred): scheduled task at boot - needs admin.
    # Reuse the battle-tested PowerShell helper (crash-restart, 20s delay).
    ps1 = os.path.join(BASE_DIR, "enable_startup_task.ps1")
    if os.path.exists(ps1):
        rc, _ = _run([
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", ps1,
        ])
        if rc == 0:
            return True, ("Startup ON - scheduled task created. "
                          "J.A.R.V.I.S. launches at boot (about 20s in).")

    # Method 2 (fallback): Startup-folder shortcut - no admin needed.
    if _create_shortcut():
        return True, ("Startup ON - J.A.R.V.I.S. launches silently "
                      "when you log in.")

    return False, ("Couldn't enable startup - neither method worked. "
                   "Try running as administrator.")


def disable_autostart():
    """Turn off start-at-boot. Returns (ok, message)."""
    removed = False
    rc, _ = _run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME])
    if rc == 0:
        removed = True
    try:
        if os.path.exists(_SHORTCUT):
            os.remove(_SHORTCUT)
            removed = True
    except Exception:
        pass

    if removed:
        return True, ("Startup OFF - J.A.R.V.I.S. won't start "
                      "at Windows startup anymore.")
    if not autostart_enabled():
        return True, "Startup was already OFF - nothing to remove."
    return False, ("Couldn't fully remove the startup entry - it was "
                   "created with admin rights. Try running as administrator.")
