"""Practice 214 (Codex's phone flow 3): HB's start/finish lines tell the truth about how work ended."""
import sqlite3

from core import hb_announce as a


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_activity_log(id INTEGER PRIMARY KEY, run_id TEXT, task_id TEXT, kind TEXT, text TEXT)')
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER PRIMARY KEY, state TEXT, stage TEXT)')
    c.execute('CREATE TABLE hb_task_requests(request_id INTEGER, task_id TEXT, task_version INT)')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT PRIMARY KEY, state TEXT, step_id TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, status TEXT)')
    c.execute('CREATE TABLE hb_task_events(task_id TEXT, kind TEXT)')
    return c


def lines(c, key, title='Repair 10'):
    said = []
    post = lambda conn, t: said.append(t)
    job = {'run_id': key, 'actor': 'apex', 'lane': 'gpu', 'title': title, 'purpose': 'workflow step'}
    a.tick(c, now=0, items=[job], post=post)
    a.tick(c, now=60, items=[], post=post)
    a.tick(c, now=120, items=[], post=post)
    return said[-1]


def test_accepted_work_is_finished_even_when_transport_was_cancelled():
    c = db()
    c.execute("INSERT INTO hb_peer_work VALUES (2727,'cancelled','Owner hold retained')")
    c.execute("INSERT INTO hb_task_requests VALUES (2727,'T-1',1)")
    c.execute("INSERT INTO hb_tasks VALUES ('T-1','active','S-1')")
    c.execute("INSERT INTO project_steps VALUES ('S-1','done')")
    assert lines(c, 'P-2727').startswith('✓ APEX finished: Repair 10')


def test_genuine_failure_of_unfinished_work_stays_a_failure():
    c = db()
    c.execute("INSERT INTO hb_peer_work VALUES (2728,'failed','run_tests timed out')")
    c.execute("INSERT INTO hb_task_requests VALUES (2728,'T-2',1)")
    c.execute("INSERT INTO hb_tasks VALUES ('T-2','active','S-2')")
    c.execute("INSERT INTO project_steps VALUES ('S-2','todo')")
    line = lines(c, 'P-2728')
    assert line.startswith('✗ APEX stopped: Repair 10') and 'failed - run_tests timed out' in line


def test_vanished_run_is_never_called_a_success():
    c = db()
    assert lines(c, 'R-GONE').startswith('■ APEX ended: Repair 10') and 'no result recorded' in lines(c, 'R-GONE')


def test_logged_finish_and_error():
    c = db()
    c.execute("INSERT INTO hb_activity_log(run_id, kind, text) VALUES ('R-OK','finish','done (30 s)')")
    c.execute("INSERT INTO hb_activity_log(run_id, kind, text) VALUES ('R-BAD','error','TimeoutError (30 s)')")
    assert lines(c, 'R-OK').startswith('✓ APEX finished')
    assert lines(c, 'R-BAD').startswith('✗ APEX stopped') and 'TimeoutError' in lines(c, 'R-BAD')


def test_completed_reply_does_not_claim_open_task_is_finished():
    c = db()
    c.execute("INSERT INTO hb_peer_work VALUES (2729,'completed','Reply saved')")
    c.execute("INSERT INTO hb_task_requests VALUES (2729,'T-3',1)")
    c.execute("INSERT INTO hb_tasks VALUES ('T-3','active','S-3')")
    c.execute("INSERT INTO project_steps VALUES ('S-3','todo')")
    line = lines(c, 'P-2729')
    assert line.startswith('■ APEX finished a turn:')
    assert 'task remains open' in line


def test_chat_record_never_announced_as_work_even_in_peer_lane():
    c = db()
    said = []
    job = {'run_id': 'P-2730', 'actor': 'apex', 'lane': 'gpu', 'title': 'Chat with JD', 'purpose': 'workflow step'}
    a.tick(c, now=1, items=[job], post=lambda _c, line: said.append(line))
    a.tick(c, now=62, items=[], post=lambda _c, line: said.append(line))
    a.tick(c, now=122, items=[], post=lambda _c, line: said.append(line))
    assert said == []
