import json
import re
from urllib.parse import parse_qs,urlsplit

import pytest

from scripts.hummingbird_apex_live_check import run_check, finish_check


class Harness:
    def __init__(self):
        self.events=[]
        self.memories=[]
        self.acked=[]
        self.posts=[]

    def api(self,agent):
        state=self
        class API:
            def __init__(self):
                self.agent=agent
            def call(self,path,body=None):
                state.events.append((agent,path,body))
                route=urlsplit(path)
                if route.path.endswith('/whoami'):
                    return {'ok':True,'principal':agent}
                if route.path.endswith('/inbox'):
                    return {'messages':[{'id':593,'conversation_id':2833,
                        'recipient':'codex-instructor','delivered_at':None,'body':'test tools and memory'}]}
                if route.path.endswith('/inbox/ack'):
                    state.acked.extend((agent,i) for i in body['ids'])
                    return {'ok':True}
                if '/threads/' in route.path:
                    # Use the real peer serializer so fixture field names cannot drift.
                    import sqlite3
                    from core import peer_bridge
                    with sqlite3.connect(':memory:') as conn:
                        conn.executescript("CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,to_agent TEXT,content TEXT,message_type TEXT,created_at TEXT); CREATE TABLE peer_messages(conversation_id INTEGER,recipient TEXT,body TEXT);")
                        conn.execute("INSERT INTO peer_messages VALUES (2833,'codex-instructor','owner invitation')")
                        for i,row in enumerate(state.posts):
                            conn.execute("INSERT INTO messages VALUES (?,2833,?,'user',?,'response','2026')",(101+i,row[0],row[2]))
                        return {'messages':peer_bridge.thread(conn,{'id':agent,'scopes':{'peer.read'}},2833,30)}
                if route.path.endswith('/audit'):
                    return {'events':[{'principal':'apex','tool':'read_file','status':'succeeded','action_id':'actual-backend-action'}]}
                if route.path.endswith('/memory'):
                    assert agent=='apex'
                    if body is not None:
                        state.memories.append({'id':17,**body})
                        return {'memory_id':17}
                    marker=parse_qs(route.query)['query'][0]
                    return {'memories':[row for row in state.memories if row['content']==marker]}
                if route.path.endswith('/tools'):
                    assert agent=='apex' and body['tool']=='read_file'
                    assert body['arguments']['path']=='.gitignore'
                    return {'ok':True,'action_id':'actual-backend-action','output':'1: # Ignore generated files'}
                raise AssertionError(path)
            def post(self,conversation,text):
                state.posts.append((agent,conversation,text))
                return {'message_id':100+len(state.posts),'handoff':{'queued':[600] if '@apex' in text else []}}
            def progress(self,conversation,status,stage):
                state.events.append((agent,'progress',{'conversation_id':conversation,'status':status,'stage':stage}))
        return API()


def test_actual_model_tool_selection_is_required_before_acknowledging_request(monkeypatch):
    monkeypatch.setattr('scripts.hummingbird_apex_live_check.time.sleep',lambda _:None)
    state=Harness()
    calls=[]
    def model(_name,messages):
        calls.append(messages)
        marker=re.search(r'HB-APEX-CHECK-[0-9a-f]+',' '.join(m['content'] for m in messages)).group()
        if len(calls)==1:
            return json.dumps({'tool_calls':[{'name':'read_file','arguments':{'path':'.gitignore','start':1,'end':10}}],
                               'answer':''}),10
        return json.dumps({'tool_calls':[],'answer':'Read .gitignore. Retrieved memory marker: '+marker}),8
    result=run_check(2833,593,api_factory=state.api,model_call=model)
    assert result['ok'] and len(calls)==2
    assert result['tool_actions']==[{'tool':'read_file','action_id':'actual-backend-action'}]
    assert ('codex-instructor',593) in state.acked and ('apex',600) in state.acked
    assert any(agent=='apex' and '.gitignore' in text for agent,_,text in state.posts)
    assert any('actual-backend-action' in text and 'memory 17' in text for _,_,text in state.posts)
    assert any(path=='progress' and data['status']=='running' for _,path,data in state.events)


def test_a_model_claim_without_a_tool_receipt_is_a_failure_and_keeps_the_request(monkeypatch):
    monkeypatch.setattr('scripts.hummingbird_apex_live_check.time.sleep',lambda _:None)
    state=Harness()
    def model(_name,messages):
        marker=re.search(r'HB-APEX-CHECK-[0-9a-f]+',' '.join(m['content'] for m in messages)).group()
        return json.dumps({'tool_calls':[],'answer':'I checked everything. '+marker}),1
    with pytest.raises(ValueError,match='without a successful read_file receipt'):
        run_check(2833,593,api_factory=state.api,model_call=model)
    assert state.acked==[]
    assert any('did not complete' in text for _,_,text in state.posts)
    assert any(path=='progress' and data['status']=='failed' for _,path,data in state.events)


def test_mismatched_conversation_does_not_start_or_acknowledge_an_agent_task():
    state=Harness()
    with pytest.raises(ValueError,match='mismatched'):
        run_check(9999,593,api_factory=state.api,model_call=lambda *_:pytest.fail('inference must not run'))
    assert not state.posts and not state.acked


def test_resume_verifies_saved_actual_api_messages_memory_and_audit_without_repeating_work():
    state=Harness()
    marker='HB-APEX-CHECK-saved'
    state.memories=[{'id':17,'content':marker}]
    state.posts=[('apex',2833,marker),('codex-instructor',2833,'Read tool actual-backend-action; memory 17 verified')]
    evidence={'conversation_id':2833,'request_id':593,'marker':marker,'memory_id':17,
              'tool_actions':[{'tool':'read_file','action_id':'actual-backend-action'}],
              'apex_message_id':101,'report_message_id':102,'handoff_ids':[600]}
    result=finish_check(2833,593,evidence,api_factory=state.api)
    assert result['ok'] and len(state.memories)==1 and len(state.posts)==2
    assert ('codex-instructor',593) in state.acked
    assert not any(path.endswith('/tools') or (path.endswith('/memory') and data is not None)
                   for _,path,data in state.events)


def test_saved_reply_with_wrong_author_is_not_acknowledged():
    state=Harness()
    marker='HB-APEX-CHECK-saved'
    state.memories=[{'id':17,'content':marker}]
    state.posts=[('codex-instructor',2833,marker),('codex-instructor',2833,'actual-backend-action; memory 17')]
    evidence={'conversation_id':2833,'request_id':593,'marker':marker,'memory_id':17,
              'tool_actions':[{'tool':'read_file','action_id':'actual-backend-action'}],
              'apex_message_id':101,'report_message_id':102}
    with pytest.raises(ValueError,match='could not be verified'):
        finish_check(2833,593,evidence,api_factory=state.api)
    assert state.acked==[]


def test_resume_rejects_failed_backend_audit_even_when_chat_claims_success():
    state=Harness()
    marker='HB-APEX-CHECK-saved'
    state.memories=[{'id':17,'content':marker}]
    state.posts=[('apex',2833,marker),('codex-instructor',2833,'actual-backend-action; memory 17')]
    evidence={'conversation_id':2833,'request_id':593,'marker':marker,'memory_id':17,
              'tool_actions':[{'tool':'read_file','action_id':'actual-backend-action'}],
              'apex_message_id':101,'report_message_id':102}
    original=state.api
    def api(agent):
        client=original(agent)
        request=client.call
        def call(path,body=None):
            if '/audit?' in path:
                return {'events':[{'principal':'apex','action_id':'actual-backend-action',
                                   'tool':'read_file','status':'failed'}]}
            return request(path,body)
        client.call=call
        return client
    with pytest.raises(ValueError,match='audit receipt'):
        finish_check(2833,593,evidence,api_factory=api)
    assert state.acked==[]
