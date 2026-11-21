"""Practice 231: inspection chunks finish on a test run; change chunks need a change; a finished chunk is progress."""
import json
import sqlite3
import time

from core import hb_chunks as ch, hb_tasks

STEP = ('Theme colours\nDo: run python -m pytest tests/test_hb_brand_icons.py and read which file fails, then replace every hard-coded colour '
        'in the five interface files with the theme variable for its job, then run the test after each file.\nDone when: tests pass')


def _db():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    c.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1','Theme colours',?)", (STEP.split('\n', 1)[1],))
    return c


def _event(c, kind, payload):
    c.execute('INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES (?,?,?,?,?)', ('T-1', 'apex', kind, json.dumps(payload), time.time()))


def test_inspection_words():
    assert ch.inspection('run python -m pytest tests/x.py and read which file fails')
    assert not ch.inspection('replace every hard-coded colour in the five files')


def test_a_failing_test_run_finishes_an_inspection_chunk_but_not_a_change_chunk():
    c = _db()
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': ''}
    assert 'chunk 1 of' in ch.focus(c, task)
    _event(c, 'test_result', {'alm_run_status': 'fail'})
    line = ch.focus(c, task)
    assert 'chunk 2 of' in line and 'replace' in line                       # the failing run was chunk 1's answer
    assert c.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='chunk_done'").fetchone()[0] == 1
    _event(c, 'test_result', {'alm_run_status': 'fail'})
    assert 'chunk 2 of' in ch.focus(c, task)                                 # a change chunk is not done by another failing run
    _event(c, 'mutation', {'path': 'frontend/static/js/views/hb-approval-popup.js'})
    assert 'chunk 3 of' in ch.focus(c, task)
