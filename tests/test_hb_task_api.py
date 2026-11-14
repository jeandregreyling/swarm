from contextlib import closing
import json
import pytest

from core import hb_tasks, peer_bridge as peers
from test_agent_identity import api, enrolled, headers, connect


@pytest.fixture
def assigned(api,enrolled,monkeypatch):
    from core.knowledge import projects, test_runs
    monkeypatch.setattr(projects,'_SCHEMA_READY',False)
    monkeypatch.setattr(test_runs,'_SCHEMA_READY',False)
    projects._ensure_schema()
    client,root=api;path,*_=enrolled
    with closing(connect(path)) as conn:
        conn.executescript('''CREATE TABLE conversations(id INTEGER PRIMARY KEY,title TEXT);
          CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,
          to_agent TEXT,content TEXT,message_type TEXT,tokens_used INTEGER DEFAULT 0,created_at TEXT);
          INSERT INTO conversations VALUES(1,'Assigned task');
          INSERT INTO messages(id,conversation_id,from_agent,content) VALUES(1,1,'user','Check the assigned source safely');''')
        peers.ensure_schema(conn)
        rid=peers.enqueue(conn,1,1,'Check the assigned source',['apex'],sender='owner')[0]
        task=hb_tasks.for_request(conn,rid)
        conn.commit()
    return client,root,path,rid,task


def invoke(assigned,tool,args):
    client,_,_,rid,_=assigned
    return client.post('/api/agent/v1/tools',headers=headers('apex'),json={
      'tool':tool,'arguments':args,'context':{'request_id':rid,'model':'actual-local-model'}})


def test_new_tools_are_attached_only_with_existing_permissions(assigned):
    client,*_=assigned
    apex=client.get('/api/agent/v1/whoami',headers=headers('apex')).get_json()['tools']
    other=client.get('/api/agent/v1/whoami',headers=headers('ten')).get_json()['tools']
    assert {'run_tests','studio_note','task_context','task_memory'}<=set(apex)
    assert not {'run_tests','studio_note','reference_import'} & set(other)
    reviewer=client.get('/api/agent/v1/whoami',headers=headers('codex-instructor')).get_json()['tools']
    assert {'task_plan','runtime_reload'}<=set(reviewer)
    assert 'runtime_reload' not in apex


def test_executor_checkpoint_saves_real_next_action_without_replacing_goal(assigned):
    client,root,path,rid,task=assigned
    text='Inspect hello.py, apply one exact approved correction, then run the assigned regression case.'
    response=invoke(assigned,'task_plan',{'next_action':text})
    assert response.status_code==200,response.get_json()
    result=json.loads(response.get_json()['output'])
    with closing(connect(path)) as conn:
        assert hb_tasks.get(conn,task['task_id'])['objective']==task['objective']
        assert conn.execute('SELECT plan_event_id FROM hb_task_manager').fetchone()[0]==result['plan_event_id']
        assert json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(result['plan_event_id'],)).fetchone()[0])['next_action']==text
        assert conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==1


def test_rejected_source_proposal_records_diagnostic_without_an_effect(assigned):
    _,root,path,rid,task=assigned
    response=invoke(assigned,'propose_patch',{'file_path':'hello.py','exact_old_text':'hello\\n','new_text':'changed\n'})
    assert response.status_code==400,response.get_json()
    assert (root/'hello.py').read_text()=='hello\n'
    with closing(connect(path)) as conn:
        row=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND request_id=? AND kind='tool_failure'",(task['task_id'],rid)).fetchone()
        data=json.loads(row[0])
        assert data['arguments_preview']['literal_backslash_n'] is True
        assert data['tool']=='propose_patch' and '0 locations' in data['error']
        assert conn.execute('SELECT COUNT(*) FROM hb_task_operations').fetchone()[0]==0


def test_running_attempt_cannot_replace_a_newer_instructor_plan(assigned):
    from core import hb_task_manager as manager
    client,_,path,rid,task=assigned
    with closing(connect(path)) as conn,conn:
        manager.register(conn,task,request_id=rid)
        base=conn.execute('SELECT plan_event_id FROM hb_task_manager').fetchone()[0]
        conn.execute('UPDATE peer_messages SET body=? WHERE id=?',(json.dumps({'task_type':'hb_managed_continuation','plan':{'arguments':{'evidence_id':base}}}),rid))
        newer=hb_tasks.event(conn,task,'owner-host','task_plan',{'next_action':'Fix the actual test failure before adding another feature.'})
        conn.execute('UPDATE hb_task_manager SET plan_event_id=?',(newer,))
    action='Add the next feature after reconciling the current test correction and its evidence.'
    stale=invoke(assigned,'task_plan',{'next_action':action})
    assert stale.status_code==400,stale.get_json()
    assert str(newer) in stale.get_json()['error']
    with closing(connect(path)) as conn:
        assert conn.execute('SELECT plan_event_id FROM hb_task_manager').fetchone()[0]==newer
    saved=invoke(assigned,'task_plan',{'next_action':action,'base_plan_event_id':newer})
    assert saved.status_code==200,saved.get_json()
    # A second checkpoint in the same attempt can build on its own saved plan.
    assert invoke(assigned,'task_plan',{'next_action':action}).status_code==200
    # Explicit stale revisions never become valid through that convenience.
    assert invoke(assigned,'task_plan',{'next_action':action,'base_plan_event_id':newer}).status_code==400


def test_instructor_plan_resumes_local_work_without_clearing_online_capacity(assigned):
    from core import hb_task_manager as manager,hb_provider_conditions as conditions
    client,_,path,_,task=assigned
    with closing(connect(path)) as conn,conn:
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Review current task')").lastrowid
        hb_tasks.bind(conn,1,mid,task_id=task['task_id'],kind='checkpoint')
        rid=peers.enqueue(conn,1,mid,'Review current task',['codex-instructor'],sender='hummingbird')[0]
        manager.register(conn,task,request_id=rid)
        conditions.record_failure(conn,task,rid,'quota exceeded')
        conn.execute("UPDATE hb_peer_work SET state='failed'")
        conn.execute("UPDATE hb_task_manager SET phase='review',recovery_count=8")
        # This native instructor has its own fresh scoped invitation; it does
        # not reuse the failed provider turn or call that provider again.
        rid=peers.enqueue(conn,1,mid,'Native instructor supplies a concrete plan',['codex-instructor'],sender='hummingbird')[0]
    result=client.post('/api/agent/v1/tools',headers=headers('codex-instructor'),json={
        'tool':'task_plan','arguments':{'next_action':'Implement one isolated approved correction in hello.py and run its existing regression.'},
        'context':{'request_id':rid,'model':'native-instructor'}})
    assert result.status_code==200,result.get_json()
    with closing(connect(path)) as conn,conn:
        assert tuple(conn.execute('SELECT phase,recovery_count FROM hb_task_manager').fetchone())==('execute',0)
        assert conditions.pending(conn,task,agent='codex-instructor')['kind']=='provider_capacity'
        conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(rid,))
        queued=manager.tick(conn)
        assert len(queued)==1
        assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(queued[0],)).fetchone()[0]=='apex'
        assert conditions.pending(conn,task,agent='codex-instructor')['kind']=='provider_capacity'
        assert hb_tasks.get(conn,task['task_id'])['objective']==task['objective']


def test_independent_acceptance_automatically_queues_only_authorized_runtime_activation(assigned,monkeypatch,tmp_path):
    from core import hb_owner_sessions as sessions,hb_runtime_reload,apex_test_runner
    client,root,path,_,original=assigned
    monkeypatch.setattr(sessions,'ROOT',root)
    monkeypatch.setattr(sessions,'KEY_FILE',tmp_path/'private-owner-key/key')
    monkeypatch.setattr(hb_runtime_reload,'ROOT',root)
    (root/'core').mkdir()
    with closing(connect(path)) as conn,conn:
        created=sessions.grant(conn,sessions.native_owner_authority(),conversation_id=1,project_id=original['project_id'],
            objective='Implement this approved isolated backend component.',evidence_text='Actual fixture owner approves this exact component and fixed runtime activation.',reason='Owner-approved runtime activation after independent review.')
        sessions.authorize_runtime_reload(conn,sessions.native_owner_authority(),created['task_id'],'Actual fixture owner permits only the fixed HB service after independent acceptance.')
    context={'request_id':created['queued'][0],'model':'actual-local-model'}
    write=client.post('/api/agent/v1/tools',headers=headers('apex'),json={'tool':'propose_write_file',
        'arguments':{'path':'core/runtime_feature.py','content':'value=1\n'},'context':context})
    assert write.status_code==200,write.get_json()
    monkeypatch.setattr(apex_test_runner,'run_tests',lambda _:{'status':'passed','exit_code':0,'summary':'1 passed','output_tail':'1 passed'})
    tested=client.post('/api/agent/v1/tools',headers=headers('apex'),json={'tool':'run_tests',
        'arguments':{'tests':['tests/test_hb_task_api.py']},'context':context})
    assert tested.status_code==200,tested.get_json()
    reply=client.post('/api/peer/v1/messages',headers=headers('apex'),json={'conversation_id':1,
        'text':'Actual task reply with saved write and guarded verification','reply_to_request_id':created['queued'][0],'route_reply':False}).get_json()
    with closing(connect(path)) as conn,conn:
        task=hb_tasks.get(conn,created['task_id'])
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Independently review the isolated component')").lastrowid
        hb_tasks.bind(conn,1,mid,task_id=task['task_id'],kind='checkpoint')
        reviewer=peers.enqueue(conn,1,mid,'Review source and verification',['codex-instructor'],sender='hummingbird')[0]
    accepted=client.post('/api/agent/v1/tools',headers=headers('codex-instructor'),json={'tool':'studio_accept',
        'arguments':{'evidence_message_ids':[reply['message_id']]},'context':{'request_id':reviewer,'model':'actual-instructor'}})
    assert accepted.status_code==200,accepted.get_json()
    result=json.loads(accepted.get_json()['output'])
    assert result['state']=='completed' and result['runtime_activation']['status']=='queued'
    with closing(connect(path)) as conn:
        row=conn.execute('SELECT state,request_id FROM hb_runtime_reloads WHERE task_id=?',(task['task_id'],)).fetchone()
        assert tuple(row)==('queued',reviewer)
        assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?',(original['task_id'],)).fetchone()[0]=='active'


def test_reply_key_is_request_scoped_and_cannot_be_reused_for_different_content(assigned):
    client,_,path,rid,_=assigned
    data={'conversation_id':1,'text':'Saved answer fragment','reply_to_request_id':rid,
        'route_reply':False,'client_message_id':'reply-unique-key-00000001'}
    one=client.post('/api/peer/v1/messages',headers=headers('apex'),json=data)
    two=client.post('/api/peer/v1/messages',headers=headers('apex'),json=data)
    assert one.status_code==201 and two.status_code==201
    assert one.get_json()['message_id']==two.get_json()['message_id'] and two.get_json()['replayed']
    assert client.post('/api/peer/v1/messages',headers=headers('apex'),json={**data,'text':'Changed fragment'}).status_code==409
    assert client.post('/api/peer/v1/messages',headers=headers('ten'),json=data).status_code==403
    with closing(connect(path)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_peer_replies WHERE request_id=?',(rid,)).fetchone()[0]==1


def test_source_write_is_idempotent_across_api_calls_and_turn_receipts(assigned):
    client,root,path,rid,task=assigned
    args={'file_path':'hello.py','exact_old_text':'hello','new_text':'hello\n# exactly once'}
    first=invoke(assigned,'propose_patch',args)
    second=invoke(assigned,'propose_patch',args)
    assert first.status_code==200,first.get_json()
    assert second.status_code==200,second.get_json()
    assert second.get_json()['receipt']['replayed']
    assert first.get_json()['receipt']['operation_id']==second.get_json()['receipt']['operation_id']
    assert (root/'hello.py').read_text().count('# exactly once')==1
    with closing(connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)).fetchone()[0]==1
        assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='mutation_replayed'",(task['task_id'],)).fetchone()[0]==1


def test_invalid_python_and_full_file_fragments_never_replace_the_module(assigned):
    client,root,path,rid,task=assigned
    source="def keep_worker():\n    return 'working'\n"
    (root/'hello.py').write_text(source)
    broken=invoke(assigned,'propose_write_file',{'path':'hello.py','content':'    invalid fragment\n'})
    assert broken.status_code==400
    fragment=invoke(assigned,'propose_write_file',{'path':'hello.py','content':'value=1\n'})
    assert fragment.status_code==400
    assert (root/'hello.py').read_text()==source


def test_studio_note_is_bound_to_actual_task_not_model_selected_project(assigned):
    client,root,path,rid,task=assigned
    response=invoke(assigned,'studio_note',{'content':'Observed one scoped tool result; no completion is claimed.'})
    assert response.status_code==200,response.get_json()
    result=json.loads(response.get_json()['output'])
    assert result['project_id']==task['project_id'] and result['step_id']==task['step_id']
    bad=invoke(assigned,'studio_note',{'content':'forged','project_id':'other'})
    assert bad.status_code==400
    assert client.post('/api/agent/v1/tools',headers=headers('apex'),json={'tool':'studio_note','arguments':{'content':'no invitation'}}).status_code==403


def test_guarded_tests_are_recorded_against_current_task(assigned,monkeypatch):
    from core import apex_test_runner
    monkeypatch.setattr(apex_test_runner,'run_tests',lambda args:{'status':'passed','exit_code':0,'summary':'1 passed','output_tail':'1 passed'})
    response=invoke(assigned,'run_tests',{'tests':['tests/test_peer_bridge.py']})
    assert response.status_code==200,response.get_json()
    result=json.loads(response.get_json()['output'])
    assert result['status']=='passed' and result['alm_run_id']
    with closing(connect(assigned[2])) as conn:
        row=conn.execute('SELECT project_id,step_id,status FROM test_runs WHERE run_id=?',(result['alm_run_id'],)).fetchone()
        assert row['project_id']==assigned[4]['project_id'] and row['step_id']==assigned[4]['step_id'] and row['status']=='pass'


def test_invalid_read_details_reach_client_and_do_not_turn_into_permission_claim(assigned):
    response=invoke(assigned,'read_file',{'path':'hello.py','start':5,'end':2})  # end before start is invalid (over-long ranges are now clipped)
    assert response.status_code==400
    data=response.get_json()
    assert data['category']=='invalid_arguments' and data['error']


def test_context_and_memory_are_task_scoped(assigned):
    assert invoke(assigned,'task_context',{}).status_code==200
    response=invoke(assigned,'task_memory',{})
    assert response.status_code==200 and json.loads(response.get_json()['output'])['task_id']==assigned[4]['task_id']
    assert invoke(assigned,'task_memory',{'agent':'ten'}).status_code==400


def test_task_evidence_cannot_read_another_tasks_event(assigned):
    from core import hb_tasks
    with closing(connect(assigned[2])) as conn:
        conn.execute("INSERT INTO messages(id,conversation_id,from_agent,content) VALUES(2,1,'user','Another task')")
        other=hb_tasks.bind(conn,1,2)
        event=hb_tasks.event(conn,other,'apex','private-task-result',{'receipt':'other-task'})
        conn.commit()
    response=invoke(assigned,'task_evidence',{'evidence_id':event})
    assert response.status_code==403


def test_executor_cannot_approve_its_own_studio_completion(assigned):
    assert invoke(assigned,'studio_accept',{'evidence_message_ids':[1]}).status_code==403
    assert invoke(assigned,'studio_status',{'status':'done'}).status_code==400


def test_failed_tool_arguments_and_validation_are_available_as_task_evidence(assigned):
    response=invoke(assigned,'read_file',{'path':'hello.py','start':5,'end':2})  # end before start is invalid (over-long ranges are now clipped)
    assert response.status_code==400
    with closing(connect(assigned[2])) as conn:
        row=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='tool_failure' ORDER BY event_id DESC LIMIT 1",(assigned[4]['task_id'],)).fetchone()
    data=json.loads(row[0])
    assert data['tool']=='read_file' and data['category']=='ValueError'
    assert data['arguments']['end']=='2' and data['error']


def test_task_amendment_requires_context_refresh_before_new_source_mutation(assigned):
    client,root,path,rid,task=assigned
    with closing(connect(path)) as conn:
        conn.execute("INSERT INTO messages(id,conversation_id,from_agent,content) VALUES(2,1,'user','Preserve the original source until reviewed')")
        hb_tasks.bind(conn,1,2,task_id=task['task_id'])
        conn.commit()
    patch={'file_path':'hello.py','exact_old_text':'hello','new_text':'changed'}
    response=invoke(assigned,'propose_patch',patch)
    assert response.status_code==409 and (root/'hello.py').read_text()=='hello\n'
    context=invoke(assigned,'task_context',{})
    assert context.status_code==200
    assert 'Preserve the original source' in context.get_json()['output']


def test_memory_saved_by_a_task_is_automatically_linked_to_that_task(assigned):
    response=invoke(assigned,'memory_save',{'subject':'Verified scoped lesson','content':'Use the real receipt and assigned Studio step.'})
    assert response.status_code==200,response.get_json()
    from core import agent_identity
    with closing(agent_identity._memory('apex')) as memory:
        row=memory.execute("SELECT ticket_ref FROM memories WHERE subject='Verified scoped lesson'").fetchone()
    assert row[0]==assigned[4]['task_id']


def test_nonexistent_source_is_not_misreported_as_permission_denial(assigned):
    response=invoke(assigned,'read_file',{'path':'scripts/config.py'})
    assert response.status_code==404
    assert response.get_json()['category']=='not_found'
    assert 'resolve the actual import' in response.get_json()['error']


def test_gemini_status_uses_backend_evidence_without_a_new_generation(assigned,monkeypatch):
    from scripts import hummingbird_gemini_peer
    monkeypatch.setattr(hummingbird_gemini_peer,'_generate',lambda *_:pytest.fail('Unexpected Google request'))
    response=invoke(assigned,'gemini_status',{})
    assert response.status_code==200,response.get_json()
    data=json.loads(response.get_json()['output'])
    assert data['provider']=='Google' and 'credential_configured' in data
    assert 'token' not in data and 'api_key' not in data

pytestmark = pytest.mark.usefixtures("owner_turned_continuation_on", "online_providers_authorised", "owner_defined_done")
