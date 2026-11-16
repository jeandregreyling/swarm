"""Practice 51 (owner 14 Nov): live activity under the thinking bubble - who runs, the stage, each tool call and result, how long."""
import json
import sqlite3
from pathlib import Path
import core.hb_live_activity as a

ROOT = Path(__file__).resolve().parents[1]


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, title TEXT)')
    c.execute('CREATE TABLE hb_executions(task_id TEXT, request_id INTEGER, agent TEXT, state TEXT, started_at REAL)')
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER, stage TEXT)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, request_id INTEGER, kind TEXT, payload TEXT)')
    c.execute("INSERT INTO hb_tasks VALUES ('T-1','Practice 51: live activity')")
    c.execute("INSERT INTO hb_executions VALUES ('T-1', 7, 'apex', 'running', 1000.0)")
    c.execute("INSERT INTO hb_executions VALUES ('T-1', 6, 'apex', 'completed', 900.0)")
    c.execute("INSERT INTO hb_peer_work VALUES (7, 'run_tests: succeeded')")
    for kind, payload in (('tool_result', {'tool': 'read_file', 'status': 'succeeded', 'arguments': {'path': 'core/x.py'}}),
                          ('tool_failure', {'tool': 'grep_repo', 'error': 'target does not exist', 'arguments': {'query': 'zz'}}),
                          ('mutation', {'tool': 'change_set', 'status': 'succeeded', 'arguments': {'action': 'apply'}}),
                          ('test_result', {'alm_run_status': 'pass'}), ('progress', {'stage': 'x'})):
        c.execute('INSERT INTO hb_task_events(task_id, request_id, kind, payload) VALUES (?,?,?,?)', ('T-1', 7, kind, json.dumps(payload)))
    return c


def test_practice_51_event_lines_are_plain():
    assert a.event_line('tool_result', '{"tool": "read_file", "status": "succeeded", "arguments": {"path": "core/x.py"}}') == 'read_file core/x.py -> succeeded'
    assert a.event_line('test_result', {'alm_run_status': 'pass'}) == 'run_tests -> PASS'
    assert a.event_line('test_result', {'alm_run_status': 'fail'}) == 'run_tests -> FAIL'
    assert a.event_line('tool_failure', {'tool': 'grep_repo', 'error': 'nope'}) == 'grep_repo -> failed: nope'
    assert a.event_line('mutation', 'not json') == 'mutation -> done'


def test_practice_51_snapshot_shows_the_running_turn_and_background_jobs():
    s = a.snapshot(db(), now=1075.0, background=[{'role': 'homework', 'model': 'homework-cpu:7b', 'task': 'spec card', 'steps': [{'what': 'reading files'}]}])
    assert s['running'] is True
    assert s['lines'][0] == 'APEX (GPU) - Practice 51: live activity - running 1 min 15 s'
    assert s['lines'][1] == '  stage: run_tests: succeeded'
    assert s['lines'][2:6] == ['  read_file core/x.py -> succeeded', '  grep_repo zz -> failed: target does not exist',
                               '  change_set apply -> succeeded', '  run_tests -> PASS']
    assert s['lines'][6] == 'HOMEWORK (homework-cpu:7b, CPU / RAM) - spec card - reading files'


def test_practice_51_nothing_running_is_quiet():
    c = db()
    c.execute("UPDATE hb_executions SET state='completed'")
    assert a.snapshot(c, now=1075.0, background=[]) == {'running': False, 'lines': []}


def test_practice_51_route_and_script_are_wired():
    assert "/api/peer/v1/hb/activity" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    assert '/static/js/hb-live-activity.js' in (ROOT / 'frontend/templates/terminal_base.html').read_text()
    js = (ROOT / 'frontend/static/js/hb-live-activity.js').read_text()
    assert "data-pending-job-id" in js and "/api/peer/v1/hb/activity" in js
