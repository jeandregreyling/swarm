import hashlib
import json

import pytest
from core import hb_tasks,hb_owner_sessions as sessions,hb_provider_conditions
from core.peer_bridge import post
from test_hb_owner_sessions import owner_store,grant
from test_peer_turns import flow


@pytest.fixture
def reviewed(owner_store):
    conn,principals=owner_store;created=grant(owner_store);task=hb_tasks.get(conn,created['task_id'])
    (sessions.ROOT/'core').mkdir();source=sessions.ROOT/'core/verified.py';source.write_text('value=1\n')
    mutation=hb_tasks.event(conn,task,'owner-host','mutation',{'after_sha256':{'core/verified.py':hashlib.sha256(source.read_bytes()).hexdigest()}})
    changed=conn.execute('SELECT created_at FROM hb_task_events WHERE event_id=?',(mutation,)).fetchone()[0]
    conn.execute('CREATE TABLE project_test_cases(step_id TEXT,status TEXT)')
    conn.execute('CREATE TABLE test_runs(step_id TEXT,status TEXT,started_at REAL)')
    conn.execute('INSERT INTO project_test_cases VALUES (?,\'passed\')',(task['step_id'],))
    conn.execute('INSERT INTO test_runs VALUES (?,\'pass\',?)',(task['step_id'],changed))
    reply=post(conn,principals['apex'],1,'Actual successful APEX verification',reply_to_request_id=created['queued'][0],route_reply=False)
    hb_provider_conditions.record_failure(conn,task,created['queued'][0],'External provider usageLimitExceeded')
    review=hb_tasks.event(conn,task,'owner-host','independent_local_review',{'actual_result':{'model':'fred-cpu:24b','need_online':False,'advice':'The supplied implementation and actual checks are ready for instructor acceptance.'}})
    args={'task_id':task['task_id'],'review_event_id':review,'evidence_message_ids':[reply['message_id']],
        'assessment':'Native instructor verified the real local review and fresh guarded tests for this component; parent project remains open.'}
    return conn,task,args,source


def test_verified_override_records_actual_host_identity_and_preserves_provider_condition(reviewed):
    conn,task,args,_=reviewed
    result=sessions.accept_instructor_override(conn,sessions.native_owner_authority(),**args)
    assert result['state']=='completed'
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()[0]=='done'
    assert conn.execute('SELECT resolved_event_id FROM hb_provider_conditions').fetchone()[0] is None
    saved=conn.execute('SELECT agent,payload FROM hb_task_events WHERE event_id=?',(result['receipt_id'],)).fetchone()
    assert saved[0]=='owner-host' and json.loads(saved[1])['mode']=='native_instructor_override'


@pytest.mark.parametrize('failure',['source_changed','failed_case','provider_policy','owner_hold','review_not_local'])
def test_override_cannot_skip_verification_or_owner_and_provider_boundaries(reviewed,failure):
    conn,task,args,source=reviewed
    if failure=='source_changed':source.write_text('value=2\n')
    elif failure=='failed_case':conn.execute("UPDATE project_test_cases SET status='failed'")
    elif failure=='provider_policy':conn.execute("UPDATE hb_provider_conditions SET kind='provider_policy'")
    elif failure=='owner_hold':conn.execute("UPDATE hb_tasks SET state='paused'")
    else:conn.execute("UPDATE hb_task_events SET payload='{}' WHERE event_id=?",(args['review_event_id'],))
    with pytest.raises((PermissionError,ValueError)):
        sessions.accept_instructor_override(conn,sessions.native_owner_authority(),**args)
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()[0]=='todo'
