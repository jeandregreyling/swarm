from contextlib import closing
import json
import pytest
from core import hb_provider_conditions as conditions,hb_tasks,hb_owner_sessions as sessions,peer_bridge as peers,agent_identity
from test_hb_task_api import assigned
from test_agent_identity import api,enrolled,connect

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.fixture
def capacity_store(assigned,monkeypatch,tmp_path):
    _,root,path,_,original=assigned
    monkeypatch.setattr(sessions,'ROOT',root)
    monkeypatch.setattr(sessions,'KEY_FILE',tmp_path/'owner-key/key')
    with closing(connect(path)) as conn,conn:
        created=sessions.grant(conn,sessions.native_owner_authority(),conversation_id=1,project_id=original['project_id'],
            objective='Continue the explicitly approved local repair and independent review.',
            evidence_text='Actual fixture owner explicitly approves Auto for the ongoing repair and instructor review.',
            reason='Test verified provider capacity recovery without resetting owner controls or quota.')
        task=hb_tasks.get(conn,created['task_id'])
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Review approved repair')").lastrowid
        hb_tasks.bind(conn,1,mid,task_id=task['task_id'],kind='checkpoint')
        rid=peers.enqueue(conn,1,mid,'Review approved repair',['codex-instructor'],sender='hummingbird')[0]
        conditions.record_failure(conn,task,rid,'usage limit exceeded')
    return path,task,rid


def status(used=53):
    return {'rateLimits':{'limitId':'codex','primary':{'usedPercent':used,'resetsAt':10000},
        'secondary':{'usedPercent':71,'resetsAt':20000}},'credential':'must not be stored'}


class ReadOnlyStatus:
    def __init__(self,data):self.data=data;self.methods=[];self.closed=False
    def call(self,method,args):
        self.methods.append(method)
        assert method=='account/rateLimits/read' and args=={}
        return self.data
    def close(self):self.closed=True


def test_actual_allowance_observation_recovers_only_with_read_only_rpc(capacity_store):
    path,task,_=capacity_store;client=ReadOnlyStatus(status())
    result=conditions.probe_codex_capacity(now=1000,client_factory=lambda:client)
    assert result['resolved_task_ids']==[task['task_id']]
    assert client.methods==['account/rateLimits/read'] and client.closed
    with closing(connect(path)) as conn:
        assert conditions.pending(conn,task) is None
        raw=conn.execute('SELECT observed FROM hb_provider_probes').fetchone()[0]
        assert 'credential' not in raw and 'must not be stored' not in raw
        assert hb_tasks.get(conn,task['task_id'])['token_budget']==task['token_budget']


def test_identical_or_worse_status_cannot_loop_another_failed_generation(capacity_store):
    path,task,rid=capacity_store
    conditions.probe_codex_capacity(now=1000,client_factory=lambda:ReadOnlyStatus(status()))
    with closing(connect(path)) as conn,conn:conditions.record_failure(conn,task,rid,'usage limit exceeded again')
    assert conditions.probe_codex_capacity(now=1001,client_factory=lambda:pytest.fail('Probe cadence must be preserved'))['state']=='not_due'
    unchanged=conditions.probe_codex_capacity(now=1301,client_factory=lambda:ReadOnlyStatus(status()))
    assert unchanged['state']=='observed_no_recovery_change' and not unchanged['resolved_task_ids']
    worse=conditions.probe_codex_capacity(now=1602,client_factory=lambda:ReadOnlyStatus(status(54)))
    assert not worse['resolved_task_ids']
    recovered=conditions.probe_codex_capacity(now=1903,client_factory=lambda:ReadOnlyStatus(status(5)))
    assert recovered['resolved_task_ids']==[task['task_id']]


@pytest.mark.parametrize('boundary',['policy','different_provider','revoked','paused'])
def test_capacity_probe_cannot_override_policy_scope_or_owner_hold(capacity_store,boundary):
    path,task,rid=capacity_store
    with closing(connect(path)) as conn,conn:
        if boundary=='policy':conditions.record_failure(conn,task,rid,'Provider safety review rejected this operation')
        elif boundary=='different_provider':conn.execute("UPDATE peer_messages SET recipient='gemini-advisor' WHERE id=?",(rid,))
        elif boundary=='revoked':conn.execute('UPDATE hb_owner_sessions SET revoked_at=1')
        else:conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?",(task['task_id'],))
    assert conditions.probe_codex_capacity(now=1000,client_factory=lambda:pytest.fail('No status call for this scope'))['state']=='idle'
    with closing(connect(path)) as conn:
        assert conn.execute('SELECT resolved_event_id FROM hb_provider_conditions').fetchone()[0] is None


@pytest.mark.parametrize('data',[status(100),{}, {'rateLimits':{'limitId':'codex','primary':{'usedPercent':False}}}])
def test_limited_or_unknown_provider_status_does_not_resume_work(capacity_store,data):
    path,task,_=capacity_store
    result=conditions.probe_codex_capacity(now=1000,client_factory=lambda:ReadOnlyStatus(data))
    assert not result['resolved_task_ids']
    with closing(connect(path)) as conn:assert conditions.pending(conn,task)


def test_agent_cannot_manufacture_provider_recovery(capacity_store):
    token=agent_identity.CURRENT.set({'principal':'apex'})
    try:
        with pytest.raises(PermissionError):conditions.probe_codex_capacity(now=1000,client_factory=lambda:ReadOnlyStatus(status()))
    finally:agent_identity.CURRENT.reset(token)


def test_status_request_holds_no_db_lock_and_cannot_clear_a_new_policy_denial(capacity_store):
    path,task,rid=capacity_store
    class ConcurrentStatus(ReadOnlyStatus):
        def call(self,method,args):
            # This write would fail if the coordinator kept its SQLite write
            # transaction open across the external account request.
            with closing(connect(path)) as conn,conn:
                conditions.record_failure(conn,task,rid,'Provider safety review rejected the changed operation')
            return super().call(method,args)
    result=conditions.probe_codex_capacity(now=1000,client_factory=lambda:ConcurrentStatus(status()))
    assert not result['resolved_task_ids']
    with closing(connect(path)) as conn:
        assert conditions.pending(conn,task)['kind']=='provider_policy'
