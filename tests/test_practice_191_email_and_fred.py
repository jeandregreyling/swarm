"""Practice 191: HB emails JD when it stops to ask him (once per task per 6 h); Fred's turns are Fred's in HB Live."""
import sqlite3

from core import hb_task_manager as tm
from core import hb_activity_log as live


def _conn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, agent TEXT, kind TEXT, message_id INTEGER, request_id INTEGER, payload TEXT, created_at REAL)')
    return c


def test_stuck_question_is_emailed_once_per_gap(monkeypatch):
    sent = []
    events = []
    monkeypatch.setattr(tm.hb_tasks, 'event', lambda conn, task, agent, kind, payload, **kw: (events.append(kind), conn.execute(
        "INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES (?,?,?,?,?)", (task['task_id'], agent, kind, '{}', payload.get('at', 0)))))
    monkeypatch.setattr('threading.Thread', lambda target, **kw: type('T', (), {'start': lambda self: target()})())
    c, task = _conn(), {'task_id': 'T-1', 'title': 'Bug: seven direct runtime', 'step_id': 'S-1'}
    assert tm.email_owner(c, task, 'APEX is stuck', send=lambda s, b: sent.append((s, b)), now=1000)
    assert not tm.email_owner(c, task, 'again', send=lambda s, b: sent.append((s, b)), now=1000 + 60)
    assert tm.email_owner(c, task, 'still stuck', send=lambda s, b: sent.append((s, b)), now=1000 + tm.EMAIL_GAP_S + 1)
    assert [s for s, _ in sent] == ['HB needs you: Bug: seven direct runtime'] * 2 and 'Needs you' in sent[0][1]


def test_never_emails_from_tests_by_default():
    assert tm.email_owner(_conn(), {'task_id': 'T-2'}, 'x') is False


def test_fred_turn_is_logged_as_fred(monkeypatch, tmp_path):
    import json
    import core.apex_tools as t
    path = tmp_path / 'l.db'
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: sqlite3.connect(path))
    monkeypatch.setattr('core.apex_routing.active_model', lambda: 'fred-cpu:24b')
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns = [json.dumps({'tool_calls': [], 'answer': 'Fred: fixed it.'})] * 3
    t.run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'fix the bug'}], lambda: True, lambda _r: None,
                     t.ReadOnlyRepository(tmp_path))
    row = sqlite3.connect(path).execute("SELECT actor, lane, text FROM hb_activity_log WHERE kind='start' AND parent IS NULL").fetchone()
    assert row == ('fred', 'cpu', 'Fred: fix the bug')
