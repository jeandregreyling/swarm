"""Practice 56 (owner 15 Nov, "it's stalled again"): the DAW step got a tested change set but HB parked it at once on three read_file
failures from the day before. Failures older than the newest prepared change set do not count; new ones still stop a spinning task."""
import json
import sqlite3
from core import hb_tasks
from core.hb_task_manager import stuck_reason, MAX_REPEATED_FAILURES


def _ev(c, kind, payload=None, agent='hummingbird'):
    c.execute('INSERT INTO hb_task_events(task_id,agent,kind,payload) VALUES(?,?,?,?)', ('T-X', agent, kind, json.dumps(payload or {})))


def test_practice_56_a_new_change_set_gives_a_fresh_try():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    for _ in range(MAX_REPEATED_FAILURES):
        _ev(c, 'tool_failure', {'tool': 'read_file', 'error': 'Protected repository path'}, agent='apex')
    assert 'read_file failed' in stuck_reason(c, 'T-X')
    _ev(c, 'change_set_prepared', {'by': 'claude-code'})
    assert stuck_reason(c, 'T-X') is None
    for _ in range(MAX_REPEATED_FAILURES):
        _ev(c, 'tool_failure', {'tool': 'read_file', 'error': 'Protected repository path'}, agent='apex')
    assert 'read_file failed' in stuck_reason(c, 'T-X')              # spinning after the new change set still stops
