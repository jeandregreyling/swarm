"""Practice 211: APEX steps without an HB task get one; the workflow no longer stalls on them."""
import sqlite3

import pytest

from core import hb_plan_workflow as wf, hb_tasks


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, "
              "order_idx INT, created_at REAL, residual_risk TEXT, acceptance_state TEXT)")
    c.execute('CREATE TABLE projects(project_id TEXT PRIMARY KEY)')
    c.execute('INSERT INTO projects VALUES (?)', (wf.DEFAULT_PROJECT,))
    hb_tasks.ensure_schema(c)
    for n, (sid, owner) in enumerate([('S-A1', 'claude-code'), ('S-B2', 'apex'), ('S-C3', 'apex')]):
        c.execute("INSERT INTO project_steps VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
                  (sid, wf.DEFAULT_PROJECT, f'Step {sid}', 'Done when: tests pass', 'todo', owner, n, n))
    return c


def test_untasked_apex_step_gets_a_task(conn, monkeypatch):
    monkeypatch.setattr(wf, 'steps', lambda c, p=wf.DEFAULT_PROJECT: [
        {'step_id': s, 'title': s, 'status': 'todo', 'task_id': None, 'skip': why}
        for s, why in [('S-A1', 'not APEX work (owner claude-code)'), ('S-B2', 'no HB task in main chat'), ('S-C3', 'no HB task in main chat')]])
    task = wf._give_next_task(conn, {'project_id': wf.DEFAULT_PROJECT, 'conversation_id': 7, 'preferred_step': None})
    assert task['step_id'] == 'S-B2' and task['title'] == 'Step S-B2'
    assert 'HB gives APEX the next plan step' in conn.execute('SELECT content FROM messages').fetchone()[0]


def test_preferred_step_wins(conn, monkeypatch):
    monkeypatch.setattr(wf, 'steps', lambda c, p=wf.DEFAULT_PROJECT: [
        {'step_id': s, 'title': s, 'status': 'todo', 'task_id': None, 'skip': 'no HB task in main chat'} for s in ('S-B2', 'S-C3')])
    task = wf._give_next_task(conn, {'project_id': wf.DEFAULT_PROJECT, 'conversation_id': 7, 'preferred_step': 'S-C3'})
    assert task['step_id'] == 'S-C3'


def test_nothing_given_while_a_step_is_ready(conn, monkeypatch):
    monkeypatch.setattr(wf, 'steps', lambda c, p=wf.DEFAULT_PROJECT: [
        {'step_id': 'S-B2', 'title': 'x', 'status': 'todo', 'task_id': 'T-1', 'skip': None},
        {'step_id': 'S-C3', 'title': 'y', 'status': 'todo', 'task_id': None, 'skip': 'no HB task in main chat'}])
    assert wf._give_next_task(conn, {'project_id': wf.DEFAULT_PROJECT, 'conversation_id': 7, 'preferred_step': None}) is None
