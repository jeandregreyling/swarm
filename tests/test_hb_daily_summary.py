"""Practice 46 (owner 14 Nov): the daily summary - done, stalled and why, best model, needs JD - once a day in main chat."""
import sqlite3
import time
import core.hb_daily_summary as d

NOW = time.mktime((2026, 11, 15, 19, 0, 0, 0, 0, -1))


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, status TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, title TEXT, state TEXT)')
    c.execute('CREATE TABLE hb_task_manager(task_id TEXT, state TEXT, detail TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_merits(at REAL, model TEXT, points INTEGER)')
    c.executemany('INSERT INTO project_steps VALUES (?,?,?,?,?)', [('S-1', d.PLAN, 'Practice 39 (owner): retired agents', 'done', NOW - 3600),
                                                                 ('S-2', d.PLAN, 'Old step', 'done', NOW - 200000), ('S-3', d.PLAN, 'Open step', 'todo', NOW)])
    c.execute("INSERT INTO hb_tasks VALUES ('T-1','S-9 System cleanup 2','active')")
    c.execute("INSERT INTO hb_task_manager VALUES ('T-1','needs_owner','Stopped, not looping: grep_repo failed 3 times',?)", (NOW,))
    c.executemany('INSERT INTO hb_merits VALUES (?,?,?)', [(NOW - 60, 'qwen2.5:14b-instruct', 3), (NOW - 50, 'qwen2.5:14b-instruct', 3), (NOW - 40, 'fred-cpu:24b', 2)])
    return c


def test_practice_46_facts_come_from_hb_records():
    f = d.facts(db(), NOW)
    assert f['done'] == ['Practice 39: retired agents']
    assert f['stalled'] == [('S-9 System cleanup 2', 'Stopped, not looping: grep_repo failed 3 times')]
    assert f['best'] == ('qwen2.5:14b-instruct', 6)


def test_practice_46_text_is_short_and_plain():
    out = d.text(d.facts(db(), NOW), NOW)
    assert out.startswith('🗓 Daily summary, Sunday 15 Nov.') and len(out.splitlines()) == 5
    assert 'Done (1): Practice 39: retired agents.' in out and 'Best model: qwen2.5:14b-instruct (6 points).' in out
    empty = d.text({'done': [], 'stalled': [], 'best': None, 'needs_you': []}, NOW)
    assert 'nothing finished in the last 24 hours' in empty and 'Needs you: nothing.' in empty


def test_practice_46_posted_once_a_day_after_the_hour():
    c = db()
    assert d.tick(c, NOW - 6 * 3600) is None                      # 13:00: not yet
    mid = d.tick(c, NOW)
    assert mid and c.execute('SELECT conversation_id, from_agent FROM messages WHERE id=?', (mid,)).fetchone() == (d.MAIN_CHAT, 'hummingbird')
    assert d.tick(c, NOW + 600) is None                           # same day: once
    assert d.tick(c, NOW + 86400) is not None                     # next day again
