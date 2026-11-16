"""Practice 122 (monitoring 17 Nov 2026, 03:35): an audit-fix card for aig_focus.js carried the check "npm run lint ..." (no package.json
exists); APEX applied the spec and broke _surfaceFromNode, and a syntax check would not have caught it. APEX now only gets a step whose check
names an existing test file."""
import sqlite3

from core import hb_homework as h, hb_plan_workflow as wf


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, updated_at REAL)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'keep an eye on it')")
    c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', ('S-J', wf.DEFAULT_PROJECT, 'Audit fix: x.js', 'Fix it.', 'todo', 'claude-code'))
    return c


def test_practice_122_only_an_existing_test_file_hands_over():
    c = _db()
    card = {'ready': True, 'model': 'homework-cpu:7b', 'goal': 'Fix x.js'}
    for check in ('npm run lint frontend/static/js/core/aig_focus.js', 'node --check frontend/static/js/core/aig_focus.js',
                  'python -m pytest tests/test_does_not_exist_xyz.py passes'):
        assert h.handoff(c, {'step_id': 'S-J'}, dict(card, check=check)) is False, check
    assert c.execute("SELECT owner FROM project_steps WHERE step_id='S-J'").fetchone()[0] == 'claude-code'
    assert h.handoff(c, {'step_id': 'S-J'}, dict(card, check='python -m pytest tests/test_hb_grounding.py passes')) is True
