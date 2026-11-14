from contextlib import closing
import pytest
from core import hb_tasks,hb_task_manager,hb_executions
from test_hb_task_api import assigned
from test_agent_identity import api,enrolled,connect

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.mark.parametrize('role',['owner','viewer'])
@pytest.mark.parametrize('message',['Please fix the isolated example','Can you fix the isolated example?','Help me implement the isolated example'])
def test_inline_endpoint_registers_only_authenticated_owner_and_releases_after_error(assigned,monkeypatch,role,message):
    from frontend.blueprints import chat
    from core import chat_continuity
    client,_,path,rid,task=assigned
    client.application.register_blueprint(chat.chat_bp)
    client.set_cookie('friday_session','isolated-owner-session')
    monkeypatch.setattr(chat,'get_current_user',lambda:{'username':'test-owner','role':role})
    monkeypatch.setattr(chat,'_resolve_identity_or_response',lambda _data:({'effective_user':'test-owner'},None))
    monkeypatch.setattr(chat_continuity,'storage_fault',lambda _:None)
    monkeypatch.setattr(chat,'_log_human_ghost_thought',lambda *a,**k:None)
    def log(conversation,sender,text,**kwargs):
        with closing(connect(path)) as conn,conn:
            conn.execute('INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES (?,?,?,?,?)',
                (conversation,sender,kwargs.get('to_agent'),text,kwargs.get('message_type','chat')))
    monkeypatch.setattr(chat,'log_message',log)
    def stop_before_inference(*args,**kwargs):raise RuntimeError('Test interruption after registration, before inference')
    monkeypatch.setattr(chat,'_fetch_chat_thread_rows',stop_before_inference)
    with closing(connect(path)) as conn,conn:conn.execute("UPDATE hb_peer_work SET state='needs_review' WHERE request_id=?",(rid,))
    response=client.post('/api/chat',json={'message':message,'conversation_id':1,'task_id':task['task_id']})
    assert response.status_code==500,response.get_json()
    with closing(connect(path)) as conn,conn:
        assert hb_task_manager.managed(conn,task)==(role=='owner')
        if role=='owner':
            assert not hb_executions.active(conn,task['task_id'])
            queued=hb_task_manager.tick(conn)
            assert len(queued)==1
            assert hb_tasks.for_request(conn,queued[0])['task_id']==task['task_id']
