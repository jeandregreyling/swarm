"""Practice 116 (monitoring 16 Nov 2026, 21:52): homework handed "Daily grounding" to APEX with the check "HB's self-check passes, the sundial
shows the current day name". APEX could not run it, reported itself blocked, and Fred took over the CPU. A backlog step now goes to APEX only
when its check is a test or a command APEX can run."""
import sqlite3

from core import hb_homework as h, hb_plan_workflow as wf


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, updated_at REAL)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'keep an eye on it')")
    c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', ('S-G', wf.DEFAULT_PROJECT, 'Daily grounding', 'Opens the day.', 'partial', 'claude-code'))
    return c


def test_practice_116_a_check_apex_cannot_run_stays_with_claude_code():
    c = _db()
    card = {'ready': True, 'model': 'homework-cpu:7b', 'goal': 'Open the day',
            'check': "HB's self-check passes, the sundial shows the current day name, and a CBT checkpoint appears"}
    assert h.handoff(c, {'step_id': 'S-G'}, card) is False
    assert c.execute("SELECT owner FROM project_steps WHERE step_id='S-G'").fetchone()[0] == 'claude-code'
    assert h.handoff(c, {'step_id': 'S-G'}, dict(card, check='python -m pytest tests/test_hb_grounding.py passes')) is True
    assert c.execute("SELECT owner FROM project_steps WHERE step_id='S-G'").fetchone()[0] == 'apex'
