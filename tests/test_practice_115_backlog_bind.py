"""Practice 115 (owner 16 Nov 2026): Practice 113's backlog homework posted "📐 Homework: HB writes a spec for ..." every 6 seconds: the real
hb_tasks.bind refuses a Studio step that is not APEX's ("Selected Studio step is not assigned to APEX"), after the line was posted. Its test
had replaced bind. This one uses the real bind: one line, one task carrying the step, and a failure never repeats."""
import sqlite3

from core import hb_homework as h, hb_tasks, hb_plan_workflow as wf


def _db():
    c = sqlite3.connect(':memory:')
    c.executescript("""
        CREATE TABLE conversations(id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT,
                              tokens_used INT, created_at TEXT DEFAULT '2026-11-16 08:00:00');
        CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, updated_at REAL);
    """)
    hb_tasks.ensure_schema(c)
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'specs please')")
    c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', ('S-AAAAAAAAAA', wf.DEFAULT_PROJECT, 'Online providers', 'Gemini, Codex.', 'partial', 'claude-code'))
    c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', ('S-BBBBBBBBBB', wf.DEFAULT_PROJECT, 'Rig benchmark', 'JD does it.', 'todo', 'jd'))
    c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?,0)', ('S-CCCCCCCCCC', wf.DEFAULT_PROJECT, 'Old work', 'Done.', 'done', 'claude-code'))
    return c


def test_practice_115_one_line_one_task_with_the_real_bind(monkeypatch):
    c = _db()
    monkeypatch.setattr(h, 'latest', lambda conn, task: None)
    first = h.backlog(c)
    again = h.backlog(c)
    assert [t['step_id'] for t in first] == ['S-AAAAAAAAAA'] and [t['task_id'] for t in again] == [first[0]['task_id']]
    lines = c.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '📐 Homework: HB writes a spec%'").fetchone()[0]
    assert lines == 1


def test_practice_115_a_failure_removes_its_line_and_does_not_repeat(monkeypatch):
    c = _db()
    h._SKIP.clear()
    monkeypatch.setattr(h, 'latest', lambda conn, task: None)
    def broken(*a, **k):
        raise PermissionError('nope')
    monkeypatch.setattr(hb_tasks, 'bind', broken)
    assert h.backlog(c) == [] and h.backlog(c) == []
    assert c.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '📐%'").fetchone()[0] == 0
    assert 'S-AAAAAAAAAA' in h._SKIP
