"""Practice 242: once a queued restart has waited its quiet minute, no new APEX turn starts, so the restart finds its gap."""
import sqlite3
import time

from core import hb_calm


def _db(at=None):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_restart_queue(task_id TEXT, scope TEXT, reason TEXT, at REAL)')
    if at is not None:
        c.execute("INSERT INTO hb_restart_queue VALUES ('T-1','ui','x',?)", (at,))
    return c


def test_no_queue_no_hold():
    assert hb_calm.restart_queued(_db()) is False


def test_a_fresh_request_does_not_hold_yet():
    assert hb_calm.restart_queued(_db(time.time() - 5)) is False


def test_a_waiting_restart_holds_new_turns():
    assert hb_calm.restart_queued(_db(time.time() - 120)) is True


def test_no_table_no_hold():
    assert hb_calm.restart_queued(sqlite3.connect(':memory:')) is False


def test_the_inbox_uses_it():
    import inspect
    from core import peer_bridge
    assert 'restart_queued(conn)' in inspect.getsource(peer_bridge.inbox)
