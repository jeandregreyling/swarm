"""Practice 180: tasks HB parked after APEX got stuck are shown as parked, not as held by JD."""
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
