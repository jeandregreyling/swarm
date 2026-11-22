"""Practice 247: a bad tool scope never takes down the inbox; the cap fits HB's own tool lists."""
import inspect
import json
import sqlite3

import pytest

from core import hb_tasks, peer_bridge


def _db(n):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, request_id INT, agent TEXT, kind TEXT, payload TEXT)')
    c.execute("INSERT INTO hb_task_events(task_id,request_id,agent,kind,payload) VALUES ('T-1',7,'hummingbird','tool_scope',?)",
              (json.dumps({'allowed_tools': [f't{i}' for i in range(n)]}),))
    return c


def test_twenty_five_tools_is_fine_now():
    assert len(hb_tasks.invitation_tools(_db(25), 7)) == 25


def test_an_absurd_scope_is_still_refused():
    with pytest.raises(ValueError):
        hb_tasks.invitation_tools(_db(65), 7)   # 258: cap 64


def test_the_inbox_sets_a_bad_request_aside_instead_of_failing():
    src = inspect.getsource(peer_bridge.inbox)
    i = src.index('scope=hb_tasks.invitation_tools(conn,row[0])')
    assert 'except ValueError' in src[i:i + 400] and 'continue' in src[i:i + 900]
