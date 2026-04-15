#!/usr/bin/env python3
"""
scripts/desktop_launcher.py — Launch swarm in desktop or headless mode (D.5.2)
═══════════════════════════════════════════════════════════════════════════════
Starts Flask backend, optionally opens browser or Tauri window.
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger('seven.launcher')


def _start_backend(port=5050):
    """Start the Flask backend."""
    terminal_py = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'terminal.py')
    env = os.environ.copy()
    env['SWARM_ENV'] = env.get('SWARM_ENV', 'prod')
    proc = subprocess.Popen(
        [sys.executable, terminal_py],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


def _wait_for_server(port=5050, timeout=30):
    """Wait for Flask backend to become available."""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f'http://localhost:{port}/_health', timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Seven's Swarm Launcher")
    parser.add_argument('--headless', action='store_true',
                        help='Run in server-only mode (no browser/window)')
    parser.add_argument('--port', type=int, default=5050,
                        help='Port for Flask backend (default: 5050)')
    parser.add_argument('--tauri', action='store_true',
                        help='Launch Tauri desktop window instead of browser')
    args = parser.parse_args()

    print(f"Starting Seven's Swarm on port {args.port}...")
    backend = _start_backend(args.port)

    def _shutdown(sig=None, frame=None):
        print('\nShutting down...')
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if not _wait_for_server(args.port):
        print('ERROR: Backend failed to start within 30 seconds')
        backend.terminate()
        sys.exit(1)

    print(f'Backend running at http://localhost:{args.port}')

    if args.headless:
        print('Headless mode — press Ctrl+C to stop')
        try:
            backend.wait()
        except KeyboardInterrupt:
            _shutdown()
    elif args.tauri:
        # Launch Tauri window
        desktop_dir = os.path.join(os.path.dirname(__file__), '..', 'desktop')
        try:
            tauri_proc = subprocess.Popen(
                ['cargo', 'tauri', 'dev'],
                cwd=desktop_dir,
            )
            tauri_proc.wait()
        except FileNotFoundError:
            print('Tauri CLI not found — falling back to browser')
            webbrowser.open(f'http://localhost:{args.port}')
            backend.wait()
        finally:
            _shutdown()
    else:
        # Open in default browser
        webbrowser.open(f'http://localhost:{args.port}')
        print('Opened in browser — press Ctrl+C to stop')
        try:
            backend.wait()
        except KeyboardInterrupt:
            _shutdown()


if __name__ == '__main__':
    main()
