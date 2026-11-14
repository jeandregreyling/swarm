"""Owner rule S-437AC764CB: Continue is Off by default and stops AUTOMATIC continuation.

The owner's own requests (a direct main-chat turn, or an @agent request the owner sent) still
run under the default Off. An explicit owner Off pauses the task and stops everything.
"""
import sqlite3
import uuid
from contextlib import closing

import pytest

from core import hb_tasks, peer_turns
from core.hb_chat_controls import continuation, set_continuation
from core.hb_executions import authorized


@pytest.fixture
def db(tmp_path, monkeypatch):
    from utils.db import _connection
    path = tmp_path / 'owner-turn.sqlite'
    monkeypatch.setattr(_connection, 'DB_PATH', str(path))
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT,'
                     ' content TEXT, message_type TEXT, tokens_used INT, created_at TEXT)')
        from core import peer_bridge
        peer_bridge.ensure_schema(conn)
        if hasattr(peer_turns, 'ensure_schema'):
            peer_turns.ensure_schema(conn)
        hb_tasks.ensure_schema(conn)
    return path


def _task(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(77,'user','apex','Read example.py','chat')").lastrowid
        task = hb_tasks.bind(conn, 77, mid)
        return task, continuation(conn, task)['revision']


def _request(path, task, sender):
    with closing(sqlite3.connect(path)) as conn, conn:
        rid = conn.execute("INSERT INTO peer_messages(conversation_id,message_id,sender,recipient,body,created_at) VALUES(77,?,?,'apex','work',0)",
                           (task['root_message_id'], sender)).lastrowid
        conn.execute('INSERT INTO hb_task_requests(task_id,request_id) VALUES(?,?)', (task['task_id'], rid))
        return rid


def _owner_turn(task, revision):
    return {'task_id': task['task_id'], 'task_version': task['version'], 'control_revision': revision, 'requested_by': 'ghost'}


def test_owner_direct_turn_runs_under_the_default_off(db):
    task, revision = _task(db)
    assert authorized(_owner_turn(task, revision)) is True


def test_automatic_turns_stay_held_by_off(db):
    task, revision = _task(db)
    assert authorized({'task_id': task['task_id'], 'task_version': task['version']}) is False      # no owner-turn marker
    rid = _request(db, task, 'hummingbird')
    assert authorized({'peer_request_id': rid}) is False
    with closing(sqlite3.connect(db)) as conn:
        assert peer_turns.ready(conn, rid) is False


def test_owner_sent_request_runs_under_the_default_off(db):
    task, _ = _task(db)
    rid = _request(db, task, 'ghost')
    assert authorized({'peer_request_id': rid}) is True
    with closing(sqlite3.connect(db)) as conn:
        assert peer_turns.ready(conn, rid) is True


def test_owner_pressing_off_stops_everything(db):
    task, revision = _task(db)
    actor = _owner_turn(task, revision)
    rid = _request(db, task, 'ghost')
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.row_factory = sqlite3.Row
        t = hb_tasks.get(conn, task['task_id'])
        set_continuation(conn, t, {'mode': 'off', 'message_id': t['root_message_id'], 'version': t['version'],
                                   'revision': revision, 'command_id': 'test-off-' + uuid.uuid4().hex[:12]}, 'ghost')
    assert authorized(actor) is False
    assert authorized({'peer_request_id': rid}) is False
    with closing(sqlite3.connect(db)) as conn:
        assert peer_turns.ready(conn, rid) is False
