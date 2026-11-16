"""Practice 109 (owner 16 Nov 2026): "are all these git changes also shown in main chat and its studio sections?" - commits made by hand
(work that was running but never committed, or what APEX wrote itself) appeared nowhere in HB. Now each one gets a line in JD's chat and,
when it names a Studio step, a record on that step's task. HB's own change-set commits are not repeated."""
import sqlite3
import subprocess

from core import hb_git_watch as w, hb_tasks


def _repo(tmp_path):
    g = lambda *a: subprocess.run(['git', '-C', str(tmp_path), *a], capture_output=True, text=True, check=True)
    g('init', '-q')
    g('config', 'user.name', 'The Ghost')
    g('config', 'user.email', 'ghost@example.invalid')
    return g


def _commit(g, tmp_path, name, msg):
    (tmp_path / name).write_text(name)
    g('add', name)
    g('commit', '-qm', msg)


def test_practice_109_hand_commits_are_announced_once(tmp_path, monkeypatch):
    g = _repo(tmp_path)
    _commit(g, tmp_path, 'a.py', 'base')
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, created_at REAL)')
    c.execute("INSERT INTO hb_tasks VALUES ('T-1', 'S-9958B487B3', 1)")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'are these shown?')")
    events = []
    monkeypatch.setattr(hb_tasks, 'get', lambda conn, tid: {'task_id': tid})
    monkeypatch.setattr(hb_tasks, 'event', lambda conn, task, agent, kind, payload, **k: events.append((task['task_id'], kind, payload['short'])))
    assert w.tick(c, root=tmp_path, every=0) == 0                       # first look: remember HEAD, announce nothing old
    _commit(g, tmp_path, 'b.css', 'HB step S-9958B487B3: terminal buttons on brand (written by APEX)')
    _commit(g, tmp_path, 'c.py', 'HB change set S-0000000000: something HB already announced')
    assert w.tick(c, root=tmp_path, every=0) == 1
    said = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert len(said) == 1 and said[0][0] == 2845
    assert said[0][1].startswith("📦 Committed outside HB's change sets: HB step S-9958B487B3") and 'b.css' in said[0][1] and 'The Ghost' in said[0][1]
    assert events and events[0][:2] == ('T-1', 'commit_recorded')
    assert w.tick(c, root=tmp_path, every=0) == 0                       # never twice
