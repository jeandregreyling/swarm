"""The clipboard's Fred doer executes authorised work on the CPU while APEX takes the next ready step."""
import json

from core import hb_clipboard, hb_dream_method, hb_model_switches, hb_tasks, hb_task_manager as tm, hb_plan_workflow as wf, peer_turns
from core.hb_chat_controls import continuation
from test_hb_plan_workflow import plan, PROPOSAL, _request, P  # noqa: F401
from test_peer_turns import flow, reply  # noqa: F401

S1 = 'S-00000000A1'
S5 = 'S-00000000A5'
CHECK = 'python -m pytest tests/test_hb_learning.py passes'


def selected(plan, doer='fred', criteria=True):
    conn, _, tasks = plan
    task = hb_tasks.get(conn, tasks[S1])
    if criteria:
        hb_dream_method.set_done(conn, task, [CHECK], 'JD')
    hb_clipboard.edit(conn, ['doer', S1, doer], 'JD')
    wf.configure(conn, True, 'JD', conversation_id=1)
    return conn, task


def fred_requests(conn):
    return [r[0] for r in conn.execute("SELECT request_id FROM hb_task_events WHERE kind='fred_turn'")]


def test_selected_fred_gets_real_tools_once_and_frees_the_gpu_lane(plan):
    conn, task = selected(plan)
    wf.tick(conn)
    rid, = fred_requests(conn)
    body = json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?', (rid,)).fetchone()[0])
    scope = json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='tool_scope'", (rid,)).fetchone()[0])
    assert scope['preferred_local_model'] == 'fred-cpu:24b' and 'propose_patch' in scope['allowed_tools']
    assert 'The clipboard selected you to execute this step.' in body['instruction']
    assert 'APEX was stuck' not in body['instruction']
    assert wf.settings(conn)['task_id'] is None and wf.settings(conn)['stage'] == 'idle'
    assert wf._lane_project(conn, task['task_id']) == P
    assert continuation(conn, task)['mode'] == 'on' and peer_turns.ready(conn, rid)
    assert 'selected as clipboard doer' in conn.execute("SELECT payload FROM hb_task_events WHERE kind='fred_turn'").fetchone()[0]
    wf.tick(conn)
    assert wf.settings(conn)['step_id'] == S5
    wf.tick(conn)
    assert fred_requests(conn) == [rid]
    assert 'APEX is scoping' in wf.status_text(conn)
    assert continuation(conn, task)['mode'] == 'on' and peer_turns.ready(conn, rid)
    wf.configure(conn, False, 'JD', conversation_id=1)
    assert continuation(conn, task)['mode'] == 'off' and not peer_turns.ready(conn, rid)
    wf.configure(conn, True, 'JD', conversation_id=1)
    assert continuation(conn, task)['mode'] == 'on' and peer_turns.ready(conn, rid)
    hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': 'off', 'actor': 'JD'})
    assert continuation(conn, task)['mode'] == 'off' and not peer_turns.ready(conn, rid)


def test_closed_cpu_lane_does_not_keep_a_continuation_grant(plan):
    conn, task = selected(plan)
    wf.tick(conn)
    rid, = fred_requests(conn)
    assert peer_turns.ready(conn, rid)
    hb_tasks.event(conn, task, 'hummingbird', 'workflow_lane_closed', {'status': 'done'})
    assert wf.grant(conn, task) is None
    assert continuation(conn, task)['mode'] == 'off' and not peer_turns.ready(conn, rid)


def test_selected_fred_keeps_spec_less_turn_read_only_then_routes_approved_plan(plan):
    conn, task = selected(plan, criteria=False)
    wf.tick(conn)
    assert not fred_requests(conn) and wf.settings(conn)['stage'] == 'planning'
    rid = _request(conn, task['task_id'])
    scope = json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='tool_scope'", (rid,)).fetchone()[0])
    assert scope['allowed_tools'] == wf.PLAN_TOOLS and 'propose_patch' not in scope['allowed_tools']
    reply(conn, plan[1]['apex'], rid, PROPOSAL)
    wf.tick(conn)
    wf.approve_plan(conn, task['task_id'], 'JD')
    assert len(fred_requests(conn)) == 1 and wf.settings(conn)['task_id'] is None


def test_selected_fred_homework_card_keeps_cpu_lane_idle_for_the_next_step(plan):
    conn, task = selected(plan, criteria=False)
    hb_tasks.event(conn, task, 'hummingbird', 'spec_card', {'ready': True, 'task_version': task['version'], 'check': CHECK, 'plan': ['Read the code', 'Run the check'],
                                                         'model': 'homework-cpu:7b', 'doer': 'fred'})
    wf.tick(conn)
    assert len(fred_requests(conn)) == 1 and wf.settings(conn)['stage'] == 'idle'
    assert wf.settings(conn)['task_id'] is None


def test_fred_off_falls_back_locally_with_a_truthful_reason(plan):
    conn, task = selected(plan)
    hb_model_switches.ensure_schema(conn)
    conn.execute('INSERT INTO hb_model_switches VALUES(?,?,?,0)', (hb_model_switches.FRED, 'off', 'JD'))
    wf.tick(conn)
    assert not fred_requests(conn) and wf.settings(conn)['task_id'] == task['task_id']
    assert wf.settings(conn)['stage'] == 'running'
    assert 'Fred is switched Off' in conn.execute("SELECT payload FROM hb_task_events WHERE kind='workflow_doer'").fetchone()[0]
    assert conn.execute("SELECT content FROM messages WHERE content LIKE '%APEX continues this step locally.%'").fetchone()


def test_completed_fred_attempt_is_not_queued_again_or_claimed_running(plan):
    conn, task = selected(plan)
    tm.register(conn, task)
    assert tm.local_help(conn, task, selected=True) == 'submitted'
    rid, = fred_requests(conn)
    conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?", (rid,))
    conn.execute('UPDATE peer_messages SET delivered_at=1 WHERE id=?', (rid,))
    conn.execute("UPDATE hb_task_manager SET enabled=0, state='idle' WHERE task_id=?", (task['task_id'],))
    wf.tick(conn)
    assert fred_requests(conn) == [rid]
    assert wf.settings(conn)['task_id'] == task['task_id'] and wf.settings(conn)['stage'] == 'running'
    assert not conn.execute("SELECT 1 FROM hb_task_events WHERE kind='workflow_lane'").fetchone()
    assert 'no current Fred turn (completed)' in conn.execute("SELECT payload FROM hb_task_events WHERE kind='workflow_doer'").fetchone()[0]


def test_online_doer_does_not_dispatch_an_online_request(plan):
    from core import hb_online
    conn, task = selected(plan, doer='codex')
    hb_online.set_mode(conn, 'codex', 'off', 'JD')
    wf.tick(conn)
    assert not conn.execute("SELECT 1 FROM peer_messages WHERE recipient!='apex'").fetchone()
    assert wf.settings(conn)['task_id'] == task['task_id']
    decision = json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='workflow_doer'").fetchone()[0])
    assert decision['requested'] == 'codex' and decision['actual'] == 'apex'
    assert 'not wired' in decision['reason']


def test_held_selected_fred_task_is_skipped_by_normal_workflow_selection(plan):
    conn, task = selected(plan)
    hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': 'off', 'actor': 'JD'})
    wf.tick(conn)
    assert not fred_requests(conn)
    assert wf.settings(conn)['step_id'] == S5
