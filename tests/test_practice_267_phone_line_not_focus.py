"""Practice 267: phone lines are never the focus."""
import sqlite3

from core import peer_bridge


def test_phone_line_is_not_the_focus():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_peer_work(request_id INT, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_task_requests(request_id INT, task_id TEXT, task_version INT)')
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, state TEXT, step_id TEXT, title TEXT)')
    c.executemany('INSERT INTO hb_tasks VALUES (?,?,?,?)', [('T-WORK', 'active', 'S-1', 'Chunk-first 3/6'), ('T-PHONE', 'active', 'S-2', '📱 Telegram: Build it Apex')])
    c.executemany('INSERT INTO hb_task_requests VALUES (?,?,1)', [(1, 'T-WORK'), (2, 'T-PHONE')])
    c.executemany("INSERT INTO hb_peer_work VALUES (?, 'apex', 'completed', '', ?)", [(1, 100), (2, 200)])
    assert peer_bridge.focus_task(c) == 'T-WORK'
