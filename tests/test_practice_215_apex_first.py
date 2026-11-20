"""Practice 215: Fred only after APEX's four attempts since the last progress."""
import sqlite3

from core import hb_task_manager as tm


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_requests(request_id INTEGER, task_id TEXT, task_version INT)')
    c.execute('CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT, created_at REAL)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, request_id INT, created_at REAL, payload TEXT)')
    return c


def add(c, rid, at, fred=False):
    c.execute('INSERT INTO peer_messages VALUES (?,?,?)', (rid, 'apex', at))
    c.execute('INSERT INTO hb_task_requests VALUES (?,?,1)', (rid, 'T-1'))
    if fred:
        c.execute("INSERT INTO hb_task_events(task_id,kind,request_id,created_at) VALUES ('T-1','fred_turn',?,?)", (rid, at))


def test_counts_only_apex_turns_since_progress():
    c = db()
    add(c, 1, 10); add(c, 2, 100); add(c, 3, 110, fred=True); add(c, 4, 120)
    assert tm.apex_tries(c, 'T-1', 50) == 2              # request 1 is before progress; 3 was Fred's
    assert tm.apex_tries(c, 'T-1', 0) == 3


def test_fred_waits_for_four_apex_attempts(monkeypatch):
    c = db()
    c.execute("CREATE TABLE project_steps(step_id TEXT, description TEXT)")
    c.execute("INSERT INTO project_steps VALUES ('S-1', 'Done when: python -m pytest tests/x.py passes')")
    monkeypatch.setattr('core.hb_model_switches.modes', lambda conn: {})
    monkeypatch.setattr('core.hb_local_jobs.ensure_schema', lambda conn: None)
    monkeypatch.setattr('core.hb_dream_method.done_when', lambda conn, task: ('x', ['python -m pytest tests/x.py']))
    for rid in (1, 2):
        add(c, rid, 100 + rid)
    said = tm.local_help(c, {'task_id': 'T-1', 'step_id': 'S-1'})
    assert said.startswith(tm.APEX_FIRST) and '2 of 4' in said


def test_review_threshold_and_fallthrough_in_source():
    src = open(tm.__file__).read()
    assert "stagnant>=APEX_TRIES" in src and "phase='execute'   # Practice 215" in src
