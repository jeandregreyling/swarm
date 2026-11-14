#!/usr/bin/env python3
"""Owner 13 Nov: every HB restart is announced so the owner sees "Maintenance in progress", never a sign-in screen.

  hb_restart.py ui  "reason"     restart the UI service (swarm-terminal)
  hb_restart.py all "reason"     restart the UI and the APEX worker

Steps: announce the reason -> wait for a gap between APEX turns -> give open pages 8 s to show the notice -> restart ->
wait until HB answers again -> clear the notice. The notice clears itself after 30 minutes if a restart ever crashes.
"""
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from core.hb_maintenance import announce, clear  # noqa: E402

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
        out = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'localhost:5050/api/hb/maintenance'],
                             capture_output=True, text=True).stdout.strip()
        if out == '200':
            return True
        time.sleep(2)
    return False


def restart(scope, reason):
    announce(reason or 'HB is restarting to load a change.', by='hb_restart')
    gap()
    time.sleep(8)                                       # open pages poll every 5 s: they show the notice before HB goes down
    if scope == 'all':
        subprocess.run('sudo -n systemctl stop swarm-terminal.service; systemctl --user restart hummingbird-apex-peer; '
                       'sudo -n systemctl start swarm-terminal.service', shell=True)
    else:
        subprocess.run('sudo -n systemctl stop swarm-terminal.service && sudo -n systemctl start swarm-terminal.service', shell=True)
    ok = answering()
    time.sleep(3)
    clear()
    return ok


if __name__ == '__main__':
    scope = sys.argv[1] if len(sys.argv) > 1 else 'ui'
    if scope not in ('ui', 'all'):
        sys.exit('usage: hb_restart.py ui|all "reason"')
    ok = restart(scope, ' '.join(sys.argv[2:]))
    print('HB back' if ok else 'HB DID NOT ANSWER after the restart')
    sys.exit(0 if ok else 1)
