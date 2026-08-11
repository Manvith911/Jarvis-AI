"""Off-screen functional check of the HUD ToastOverlay widget.

Runs headless (QT_QPA_PLATFORM=offscreen) so it works on any machine:
    python tests/toast_check.py

Exercises: show, fade-in animation, message queueing while visible, fade-out,
and the queue draining to empty. Exit code 0 = all checks passed.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ui.gui import ToastOverlay  # noqa: E402


def pump(app, seconds):
    """Run the Qt event loop for a little real time (drives animations)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.resize(1120, 720)
    toast = ToastOverlay(window)
    window.show()

    # sanity: the animated property is registered on the meta-object
    assert toast.metaObject().indexOfProperty("fade") >= 0, \
        "'fade' property must be registered for QPropertyAnimation"

    # 1. a toast appears and fades in
    toast.show_toast("Reminder: call dad", hold_ms=150)
    assert toast.isVisible(), "toast should be visible after show_toast"
    pump(app, 0.25)
    assert toast.get_fade() > 0.0, "fade-in should raise alpha above 0"
    print("PASS: toast shows and fades in")

    # 2. a second notice while visible is queued, not dropped
    toast.show_toast("Timer done", hold_ms=80)
    assert len(toast._queue) == 1, "second notice should be queued"
    print("PASS: notices queue while one is on screen")

    # 3. wait for hold + fade-out; the queued one takes the stage, then all drain
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline and toast.isVisible():
        pump(app, 0.05)
    assert not toast.isVisible(), "toast should hide once the queue drains"
    assert toast._queue == [], "queue should be empty at the end"
    print("PASS: toast fades out and the queue drains to empty")

    # 4. empty/blank messages are ignored
    toast.show_toast("   ")
    assert toast._queue == [], "blank message must not be queued"
    print("PASS: blank messages are ignored")

    print("ALL TOAST CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
