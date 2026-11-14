import pytest
import json
import sqlite3
from pathlib import Path

from core import hb_tasks,peer_bridge as peers,hb_task_manager as manager
from test_peer_turns import flow,owner,reply,four_handoffs


def test_many_handoffs_are_checkpoints_not_end_of_task(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    for n in range(12):
        agent=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(rid,)).fetchone()[0]
        answer='Step evidence '+str(n)+(' @codex' if agent=='apex' else '')
        result=reply(conn,p[agent],rid,answer)
        assert result['handoff']['queued'] and not result['handoff'].get('locked')
        rid=result['handoff']['queued'][0]
        assert conn.execute('SELECT kind FROM hb_peer_routes WHERE request_id=?',(rid,)).fetchone()[0]=='work'
        assert hb_tasks.for_request(conn,rid)['task_id']==task['task_id']
    assert hb_tasks.get(conn,task['task_id'])['state']=='active'


def test_failed_turn_is_retained_and_fresh_work_is_queued_without_owner_prompt(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='needs_review',stage='Worker restarted' WHERE request_id=?",(rid,))
    before=hb_tasks.budget(conn,task)
    queued=manager.tick(conn)
    assert len(queued)==1 and queued[0]!=rid
    assert hb_tasks.for_request(conn,queued[0])['task_id']==task['task_id']
    assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='needs_review'
    assert hb_tasks.get(conn,task['task_id'])['token_budget']==before['token_budget']
    packet=json.loads(peers.inbox(conn,p['apex'],pending_only=True)[0]['body'])
    assert packet['task_type']=='hb_managed_continuation' and packet['plan']['arguments']['evidence_id']
    assert manager.tick(conn)==[]  # A live attempt cannot be duplicated.


def test_checkpoint_carries_real_source_paths_and_current_plan(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    hb_tasks.event(conn,task,'apex','mutation',{'paths':['core/hb_dream.py','tests/test_hb_dream.py']})
    conn.execute("UPDATE hb_peer_work SET state='needs_review' WHERE request_id=?",(rid,))
    queued=manager.tick(conn)
    body=json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0])
    assert body['recent_source_files']==['core/hb_dream.py','tests/test_hb_dream.py']
    current=hb_tasks.packet(conn,task)
    assert current['recent_source_files']==body['recent_source_files']
    assert current['execution_plan']['evidence_id']==body['plan']['arguments']['evidence_id']
    other=hb_tasks.for_request(conn,owner(conn))
    hb_tasks.event(conn,other,'apex','mutation',{'paths':['core/other_owner_task.py']})
    assert 'core/other_owner_task.py' not in hb_tasks.recent_source_paths(conn,task)


def test_owner_hold_and_cancellation_stop_execution(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='completed'")
    conn.execute("UPDATE hb_tasks SET state='paused'")
    assert manager.tick(conn)==[]
    assert conn.execute('SELECT state FROM hb_task_manager').fetchone()[0]=='held'
    conn.execute("UPDATE hb_tasks SET state='cancelled'")
    assert manager.tick(conn)==[]
    assert conn.execute('SELECT state FROM hb_task_manager').fetchone()[0]=='cancelled'


def test_recorded_token_counts_and_project_age_do_not_end_the_goal(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    conn.execute('UPDATE hb_tasks SET token_budget=0,time_budget=0')
    assert manager.tick(conn)


def test_legacy_decision_failure_is_checkpoint_not_dead_end(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow);task=hb_tasks.for_request(conn,decision)
    manager.register(conn,task,request_id=decision)
    posted=reply(conn,p['apex'],decision,'Decision parser failed',outcome='failed')
    text=conn.execute('SELECT content FROM messages WHERE id=?',(posted['message_id'],)).fetchone()[0]
    assert 'checkpoint' in text and 'blocked' not in text.lower()
    assert hb_tasks.get(conn,task['task_id'])['state']=='active'
    assert manager.tick(conn)


def test_independent_review_is_queued_after_guarded_checks_not_while_parent_waits(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    result=reply(conn,p['apex'],rid,'Guarded checks passed; inspect the actual receipts.')
    conn.execute("CREATE TABLE project_test_cases(step_id TEXT,status TEXT)")
    conn.execute("UPDATE hb_tasks SET step_id='S-VERIFY'")
    conn.execute("INSERT INTO project_test_cases VALUES ('S-VERIFY','passed')")
    hb_tasks.event(conn,task,'apex','test_result',{'alm_run_status':'pass'})
    queued=manager.tick(conn)
    row=conn.execute('SELECT recipient,body FROM peer_messages WHERE id=?',(queued[0],)).fetchone()
    assert row[0]=='codex-instructor'
    body=json.loads(row[1]);assert result['message_id'] in body['successful_apex_reply_message_ids']
    tools=hb_tasks.invitation_tools(conn,queued[0])
    assert 'studio_accept' in tools and 'apex_dispatch' not in tools and 'propose_patch' not in tools


def test_saved_followup_after_partial_checks_stays_with_local_executor(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    reply(conn,p['apex'],rid,'The isolated first part passed; more implementation remains.')
    conn.execute("CREATE TABLE project_test_cases(step_id TEXT,status TEXT)")
    conn.execute("UPDATE hb_tasks SET step_id='S-VERIFY'")
    conn.execute("INSERT INTO project_test_cases VALUES ('S-VERIFY','passed')")
    hb_tasks.event(conn,task,'apex','mutation',{'paths':['core/example.py']})
    hb_tasks.event(conn,task,'apex','test_result',{'alm_run_status':'pass'})
    eid=hb_tasks.event(conn,task,'apex','task_plan',{'next_action':'Wire the tested isolated module into the coordinator and verify owner return cancellation.'})
    conn.execute('UPDATE hb_task_manager SET plan_event_id=?',(eid,))
    queued=manager.tick(conn)
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='apex'
    assert hb_tasks.get(conn,task['task_id'])['state']=='active'


def test_transition_to_review_does_not_retry_a_known_unavailable_provider(flow):
    from core import hb_provider_conditions as conditions
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conditions.record_failure(conn,task,rid,'quota exceeded')
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    conn.execute("UPDATE hb_task_manager SET phase='execute',recovery_count=2")
    before=conn.execute('SELECT COUNT(*) FROM peer_messages').fetchone()[0]
    assert manager.tick(conn)==[]
    assert conn.execute('SELECT COUNT(*) FROM peer_messages').fetchone()[0]==before
    assert tuple(conn.execute('SELECT state,phase FROM hb_task_manager').fetchone())==('waiting_provider','review')
    assert conditions.pending(conn,task,agent='codex-instructor')['kind']=='provider_capacity'


def test_old_queued_unavailable_review_does_not_strand_new_local_action(flow):
    from core import hb_provider_conditions as conditions
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conditions.record_failure(conn,task,rid,'quota exceeded')
    conn.execute("UPDATE hb_task_manager SET phase='execute'")
    queued=manager.tick(conn)
    assert len(queued)==1
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='apex'
    assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='needs_review'
    assert conn.execute('SELECT delivered_at FROM peer_messages WHERE id=?',(rid,)).fetchone()[0] is None
    assert conditions.pending(conn,task,agent='codex-instructor')['kind']=='provider_capacity'


def test_review_not_yet_issued_is_resumed_before_another_executor_turn(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    conn.execute("UPDATE hb_task_manager SET phase='review'")
    queued=manager.tick(conn)
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='codex-instructor'


def test_failed_review_is_not_mistaken_for_a_completed_instructor_answer(flow):
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    peers.post(conn,p['codex-instructor'],1,'Transport disconnected before a review',reply_to_request_id=rid,route_reply=False,outcome='failed')
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    conn.execute("UPDATE hb_task_manager SET phase='review'")
    queued=manager.tick(conn)
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='codex-instructor'


def test_memory_pressure_keeps_work_pending(flow):
    conn,p=flow;rid=owner(conn);task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    assert manager.tick(conn,memory=lambda:{'MemAvailable_bytes':1024})==[]
    assert conn.execute('SELECT state FROM hb_task_manager').fetchone()[0]=='waiting_resources'


def test_dependencies_wait_for_acceptance_and_reject_cycles(flow):
    import pytest
    conn,p=flow;first=owner(conn);a=hb_tasks.for_request(conn,first)
    second=owner(conn);b=hb_tasks.for_request(conn,second)
    manager.register(conn,a,request_id=first)
    manager.register(conn,b,request_id=second,dependencies=[a['task_id']])
    assert not manager.dependencies_ready(conn,b)
    with pytest.raises(ValueError,match='cycle'):
        manager.register(conn,a,dependencies=[b['task_id']])
    conn.execute("UPDATE hb_tasks SET state='completed' WHERE task_id=?",(a['task_id'],))
    assert manager.dependencies_ready(conn,b)


def test_oversized_plan_preserves_full_evidence_and_queues_bounded_envelope(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    plan='Full exact implementation instructions '*250
    manager.register(conn,task,request_id=rid,next_action=plan)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    queued=manager.tick(conn)
    body=conn.execute('SELECT body FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]
    assert len(body)<=peers.MAX_BODY
    packet=json.loads(body);assert packet['next_action_is_excerpt']
    saved=conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(packet['plan']['arguments']['evidence_id'],)).fetchone()[0]
    assert json.loads(saved)['next_action']==plan


def test_one_scheduling_failure_cannot_roll_back_other_tasks(flow,monkeypatch):
    conn,p=flow;one=owner(conn,'apex');a=hb_tasks.for_request(conn,one)
    two=owner(conn,'apex');b=hb_tasks.for_request(conn,two)
    manager.register(conn,a,request_id=one);manager.register(conn,b,request_id=two)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    real=manager._queue
    def queue(conn,task,*args):
        if task['task_id']==a['task_id']:raise ValueError('Malformed scoped metadata')
        return real(conn,task,*args)
    monkeypatch.setattr(manager,'_queue',queue)
    queued=manager.tick(conn)
    assert len(queued)==1 and hb_tasks.for_request(conn,queued[0])['task_id']==b['task_id']
    assert conn.execute('SELECT state FROM hb_task_manager WHERE task_id=?',(a['task_id'],)).fetchone()[0]=='waiting_recovery'


def test_repeated_failed_checks_do_not_masquerade_as_implementation_progress(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    for _ in range(3):
        conn.execute("UPDATE hb_peer_work SET state='failed'")
        conn.execute('UPDATE hb_task_manager SET next_due=0')
        hb_tasks.event(conn,task,'apex','test_result',{'alm_run_status':'fail','summary':'Same failing check; no source correction'})
        queued=manager.tick(conn)
        assert queued
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='codex-instructor'
    assert hb_tasks.get(conn,task['task_id'])['state']=='active'

pytestmark = pytest.mark.usefixtures("owner_turned_continuation_on", "online_providers_authorised", "owner_defined_done")


def test_stalled_task_gets_local_help_before_the_owner_and_never_asks_for_codex(flow,monkeypatch):
    """Owner 13 Nov: HB knows Codex is unavailable. A stalled task first gets Fred; the owner is asked only after that,
    with Keep working (not Approve, not Allow Codex). Owner 14 Nov: "give it some teeth" - Fred takes over the step with APEX's
    tools (a working turn on Fred's model) instead of only advising."""
    from core import hb_online
    monkeypatch.setattr(hb_online,'status',lambda conn,provider:{'usable':False,'authorised':True,'reason':'usage limit reached'})
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    conn.execute("UPDATE hb_tasks SET step_id='S-ABCDEF0123' WHERE task_id=?",(task['task_id'],))
    manager.register(conn,task,request_id=rid)

    def stall(times):
        for _ in range(times):
            conn.execute("UPDATE hb_peer_work SET state='failed' WHERE state<>'completed'")
            conn.execute("UPDATE hb_task_manager SET next_due=0")
            hb_tasks.event(conn,task,'apex','test_result',{'alm_run_status':'fail','summary':'Same failing check'})
            manager.tick(conn)
    stall(3)
    questions=lambda:' '.join(json.loads(r[0]).get('text','') for r in conn.execute("SELECT payload FROM hb_task_events WHERE kind='owner_question'"))
    fred=conn.execute("SELECT request_id FROM hb_task_events WHERE kind='fred_turn'").fetchone()[0]
    scope=json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='tool_scope' AND request_id=?",(fred,)).fetchone()[0])
    assert scope['preferred_local_model']=='fred-cpu:24b' and 'propose_patch' in scope['allowed_tools']   # Fred works with APEX's tools
    body=json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?',(fred,)).fetchone()[0])
    assert body['instruction'].startswith('FRED TAKES OVER')
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '🛠 Fred is taking over%'").fetchone()[0]==1
    assert questions()==''
    conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(fred,))   # Fred's turn ran to the end
    stall(3)                                                                     # ...and still no progress
    text=questions()
    assert 'APEX is stuck on' in text and 'Fred took over and could not finish it either' in text
    assert '/continue '+task['task_id'] in text and '/accept' not in text and '/online codex' not in text
    assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='fred_turn'").fetchone()[0]==1   # once per progress point


def test_continuation_carries_the_newest_plan_not_the_first(flow):
    """13 Nov: reviewer coaching (a newer task_plan) never reached APEX's managed continuation turns."""
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid,next_action='Original objective text')
    hb_tasks.event(conn,task,'claude-code','task_plan',{'next_action':'Coaching: your patch is right; just run the test'})
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    conn.execute('UPDATE hb_task_manager SET next_due=0')
    queued=manager.tick(conn)
    body=conn.execute('SELECT body FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]
    assert 'Coaching: your patch is right' in body and 'Original objective text' not in json.loads(body)['next_action']


def test_workflow_auto_approve_accepts_a_step_whose_checks_pass(flow):
    """Owner 13 Nov: approvals are automatic while the workflow runs; a step whose own checks pass after its last change is approved by HB."""
    from core import hb_plan_workflow as wf
    conn,p=flow
    conn.execute("CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, order_idx REAL, created_at REAL, updated_at REAL, residual_risk TEXT)")
    conn.execute("INSERT INTO project_steps VALUES('S-ABCDEF0123','P-2AB8250A87','Practice X','Done when: test passes','todo','apex',1,0,0,NULL)")
    rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    conn.execute("UPDATE hb_tasks SET step_id='S-ABCDEF0123',project_id='P-2AB8250A87' WHERE task_id=?",(task['task_id'],))
    task=hb_tasks.get(conn,task['task_id'])
    manager.register(conn,task,request_id=rid)
    conn.execute("CREATE TABLE IF NOT EXISTS project_test_cases(case_id TEXT, project_id TEXT, step_id TEXT, title TEXT, description TEXT, status TEXT, owner TEXT, created_at REAL, updated_at REAL)")
    conn.execute("INSERT INTO project_test_cases VALUES('C-1','P-2AB8250A87','S-ABCDEF0123','t','','passed','apex',0,0)")
    hb_tasks.event(conn,task,'apex','mutation',{'status':'succeeded'})
    hb_tasks.event(conn,task,'apex','test_result',{'alm_run_status':'pass','verdict':'PASS: 1 passed'})
    wf.configure(conn,True,'jd')
    conn.execute("UPDATE hb_plan_workflow SET task_id=?,step_id='S-ABCDEF0123',stage='running'",(task['task_id'],))
    assert 'Auto-approve ON' in wf.command(conn,1,['auto','on'],'jd')
    conn.execute("UPDATE hb_peer_work SET state='completed'")
    conn.execute('UPDATE hb_task_manager SET next_due=0')
    manager.tick(conn)
    assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-ABCDEF0123'").fetchone()[0]=='done'
    assert hb_tasks.get(conn,task['task_id'])['state']=='completed'
    text=conn.execute("SELECT content FROM messages WHERE content LIKE '✅ Done:%'").fetchone()[0]
    assert 'S-ABCDEF0123' in text and 'auto-approve is on' in text and 'check: PASS: 1 passed' in text
    assert not conn.execute("SELECT 1 FROM hb_task_events WHERE kind='owner_question'").fetchone()


def test_going_round_in_circles_hands_the_step_to_fred_before_jd(flow,monkeypatch):
    """Owner 14 Nov: DOES rename 5 failed the same patch 3 times and HB asked JD without trying Fred."""
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    for _ in range(manager.MAX_REPEATED_FAILURES):
        hb_tasks.event(conn,task,'apex','tool_failure',{'tool':'propose_patch','error':'Exact patch text matched 0 locations'})
    assert manager.stuck_reason(conn,task['task_id'])
    conn.execute("UPDATE hb_task_manager SET next_due=0")
    manager.tick(conn)
    assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='fred_turn'").fetchone()[0]==1
    assert not conn.execute("SELECT 1 FROM hb_task_events WHERE kind='owner_question'").fetchone()
    assert 'Fred took over' in conn.execute('SELECT detail FROM hb_task_manager').fetchone()[0]


def test_a_crashed_fred_turn_gets_one_retry(flow,monkeypatch):
    """14 Nov: Fred's first working turn crashed (APEX's prompt did not fit his context); that is not Fred's try."""
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    assert manager.local_help(conn,task)=='submitted'
    first=conn.execute("SELECT request_id FROM hb_task_events WHERE kind='fred_turn'").fetchone()[0]
    conn.execute("UPDATE hb_peer_work SET state='failed' WHERE request_id=?",(first,))
    assert manager.local_help(conn,task)=='submitted'                       # crashed: one retry
    second=conn.execute("SELECT request_id FROM hb_task_events WHERE kind='fred_turn' ORDER BY event_id DESC").fetchone()[0]
    conn.execute("UPDATE hb_peer_work SET state='failed' WHERE request_id=?",(second,))
    assert manager.local_help(conn,task)=='completed'                       # no third
