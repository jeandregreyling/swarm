"""The owner can pause the task visible as running without looking up its task ID."""
import time

import pytest

from core import hb_commands as hc, hb_plan_workflow, hb_activity_log
from test_hb_commands import conn


def task(conn, number, *, conversation=1, state="active"):
    tid = "T-" + f"{number:012X}"
    conn.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,state,created_at,updated_at,version) "
                 "VALUES(?,?,?,'A task','Its checks pass',?,0,?,1)", (tid, conversation, number, state, number))
    conn.execute("INSERT INTO hb_task_messages(message_id,task_id,kind) VALUES(?,?,'instruction')", (number, tid))
    return tid


def running(conn, tid, source):
    if source == "workflow":
        hb_plan_workflow.ensure_schema(conn)
        conn.execute("INSERT INTO hb_plan_workflow(project_id,enabled,task_id,stage) VALUES(?,1,?,'running')", (tid, tid))
    elif source == "peer":
        rid = int(tid[2:], 16)
        conn.execute("INSERT INTO hb_task_requests(request_id,task_id) VALUES(?,?)", (rid, tid))
        conn.execute("INSERT INTO hb_peer_work VALUES(?,'apex','running','working',?)", (rid, time.time()))
    else:
        hb_activity_log.ensure(conn)
        conn.execute("INSERT INTO hb_activity_log(at,run_id,lane,actor,task_id,kind,text) VALUES(?,?,'gpu','apex',?,'start','working')",
                     (time.time(), tid, tid))


@pytest.mark.parametrize("source", ["workflow", "peer", "activity"])
def test_pause_without_id_holds_the_running_task_and_stops_its_executor(conn, monkeypatch, source):
    tid = task(conn, 1)
    unrelated = task(conn, 2)                     # newer is not necessarily running
    running(conn, tid, source)
    stopped = []
    monkeypatch.setattr('core.hb_executions.stop_held_executors', lambda selected: stopped.append(selected))
    after = []
    reply = hc.handle(conn, 1, '/pause', 'JD', after=after, interpreter=lambda *_: pytest.fail('fixed command needs no model'))
    assert tid in reply and 'Off' in reply
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'paused'
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (unrelated,)).fetchone()[0] == 'active'
    assert len(after) == 1
    after[0]()
    assert stopped == [tid]


def test_pause_without_id_preserves_other_chats_and_existing_holds(conn):
    local = task(conn, 1)
    other_chat = task(conn, 2, conversation=2)
    held = task(conn, 3, state='paused')
    for tid in (other_chat, held):
        running(conn, tid, 'peer')
    after = []
    reply = hc.handle(conn, 1, '/pause', 'JD', after=after)
    assert 'No task is running' in reply and after == []
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (local,)).fetchone()[0] == 'active'
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (held,)).fetchone()[0] == 'paused'


def test_pause_without_id_lists_simultaneous_tasks_and_explicit_id_still_works(conn):
    one, two = task(conn, 1), task(conn, 2)
    running(conn, one, 'peer')
    running(conn, two, 'activity')
    after = []
    reply = hc.handle(conn, 1, '/pause', 'JD', after=after)
    assert '/pause ' + one in reply and '/pause ' + two in reply and after == []
    assert all(row[0] == 'active' for row in conn.execute('SELECT state FROM hb_tasks'))
    reply = hc.handle(conn, 1, '/pause ' + two, 'JD', after=after)
    assert two in reply and 'Off' in reply and len(after) == 1
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (one,)).fetchone()[0] == 'active'


def test_pause_ignores_queued_and_finished_activity(conn):
    tid = task(conn, 1)
    running(conn, tid, 'peer')
    conn.execute("UPDATE hb_peer_work SET state='queued'")
    running(conn, tid, 'activity')
    conn.execute("INSERT INTO hb_activity_log(run_id,kind) VALUES(?,'finish')", (tid,))
    assert 'No task is running' in hc.handle(conn, 1, '/pause', 'JD')


def test_pause_fixed_grammar_and_typo_suggestion():
    assert hc.parse('pause') == ('pause', [])
    assert hc.parse('continue') is None and hc.parse('cancel') is None
    assert hc.parse('pause t-000000000001') == ('pause', ['T-000000000001'])
    assert hc.parse('pause random words') is None
    assert hc.suggest('pase') == 'pause'
