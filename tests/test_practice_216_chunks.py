"""Practice 216: HB breaks a task into chunks and gives APEX one at a time."""
import sqlite3

from core import hb_chunks as ch

DESC = ('Studio step S-1: fix the meter\nHB extra tools: change_set\n'
        'Do: change_set show (read why), change_set apply, then run_tests with the 4 files, then report in 2-4 lines.\nDone when: tests pass')


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1','Fix the meter',?)", (DESC,))
    return c


def test_plan_splits_the_do_sequence():
    assert ch.plan(DESC) == ['change_set show (read why)', 'change_set apply', 'run_tests with the 4 files', 'report in 2-4 lines']
    assert ch.plan('1. read the file\n2. change the label\n3. run the test') == ['read the file', 'change the label', 'run the test']
    assert ch.plan('one small thing') == []


def test_one_chunk_at_a_time_and_advance_on_progress():
    c = db()
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    line = ch.focus(c, task)
    assert 'chunk 1 of 4: change_set show' in line and 'Next after this: change_set apply' in line
    assert 'chunk 1 of 4' in ch.focus(c, task)                       # no progress yet: same chunk
    c.execute("INSERT INTO hb_task_events(task_id, kind, payload) VALUES ('T-1','mutation','{}')")
    line = ch.focus(c, task)
    assert 'chunk 2 of 4: change_set apply' in line and 'Done so far: 1. change_set show' in line


def test_command_shows_and_steers(monkeypatch):
    c = db()
    monkeypatch.setattr('core.hb_tasks.get', lambda conn, tid: {'task_id': 'T-1', 'step_id': 'S-1', 'objective': '', 'title': 'Fix'})
    out = ch.command(c, ['T-1'], 'JD')
    assert '▶ 1. change_set show' in out and '· 4. report' in out
    assert '✓ 1.' in ch.command(c, ['T-1', 'done'], 'JD')
    assert '5. check the page' in ch.command(c, ['T-1', 'add', 'check', 'the', 'page'], 'JD')
