import sqlite3
import json

import pytest
from core import hb_tasks
from core.hb_chat_controls import owner_text_decision
from test_peer_turns import flow
from test_hb_chat_controls import control_app


@pytest.mark.parametrize('text',['approved','go ahead','Go ahead with the changes please.',"I'm giving you my approval in chat, go ahead",'you have my permission to execute the changes','approved request #123'])
def test_explicit_owner_authorization_is_recognized(text):
    assert owner_text_decision(text)=='approved'


@pytest.mark.parametrize('text',['do not approve','not approved','if tests pass, go ahead','after review go ahead','APEX said go ahead','"approved"',"'go ahead'",'‘go ahead’','should I approve?','maybe approved','> go ahead','`approved`'])
def test_reference_negation_condition_and_questions_are_not_authority(text):
    assert owner_text_decision(text) is None


def test_real_main_chat_approval_updates_same_record_without_new_task(control_app):
    from frontend.blueprints.chat import chat_bp
    client,task,rid,path,_,_=control_app
    client.application.register_blueprint(chat_bp)
    response=client.post('/api/chat',json={'message':'go ahead','conversation_id':1,'task_id':task['task_id']})
    assert response.status_code==200,response.get_json()
    result=response.get_json();assert result['mode']=='control'
    assert result['control_receipt']['queued']==[rid]
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==1
        row=conn.execute("SELECT payload FROM hb_task_events WHERE kind='request_approval' ORDER BY event_id DESC LIMIT 1").fetchone()
        saved=json.loads(row[0]);assert saved['owner_message_id']==result['operator_message_id']
        assert saved['actor']=='test-owner'
        assert conn.execute('SELECT from_agent,content FROM messages WHERE id=?',(saved['owner_message_id'],)).fetchone()==('user','go ahead')


def test_new_owner_constraint_is_pinned_before_approval(control_app):
    from frontend.blueprints.chat import chat_bp
    client,task,rid,path,_,_=control_app;client.application.register_blueprint(chat_bp)
    text='Go ahead, but only change this test.'
    response=client.post('/api/chat',json={'message':text,'conversation_id':1,'task_id':task['task_id']})
    assert response.status_code==200,response.get_json()
    with sqlite3.connect(path) as conn:
        updated=hb_tasks.get(conn,task['task_id'])
        assert updated['version']>task['version']
        assert any(i.get('content')==text for i in hb_tasks.packet(conn,updated)['instructions'])


def test_reply_quote_cannot_supply_owner_approval(control_app):
    from frontend.blueprints import peer_bridge as bp
    client,task,_,path,_,_=control_app
    body={'conversation_id':1,'task_id':task['task_id'],'approval_request_message_id':task['root_message_id'],'approval_reply_text':'No changes please.'}
    message='[Reply to apex]\nQuoted:\n- apex: "go ahead"\n\nNo changes please.'
    with client.application.test_request_context('/api/chat',method='POST',json=body):
        assert bp.maybe_owner_chat_control(body,message) is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='request_approval'").fetchone()[0]==0
