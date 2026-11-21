"""Practice 226: a newly prepared change set gives APEX a fresh start instead of a question to JD."""
import json
import sqlite3
import time

from core import hb_task_manager as tm


def test_change_set_prepared_after_freds_turn_means_apex_first(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, agent TEXT, kind TEXT, payload TEXT, request_id INTEGER, created_at REAL)')
    c.execute('CREATE TABLE hb_task_requests(task_id TEXT, request_id INTEGER)')
    c.execute('CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT, created_at REAL)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, description TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1', 'Do: change_set apply. Done when: python -m pytest tests/x.py passes')")
    now = time.time()
    for rid in (1, 2, 3, 4):                                      # four APEX turns, then Fred's turn, all before the new change set
        c.execute('INSERT INTO hb_task_requests VALUES (?,?)', ('T-1', rid))
        c.execute('INSERT INTO peer_messages VALUES (?,?,?)', (rid, 'apex', now - 600))
    c.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload,request_id,created_at) VALUES ('T-1','hummingbird','fred_turn','{}',5,?)", (now - 300,))
    c.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload,request_id,created_at) VALUES ('T-1','claude-code','change_set_prepared','{}',NULL,?)", (now - 10,))
    monkeypatch.setattr('core.hb_model_switches.modes', lambda conn: {})
    monkeypatch.setattr('core.hb_local_jobs.ensure_schema', lambda conn: None)
    out = tm.local_help(c, {'task_id': 'T-1', 'step_id': 'S-1', 'conversation_id': 1})
    assert str(out).startswith(tm.APEX_FIRST), out
