"""Practice 235: a stuck task is parked with one plain line and HB moves on - no question to JD."""
import inspect
import sqlite3
import time

from core import hb_tasks
from core import hb_task_manager as tm


def test_park_stuck_pauses_says_so_and_asks_nothing():
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    tm.ensure_schema(c)
    c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO hb_tasks(task_id, conversation_id, root_message_id, title, objective, state, created_at, updated_at) VALUES ('T-1', 7, 1, 'Theme colours', 'x', 'active', 0, 0)")
    c.execute("INSERT INTO hb_task_manager(task_id, enabled, state, phase, next_due, updated_at) VALUES ('T-1', 1, 'running', 'execute', 0, 0)")
    task = hb_tasks.get(c, 'T-1')
    tm.park_stuck(c, task, 'four attempts on chunk 2')
    assert c.execute("SELECT state FROM hb_tasks WHERE task_id='T-1'").fetchone()[0] == 'paused'
    line = c.execute('SELECT content FROM messages').fetchone()[0]
    assert line.startswith('⏸ HB parked') and 'moved on' in line and '?' not in line


def test_the_stuck_paths_park_instead_of_asking():
    src = inspect.getsource(tm.tick)
    assert 'Keep working gives it' not in src and src.count('park_stuck(conn,task,') == 2
