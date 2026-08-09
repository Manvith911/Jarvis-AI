"""J.A.R.V.I.S. — entry point.

Running `python main.py` (or double-clicking run.bat) starts the Desktop HUD —
the only interface now. All the assistant logic lives in ``core/assistant.py``;
this file just handles the console/stdout setup for silent autostart and then
launches the GUI.
"""

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


if __name__ == '__main__':
    # The Desktop HUD is the only interface now — running `python main.py`
    # pops up the HUD (ui/gui.py) instead of the old terminal voice loop.
    from ui.gui import main as gui_main
    gui_main()
