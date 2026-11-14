import json
import sqlite3
from datetime import datetime, timezone

from core import hb_tasks, hb_dream_cycle as dc
from core.hb_task_manager import MAX_CHECKPOINTS_WITHOUT_PASS

BASE = datetime(2026, 11, 12, 1, 0, 0, tzinfo=timezone.utc).timestamp()


def _conn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT,'
              ' to_agent TEXT, content TEXT, message_type TEXT, created_at TEXT)')
    hb_tasks.ensure_schema(c)
    return c


def _owner_says(c, when):
    stamp = datetime.fromtimestamp(when, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,created_at)"
              " VALUES(1,'user','apex','hi','chat',?)", (stamp,))


def test_off_by_default_and_no_cycle():
    c = _conn(); _owner_says(c, BASE)
    assert dc.settings(c)['enabled'] is False
    assert dc.tick(c, now=BASE + 10_000) is None


def test_one_cycle_per_idle_period_and_owner_return_resets():
    c = _conn(); _owner_says(c, BASE)
    dc.configure(c, True, 3600)
    assert dc.tick(c, now=BASE + 3599) is None                     # not idle long enough
    first = dc.tick(c, now=BASE + 3601)
    assert first and dc.latest_report(c)['state'] == 'reported'
    assert dc.tick(c, now=BASE + 9000) is None                     # same idle period: no repeat
    _owner_says(c, BASE + 10_000)                                  # owner came back
    assert dc.tick(c, now=BASE + 10_100) is None
    second = dc.tick(c, now=BASE + 10_000 + 3601)
    assert second and second != first


def test_agent_chatter_does_not_count_as_owner_activity():
    c = _conn(); _owner_says(c, BASE); dc.configure(c, True, 3600)
    c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,created_at)"
              " VALUES(1,'apex','user','busy','chat','2026-11-12 01:50:00')")
    assert dc.tick(c, now=BASE + 3601)


def test_report_names_spinning_task_with_measured_reason():
    from core import hb_task_manager as m
    c = _conn(); m.ensure_schema(c)
    c.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,state,created_at,updated_at)"
              " VALUES('T-SPIN',1,1,'Continue the build','x','active',0,0)")
    c.execute("INSERT INTO hb_task_manager(task_id,enabled,state,phase,sequence,recovery_count,next_due,detail,updated_at) VALUES('T-SPIN',1,'execute','execute',0,0,0,'',0)")
    for _ in range(MAX_CHECKPOINTS_WITHOUT_PASS):
        c.execute("INSERT INTO hb_task_events(task_id,agent,kind,payload) VALUES('T-SPIN','hummingbird','checkpoint','{}')")
    text = dc.build_report(c)['text']
    assert 'SPINNING T-SPIN' in text and 'checkpoints' in text


def test_idle_after_minimum():
    import pytest
    with pytest.raises(ValueError):
        dc.configure(_conn(), True, 5)
