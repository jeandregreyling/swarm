import json
import sqlite3

from core import hb_tasks,peer_bridge as peers,peer_turns
from test_peer_turns import flow,owner
from test_hb_chat_controls import control_app,command


def approval_url(task):
    return '/api/peer/v1/tasks/'+task['task_id']+'/requests/'+str(task['root_message_id'])+'/approval'


def decision(client,task,value,**extra):
    saved=client.get(approval_url(task)).get_json()['request_control']
    return {'decision':value,'message_id':saved['message_id'],'version':saved['version'],
            'revision':saved['revision'],'scope_hash':saved['scope_hash'],
            'command_id':'request-decision-'+value+'-001',**extra}


def test_approval_is_attached_to_actual_request_and_alm(control_app):
    client,task,rid,path,_,_=control_app
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE project_blackboard_notes(note_id TEXT PRIMARY KEY,project_id TEXT,author TEXT,kind TEXT,content TEXT,status TEXT,created_at REAL,updated_at REAL)")
        conn.execute("UPDATE hb_tasks SET project_id='P-TEST',step_id='S-TEST'")
        enriched=hb_tasks.enrich(conn,[{'id':task['root_message_id']}])[0]
        assert enriched['request_control']['attempts'][0]['request_id']==rid
    response=client.post(approval_url(task),json=decision(client,task,'approved'))
    assert response.status_code==200,response.get_json()
    data=response.get_json();assert data['queued']==[rid]
    assert data['request_control']['decision']=='approved'
    assert data['task']['state']!='completed'
    with sqlite3.connect(path) as conn:
        saved=json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE event_id=?",(data['receipt_id'],)).fetchone()[0])
        assert saved['actor']=='test-owner' and saved['result']['queued']==[rid]
        note=json.loads(conn.execute('SELECT content FROM project_blackboard_notes ORDER BY created_at DESC LIMIT 1').fetchone()[0])
        assert note['event_id']==data['receipt_id'] and note['evidence']==saved


def test_review_and_decline_preserve_other_tasks_and_have_real_hold(control_app):
    client,task,rid,path,_,_=control_app
    with sqlite3.connect(path) as conn:
        other_rid=owner(conn);other=hb_tasks.for_request(conn,other_rid)
    for value in ['needs_review','declined']:
        response=client.post(approval_url(task),json=decision(client,task,value))
        assert response.status_code==200,response.get_json()
        with sqlite3.connect(path) as conn:
            assert not peer_turns.ready(conn,rid)
            assert peer_turns.ready(conn,other_rid)
            assert hb_tasks.get(conn,other['task_id'])['state']=='active'
        blocked=client.post('/api/peer/v1/tasks/'+task['task_id']+'/control',json=command(client,task,'on'))
        assert blocked.status_code==403
    approved=client.post(approval_url(task),json=decision(client,task,'approved')).get_json()
    assert approved['queued']==[rid] and approved['task']['state']=='active'


def test_retry_reconciles_reviewed_request_without_duplicate_success(control_app):
    client,task,rid,path,_,principals=control_app
    assert client.post(approval_url(task),json=decision(client,task,'try_again')).status_code==409
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(rid,))
        peers.acknowledge(conn,principals['codex-instructor'],[rid])
    approved=client.post(approval_url(task),json=decision(client,task,'approved')).get_json()
    assert approved['queued']==[] and approved['already_executed']
    retry=decision(client,task,'try_again')
    first=client.post(approval_url(task),json=retry).get_json()
    replay=client.post(approval_url(task),json=retry).get_json()
    assert first['queued']==replay['queued'] and replay['replayed']
    with sqlite3.connect(path) as conn:
        queued=peers.inbox(conn,principals['codex-instructor'],pending_only=True)
        assert len(queued)==1
        packet=json.loads(queued[0]['body'])
        original=json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(packet['read_exact_request']['arguments']['evidence_id'],)).fetchone()[0])
        assert 'Assess the existing file proposal' in original['content']
        assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='completed'


def test_stale_and_replayed_decisions_do_not_overwrite_decline(control_app):
    client,task,rid,path,_,_=control_app
    approved=decision(client,task,'approved')
    assert client.post(approval_url(task),json=approved).status_code==200
    assert client.post(approval_url(task),json=decision(client,task,'declined')).status_code==200
    old=client.post(approval_url(task),json=approved).get_json()
    assert old['request_control']['decision']=='declined' and old['task']['state']=='paused'
    stale={**approved,'command_id':'another-command-00000001'}
    assert client.post(approval_url(task),json=stale).status_code==409


def test_changed_request_requires_fresh_review_and_blocks_old_execution(control_app):
    client,task,rid,path,_,_=control_app
    assert client.post(approval_url(task),json=decision(client,task,'approved')).status_code==200
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE messages SET content=? WHERE id=?',('Changed proposed scope',task['root_message_id']))
    saved=client.get(approval_url(task)).get_json()['request_control']
    assert saved['revised'] and saved['decision']=='needs_review'
    with sqlite3.connect(path) as conn:assert not peer_turns.ready(conn,rid)


def test_approval_respects_owner_off_and_reconnect_restores_decision(control_app):
    client,task,rid,path,_,_=control_app
    control='/api/peer/v1/tasks/'+task['task_id']+'/control'
    assert client.post(control,json=command(client,task,'off')).status_code==200
    saved=client.post(approval_url(task),json=decision(client,task,'approved')).get_json()
    assert saved['held_by_continuation'] and saved['task']['state']=='paused'
    assert client.get(approval_url(task)).get_json()['request_control']['decision']=='approved'
    resumed=client.post(control,json=command(client,task,'on')).get_json()
    assert resumed['queued']==[rid]


def test_approval_requires_actual_owner_and_linked_bubble(control_app):
    client,task,_,_,current,_=control_app
    data=decision(client,task,'approved')
    assert client.post(approval_url(task),json={**data,'message_id':99999}).status_code==403
    assert client.post(approval_url(task),json=data,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.post(approval_url(task),json={**data,'actor':'owner'}).status_code==400
    current[0]={'username':'apex','role':'viewer'}
    assert client.post(approval_url(task),json=data).status_code==403
