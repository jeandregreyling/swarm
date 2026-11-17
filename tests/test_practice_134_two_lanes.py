"""Practice 134 (owner 17 Nov 2026: "Apex and Fred can work at the same time on different things"). While Fred worked a stuck step on the
CPU, the plan (one step at a time) left APEX idle. A step Fred has taken over now moves to the CPU lane and APEX starts the next ready step;
auto-approve still covers the lane step and its restart is queued when it is done."""
from core import hb_tasks, hb_plan_workflow as wf, hb_commands as hc, peer_bridge
from test_peer_turns import flow  # noqa: F401
from test_hb_plan_workflow import plan, P  # noqa: F401


def _fred(conn, task_id, state):
    task = hb_tasks.get(conn, task_id)
    rid = peer_bridge.enqueue(conn, 1, task['root_message_id'], 'fred turn ' + task_id, ['apex'], sender='hummingbird')[0]
    hb_tasks.event(conn, task, 'hummingbird', 'fred_turn', {'model': 'fred-cpu:24b'}, request_id=rid)
    conn.execute('UPDATE hb_peer_work SET state=? WHERE request_id=?', (state, rid))
    return rid


def _running(conn, task_id):
    wf._update(conn, P, stage='running')
    conn.execute("UPDATE hb_task_manager SET enabled=1, state='running', phase='execute' WHERE task_id=?", (task_id,))


def test_practice_134_fred_on_the_cpu_frees_apex_for_the_next_step(plan, monkeypatch):
    conn, _, tasks = plan
    t1, t5 = tasks['S-00000000A1'], tasks['S-00000000A5']
    hc.handle(conn, 1, '/workflow on', 'jd')
    assert wf.settings(conn, P)['task_id'] == t1
    _running(conn, t1)
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t1                       # APEX on it, no Fred: one step at a time as before
    _fred(conn, t1, 'running')
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t5                       # Fred has t1 on the CPU; APEX starts the next ready step
    assert any('🧵 Fred keeps working on' in r[0] for r in conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird'"))
    assert [s['skip'] for s in wf.steps(conn, P) if s['step_id'] == 'S-00000000A1'] == ['already in progress with HB']
    wf.set_auto_accept(conn, True, 'jd', P)
    assert wf.auto_accept_for(conn, hb_tasks.get(conn, t1)) and wf.auto_accept_for(conn, hb_tasks.get(conn, t5))
    restarts = []
    monkeypatch.setattr(wf, 'restart_after', lambda conn, task, run=None: restarts.append(task['task_id']))
    conn.execute("UPDATE project_steps SET status='done' WHERE step_id='S-00000000A1'")
    wf.tick(conn)
    wf.tick(conn)
    assert restarts == [t1]                                            # once, when the lane step is done


def test_practice_134_a_queued_fred_turn_counts_and_a_finished_one_does_not(plan):
    conn, _, tasks = plan
    t1 = tasks['S-00000000A1']
    hc.handle(conn, 1, '/workflow on', 'jd')
    _running(conn, t1)
    _fred(conn, t1, 'completed')
    wf.tick(conn)
    assert wf.settings(conn, P)['task_id'] == t1
