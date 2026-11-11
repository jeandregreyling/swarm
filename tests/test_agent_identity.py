from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "utils")]

from flask import Flask, jsonify
import pytest

from core import agent_identity as runtime
from core import peer_bridge as peers
from core.apex_tools import ReadOnlyRepository
from core.tool_approval import ApprovalStore


@pytest.fixture
def enrolled(tmp_path,monkeypatch):
    from utils.db import _connection
    path = tmp_path/'main.sqlite'
    monkeypatch.setattr(runtime,'STATE',tmp_path/'agents')
    monkeypatch.setattr(_connection,'DB_PATH',str(path))
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript('''
            CREATE TABLE agents(name TEXT PRIMARY KEY,tier TEXT,model TEXT);
            INSERT INTO agents VALUES ('gemma','local','model-a'),('ten','paid','model-b'),
                ('apex','local','model-c'),('ghost','human','external');
            CREATE TABLE user_profiles(id INTEGER PRIMARY KEY,username TEXT UNIQUE,
                display_name TEXT,user_type TEXT,linked_agent TEXT,is_active INTEGER DEFAULT 1,
                can_proxy INTEGER DEFAULT 0,created_by TEXT DEFAULT 'ghost',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                role TEXT DEFAULT 'viewer',approved INTEGER DEFAULT 1);
            CREATE TABLE user_skill_permissions(username TEXT,skill_name TEXT,allowed INTEGER,
                created_by TEXT DEFAULT 'ghost',created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(username,skill_name));
            INSERT INTO user_skill_permissions(username,skill_name,allowed)
                VALUES ('gemma','fs_write',1),('apex','fs_write',1);
            CREATE TABLE memory_gemma(id INTEGER PRIMARY KEY,agent TEXT,subject TEXT,content TEXT,
                tags TEXT,importance INTEGER,source TEXT,created_at TEXT,archived INTEGER);
            INSERT INTO memory_gemma VALUES (1,'gemma','old lesson','original memory','',7,'legacy','2026-01-01',0);
            INSERT INTO memory_gemma VALUES (2,'ten','wrong partition','must not import','',7,'legacy','2026-01-01',0);
        ''')
        peers.ensure_schema(conn)
        old_peer = peers.issue_token(conn,'codex-instructor')
        peers.remember(conn,'codex-instructor','lesson','existing peer lesson','receipt-one')
        rows = runtime.provision(conn,activate=True)
    return path,rows,old_peer


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def login(path,agent):
    with closing(connect(path)) as conn:
        principal = runtime.authenticate(conn,runtime.credentials(agent)['token'],agent)
        conn.commit()
        return principal


def test_all_registered_machines_have_distinct_logins_and_memory_files(enrolled):
    path,rows,old_peer = enrolled
    identities = {row['principal'] for row in rows}
    assert {'gemma','ten','apex','codex-instructor','fridays'}<=identities
    assert 'ghost' not in identities
    tokens = [runtime.credentials(agent)['token'] for agent in identities]
    assert len(tokens)==len(set(tokens))
    for agent in identities:
        assert login(path,agent)['id']==agent
        assert (runtime.STATE/agent/'credentials.json').stat().st_mode & 0o077 == 0
        assert (runtime.STATE/agent/'memory.sqlite').is_file()
    with closing(connect(path)) as conn:
        assert peers.authenticate(conn,old_peer)['id']=='codex-instructor'
        hashes = {row[0] for row in conn.execute('SELECT token_sha256 FROM service_tokens')}
    assert not hashes.intersection(tokens)


def test_migration_is_private_idempotent_and_preserves_original_tables(enrolled):
    path,_,_ = enrolled
    assert [row['content'] for row in runtime.read_memory('gemma')]==['original memory']
    assert 'existing peer lesson' in [row['content'] for row in runtime.read_memory('codex-instructor')]
    old_token = runtime.credentials('gemma')['token']
    with closing(connect(path)) as conn:
        assert all(row['imported']==0 for row in runtime.provision(conn,activate=True))
        assert conn.execute('SELECT count(*) FROM memory_gemma').fetchone()[0]==2
    assert runtime.credentials('gemma')['token']==old_token


def test_logins_cannot_claim_another_agent_and_revocation_takes_effect(enrolled):
    path,_,_ = enrolled
    raw = runtime.credentials('gemma')['token']
    with closing(connect(path)) as conn:
        with pytest.raises(PermissionError):
            runtime.authenticate(conn,raw,'ten')
        with pytest.raises(PermissionError):
            runtime.authenticate(conn,'shared-key','gemma')
        conn.execute('UPDATE service_tokens SET revoked_at=1 WHERE token_sha256=?',
                     (hashlib.sha256(raw.encode()).hexdigest(),))
        conn.commit()
    with pytest.raises(PermissionError):
        login(path,'gemma')


def test_authenticated_execution_rejects_other_private_memory_and_identity(enrolled):
    path,_,_ = enrolled
    with runtime.execution('gemma',principal=login(path,'gemma')):
        runtime.save_memory('gemma','my lesson','only gemma')
        with pytest.raises(PermissionError):
            runtime.read_memory('ten')
        with pytest.raises(PermissionError):
            runtime.save_memory('ten','impersonation','bad')
        with pytest.raises(PermissionError):
            with runtime.execution('ten',principal=login(path,'ten')):
                pass
    assert runtime.CURRENT.get() is None


def test_concurrent_agent_runs_keep_their_own_actor_and_model(enrolled):
    path,_,_ = enrolled
    principals = {agent:login(path,agent) for agent in ['gemma','ten']}
    def run(agent):
        with runtime.execution(agent,model='actual-'+agent,requested_by='ghost',principal=principals[agent]) as identity:
            runtime.event(identity,'action-'+agent,'read_file','succeeded')
            return runtime.CURRENT.get()['principal']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(run,['gemma','ten']))=={'gemma','ten'}
    for agent in principals:
        row = runtime.audit_rows(agent=agent)[0]
        assert row['model']=='actual-'+agent and row['requested_by']=='ghost'
    assert runtime.CURRENT.get() is None


def test_file_change_records_executor_owner_paths_and_before_after_hashes(enrolled,tmp_path):
    path,_,_ = enrolled
    root = tmp_path/'repository'
    root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    (root/'file.py').write_text('before\n')
    subprocess.run(['git','-C',str(root),'add','file.py'],check=True)
    repo = ReadOnlyRepository(root)
    store = ApprovalStore()
    with runtime.execution('apex',model='actual-model',requested_by='ghost',conversation_id=12,principal=login(path,'apex')):
        transaction = store.propose(repo,'propose_write_file',{'path':'file.py','content':'after\n'},'ghost','owner-session',12)
    # A later owner decision must retain the proposing agent identity across requests.
    result = store.decide(transaction.id,True,'ghost','owner-session',transaction.csrf,lambda _:True)
    assert result['status']=='succeeded'
    rows = runtime.audit_rows(agent='apex')
    assert [row['status'] for row in rows]==['succeeded','started']
    assert rows[0]['requested_by']=='ghost' and rows[0]['model']=='actual-model'
    assert rows[0]['paths']==['file.py']
    assert rows[0]['before']['file.py']==hashlib.sha256(b'before\n').hexdigest()
    assert rows[0]['after']['file.py']==hashlib.sha256(b'after\n').hexdigest()
    assert rows[0]['action_id']==transaction.id
    assert (root/'file.py').read_text()=='after\n'


def test_audit_failure_blocks_file_mutation_before_it_occurs(enrolled,tmp_path,monkeypatch):
    path,_,_ = enrolled
    root = tmp_path/'repository'
    root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    (root/'file.py').write_text('before\n')
    subprocess.run(['git','-C',str(root),'add','file.py'],check=True)
    store = ApprovalStore()
    with runtime.execution('apex',principal=login(path,'apex')):
        tx = store.propose(ReadOnlyRepository(root),'propose_write_file',{'path':'file.py','content':'after\n'},'ghost','session',1)
    monkeypatch.setattr(runtime,'event',lambda *_a,**_k: (_ for _ in ()).throw(RuntimeError('Audit unavailable')))
    assert store.decide(tx.id,True,'ghost','session',tx.csrf,lambda _:True)['status']=='failed'
    assert (root/'file.py').read_text()=='before\n'


@pytest.fixture
def api(enrolled,monkeypatch,tmp_path):
    path,_,_ = enrolled
    from frontend.blueprints import agent_identity as api
    from frontend.blueprints import peer_bridge as bridge
    from frontend.services import identity
    from core import apex_permissions
    monkeypatch.setattr(apex_permissions,'autonomous_writes_allowed',lambda *_a,**_k: True)
    monkeypatch.setattr(api,'get_connection',lambda:connect(path))
    app = Flask(__name__)
    app.register_blueprint(api.agent_identity_bp)
    app.register_blueprint(bridge.peer_bridge_bp)
    def legacy():
        agent,error = identity._validate_agent_request()
        return error or jsonify(ok=True,principal=agent)
    app.add_url_rule('/api/agent/legacy','agent_api.legacy',legacy)
    root = tmp_path/'source'
    root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    (root/'hello.py').write_text('hello\n')
    subprocess.run(['git','-C',str(root),'add','hello.py'],check=True)
    monkeypatch.setattr(api,'ReadOnlyRepository',lambda:ReadOnlyRepository(root))
    return app.test_client(),root


def headers(agent):
    return {'Authorization':'Bearer '+runtime.credentials(agent)['token']}


def test_api_tokens_control_identity_instead_of_request_names(api):
    client,_ = api
    own = client.get('/api/agent/v1/whoami',headers=headers('gemma'))
    assert own.status_code==200 and own.get_json()['principal']=='gemma'
    assert 'read_file' in own.get_json()['tools']
    assert 'propose_write_file' not in own.get_json()['tools']
    assert client.get('/api/agent/v1/whoami',headers={**headers('gemma'),'X-Agent-Id':'ten'}).status_code==403
    assert client.get('/api/agent/v1/whoami').status_code==401
    assert client.get('/api/agent/legacy',headers={'X-Agent-Key':'shared-key','X-Agent-Id':'gemma'}).status_code==403
    authenticated = client.get('/api/agent/legacy',headers=headers('gemma'))
    assert authenticated.status_code==200 and authenticated.get_json()['principal']=='gemma'
    assert runtime.CURRENT.get() is None


def test_api_private_memory_and_tools_reject_impersonation_and_respect_grants(api):
    client,root = api
    response = client.post('/api/agent/v1/memory',headers=headers('gemma'),json={'subject':'mine','content':'private note'})
    assert response.status_code==201
    own = client.get('/api/agent/v1/memory',headers=headers('gemma')).get_json()['memories']
    other = client.get('/api/agent/v1/memory',headers=headers('ten')).get_json()['memories']
    assert any(row['content']=='private note' for row in own)
    assert not any(row['content']=='private note' for row in other)
    assert client.post('/api/agent/v1/memory',headers=headers('gemma'),json={
        'subject':'fake','content':'bad','principal':'ten'}).status_code==400
    payload = {'tool':'propose_patch','arguments':{'file_path':'hello.py','exact_old_text':'hello','new_text':'changed'}}
    assert client.post('/api/agent/v1/tools',headers=headers('ten'),json=payload).status_code==403
    result = client.post('/api/agent/v1/tools',headers=headers('apex'),json=payload)
    assert result.status_code==200 and result.get_json()['receipt']['status']=='succeeded'
    assert (root/'hello.py').read_text()=='changed\n'
    events = client.get('/api/agent/v1/audit',headers=headers('apex')).get_json()['events']
    assert events and {row['principal'] for row in events}=={'apex'}
    mutation = next(row for row in events if row['tool']=='propose_patch' and row['status']=='succeeded')
    assert mutation['before']!=mutation['after']


def test_legacy_tool_entry_cannot_run_without_an_individual_login(enrolled):
    calls = []
    with pytest.raises(FileNotFoundError):
        runtime.authenticated_skill_call('fs_readonly','','unknown-agent',None,lambda:calls.append(True))
    assert not calls
    result = runtime.authenticated_skill_call('fs_readonly','status','gemma',12,lambda:(True,'read succeeded'))
    assert result==(True,'read succeeded')
    assert [row['status'] for row in runtime.audit_rows(agent='gemma')]==['succeeded','started']


def test_registered_but_legacy_unmapped_memory_pool_is_migrated(enrolled):
    path,_,_ = enrolled
    with closing(connect(path)) as conn:
        conn.execute('CREATE TABLE memory_apex(id INTEGER PRIMARY KEY,agent TEXT,subject TEXT,content TEXT)')
        conn.execute("INSERT INTO memory_apex VALUES (1,'apex','old task','preserved apex context')")
        runtime.provision(conn,activate=True)
    assert any(row['content']=='preserved apex context' for row in runtime.read_memory('apex'))


def test_revoked_actor_cannot_execute_an_already_prepared_write(enrolled,tmp_path):
    path,_,_ = enrolled
    root = tmp_path/'repository'
    root.mkdir()
    subprocess.run(['git','init','-q',str(root)],check=True)
    (root/'file.py').write_text('before\n')
    subprocess.run(['git','-C',str(root),'add','file.py'],check=True)
    store = ApprovalStore()
    with runtime.execution('apex',principal=login(path,'apex')):
        tx = store.propose(ReadOnlyRepository(root),'propose_write_file',
            {'path':'file.py','content':'after\n'},'ghost','session',1)
    with closing(connect(path)) as conn:
        conn.execute("UPDATE service_principals SET enabled=0 WHERE id='apex'")
        conn.commit()
    result = store.decide(tx.id,True,'ghost','session',tx.csrf,lambda _:True)
    assert result['status']=='denied' and result['executor']=='apex'
    assert (root/'file.py').read_text()=='before\n'


def test_request_body_cannot_select_the_user_login(enrolled,monkeypatch):
    from frontend.services import identity,auth
    app = Flask(__name__)
    monkeypatch.setattr(auth,'get_current_user',lambda:None)
    with app.test_request_context('/api/chat',json={'acting_user':'ghost'}):
        _,error = identity._resolve_identity_or_response({'acting_user':'ghost'})
        assert error[1]==401
    monkeypatch.setattr(auth,'get_current_user',lambda:{'username':'ghost','role':'owner'})
    with app.test_request_context('/api/chat',json={'acting_user':'gemma'}):
        _,error = identity._resolve_identity_or_response({'acting_user':'gemma'})
        assert error[1]==403


def test_agent_credential_cannot_reach_owner_audit_even_with_owner_cookie(api):
    client,_ = api
    client.set_cookie('friday_session','owner-cookie')
    assert client.get('/api/agent-identities/audit',headers=headers('gemma')).status_code==403


def test_owner_memory_screens_use_private_files_and_attribute_owner_notes(api,monkeypatch):
    from frontend.blueprints import agents
    from services import auth
    client,_ = api
    client.application.register_blueprint(agents.agents_bp)
    monkeypatch.setattr(auth,'get_current_user',lambda:None)
    assert client.get('/api/agents/ten/memory').status_code==403
    owner = {'username':'ghost','role':'owner'}
    monkeypatch.setattr(auth,'get_current_user',lambda:owner)
    result = client.post('/api/agents/ten/memory/write',json={'subject':'owner supplied','content':'a new instruction note'})
    assert result.status_code==200,result.get_json()
    assert result.get_json()['executor']=='fridays'
    assert result.get_json()['requested_by']=='ghost'
    rows = client.get('/api/agents/ten/memory').get_json()['entries']
    assert any(row['content']=='a new instruction note' and row['source']=='owner:ghost' for row in rows)
    assert any(row['tool']=='memory.owner_note' and row['requested_by']=='ghost'
               for row in runtime.audit_rows(agent='fridays'))


def test_peer_memory_mirror_is_not_duplicated_on_reenrollment(enrolled):
    path,_,_ = enrolled
    with closing(connect(path)) as conn:
        peers.remember(conn,'codex-instructor','reply','a fresh peer memory','receipt-two')
        conn.commit()
        rows = runtime.provision(conn,activate=True)
    assert next(row for row in rows if row['principal']=='codex-instructor')['imported']==0
    assert sum(row['content']=='a fresh peer memory' for row in runtime.read_memory('codex-instructor'))==1


def test_twenty_specialist_memory_uses_its_private_file_and_keeps_ticket_reference(enrolled):
    path,_,_ = enrolled
    with closing(connect(path)) as conn:
        conn.execute("INSERT INTO agents VALUES ('twenty','local','specialist-model')")
        runtime.provision(conn,activate=True)
    from agents.twenty import memory
    record = memory.remember('specialist task','its own fact',ticket_ref='T-123')
    notes = memory.recall(subject_like='specialist')
    assert len(notes)==1 and notes[0]['id']==record
    assert notes[0]['content']=='its own fact' and notes[0]['ticket_ref']=='T-123'
    with closing(connect(path)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='memory_twenty'").fetchone() is None


def test_private_memory_archive_records_affected_ids_and_actual_agent(enrolled):
    path,_,_ = enrolled
    record = runtime.read_memory('gemma')[0]['id']
    changed = runtime.private_memory_call('gemma','memory.archive',lambda conn: conn.execute(
        'UPDATE memories SET archived=1 WHERE id=?',(record,)).rowcount)
    assert changed==1
    assert not runtime.read_memory('gemma')
    event = runtime.audit_rows(agent='gemma')[0]
    assert event['status']=='succeeded' and event['result']['memory_ids']==[record]


def test_peer_progress_requires_an_invitation_and_cannot_choose_another_actor(api,enrolled,monkeypatch):
    from frontend.blueprints import peer_bridge
    client,_=api
    path,_,_=enrolled
    calls=[]
    monkeypatch.setattr(peer_bridge,'_publish',lambda *a,**kw:calls.append((a,kw)))
    data={'conversation_id':2833,'status':'running','stage':'Reading the requested file'}
    assert client.post('/api/agent/v1/progress',headers=headers('apex'),json=data).status_code==403
    with closing(connect(path)) as conn:
        conn.execute('''INSERT INTO peer_messages(conversation_id,sender,recipient,body,created_at)
            VALUES (2833,'ghost','apex','test',0)''')
        conn.commit()
    result=client.post('/api/agent/v1/progress',headers=headers('apex'),json=data)
    assert result.status_code==200
    assert calls==[((2833,'apex'),{'state':'running','peer':True,'stage':'Reading the requested file'})]
    assert client.post('/api/agent/v1/progress',headers=headers('apex'),json={**data,'agent':'codex-instructor'}).status_code==400


def test_progress_survives_reload_and_keeps_background_and_request_jobs_distinct(api,enrolled,monkeypatch):
    from frontend.blueprints import peer_bridge
    from core.hb_workflow import visible_jobs
    client,_=api;path,_,_=enrolled
    monkeypatch.setattr(peer_bridge,'_publish',lambda *_a,**_k:None)
    with closing(connect(path)) as conn,conn:
        first=conn.execute("INSERT INTO peer_messages(conversation_id,sender,recipient,body,created_at) VALUES (2833,'ghost','apex','test',0)").lastrowid
        other=conn.execute("INSERT INTO peer_messages(conversation_id,sender,recipient,body,created_at) VALUES (2833,'ghost','codex-instructor','test',0)").lastrowid
    data={'conversation_id':2833,'status':'running','stage':'Reading source','request_id':first}
    assert client.post('/api/agent/v1/progress',headers=headers('apex'),json={**data,'request_id':other}).status_code==403
    assert client.post('/api/agent/v1/progress',headers=headers('apex'),json=data).status_code==200
    background={k:v for k,v in data.items() if k!='request_id'}
    assert client.post('/api/agent/v1/progress',headers=headers('apex'),json={**background,'activity_id':'hf-public-mirror','stage':'Cataloguing public repositories'}).status_code==200
    with closing(connect(path)) as conn:
        jobs=visible_jobs(conn,2833)
        assert {job['job_id'] for job in jobs}=={f'peer-2833-apex-request-{first}','peer-2833-apex-activity-hf-public-mirror'}
        assert visible_jobs(conn,999)==[]


def test_invalid_utf8_memory_is_migrated_without_losing_legacy_bytes(enrolled):
    path,_,_ = enrolled
    damaged = b'\xff\x80legacy'
    with closing(connect(path)) as conn:
        conn.execute('INSERT INTO memory_gemma VALUES (3,\'gemma\',\'damaged\',CAST(? AS TEXT),CAST(? AS TEXT),7,\'legacy\',\'2026\',0)',
                     (damaged, damaged))
        conn.execute("INSERT INTO service_memory(principal_id,kind,content,source_receipt,created_at) VALUES ('codex-instructor','damaged',CAST(? AS TEXT),'receipt',1)", (damaged,))
        rows = runtime.provision(conn,activate=True)
        assert sum(row['imported'] for row in rows) == 2
        assert sum(row['imported'] for row in runtime.provision(conn,activate=True)) == 0
        assert conn.execute('SELECT CAST(content AS BLOB) FROM memory_gemma WHERE id=3').fetchone()[0] == damaged
    for agent, store in [('gemma','memory_gemma'), ('codex-instructor','service_memory')]:
        with closing(sqlite3.connect(runtime.STATE/agent/'memory.sqlite')) as memory:
            assert memory.execute('SELECT CAST(content AS BLOB) FROM memories WHERE legacy_store=? ORDER BY id DESC', (store,)).fetchone()[0] == damaged
        assert any('legacy' in row['content'] for row in runtime.read_memory(agent))


def test_tool_context_is_bound_to_the_authenticated_agents_pending_request(api,enrolled):
    client,_=api
    path,_,_=enrolled
    with closing(connect(path)) as conn:
        conn.executescript("CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,content TEXT); INSERT INTO messages VALUES(1,2833,'user','Inspect source');")
        own=peers.enqueue(conn,2833,1,'@apex inspect',['apex'],sender='ghost')[0]
        other=peers.enqueue(conn,2833,1,'@codex inspect',['codex-instructor'],sender='ghost')[0]
        conn.commit()
    payload={'tool':'read_file','arguments':{'path':'hello.py'},'context':{'request_id':own,'model':'actual-local-model'}}
    response=client.post('/api/agent/v1/tools',headers=headers('apex'),json=payload)
    assert response.status_code==200,response.get_json()
    action=response.get_json()['action_id']
    events=runtime.audit_rows(agent='apex')
    event=next(r for r in events if r['action_id']==action and r['status']=='succeeded')
    assert event['conversation_id']==2833 and event['model']=='actual-local-model'
    assert event['requested_by']=='ghost' and event['model_provenance']=='agent_runtime_report'
    payload['context']['request_id']=other
    assert client.post('/api/agent/v1/tools',headers=headers('apex'),json=payload).status_code==403


def test_private_memory_tool_never_accepts_another_agent_target(api):
    client,_=api
    payload={'tool':'memory_save','arguments':{'subject':'lesson','content':'Verified with receipt 1'}}
    result=client.post('/api/agent/v1/tools',headers=headers('gemma'),json=payload)
    assert result.status_code==200,result.get_json()
    assert any(row['subject']=='lesson' for row in runtime.read_memory('gemma'))
    assert not any(row['subject']=='lesson' for row in runtime.read_memory('ten'))
    payload['arguments']['agent']='ten'
    assert client.post('/api/agent/v1/tools',headers=headers('gemma'),json=payload).status_code==400


def test_peer_api_reads_assigned_studio_step_and_records_audit(api, enrolled, monkeypatch):
    from core.knowledge import projects
    from core.knowledge import test_runs
    client, _ = api
    path, _, _ = enrolled
    monkeypatch.setattr(projects, '_SCHEMA_READY', False)
    monkeypatch.setattr(test_runs, '_SCHEMA_READY', False)
    project = projects.create_project('Download verification')
    step = projects.add_step(project, 'Verify existing archive', description='Keep downloads paused.', owner='apex')
    other = projects.add_step(project, 'Private assignment', owner='seven')
    with closing(connect(path)) as conn, conn:
        conn.execute("INSERT INTO peer_messages(id,conversation_id,sender,recipient,body,created_at) VALUES (900,2833,'ghost','apex','Read assigned Studio step',1)")
    listing = client.get('/api/agent/v1/tools', headers=headers('apex')).get_json()['tools']
    assert 'alm_step_get' in listing
    assert 'alm_step_get' not in client.get('/api/agent/v1/tools', headers=headers('gemma')).get_json()['tools']
    payload = {'tool': 'alm_step_get', 'arguments': {'step_id': step},
               'context': {'request_id': 900, 'model': 'test-model'}}
    response = client.post('/api/agent/v1/tools', headers=headers('apex'), json=payload)
    assert response.status_code == 200, response.get_json()
    result = response.get_json()
    output = json.loads(result['output'])
    assert output['status'] == 'found' and output['step_id'] == step
    assert output['title'] == 'Verify existing archive'
    events = runtime.audit_rows(agent='apex')
    assert any(e['action_id'] == result['action_id'] and e['status'] == 'succeeded' and e['tool'] == 'alm_step_get' for e in events)
    payload['arguments'] = {'step_id': other}
    response = client.post('/api/agent/v1/tools', headers=headers('apex'), json=payload)
    assert json.loads(response.get_json()['output'])['status'] == 'not_assigned'
    payload['arguments'] = {'step_id': step, 'unexpected': True}
    response = client.post('/api/agent/v1/tools', headers=headers('apex'), json=payload)
    assert response.status_code == 400 and 'only step_id' in response.get_json()['error']
    payload['arguments'] = {'step_id': step}
    payload['context']['request_id'] = 901
    assert client.post('/api/agent/v1/tools', headers=headers('apex'), json=payload).status_code == 403
    payload.pop('context')
    assert client.post('/api/agent/v1/tools', headers=headers('apex'), json=payload).status_code == 403
    assert client.post('/api/agent/v1/tools', headers=headers('gemma'), json=payload).status_code == 403


def test_deliberate_lessons_outrank_transport_and_old_copies_are_bounded(enrolled):
    with runtime.execution('apex'):
        saved=runtime.save_memory('apex','Verified lesson','Use actual receipts for task T-123456789ABC')
    with closing(runtime._memory('apex')) as conn:
        for index in range(10):
            conn.execute("INSERT INTO memories(subject,content,source,ticket_ref,legacy_id) VALUES(?,?,?,?,?)",
                         ('Task T-123456789ABC: tool_result',json.dumps({'task_id':'T-123456789ABC','evidence':'Verified lesson '+('x'*10000)}),'hb-transport:task-event','T-123456789ABC',100+index))
        for index in range(8):
            conn.execute("INSERT INTO memories(subject,content,source,ticket_ref) VALUES(?,?,?,?)",
                         ('inbound','Please retrieve Verified lesson','peer:peer_message:'+str(index),'T-123456789ABC'))
        conn.commit()
    rows=runtime.read_memory('apex','Verified lesson',5)
    assert rows[0]['id']==saved
    assert all(len(r['content'])<1800 for r in rows)
    with closing(runtime._memory('apex')) as conn:
        old=conn.execute('SELECT id,subject,content,source,legacy_id FROM memories WHERE legacy_id=109').fetchone()
        handle=json.loads(runtime.memory_record(old)['content'])['read']
    assert handle['tool']=='task_evidence' and handle['arguments']['evidence_id']==109
    with closing(runtime._memory('apex')) as conn:
        assert len(conn.execute('SELECT content FROM memories WHERE legacy_id=109').fetchone()[0])>10000
    assert not runtime.read_memory('ten','Verified lesson')
