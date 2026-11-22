"""Practice 248: HB keeps APEX on one task until it is done or parked; JD's questions still go first."""
import inspect
import sqlite3

from core import peer_bridge


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_peer_work(request_id INT, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_task_requests(request_id INT, task_id TEXT, task_version INT)')
    c.execute("CREATE TABLE hb_tasks(task_id TEXT, state TEXT, step_id TEXT, title TEXT DEFAULT '')")
    c.executemany('INSERT INTO hb_tasks(task_id, state, step_id) VALUES (?,?,?)', [('T-A', 'active', 'S-A'), ('T-B', 'active', 'S-B'), ('T-C', 'paused', 'S-C'), ('T-CHAT', 'active', None)])
    c.executemany('INSERT INTO hb_task_requests VALUES (?,?,1)', [(1, 'T-A'), (2, 'T-B'), (3, 'T-C'), (10, 'T-A'), (11, 'T-B'), (12, 'T-C')])
    c.executemany("INSERT INTO hb_peer_work VALUES (?, 'apex', 'completed', '', ?)", [(1, 100), (2, 200), (3, 300)])
    return c


def test_focus_is_the_last_task_worked_that_is_still_open():
    assert peer_bridge.focus_task(_db()) == 'T-B'          # T-C was later but is paused (parked)


def test_order_is_chat_then_focus_then_oldest():
    items = [{'id': 10}, {'id': 11}, {'id': 12}, {'id': 50}]   # 50: no task - JD's question
    assert [i['id'] for i in peer_bridge.focus_order(_db(), items)] == [50, 11, 10, 12]


def test_the_inbox_and_the_worker_use_it():
    assert 'focus_order(conn' in inspect.getsource(peer_bridge.inbox)
    from pathlib import Path
    w = (Path(__file__).resolve().parents[1] / 'scripts/hummingbird_peer_worker.py').read_text()
    assert "if agent=='apex':break   # Practice 248" in w and 'inbox=focus_order(_c,inbox)' in w


def test_a_chat_thread_is_never_the_focus():
    c = _db()
    c.execute("INSERT INTO hb_task_requests VALUES (4, 'T-CHAT', 1)")
    c.execute("INSERT INTO hb_peer_work VALUES (4, 'apex', 'completed', '', 400)")
    assert peer_bridge.focus_task(c) == 'T-B'
