"""Owner 14 Nov: "it should never do self looping - same answer, same request: immediate red flag and termination of the process"."""
import json
import time

from core import hb_tasks, hb_loop_guard as lg, peer_bridge as peers
from test_peer_turns import flow, reply, owner  # noqa: F401
from test_hb_plan_workflow import plan  # noqa: F401


def _again(conn, task, body):
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'hummingbird','apex',?,'checkpoint')",
                       (body,)).lastrowid
    hb_tasks.bind(conn, 1, mid, task_id=task['task_id'], kind='checkpoint')
    return peers.enqueue(conn, 1, mid, body, ['apex'], sender='hummingbird')[0]


BODY = json.dumps({'task_type': 'hb_managed_continuation', 'task_id': 'X', 'sequence': 4, 'instruction': 'Continue', 'next_action': 'Run the tests'})


def test_same_answer_to_the_same_request_is_stopped_at_once(flow):
    conn, p = flow
    rid = owner(conn, 'apex')
    task = hb_tasks.for_request(conn, rid)
    first = _again(conn, task, BODY)
    reply(conn, p['apex'], first, 'I will run the tests now. [Backend action check: no test ran]')
    second = _again(conn, task, BODY.replace('"sequence": 4', '"sequence": 5'))   # the same request (only its counter moved)
    third = _again(conn, task, BODY.replace('"sequence": 4', '"sequence": 6'))
    reply(conn, p['apex'], second, 'I will run the tests now.')
    t = hb_tasks.get(conn, task['task_id'])
    assert t['state'] == 'paused'
    assert conn.execute("SELECT state FROM hb_peer_work WHERE request_id=?", (third,)).fetchone()[0] == 'cancelled'
    flag = conn.execute("SELECT content FROM messages WHERE content LIKE '🔴 Loop stopped%'").fetchone()[0]
    assert 'apex gave the same answer to the same request twice' in flag and f"/continue {task['task_id']}" in flag
    assert conn.execute("SELECT 1 FROM hb_task_events WHERE kind='loop_stopped'").fetchone()


def test_a_different_answer_or_real_progress_is_not_a_loop(flow):
    conn, p = flow
    rid = owner(conn, 'apex')
    task = hb_tasks.for_request(conn, rid)
    a = _again(conn, task, BODY)
    reply(conn, p['apex'], a, 'I will run the tests now.')
    b = _again(conn, task, BODY.replace('"sequence": 4', '"sequence": 5'))
    reply(conn, p['apex'], b, 'Tests ran: 2 failed in test_x.py; fixing the import next.')
    hb_tasks.event(conn, task, 'apex', 'mutation', {'output': 'patch completed: core/x.py'})
    c = _again(conn, task, BODY.replace('"sequence": 4', '"sequence": 6'))
    reply(conn, p['apex'], c, 'Tests ran: 2 failed in test_x.py; fixing the import next.')   # same words, but a change was made between
    assert hb_tasks.get(conn, task['task_id'])['state'] != 'paused'
    assert not conn.execute("SELECT 1 FROM messages WHERE content LIKE '🔴 Loop stopped%'").fetchone()


def test_hb_cannot_repeat_itself_to_jd(flow):
    conn, _ = flow
    lg.install(conn)
    for _ in range(3):
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'hummingbird','user','⏸ Parked X','response')")
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'hummingbird','user','Downloads: none','response')")
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content='⏸ Parked X'").fetchone()[0] == 1      # an automatic notice: once
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content='Downloads: none'").fetchone()[0] == 3  # answers to JD's commands: every time
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'apex','user','same words','response')")
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'apex','user','same words','response')")
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content='same words'").fetchone()[0] == 2   # agents' turns are the reply guard's job


def test_the_same_restart_twice_is_refused(plan):
    from core import hb_plan_workflow as wf
    conn, _, tasks = plan
    ran = []
    for round_ in range(2):
        conn.execute('CREATE TABLE IF NOT EXISTS hb_restart_queue(task_id TEXT PRIMARY KEY, scope TEXT, reason TEXT, at REAL)')
        conn.execute("INSERT OR REPLACE INTO hb_restart_queue VALUES('T-1','ui','Practice 28',?)", (time.time() - 120,))
        wf.restart_tick(conn, run=ran.append)
    assert len(ran) == 1
    assert conn.execute("SELECT 1 FROM messages WHERE content LIKE '🔴 Loop stopped: HB was about to restart again%'").fetchone()


def test_jd_asking_the_same_question_twice_gets_the_same_answer_twice(flow):
    """JD: "if I ask for an IP address or task number, the answer should technically be the same every time"."""
    conn, p = flow
    for _ in range(2):
        rid = owner(conn, 'apex')                    # JD's own request, asked twice
        reply(conn, p['apex'], rid, 'The IP address is 10.0.0.8.')
    task = hb_tasks.for_request(conn, rid)
    assert hb_tasks.get(conn, task['task_id'])['state'] != 'paused'
    assert not conn.execute("SELECT 1 FROM messages WHERE content LIKE '🔴 Loop stopped%'").fetchone()
