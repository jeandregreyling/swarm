#!/usr/bin/env python3
"""Owner 13 Nov: every HB restart is announced so the owner sees "Maintenance in progress", never a sign-in screen.

  hb_restart.py ui  "reason"     restart the UI service (swarm-terminal)
  hb_restart.py all "reason"     restart the UI and the APEX worker

Steps: announce -> hold the actual APEX turn gate -> restart -> verify readiness -> clear.
An all-scope restart reloads the HB-supervised worker too, even when the legacy user unit is inactive.
"""
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from core.hb_maintenance import announce, clear  # noqa: E402
from core.hb_process_lock import ProcessLock  # noqa: E402

DB = ROOT / 'swarm_memory.db'


def gap(limit=900):
    end = time.time() + limit
    while time.time() < end:
        try:
            busy = sqlite3.connect(f'file:{DB}?mode=ro', uri=True).execute("SELECT 1 FROM hb_task_manager WHERE state='running'").fetchone()
        except sqlite3.Error:
            busy = None
        if not busy:
            return True
        time.sleep(5)
    return False


def answering(tries=60):
    for _ in range(tries):
        out = subprocess.run(['curl', '--max-time', '3', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'localhost:5050/api/hb/maintenance'],
                             capture_output=True, text=True).stdout.strip()
        if out == '200':
            return True
        time.sleep(2)
    return False


def stop_supervised_apex():
    from core.hb_executions import alive, process_identity
    expected = (ROOT / 'scripts/hummingbird_peer_worker.py').resolve()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry / 'cmdline').read_bytes().decode().split('\0')
            if len(args) < 4 or Path(args[1]).resolve() != expected or args[2:4] != ['--agent', 'apex']:
                continue
            identity = process_identity(int(entry.name))
            if alive(identity) is not True:
                raise RuntimeError('Cannot verify the supervised APEX worker identity')
            os.kill(identity['pid'], signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            continue
        end = time.monotonic() + 10
        while alive(identity) is not False:
            if time.monotonic() >= end:
                raise RuntimeError('Supervised APEX worker did not stop; activation aborted')
            time.sleep(.1)


def restart(scope, reason):
    announced = False
    try:
        with ProcessLock('apex-turn', ROOT, timeout=900), ProcessLock('source-write', ROOT):
            # Do not cover a working UI while waiting for another turn to finish.
            announce(reason or 'HB is restarting to load a change.', by='hb_restart')
            announced = True
            time.sleep(8)
            if scope == 'all':
                subprocess.run(['sudo', '-A', 'systemctl', 'stop', 'swarm-terminal.service'], check=True)
                try:
                    stop_supervised_apex()
                    subprocess.run(['systemctl', '--user', 'try-restart', 'hummingbird-apex-peer'], check=True)
                finally:
                    subprocess.run(['sudo', '-A', 'systemctl', 'start', 'swarm-terminal.service'], check=True)
            else:
                subprocess.run(['sudo', '-A', 'systemctl', 'restart', 'swarm-terminal.service'], check=True)
            if not answering():
                raise RuntimeError('HB did not answer after the restart')
            time.sleep(3)
            clear()
            return True
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        if announced:
            announce('HB restart failed: ' + str(exc), by='hb_restart')
        raise


if __name__ == '__main__':
    scope = sys.argv[1] if len(sys.argv) > 1 else 'ui'
    if scope not in ('ui', 'all'):
        sys.exit('usage: hb_restart.py ui|all "reason"')
    ok = restart(scope, ' '.join(sys.argv[2:]))
    print('HB back' if ok else 'HB DID NOT ANSWER after the restart')
    sys.exit(0 if ok else 1)
