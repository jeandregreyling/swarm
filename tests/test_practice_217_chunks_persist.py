"""Practice 217: chunks for prepared steps ('Do:' mid-line) and chunks that persist."""
import sqlite3
from core import hb_chunks as ch

PREP = ('Practice 79\nHB extra tools: change_set\nPREPARED (Claude Code, 15 Nov): this step has a tested change set. Do: change_set show (read why), '
        'change_set apply, then run_tests with {"tests": ["tests/x.py"]}, then report in 2-4 lines.\nDone when: tests pass')


def test_prepared_step_gets_chunks():
    assert ch.plan(PREP)[:2] == ['change_set show (read why)', 'change_set apply']


def test_writer_persists_and_advances(tmp_path):
    path = tmp_path / 'h.db'
    def connect():
        return sqlite3.connect(path)
    c = connect()
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1','P79',?)", (PREP,))
    c.commit(); c.close()
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    reader = connect()
    assert 'chunk 1 of' in ch.focus(reader, task, writer=connect)
    reader.rollback()                                                  # the caller's transaction is never committed
    assert connect().execute('SELECT COUNT(*) FROM hb_chunks').fetchone()[0] >= 2
    w = connect(); w.execute("INSERT INTO hb_task_events(task_id,kind,payload) VALUES ('T-1','mutation','{}')"); w.commit()
    assert 'chunk 2 of' in ch.focus(connect(), task, writer=connect)
