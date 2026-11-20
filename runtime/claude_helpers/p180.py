"""Prepare Practice 180: the HB Driving board says which tasks HB parked (APEX got stuck), instead of 'held by you'."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
W = 'core/hb_plan_workflow.py'
Q = 'core/hb_queue.py'
J = 'frontend/static/js/views/hb-queue.js'

edits = [
    {'path': W, 'old': "def _owner_mode(conn, task_id):\n", 'new': '''# Practice 180 (owner 20 Nov 2026: "the HB Driving section at the top of the screen isn't showing the task queue as expected"): 11 bug
# tasks showed as "held by you (Continue off)", but JD never held them - HB parked each one after APEX went 9 checkpoints without a
# passing check (continuation_control via 'stalled'). The board now says so.
def _parked_why(conn, task_id):
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='continuation_control' AND agent='user' "
                       "ORDER BY event_id DESC LIMIT 1", (task_id,)).fetchone()
    try:
        saved = json.loads(row[0]) if row else {}
    except (TypeError, ValueError):
        return ''
    if saved.get('mode') == 'off' and saved.get('via') == 'stalled':
        return ('parked by HB: APEX got stuck (' + str(saved.get('why') or 'no passing check')[:80]
                + ') - Continue gives it a fresh try, Cancel drops it')
    return ''


def _owner_mode(conn, task_id):
'''},
    {'path': W, 'old': '''        elif task[1] == 'paused' or _owner_mode(conn, task[0]) == 'off':
            why = 'held by you (Continue off)'
''', 'new': '''        elif task[1] == 'paused' or _owner_mode(conn, task[0]) == 'off':
            why = _parked_why(conn, task[0]) or 'held by you (Continue off)'      # Practice 180
'''},
    {'path': Q, 'old': "                    'why': str(why)[:160]})", 'new': "                    'why': str(why)[:160], 'parked': str(skip).startswith('parked')})   # Practice 180"},
    {'path': J, 'old': "      const line = (now ? 'now: ' + now.title : '') + (next ? (now ? ' · ' : '') + 'next: ' + next.title : '');",
     'new': '''      // Practice 180: with nothing running or next, the header says why - instead of an empty line
      const parked = d.items.filter(i => i.parked).length;
      const line = (now ? 'now: ' + now.title : '') + (next ? (now ? ' · ' : '') + 'next: ' + next.title : '') ||
        (parked ? `nothing running · ${parked} parked by HB (APEX got stuck) - open the list: Continue gives one a fresh try, Cancel drops it`
                : (d.open ? 'nothing ready to start' : 'queue empty'));'''},
    {'path': J, 'old': "      `<span class=\"hb-chip${i.ready ? ' ready' : ''}\">${i.ready ? 'ready' : 'no card'}</span>${check}${editHtml(i)}</li>`;",
     'new': "      (i.parked ? `<span class=\"hb-chip parked\" title=\"${esc(i.why || '')}\">parked by HB</span>`\n"
            "                : `<span class=\"hb-chip${i.ready ? ' ready' : ''}\">${i.ready ? 'ready' : 'no card'}</span>`) + `${check}${editHtml(i)}</li>`;   // Practice 180"},
    {'path': J, 'old': "i.state, i.ready, i.check_result, i.importance, i.doer])]);",
     'new': "i.state, i.ready, i.check_result, i.importance, i.doer, i.parked])]);"},
    {'path': J, 'old': "    '.hb-chip.ready{border-color:var(--accent,#6aa9ff);color:var(--accent,#6aa9ff)}' +",
     'new': "    '.hb-chip.ready{border-color:var(--accent,#6aa9ff);color:var(--accent,#6aa9ff)}' +\n    '.hb-chip.parked{border-color:#ffb300;color:#ffb300}' +   // Practice 180"},
]

test = '''"""Practice 180: tasks HB parked after APEX got stuck are shown as parked, not as held by JD."""
import json
import sqlite3
from pathlib import Path

from core import hb_plan_workflow as wf
from core import hb_queue

ROOT = Path(__file__).resolve().parents[1]


def _conn(payload):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, agent TEXT, kind TEXT, payload TEXT)')
    c.execute("INSERT INTO hb_task_events(task_id, agent, kind, payload) VALUES ('T-1', 'user', 'continuation_control', ?)", (json.dumps(payload),))
    return c


def test_parked_by_hb_is_not_held_by_jd():
    parked = wf._parked_why(_conn({'mode': 'off', 'via': 'stalled', 'why': 'Stopped, not looping: 9 checkpoints'}), 'T-1')
    assert parked.startswith('parked by HB: APEX got stuck (Stopped, not looping: 9 checkpoints)')
    assert wf._parked_why(_conn({'mode': 'off', 'via': 'global'}), 'T-1') == ''


def test_queue_rows_carry_parked(monkeypatch):
    monkeypatch.setattr(wf, 'settings', lambda conn, project_id=None: {})
    monkeypatch.setattr(wf, 'steps', lambda conn, project_id=None: [
        {'step_id': 'S-1', 'task_id': 'T-1', 'title': 'Bug: a', 'skip': 'parked by HB: APEX got stuck (x) - Continue gives it a fresh try'},
        {'step_id': 'S-2', 'task_id': 'T-2', 'title': 'Bug: b', 'skip': 'held by you (Continue off)'}])
    rows = hb_queue.items(sqlite3.connect(':memory:'))
    assert [r['parked'] for r in rows] == [True, False]


def test_board_header_and_chip():
    js = (ROOT / 'frontend/static/js/views/hb-queue.js').read_text()
    assert 'parked by HB (APEX got stuck)' in js and "'nothing ready to start'" in js and 'hb-chip parked' in js
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov: \"the HB Driving section at the top of the screen isn't showing the task queue as expected\". It said "
                            "'driving · 13 open' with an empty line: nothing was now or next, and 11 bug tasks showed 'held by you (Continue "
                            "off)' although HB itself parked them after APEX got stuck (continuation_control via 'stalled'). "
                            "hb_plan_workflow._parked_why names them 'parked by HB: APEX got stuck (...)'; hb_queue rows carry parked; "
                            "hb-queue.js shows a 'parked by HB' chip and a header line that says why nothing runs."),
                 edits=edits, new_files={'tests/test_practice_180_parked_tasks.py': test},
                 test={'tests': ['tests/test_practice_180_parked_tasks.py', 'tests/test_practice_168_placeholder_case.py'], 'keyword': ''}, run=run)
print(out['verified'])
