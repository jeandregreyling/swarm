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
