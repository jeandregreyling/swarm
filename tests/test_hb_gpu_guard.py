"""Owner 14 Nov: HB manages the GPU model server - after ErrorDeviceLost it restarts it, proves it answers, and resumes the work."""
import sqlite3
import time

from core import hb_gpu_guard as g


def _db():
    c = sqlite3.connect(':memory:')
    c.executescript("""CREATE TABLE hb_peer_work(request_id INT, state TEXT, stage TEXT, updated_at REAL);
        CREATE TABLE hb_task_requests(request_id INT, task_id TEXT);""")
    return c


def test_restarts_once_proves_it_and_waits_between_restarts():
    c, said, calls = _db(), [], []
    now = time.time()
    c.execute("INSERT INTO hb_peer_work VALUES (7,'failed','decode() failed: vk::Queue::submit: ErrorDeviceLost',?)", (now - 10,))
    c.execute("INSERT INTO hb_task_requests VALUES (7,'T-X')")
    out = g.tick(c, now, restart=lambda: calls.append(1) or True, answers=lambda: True, say=said.append)
    assert calls == [1] and 'A test answer works again; 1 interrupted task' in said[0]
    assert g.tick(c, now + 60, restart=lambda: calls.append(1) or True, answers=lambda: True, say=said.append) is None and calls == [1]


def test_nothing_failed_nothing_restarted():
    c = _db()
    c.execute("INSERT INTO hb_peer_work VALUES (8,'failed','some other error',?)", (time.time(),))
    assert g.tick(c, restart=lambda: 1 / 0, answers=lambda: True, say=print) is None
