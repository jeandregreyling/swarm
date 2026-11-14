"""Owner 13 Nov: when HB is taken down (restarts, foundation changes) the owner sees "Maintenance in progress", not a sign-in screen.

announce(reason) writes runtime/maintenance.json before a restart; clear() removes the notice afterwards. The page polls
GET /api/hb/maintenance (no login needed) and shows a calm overlay while the notice is on or while HB cannot be reached.
"""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAG = ROOT / 'runtime' / 'maintenance.json'


def state():
    try:
        data = json.loads(FLAG.read_text())
    except (OSError, ValueError):
        data = {}
    on = bool(data.get('on'))
    if on and time.time() - float(data.get('since') or 0) > float(data.get('max_seconds') or 1800):
        on = False                                  # a notice left behind by a crashed restart never hides HB for long
    return {'on': on, 'reason': str(data.get('reason') or '')[:300], 'since': data.get('since'), 'by': data.get('by', '')}


def announce(reason, by='HB', max_seconds=1800):
    FLAG.parent.mkdir(parents=True, exist_ok=True)
    tmp = FLAG.with_suffix('.tmp')
    tmp.write_text(json.dumps({'on': True, 'reason': str(reason)[:300], 'since': time.time(), 'by': by, 'max_seconds': max_seconds}))
    os.replace(tmp, FLAG)
    return state()


def clear():
    previous = state()
    FLAG.parent.mkdir(parents=True, exist_ok=True)
    tmp = FLAG.with_suffix('.tmp')
    tmp.write_text(json.dumps({'on': False, 'last_reason': previous.get('reason', ''), 'ended': time.time()}))
    os.replace(tmp, FLAG)
    return state()
