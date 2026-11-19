"""Practice 168 (owner 19 Nov 2026): 9 bug steps were skipped as 'needs a spec' because run_tests' auto case 'Guarded task regression checks'
became their done criterion."""
import sqlite3

from core import hb_dream_method as dm, hb_plan_workflow as wf


def test_practice_168_placeholder_case_is_not_a_criterion(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE project_test_cases(case_id TEXT, step_id TEXT, title TEXT, created_at REAL)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, agent TEXT, payload TEXT)')
    c.execute("INSERT INTO project_test_cases VALUES ('C-1','S-1','Guarded task regression checks',1)")
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': 'Bug: x\nDone when: python -m pytest tests/test_x.py passes\n'}
    src, crit = dm.done_when(c, task)
    assert src == 'task' and wf.runnable_check(crit[0])


def test_practice_168_auto_case_names_its_command():
    assert "'Guarded task regression checks: python -m pytest '" in open('core/hb_agent_tools.py').read()
