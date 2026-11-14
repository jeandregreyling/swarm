from contextlib import nullcontext
import json
import sqlite3
from urllib.parse import urlsplit, parse_qs

import pytest
from core import agent_identity
from scripts import hummingbird_gemini_peer as worker


@pytest.fixture(autouse=True)
def isolated_provider_selection(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'provider-identities')


class API:
    def __init__(self):
        self.acked=[];self.messages=[];self.progress=[]

    def call(self,path,body=None):
        parsed=urlsplit(path)
        if path.endswith('/whoami'):return {'principal':'gemini-advisor'}
        if parsed.path.endswith('/inbox'):
            after=int(parse_qs(parsed.query).get('after',['0'])[0])
            return {'messages':[] if self.acked or after>=615 else
                    [{'id':615,'message_id':100,'recipient':'gemini-advisor','sender':'ghost',
                      'conversation_id':2834,'body':'@gemini what do you think?','delivered_at':None}]}
        if parsed.path.endswith('/threads/2834'):return {'messages':self.messages}
        if parsed.path.endswith('/memory'):return {'memories':[]}
        if parsed.path.endswith('/progress'):
            self.progress.append(body);return {'ok':True}
        if parsed.path.endswith('/inbox/ack'):
            self.acked.extend(body['ids']);return {'ok':True}
        raise AssertionError(path)

    def post(self,conversation,text,**routing):
        row={'id':1000+len(self.messages),'sender':'gemini-advisor','content':text,'message_type':'response'}
        self.messages.append(row);return {'message_id':row['id']}


@pytest.fixture
def relay(tmp_path,monkeypatch):
    monkeypatch.setattr(agent_identity,'STATE',tmp_path/'identities')
    monkeypatch.setattr(agent_identity,'execution',lambda *_a,**_k:nullcontext())
    return API()


def test_invited_gemini_request_gets_saved_verified_reply_and_is_not_replayed(relay,monkeypatch):
    generated=[]
    def generate(question,*_,**__):
        generated.append(question);return 'configured-model','Inspect the actual inventory, keep downloads paused.',20
    monkeypatch.setattr(worker,'_generate',generate)
    worker.serve(once=True,api_factory=lambda _:relay)
    assert relay.acked==[615] and len(relay.messages)==1
    assert relay.progress[-1]['status']=='completed'
    with sqlite3.connect(agent_identity.STATE/'gemini-advisor/hb-worker.sqlite') as conn:
        assert conn.execute('SELECT state,model FROM jobs').fetchone()==('completed','configured-model')
    worker.serve(once=True,api_factory=lambda _:relay)
    assert len(generated)==1 and len(relay.messages)==1


def test_provider_failure_is_visible_unacknowledged_and_not_retried(relay,monkeypatch):
    generated=[]
    def fail(*_,**__):
        generated.append(1);raise RuntimeError('429 quota private-error-details')
    monkeypatch.setattr(worker,'_generate',fail)
    worker.serve(once=True,api_factory=lambda _:relay)
    assert relay.acked==[] and relay.progress[-1]['status']=='failed'
    assert 'quota/rate limit' in relay.messages[0]['content']
    assert 'private-error-details' not in str(relay.messages)
    worker.serve(once=True,api_factory=lambda _:relay)
    assert len(generated)==1


def test_restart_marks_interrupted_inference_for_review_without_reexecution(relay,monkeypatch):
    folder=agent_identity.directory('gemini-advisor')
    with sqlite3.connect(folder/'hb-worker.sqlite') as conn:
        conn.execute('CREATE TABLE jobs(request_id INTEGER PRIMARY KEY,conversation_id INTEGER,state TEXT,model TEXT,answer TEXT,error TEXT)')
        conn.execute("INSERT INTO jobs(request_id,conversation_id,state) VALUES (615,2834,'running')")
    monkeypatch.setattr(worker,'_generate',lambda *_,**__:pytest.fail('Interrupted request was replayed'))
    worker.serve(once=True,api_factory=lambda _:relay)
    with sqlite3.connect(folder/'hb-worker.sqlite') as conn:
        assert conn.execute('SELECT state FROM jobs').fetchone()[0]=='needs_review'
    assert relay.acked==[] and relay.messages==[]


def test_provider_uses_only_configured_model_and_redacts_failures(monkeypatch):
    from google import genai
    import config
    calls=[]
    class Client:
        def __init__(self,**_):self.models=self
        def generate_content(self,**kwargs):
            calls.append(kwargs['model']);raise ValueError('429 quota SECRET')
        def close(self):calls.append('closed')
    monkeypatch.setattr(genai,'Client',Client)
    monkeypatch.setattr(config,'GEMINI_API_KEY','test-key')
    monkeypatch.setattr(config,'GEMINI_AGENT_MODEL','configured-model')
    with pytest.raises(RuntimeError,match='quota/rate limit') as error:
        worker._generate('question','quoted history','')
    assert 'SECRET' not in str(error.value) and calls==['configured-model','closed']


def test_reviewed_boundary_prevents_old_request_replay(relay,monkeypatch):
    monkeypatch.setattr(worker,'_generate',lambda *_,**__:pytest.fail('An old request was replayed'))
    worker.serve(once=True,after_id=615,api_factory=lambda _:relay)
    assert relay.messages==[] and relay.acked==[]


def test_google_server_failure_keeps_precise_sanitized_status(relay,monkeypatch):
    class Unavailable(Exception):
        code=504
    failure=worker.ProviderFailure(worker._failure_category(Unavailable('private provider details')))
    monkeypatch.setattr(worker,'_generate',lambda *_,**__:(_ for _ in ()).throw(failure))
    worker.serve(once=True,api_factory=lambda _:relay)
    assert relay.messages==[] and relay.acked==[]
    assert relay.progress[-1]['status']=='queued' and 'retrying the same request' in relay.progress[-1]['stage']
    with sqlite3.connect(agent_identity.STATE/'gemini-advisor/hb-worker.sqlite') as conn:
        assert conn.execute('SELECT state,retry_count FROM jobs').fetchone()==('awaiting_provider',1)




@pytest.mark.parametrize('code,expected_calls',[(503,2),(504,2),(502,2),(403,1),(429,1),(404,1),(400,1)])
def test_native_generation_retries_only_one_transient_attempt(monkeypatch,code,expected_calls):
    from google import genai
    import config
    calls=[]
    class Failure(Exception):pass
    class Client:
        def __init__(self,**kwargs):self.models=self
        def generate_content(self,**kwargs):
            calls.append(kwargs['model'])
            if len(calls)==1:
                error=Failure('provider failed');error.code=code;raise error
            from types import SimpleNamespace
            return SimpleNamespace(text='saved provider answer',usage_metadata=None)
        def close(self):pass
    monkeypatch.setattr(genai,'Client',Client)
    monkeypatch.setattr(config,'GEMINI_API_KEY','test-key')
    monkeypatch.setattr(config,'GEMINI_AGENT_MODEL','configured-model')
    monkeypatch.setattr(worker.time,'sleep',lambda _:None)
    if code in {502,503,504}:
        assert worker._generate('question','','')[1]=='saved provider answer'
    else:
        with pytest.raises(worker.ProviderFailure):worker._generate('question','','')
    assert len(calls)==expected_calls and set(calls)=={'configured-model'}


def test_two_transient_failures_stop_without_a_third_call(monkeypatch):
    from google import genai
    import config
    calls=[]
    class Failure(Exception):code=504
    class Client:
        def __init__(self,**kwargs):self.models=self
        def generate_content(self,**kwargs):calls.append(1);raise Failure('unavailable')
        def close(self):pass
    monkeypatch.setattr(genai,'Client',Client)
    monkeypatch.setattr(config,'GEMINI_API_KEY','test-key')
    monkeypatch.setattr(worker.time,'sleep',lambda _:None)
    with pytest.raises(worker.ProviderFailure,match='HTTP 504'):worker._generate('question','','')
    assert len(calls)==2


def test_transient_provider_wait_survives_restart_and_can_deliver_same_invitation(relay,monkeypatch):
    now=[1000.0];calls=[]
    monkeypatch.setattr(worker.time,'time',lambda:now[0])
    def generate(*args,**kw):
        calls.append(1)
        if len(calls)==1:raise worker.ProviderFailure('provider unavailable (HTTP 503)')
        return 'configured-model','RECOVERED',4
    monkeypatch.setattr(worker,'_generate',generate)
    worker.serve(once=True,api_factory=lambda _:relay)
    assert relay.messages==[] and len(calls)==1
    worker.serve(once=True,api_factory=lambda _:relay)
    assert len(calls)==1
    now[0]+=16
    worker.serve(once=True,api_factory=lambda _:relay)
    assert len(calls)==2 and relay.acked==[615] and relay.messages[0]['content']=='RECOVERED'


def test_provider_wait_budget_is_finite_and_never_replays_delivery():
    conn=sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE jobs(request_id INTEGER PRIMARY KEY,retry_count INTEGER,state TEXT,answer TEXT,next_attempt REAL,error TEXT)')
    conn.execute("INSERT INTO jobs VALUES(1,0,'running',NULL,0,NULL)")
    req={'id':1};failure=worker.ProviderFailure('provider unavailable (HTTP 504)')
    assert worker._provider_wait(conn,req,failure,now=100)==15
    conn.execute("UPDATE jobs SET state='running'")
    assert worker._provider_wait(conn,req,failure,now=120)==45
    conn.execute("UPDATE jobs SET state='running'")
    assert worker._provider_wait(conn,req,failure,now=200) is None
    conn.execute("UPDATE jobs SET retry_count=0,state='reply_pending',answer='already generated'")
    assert worker._provider_wait(conn,req,failure,now=200) is None
    assert worker._provider_wait(conn,req,RuntimeError('post failed'),now=200) is None


def test_stopped_task_never_starts_a_provider_call(relay,monkeypatch):
    original=relay.call
    def call(path,body=None):
        result=original(path,body)
        if '/inbox?' in path:
            for request in result['messages']:request['routing']={'task_context':{'state':'cancelled'}}
        return result
    relay.call=call
    monkeypatch.setattr(worker,'_generate',lambda *args:pytest.fail('Cancelled task called provider'))
    worker.serve(once=True,api_factory=lambda _:relay)
    assert relay.messages==[] and relay.acked==[]
    with sqlite3.connect(agent_identity.STATE/'gemini-advisor/hb-worker.sqlite') as conn:
        assert conn.execute('SELECT state FROM jobs').fetchone()[0]=='needs_review'


def test_gemini_context_uses_only_the_current_task(relay):
    relay.messages=[{'id':1,'sender':'user','message_type':'chat','content':'unrelated old permission claim','task':{'task_id':'other'}},
                    {'id':2,'sender':'apex','message_type':'chat','content':'Actual current test evidence','task':{'task_id':'current'}}]
    history=worker._history(relay,{'id':615,'conversation_id':2834,'routing':{'task_id':'current'}})
    assert 'current test evidence' in history and 'unrelated old' not in history


@pytest.mark.parametrize('code,category',[(401,'provider credential/permission'),(403,'provider credential/permission'),(429,'provider quota/rate limit'),(404,'configured model unavailable'),(504,'provider unavailable (HTTP 504)')])
def test_numeric_provider_errors_keep_their_actual_category(code,category):
    failure=type('ProviderError',(Exception,),{'code':code})('sanitized opaque provider error')
    assert worker._failure_category(failure)==category


def test_only_validated_private_flash_override_can_change_provider_model(tmp_path):
    folder=agent_identity.directory(worker.AGENT);path=folder/'hb-provider-model.json'
    assert worker.selected_provider_model('configured-model')=='configured-model'
    path.write_text(' {"model":"gemini-2.5-flash"} ');path.chmod(0o600)
    assert worker.selected_provider_model('configured-model')=='gemini-2.5-flash'
    path.write_text('{"model":"arbitrary-unapproved-model"}')
    with pytest.raises(ValueError):worker.selected_provider_model('configured-model')
    path.unlink();other=tmp_path/'outside';other.write_text('{"model":"gemini-2.5-flash"}');path.symlink_to(other)
    with pytest.raises(PermissionError):worker.selected_provider_model('configured-model')
