"""Practice 224: HB assigns open plan steps instead of skipping them as 'not APEX work'."""
import sqlite3

from core import hb_plan_workflow as wf, hb_tasks


def _conn(owners):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, "
              "order_idx INT, created_at REAL, residual_risk TEXT, acceptance_state TEXT)")
    c.execute('CREATE TABLE projects(project_id TEXT PRIMARY KEY)')
    c.execute('INSERT INTO projects VALUES (?)', (wf.DEFAULT_PROJECT,))
    hb_tasks.ensure_schema(c)
    for n, (sid, owner) in enumerate(owners):
        c.execute("INSERT INTO project_steps VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
                  (sid, wf.DEFAULT_PROJECT, f'Step {sid}', 'Done when: python -m pytest tests/x.py passes', 'todo', owner, n, n))
    return c


def test_steps_owned_by_someone_not_working_on_them_are_hbs_to_assign():
    c = _conn([('S-CC', 'claude-code'), ('S-CX', 'codex'), ('S-UN', ''), ('S-AP', 'apex'), ('S-JD', 'jd'), ('S-HB', 'hummingbird')])
    why = {s['step_id']: s['skip'] for s in wf.steps(c, wf.DEFAULT_PROJECT)}
    for sid in ('S-CC', 'S-CX', 'S-UN', 'S-AP'):
        assert not str(why[sid] or '').startswith('not APEX work'), (sid, why[sid])
    assert why['S-JD'] == 'not APEX work (owner jd)' and why['S-HB'] == 'not APEX work (owner hummingbird)'


def test_the_workflow_gives_a_claude_code_step_to_apex():
    c = _conn([('S-CC', 'claude-code')])
    task = wf._give_next_task(c, {'project_id': wf.DEFAULT_PROJECT, 'conversation_id': 7, 'preferred_step': None})
    assert task and task['step_id'] == 'S-CC'
