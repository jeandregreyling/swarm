"""DREAM stop rule: a task that spins without progress stops and asks the owner."""
import json
import sqlite3

from core import hb_tasks
from core.hb_task_manager import stuck_reason, MAX_CHECKPOINTS_WITHOUT_PASS


def _conn():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    return c


def _ev(c, kind, payload=None, agent='hummingbird'):
    c.execute('INSERT INTO hb_task_events(task_id,agent,kind,payload) VALUES(?,?,?,?)',
              ('T-X', agent, kind, json.dumps(payload or {})))


def test_fresh_task_is_not_stuck():
    assert stuck_reason(_conn(), 'T-X') is None


def test_checkpoints_without_a_passing_check_stop():
    c = _conn()
    for _ in range(MAX_CHECKPOINTS_WITHOUT_PASS - 1):
        _ev(c, 'checkpoint')
    assert stuck_reason(c, 'T-X') is None
    _ev(c, 'checkpoint')
    assert 'checkpoints' in stuck_reason(c, 'T-X')


def test_passing_check_or_owner_on_resets_but_owner_off_does_not():
    c = _conn()
    for _ in range(MAX_CHECKPOINTS_WITHOUT_PASS):
        _ev(c, 'checkpoint')
    _ev(c, 'continuation_control', {'mode': 'off'}, agent='user')
    assert stuck_reason(c, 'T-X') is not None
    _ev(c, 'continuation_control', {'mode': 'on'}, agent='user')
    assert stuck_reason(c, 'T-X') is None
    for _ in range(MAX_CHECKPOINTS_WITHOUT_PASS):
        _ev(c, 'checkpoint')
    _ev(c, 'test_result', {'alm_run_status': 'pass'}, agent='apex')
    assert stuck_reason(c, 'T-X') is None


def test_same_tool_error_three_times_stops_and_a_change_breaks_the_run():
    c = _conn()
    bad = {'tool': 'read_file', 'error': 'Invalid line range 1-103'}
    _ev(c, 'tool_failure', bad, agent='apex'); _ev(c, 'tool_failure', bad, agent='apex')
    assert stuck_reason(c, 'T-X') is None
    _ev(c, 'tool_failure', bad, agent='apex')
    assert 'read_file failed 3 times' in stuck_reason(c, 'T-X')
    _ev(c, 'mutation', {}, agent='apex')
    assert stuck_reason(c, 'T-X') is None
    _ev(c, 'tool_failure', bad, agent='apex'); _ev(c, 'tool_failure', {'tool': 'grep_repo', 'error': 'x'}, agent='apex')
    _ev(c, 'tool_failure', bad, agent='apex')
    assert stuck_reason(c, 'T-X') is None
