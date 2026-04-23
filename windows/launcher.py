"""
windows/launcher.py — Fridays Standalone Windows Launcher

Handles two modes:
  - PyInstaller frozen .exe: app code in sys._MEIPASS, user data next to the .exe
  - Source (dev): everything under the project root

User data (DB, sandpits, logs) is always written to _DATA_ROOT so it persists
between updates. App code (blueprints, templates, static) comes from _APP_ROOT
which may be a PyInstaller temp dir.
"""

import sys
import os
import threading
import time

# ── Detect frozen vs source ───────────────────────────────────────────────────

if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    _APP_ROOT  = sys._MEIPASS                       # bundled source code (temp)
    _DATA_ROOT = os.path.dirname(sys.executable)    # next to Fridays.exe (persistent)
else:
    # Running from source (dev / testing)
    _APP_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _DATA_ROOT = _APP_ROOT

_FRONT = os.path.join(_APP_ROOT, 'frontend')
_UTILS = os.path.join(_APP_ROOT, 'utils')

# terminal.py imports relative to frontend/
os.chdir(_FRONT)

for _p in (_APP_ROOT, _FRONT, _UTILS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── First-run: create user data directories ───────────────────────────────────

def _bootstrap_data_root(data_root):
    for subdir in ('sandpits/shared', 'sandpits/qwen', 'sandpits/gemma',
                   'sandpits/llama', 'logs'):
        os.makedirs(os.path.join(data_root, subdir), exist_ok=True)

    # Seed CURRENT_FOCUS if missing
    focus = os.path.join(data_root, 'sandpits', 'shared', 'CURRENT_FOCUS.md')
    if not os.path.exists(focus):
        with open(focus, 'w') as f:
            f.write('# SWARM CURRENT FOCUS\nUpdated: first boot\n\n## Status\nFridays is starting up.\n')

_bootstrap_data_root(_DATA_ROOT)

# ── Environment ───────────────────────────────────────────────────────────────

os.environ.setdefault('SWARM_ENV',      'prod')
os.environ['SWARM_PLATFORM'] = 'windows'
os.environ['SWARM_ROOT']     = _DATA_ROOT
os.environ['SWARM_DB_PATH']  = os.path.join(_DATA_ROOT, 'swarm_memory.db')

# Tell agents where sandpits live (they default to SWARM_ROOT/sandpits)
os.environ.setdefault('SANDPITS_ROOT', os.path.join(_DATA_ROOT, 'sandpits'))

_PORT = int(os.environ.get('PORT', 5050))
_HOST = '127.0.0.1'
_URL  = f'http://{_HOST}:{_PORT}'

# ── Splash window ─────────────────────────────────────────────────────────────

def _show_splash():
    """Simple tk splash while the server starts. Silent if tk missing."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title('Fridays')
        root.geometry('340x100')
        root.resizable(False, False)
        root.configure(bg='#0d1117')
        root.overrideredirect(True)
        # Centre on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth()  - 340) // 2
        y = (root.winfo_screenheight() - 100) // 2
        root.geometry(f'340x100+{x}+{y}')
        tk.Label(root, text='Fridays', font=('Segoe UI', 22, 'bold'),
                 fg='#5bc0de', bg='#0d1117').pack(pady=(18, 2))
        tk.Label(root, text='Starting…', font=('Segoe UI', 10),
                 fg='#888', bg='#0d1117').pack()
        root.update()
        return root
    except Exception:
        return None


def _close_splash(splash):
    try:
        if splash:
            splash.destroy()
    except Exception:
        pass

# ── Backend server ────────────────────────────────────────────────────────────

def _run_server():
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server
    from terminal import create_app, time_wizard

    class _Server(ThreadingMixIn, WSGIServer):
        allow_reuse_address = True
        daemon_threads      = True

    try:
        time_wizard.bootstrap_session()
    except Exception:
        pass

    app = create_app()
    with make_server(_HOST, _PORT, app, server_class=_Server) as httpd:
        httpd.serve_forever()


def _wait_ready(timeout=60):
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(_URL + '/_health', timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False

# ── System tray icon ──────────────────────────────────────────────────────────

def _start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw

        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse([4, 4, 60, 60], fill='#5bc0de')
        d.text((20, 18), 'F', fill='white', font=None)

        def _open_browser(_i, _item):
            import webbrowser
            webbrowser.open(_URL + '/ui')

        def _quit(_i, _item):
            _i.stop()
            os._exit(0)

        icon = pystray.Icon(
            'Fridays', img, 'Fridays',
            menu=pystray.Menu(
                pystray.MenuItem('Open Fridays', _open_browser, default=True),
                pystray.MenuItem('Quit',         _quit),
            ),
        )
        icon.run_detached()
    except Exception:
        pass

# ── Main window ───────────────────────────────────────────────────────────────

def _open_window():
    try:
        import webview
        webview.create_window(
            title       = 'Fridays',
            url         = _URL + '/ui',
            width       = 1440,
            height      = 900,
            min_size    = (900, 600),
            text_select = True,
        )
        webview.start(debug=False)
    except ImportError:
        import webbrowser
        webbrowser.open(_URL + '/ui')
        print('[Fridays] Running in browser mode. Close this window to quit.')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    splash = _show_splash()

    server_thread = threading.Thread(target=_run_server, daemon=True, name='fridays-server')
    server_thread.start()

    _wait_ready(timeout=60)
    _close_splash(splash)
    _start_tray()
    _open_window()

    os._exit(0)


if __name__ == '__main__':
    main()
