"""Practice 218: the chunk writer must not deadlock against the caller's own open write transaction."""
import sqlite3
import time
from core import hb_chunks as ch

PREP = ('Practice 79\nHB extra tools: change_set\nPREPARED (Claude Code, 15 Nov): this step has a tested change set. Do: change_set show (read why), '
        'change_set apply, then run_tests with {"tests": ["tests/x.py"]}, then report in 2-4 lines.\nDone when: tests pass')


def _db(path):
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute('CREATE TABLE service_tokens(id INTEGER PRIMARY KEY, last_used_at REAL)')
    c.execute("INSERT INTO project_steps VALUES ('S-1','P79',?)", (PREP,))
    c.execute('INSERT INTO service_tokens VALUES (1, 0)')
    c.commit(); c.close()


def test_caller_holding_write_lock_does_not_deadlock(tmp_path):
    path = tmp_path / 'h.db'
    _db(path)
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    outer = sqlite3.connect(path)
    outer.execute('UPDATE service_tokens SET last_used_at=1 WHERE id=1')   # like peers.authenticate in the inbox request
    assert outer.in_transaction
    opened = []
    def writer():
        opened.append(1)
        return sqlite3.connect(path, timeout=0.2)
    t = time.time()
    line = ch.focus(outer, task, writer=writer)
    assert time.time() - t < 2 and 'chunk 1 of' in line and not opened
    outer.commit()                                                     # the inbox request commits its own connection
    assert sqlite3.connect(path).execute('SELECT COUNT(*) FROM hb_chunks').fetchone()[0] >= 2


def test_writer_gives_up_fast_when_another_connection_holds_the_lock(tmp_path):
    path = tmp_path / 'h.db'
    _db(path)
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    other = sqlite3.connect(path)
    other.execute('UPDATE service_tokens SET last_used_at=2 WHERE id=1')   # someone else holds the write lock
    reader = sqlite3.connect(path)
    t = time.time()
    assert ch.focus(reader, task, writer=lambda: sqlite3.connect(path, timeout=30)) == ''
    assert time.time() - t < 6
    other.commit()


def test_idle_caller_still_uses_writer(tmp_path):
    path = tmp_path / 'h.db'
    _db(path)
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    reader = sqlite3.connect(path)
    assert 'chunk 1 of' in ch.focus(reader, task, writer=lambda: sqlite3.connect(path))
    reader.close()                                                     # APEX's chat turn never commits its card connection
    assert sqlite3.connect(path).execute('SELECT COUNT(*) FROM hb_chunks').fetchone()[0] >= 2
