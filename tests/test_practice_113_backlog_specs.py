"""Practice 113 (owner 16 Nov 2026): "the little bots should be doing some more specs on them to add to APEX to work on properly". The open
living-plan steps owned by claude-code never got homework spec cards; now they do, and a READY card hands the step to APEX with the spec in it."""
import sqlite3

from core import hb_homework as h, hb_tasks, hb_plan_workflow as wf


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, state TEXT, created_at REAL)')
    c.execute('CREATE TABLE hb_task_events(task_id TEXT, kind TEXT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'specs please')")
    for sid, owner, status in (('S-A', 'claude-code', 'todo'), ('S-B', 'jd', 'todo'), ('S-C', 'claude-code', 'done'),
                               ('S-D', 'claude-code', 'partial'), ('S-E', 'claude-code', 'todo')):
        c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', (sid, wf.DEFAULT_PROJECT, f'Step {sid}', 'Build it.', status, owner))
    c.execute("INSERT INTO hb_tasks VALUES ('T-E', 'S-E', 'completed', 1)")
    c.execute("INSERT INTO hb_task_events VALUES ('T-E', 'spec_card')")          # carded before
    return c


# The backlog-binding test moved to tests/test_practice_115_backlog_bind.py: it now uses the real hb_tasks.bind (Practice 115).


def test_practice_113_a_ready_card_hands_the_step_to_apex():
    c = _db()
    card = {'ready': True, 'model': 'homework-cpu:7b', 'goal': 'Network manager picks a link', 'plan': ['measure links', 'pick'],
            'files': ['core/hb_downloads.py'], 'check': 'python -m pytest tests/test_hb_network.py passes'}
    assert h.handoff(c, {'step_id': 'S-A'}, card) is True
    owner, desc = c.execute("SELECT owner, description FROM project_steps WHERE step_id='S-A'").fetchone()
    assert owner == 'apex' and 'SPEC (homework card by homework-cpu:7b' in desc and 'Done when: python -m pytest tests/test_hb_network.py passes' in desc
    assert 'APEX takes it' in c.execute("SELECT content FROM messages WHERE from_agent='hummingbird'").fetchone()[0]
    assert h.handoff(c, {'step_id': 'S-D'}, dict(card, ready=False)) is False
    assert c.execute("SELECT owner FROM project_steps WHERE step_id='S-D'").fetchone()[0] == 'claude-code'
    assert h.handoff(c, {'step_id': 'S-B'}, card) is None                    # JD's own step is never handed over
