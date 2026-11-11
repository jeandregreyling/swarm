import pytest
from core import hb_tasks,hb_task_manager,peer_bridge,peer_turns,hb_provider_conditions as conditions
from test_peer_turns import flow,owner,reply


def test_provider_rejection_retains_task_without_repeating_unchanged_operation(flow):
    conn,p=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    hb_task_manager.register(conn,task,request_id=rid)
    reply(conn,p['apex'],rid,'Provider safety review rejected: Potentially unintended activity',outcome='failed')
    assert hb_task_manager.tick(conn)==[]
    assert conn.execute('SELECT state FROM hb_task_manager').fetchone()[0]=='waiting_provider'
    assert conditions.pending(conn,task)['recovery_requirement']
    assert not peer_turns.ready(conn,rid)
    # A resume/version bump with the same instruction cannot bypass a provider rejection.
    conn.execute('UPDATE hb_tasks SET version=version+1')
    assert conditions.pending(conn,hb_tasks.get(conn,task['task_id']))
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Use only the local read-only diagnostic instead of the rejected operation')").lastrowid
    revised=hb_tasks.bind(conn,1,mid,task_id=task['task_id'])
    assert conditions.pending(conn,revised) is None


def test_managed_review_does_not_spawn_child_with_reviewers_read_only_scope(flow):
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    hb_task_manager.register(conn,task,request_id=rid)
    conn.execute('UPDATE peer_messages SET body=? WHERE id=?',('{"task_type":"hb_managed_review"}',rid))
    response=reply(conn,p['codex-instructor'],rid,'Specific verification remains; return to APEX.')
    assert response['handoff']['queued']==[]
    queued=hb_task_manager.tick(conn)
    assert queued
    assert 'propose_patch' in hb_tasks.invitation_tools(conn,queued[0])


def test_online_capacity_condition_does_not_prevent_local_reverification(flow):
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    hb_task_manager.register(conn,task,request_id=rid)
    conn.execute("UPDATE hb_task_manager SET phase='review'")
    reply(conn,p['codex-instructor'],rid,'Provider usageLimitExceeded',outcome='failed')
    assert hb_task_manager.tick(conn)==[]
    hb_tasks.event(conn,task,'owner-host','mutation',{'reason':'New local correction requires guarded verification'})
    queued=hb_task_manager.tick(conn)
    assert queued and peer_turns.ready(conn,queued[0])
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='apex'
    assert conditions.pending(conn,task,agent='codex-instructor')


@pytest.mark.parametrize('error,recovers',[('Provider usageLimitExceeded',True),('Provider safety review rejected',False)])
def test_only_real_capacity_recovery_is_cleared_by_verified_later_provider_success(flow,error,recovers):
    conn,p=flow;rid=owner(conn,'codex-instructor');task=hb_tasks.for_request(conn,rid)
    hb_task_manager.register(conn,task,request_id=rid)
    reply(conn,p['codex-instructor'],rid,error,outcome='failed')
    assert conditions.pending(conn,task)
    another=owner(conn,'codex-instructor')
    reply(conn,p['codex-instructor'],another,'Actual successful provider response',
        model='actual-test-provider-model',usage={'source':'provider','input_tokens':2,'output_tokens':1,'total_tokens':3})
    assert (conditions.pending(conn,task) is None)==recovers
