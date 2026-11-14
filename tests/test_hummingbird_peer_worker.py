from pathlib import Path
import sqlite3
from urllib.parse import urlsplit,parse_qs
from core import agent_identity
from scripts import hummingbird_peer_worker as worker


class API:
    def __init__(self):self.events=[];self.messages=[];self.acked=[]
    def call(self,path,body=None):
        self.events.append((path,body));parsed=urlsplit(path)
        if path.endswith('/whoami'):return {'principal':'codex-instructor'}
        if parsed.path.endswith('/inbox'):
            after=int(parse_qs(parsed.query).get('after',['0'])[0])
            return {'messages':[] if after>=42 or self.acked else [{'id':42,'recipient':'codex-instructor','sender':'ghost','conversation_id':2833,'delivered_at':None,'body':'@codex inspect source'}]}
        if parsed.path.endswith('/threads/2833'):return {'messages':self.messages}
        if parsed.path.endswith('/tools'):
            if body is None:return {'tools':['read_file']}
            assert body['context']=={'request_id':42,'model':'actual-codex'}
            return {'output':'actual source','action_id':'receipt-1'}
        if parsed.path.endswith('/inbox/ack'):self.acked.extend(body['ids']);return {'ok':True}
        if parsed.path.endswith('/progress'):return {'ok':True}
        raise AssertionError(path)
    def post(self,conversation,text,**routing):
        self.events.append(('peer.reply',routing))
        row={'id':100+len(self.messages),'sender':'codex-instructor','content':text}
        self.messages.append(row);return {'message_id':row['id']}


class Runtime:
    model='actual-codex'
    def call(self,*_):return {'account':{'type':'chatgpt'}}
    def turn(self,text,**kwargs):
        assert kwargs['handler']('hb_read_file',{'path':'README.md'})['action_id']=='receipt-1'
        return {'thread_id':'persisted-thread','answer':'Verified with receipt-1','model':self.model}
    def close(self):pass


def test_instructor_planning_and_fixed_reload_have_complete_runtime_tool_schemas():
    tools=worker.tools_for(['task_plan','runtime_reload'])
    assert tools[0]['name']=='hb_task_plan'
    assert tools[0]['inputSchema']['required']==['next_action']
    assert tools[0]['inputSchema']['properties']['next_action']['maxLength']==3500
    assert tools[1]['name']=='hb_runtime_reload' and tools[1]['inputSchema']['properties']=={}


def test_local_checkpoint_uses_its_authenticated_task_handler(monkeypatch):
    import json
    from core.apex_tools import run_apex_tools
    messages=iter([
        {'tool_calls':[{'name':'task_plan','arguments':{'next_action':'Inspect core/example.py and apply the next exact approved edit; verify its case.'}}],'answer':''},
        {'tool_calls':[],'answer':'Checkpoint saved; implementation remains unfinished.'}])
    calls=[]
    def model(*_):return json.dumps(next(messages)),1
    def control(name,args):calls.append((name,args));return {'state':'saved','plan_event_id':42}
    answer,_,receipts=run_apex_tools(model,[{'role':'user','content':'Continue this existing task.'}],lambda:True,lambda _:None,studio_handler=control)
    assert calls[0][0]=='task_plan' and receipts[0]['status']=='succeeded'
    assert 'unfinished' in answer


def test_explicit_codex_request_gets_an_authenticated_saved_reply_and_ack(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    api=API()
    worker.serve('codex-instructor',once=True,api_factory=lambda _:api,runtime_factory=Runtime)
    assert api.acked==[42] and api.messages[0]['content']=='Verified with receipt-1'
    with sqlite3.connect(agent_identity.STATE/'codex-instructor/hb-worker.sqlite') as c:
        assert c.execute('SELECT state FROM jobs').fetchone()[0]=='completed'
        assert c.execute('SELECT thread_id FROM task_sessions').fetchone()[0]=='persisted-thread'
    worker.serve('codex-instructor',once=True,api_factory=lambda _:api,runtime_factory=lambda:1/0)
    assert len(api.messages)==1
    assert any(path.endswith('/progress') and body['request_id']==42 for path,body in api.events)


def test_failed_codex_turn_remains_unacknowledged_and_is_not_silently_retried(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    class Broken(Runtime):
        def turn(self,*_a,**_k):raise RuntimeError('provider unavailable')
    api=API()
    worker.serve('codex-instructor',once=True,api_factory=lambda _:api,runtime_factory=Broken)
    assert api.acked==[] and 'provider unavailable' in api.messages[0]['content']
    worker.serve('codex-instructor',once=True,api_factory=lambda _:api,runtime_factory=lambda:1/0)
    assert len(api.messages)==1


def test_activation_cutover_leaves_stale_requests_unexecuted(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    api=API()
    worker.serve('codex-instructor',once=True,after_id=42,
                 api_factory=lambda _:api,runtime_factory=lambda:1/0)
    assert api.messages==[] and api.acked==[]


def test_local_worker_gateway_closes_tools_after_repeated_reads(monkeypatch):
    import json
    from contextlib import nullcontext
    from core import apex_context, apex_routing, llm
    from core.apex_tools import TURN_FORMAT, response_format_for_turn

    monkeypatch.setattr(apex_routing, 'choose_local_model', lambda _: apex_routing.LocalRoute('test-local', 'general', 16384, 'test'))
    monkeypatch.setattr(agent_identity, 'execution', lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(apex_context, 'prepare_context', lambda messages: messages)
    monkeypatch.setattr(apex_context, 'budget_receipts', lambda _messages, batch: batch)
    monkeypatch.setattr(apex_context, 'generation_budget', lambda _messages: 1024)
    formats, tools_called = [], []

    def gateway(_model, _messages, **kwargs):
        schema = kwargs['response_format']['json_schema']['schema']
        formats.append(schema)
        if len(formats) <= 3:
            variants = schema['oneOf'][0]['properties']['tool_calls']['items']['oneOf']
            assert [v['properties']['name']['const'] for v in variants] == ['archive_status']
            return json.dumps({'tool_calls': [{'name': 'archive_status', 'arguments': {}}], 'answer': ''}), 1
        assert schema['properties']['tool_calls']['maxItems'] == 0
        return json.dumps({'tool_calls': [], 'answer': 'Downloads are paused; row citations were not tested.'}), 1

    class LocalAPI:
        def call(self, path, body):
            if path.endswith('/progress'):
                return {'ok': True}
            assert path.endswith('/tools')
            tools_called.append(body['tool'])
            return {'output': json.dumps({'downloads_paused': True})}

    monkeypatch.setattr(llm, 'chat_via_gateway', gateway)
    result = worker.local_turn(LocalAPI(), {'id': 42, 'body': 'Inspect archive state. Keep downloads paused.',
                                          'conversation_id': 2834}, [], ['archive_status'])
    assert result['answer'] == 'Downloads are paused; row citations were not tested.'
    assert len(formats) == 4 and tools_called == ['archive_status']
    assert response_format_for_turn() is TURN_FORMAT


def test_hb_decision_generation_has_a_strict_schema_and_no_operational_tools(monkeypatch):
    import json
    from contextlib import nullcontext
    from core import apex_context,apex_routing,llm
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda _:apex_routing.LocalRoute('local-decision','general',16384,'test'))
    monkeypatch.setattr(agent_identity,'execution',lambda *_a,**_k:nullcontext())
    monkeypatch.setattr(apex_context,'prepare_context',lambda messages:messages)
    monkeypatch.setattr(apex_context,'generation_budget',lambda _:2048)
    expected={'action':'blocked','reason':'The provider failed; report the actual failure.',
              'next_task':'','evidence_message_ids':[100]}
    def gateway(model,messages,**kwargs):
        assert model=='local-decision' and 'tools' not in kwargs
        schema=kwargs['response_format']['json_schema']['schema']
        assert schema['properties']['action']['enum']==['finish','blocked','continue']
        assert kwargs['options']['num_predict']<=1536
        assert 'No tools run' in messages[0]['content']
        return json.dumps(expected),5
    monkeypatch.setattr(llm,'chat_via_gateway',gateway)
    api=API()
    result=worker.decision_turn(api,{'id':42,'conversation_id':2833,'body':'HB round decision required'},
        [{'id':100,'sender':'gemini-advisor','message_type':'response','content':'Provider HTTP 503'}])
    assert result['decision']==expected and result['receipts']==[]
    assert all(not (path.endswith('/tools') and body) for path,body in api.events)


def test_task_codex_defers_dispatch_until_release(tmp_path,monkeypatch):
    import json
    import pytest
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    trace=[]
    class TaskAPI(API):
        def call(self,path,body=None):
            parsed=urlsplit(path)
            if parsed.path.endswith('/execution'):
                trace.append(body['action'])
                if body['action']=='claim':return {'execution_id':'execution-42'}
                assert body['execution_id']=='execution-42' and body['state']=='completed'
                return {'ok':True}
            if parsed.path.endswith('/memory'):return {'memories':[]}
            if parsed.path.endswith('/tools'):
                if body is None:return {'tools': ['apex_dispatch', 'task_plan']}
                assert body['tool'] == 'task_plan', body
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}
                assert body['tool'] == 'task_plan', body
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}, body
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}, body['context']
                assert body['context']['request_id'] == 42
                assert body['context']['model'] == 'actual-codex'
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}
                assert body['tool'] == 'task_plan'
                assert body['context'] == {'request_id': 42, 'model': 'actual-codex'}

                # Submit the complete exact replacement
                assert body == {'tool': 'task_evidence', 'arguments': {'evidence_id': 19464, 'offset': 0}}
                assert decoded_body['recent_source_files'] == ['tests/test_hummingbird_peer_worker.py']
                assert decoded_body['evidence_ids'] == [19470, 19469, 19454, 19410, 19409, 19407]
                assert decoded_body['successful_apex_reply_message_ids'] == [11930, 11924, 11908]
                assert decoded_body['next_action_is_excerpt'] == True
                # Decode the JSON object
                decoded_body = json.loads(body)
                assert decoded_body['tool'] == 'task_plan'
                assert decoded_body['context'] == {'request_id': 42, 'model': 'actual-codex'}
                assert decoded_body['next_action'] == {'tool': 'task_evidence', 'arguments': {'evidence_id': 19464, 'offset': 0}}
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    expected={'action':'finish','reason':'The reviewed results were reported.','next_task':'','evidence_message_ids':[99]}
    class DecisionAPI(API):
        def call(self,path,body=None):
            if path.endswith('/whoami'):return {'principal':'apex'}
            result=super().call(path,body)
            if path.split('?')[0].endswith('/inbox'):
                for row in result['messages']:
                    row['recipient']='apex';row['routing']={'kind':'decision'}
            return result
        def post(self,conversation,text,**routing):
            result=super().post(conversation,text,**routing)
            self.messages[-1]['sender']='apex'
            return result
    api=DecisionAPI()
    monkeypatch.setattr(worker,'decision_turn',lambda *_:{'answer':'APEX decision: finish.',
        'decision':expected,'model':'local-decision','category':'peer_decision','tokens':5,'receipts':[]})
    monkeypatch.setattr(worker,'local_turn',lambda *_:1/0)
    worker.serve('apex',once=True,api_factory=lambda _:api,runtime_factory=lambda:1/0)
    routed=next(body for path,body in api.events if path=='peer.reply')
    assert routed=={'reply_to_request_id':42,'route_reply':True,'decision':expected}
    assert api.acked==[42]


def test_local_worker_attaches_guarded_test_handler_and_uses_actual_receipt(monkeypatch):
    import json
    from contextlib import nullcontext
    from core import apex_context,apex_routing,llm
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda _:apex_routing.LocalRoute('test-local','general',16384,'test'))
    monkeypatch.setattr(agent_identity,'execution',lambda *_a,**_k:nullcontext())
    monkeypatch.setattr(apex_context,'prepare_context',lambda messages:messages)
    monkeypatch.setattr(apex_context,'budget_receipts',lambda _messages,batch:batch)
    monkeypatch.setattr(apex_context,'generation_budget',lambda _:1024)
    calls=[]
    class RemoteAPI:
        def call(self,path,body):
            if path.endswith('/tools'):
                calls.append(body['tool'])
                return {'output':json.dumps({'status':'passed','verdict':'PASS: 1 passed','alm_run_id':'actual-test-run'})}
            return {'ok':True}
    generated=[]
    def gateway(*_args,**_kwargs):
        generated.append(1)
        if len(generated)==1:return json.dumps({'tool_calls':[{'name':'run_tests','arguments':{'tests':['tests/test_peer_bridge.py']}}],'answer':''}),1
        return json.dumps({'tool_calls':[],'answer':'PASS: 1 passed; actual-test-run'}),1
    monkeypatch.setattr(llm,'chat_via_gateway',gateway)
    result=worker.local_turn(RemoteAPI(),{'id':9,'conversation_id':1,'body':'Run the scoped tests'},[],['run_tests'])
    assert calls==['run_tests']
    assert result['receipts'][0]['status']=='succeeded'
    assert 'actual-test-run' in result['answer']


def test_patch_only_invitation_uses_authenticated_proposal_handler(monkeypatch):
    import json
    from contextlib import nullcontext
    from core import apex_context,apex_routing,llm
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda _:apex_routing.LocalRoute('test-local','general',16384,'test'))
    monkeypatch.setattr(agent_identity,'execution',lambda *_a,**_k:nullcontext())
    monkeypatch.setattr(apex_context,'prepare_context',lambda messages:messages)
    monkeypatch.setattr(apex_context,'budget_receipts',lambda _messages,batch:batch)
    monkeypatch.setattr(apex_context,'generation_budget',lambda _:1024)
    calls=[];generated=[]
    class RemoteAPI:
        def call(self,path,body):
            if path.endswith('/tools'):
                assert body['tool']=='propose_patch'
                assert body['context']=={'request_id':9,'model':'test-local'}
                calls.append(body)
                return {'receipt':{'status':'executed','transaction_id':'actual-patch-transaction'}}
            return {'ok':True}
    def gateway(*_args,**kwargs):
        generated.append(1)
        if len(generated)==1:
            variants=kwargs['response_format']['json_schema']['schema']['oneOf'][0]['properties']['tool_calls']['items']['oneOf']
            assert [v['properties']['name']['const'] for v in variants]==['propose_patch']
            return json.dumps({'tool_calls':[{'name':'propose_patch','arguments':{'file_path':'scripts/example.py','exact_old_text':'old','new_text':'new'}}],'answer':''}),1
        return json.dumps({'tool_calls':[],'answer':'Source edit executed; actual-patch-transaction'}),1
    monkeypatch.setattr(llm,'chat_via_gateway',gateway)
    result=worker.local_turn(RemoteAPI(),{'id':9,'conversation_id':1,'body':'Apply the provided patch'},[],['propose_patch'])
    assert len(calls)==1 and result['receipts'][0]['status']=='executed'
    assert result['receipts'][0]['transaction_id']=='actual-patch-transaction'


def test_pickup_refreshes_current_plan_and_files_without_expanding_scope():
    import json,pytest
    request={'id':42,'body':json.dumps({'task_type':'hb_managed_continuation','task_id':'T-CURRENT',
        'next_action':'Old correction','plan':{'arguments':{'evidence_id':10}}}),
        'routing':{'allowed_tools':['read_file','task_evidence']}}
    packet={'task_id':'T-CURRENT','execution_plan':{'evidence_id':20},'recent_source_files':['core/hb_dream.py']}
    refreshed=worker.current_assignment(request,packet)
    body=json.loads(refreshed['body'])
    assert body['plan']['arguments']['evidence_id']==20
    assert body['recent_source_files']==['core/hb_dream.py']
    assert 'Old correction' not in body['next_action']
    assert refreshed['routing']==request['routing']
    assert json.loads(request['body'])['plan']['arguments']['evidence_id']==10
    with pytest.raises(PermissionError):
        worker.current_assignment(request,dict(packet,task_id='T-OTHER'))


def test_scoped_checkpoint_keeps_real_task_reply_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'agents')
    evidence={'id':99,'sender':'apex','message_type':'response','content':'Source edit verified by saved receipt','task':{'task_id':'T-CURRENT'}}
    seen=[]
    class DecisionAPI(API):
        def call(self,path,body=None):
            if path.endswith('/whoami'):return {'principal':'apex'}
            if path.startswith('/api/agent/v1/memory'):return {'memories':[]}
            if path.startswith('/api/peer/v1/threads/'):return {'messages':[evidence,*self.messages]}
            result=super().call(path,body)
            if path.split('?')[0].endswith('/inbox'):
                for row in result['messages']:
                    row['recipient']='apex';row['routing']={'kind':'decision','task_id':'T-CURRENT','task_context':{},'allowed_tools':['read_file']}
            return result
        def post(self,conversation,text,**routing):
            result=super().post(conversation,text,**routing);self.messages[-1]['sender']='apex';return result
    def decide(_api,_request,context):
        seen.extend(context)
        return {'answer':'Continue from verified evidence','decision':{'action':'continue','reason':'Actual reply','next_task':'Inspect current source','evidence_message_ids':[99]},'model':'local','category':'peer_decision','tokens':1,'receipts':[]}
    monkeypatch.setattr(worker,'decision_turn',decide)
    api=DecisionAPI();worker.serve('apex',once=True,api_factory=lambda _:api)
    assert seen==[evidence] and api.acked==[42]


def test_checkpoint_evidence_schema_allows_only_actual_saved_reply_ids(monkeypatch):
    import json
    from contextlib import nullcontext
    from core import apex_context,apex_routing,llm
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda _:apex_routing.LocalRoute('local-decision','general',16384,'test'))
    monkeypatch.setattr(agent_identity,'execution',lambda *_a,**_k:nullcontext())
    monkeypatch.setattr(apex_context,'prepare_context',lambda m:m)
    monkeypatch.setattr(apex_context,'generation_budget',lambda _:1024)
    def gateway(_model,_messages,**kwargs):
        evidence=kwargs['response_format']['json_schema']['schema']['properties']['evidence_message_ids']
        assert evidence['items']['enum']==[99,100] and evidence['minItems']==1
        return json.dumps({'action':'continue','reason':'Actual saved reply100','next_task':'Execute pending verified local repair','evidence_message_ids':[100]}),1
    monkeypatch.setattr(llm,'chat_via_gateway',gateway)
    body=json.dumps({'current_round_reply_evidence':[{'message_id':100},{'message_id':99}],'pending_requested_work':[{'message_id':500}]})
    result=worker.decision_turn(API(),{'id':42,'conversation_id':2833,'body':body},[])
    assert result['decision']['evidence_message_ids']==[100]
