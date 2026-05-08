"""
app_launcher.py — Seven
═══════════════════════════════════════════════════════════════════════════════
Native desktop app for Seven's Swarm (Ten).

Starts the Flask dashboard on port 5051 (separate from the systemd terminal
on 5050) and opens it in a pywebview native window titled "Seven".

Usage:
  python3 /home/seven/swarm/app_launcher.py

The app runs its own Flask instance — does not depend on swarm-terminal.
Both can run simultaneously. This window is the operator surface.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import threading
import time
import logging

# S-7C7ED96F5B — derive SWARM_ROOT from this file's location (utils/ -> parent)
_SWARM_ROOT = os.environ.get(
    'SWARM_ROOT',
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)

# Bug fix 2026-05-03: SwarmAPI methods called undefined `window`, and main()
# called undefined `get_system_clock`. The clock helper lives in
# lib.system.system_clock; the window has to be threaded into SwarmAPI as
# an instance attribute so the API methods can reach it.
from lib.system.system_clock import get_system_clock

# Silence Flask startup noise
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

APP_PORT  = 5051
APP_TITLE = 'Seven'
APP_URL   = f'http://127.0.0.1:{APP_PORT}'

# ── Start Flask in background ──────────────────────────────────────────────────

def _start_flask():
    from terminal import app
    app.run(host='127.0.0.1', port=APP_PORT, debug=False, use_reloader=False)


def _wait_for_flask(timeout=10):
    """Block until Flask is accepting connections."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(('127.0.0.1', APP_PORT), timeout=0.3)
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.15)
    return False


# ── Native API Bridge ──────────────────────────────────────────────────────────

class SwarmAPI:
    """Exposed to the JS frontend as window.pywebview.api

    The pywebview window is set after creation via :meth:`attach_window`.
    Calling toggle_fullscreen / minimize before that is a no-op rather
    than a NameError (previously crashed because `window` was a free
    variable).
    """
    def __init__(self):
        self._window = None

    def attach_window(self, window):
        self._window = window

    def toggle_fullscreen(self):
        if self._window is not None:
            self._window.toggle_fullscreen()

    def minimize(self):
        if self._window is not None:
            self._window.minimize()

    def get_local_path(self):
        return os.getcwd()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'[{get_system_clock().timestamp_compact()}] Seven — starting on port {APP_PORT}...')

    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()

    if not _wait_for_flask():
        print('  ✗  Flask did not start in time. Check for port conflicts.')
        sys.exit(1)

    print(f'[{get_system_clock().timestamp_compact()}] ✓ Flask ready at {APP_URL}')
    print(f'[{get_system_clock().timestamp_compact()}] Opening Seven...')

    import webview
    
    api = SwarmAPI()
    window = webview.create_window(
        title       = APP_TITLE,
        url         = APP_URL + '?app=1',
        js_api      = api,
        width       = 1440,
        height      = 900,
        min_size    = (900, 600),
        resizable   = True,
        text_select = True,
    )
    api.attach_window(window)

    webview.start(debug=False)
    print(f'[{get_system_clock().timestamp_compact()}] Seven closed.')


if __name__ == '__main__':
    main()
