import json
import sqlite3
import pytest

from core import hb_owner_sessions as sessions,hb_tasks
from core.hb_chat_controls import request_snapshot,set_request_approval
from test_peer_turns import flow


@pytest.fixture
def owner_store(flow,tmp_path,monkeypatch):
    conn,principals=flow
    root=tmp_path/'owner-repository';root.mkdir()
    monkeypatch.setattr(sessions,'ROOT',root)
    monkeypatch.setattr(sessions,'KEY_FILE',tmp_path/'private-owner-control/key')
    conn.executescript('''CREATE TABLE projects(project_id TEXT PRIMARY KEY,name TEXT,description TEXT,methodology TEXT,status TEXT,owner TEXT,created_at REAL,updated_at REAL);
      CREATE TABLE project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,description TEXT,status TEXT,owner TEXT,order_idx INTEGER,created_at REAL,updated_at REAL);
      INSERT INTO projects(project_id,name) VALUES('P-OWNER','Approved project');''')
    return conn,principals


def grant(owner_store,**extra):
    conn,_=owner_store
    return sessions.grant(conn,sessions.native_owner_authority(),conversation_id=1,project_id='P-OWNER',
        objective='Verify the scoped chat controls and preserve all unfinished actions.',
        evidence_text='Actual fixture owner explicitly approves Auto for this bounded session.',
        reason='Owner-authorized instructor override after a bad handoff citation.',**extra)


def test_owner_host_grant_is_signed_scoped_and_idempotent(owner_store):
    conn,p=owner_store
    first=grant(owner_store,session_id='session-test-0000000000000001')
    second=grant(owner_store,session_id='session-test-0000000000000001')
    assert second['task_id']==first['task_id'] and second['deduplicated']
    assert conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==1
    task=hb_tasks.get(conn,first['task_id'])
    saved=sessions.for_task(conn,task['task_id'],active=True)
    assert saved['project_id']=='P-OWNER' and saved['mode']=='auto'
    control=request_snapshot(conn,first['message_id'])
    assert control['decision']=='approved' and control['actor']=='owner-host (session Auto)'
    assert conn.execute('SELECT from_agent,message_type FROM messages WHERE id=?',(first['message_id'],)).fetchone()==('hummingbird','owner_authorization')


def test_agent_context_cannot_create_owner_authority(owner_store):
    from core.agent_identity import CURRENT
    token=CURRENT.set({'principal':'apex'})
    try:
        with pytest.raises(PermissionError):sessions.native_owner_authority()
    finally:CURRENT.reset(token)


def test_tampered_session_cannot_authorize_a_write(owner_store):
    conn,_=owner_store;created=grant(owner_store)
    payload=json.loads(conn.execute('SELECT payload FROM hb_owner_sessions').fetchone()[0])
    payload['project_id']='P-UNAPPROVED'
    conn.execute('UPDATE hb_owner_sessions SET payload=?',(json.dumps(payload),))
    with pytest.raises(PermissionError,match='signature'):sessions.for_task(conn,created['task_id'],active=True)


def test_session_expiry_prevents_new_auto_approvals_not_old_receipts(owner_store,monkeypatch):
    conn,_=owner_store;created=grant(owner_store,lifetime_seconds=60)
    saved=sessions.for_task(conn,created['task_id'])
    monkeypatch.setattr(sessions.time,'time',lambda:saved['expires_at']+1)
    assert sessions.for_task(conn,created['task_id'],active=True) is None
    assert sessions.for_task(conn,created['task_id'])['session_id']==created['session_id']
    assert request_snapshot(conn,created['message_id'])['decision']=='approved'


def test_session_write_scope_and_completion_are_separate(owner_store):
    conn,_=owner_store;created=grant(owner_store);task=hb_tasks.get(conn,created['task_id'])
    sessions.enforce_write_scope(conn,task,created['queued'][0],'propose_patch',{'file_path':'core/scoped.py'})
    with pytest.raises(PermissionError):sessions.enforce_write_scope(conn,task,created['queued'][0],'propose_patch',{'file_path':'.env'})
    with pytest.raises(PermissionError):sessions.enforce_write_scope(conn,task,created['queued'][0],'propose_commit',{'paths':['core/scoped.py']})
    assert hb_tasks.get(conn,created['task_id'])['state']=='active'


def test_auto_never_overwrites_an_explicit_owner_hold(owner_store):
    conn,_=owner_store;created=grant(owner_store);task=hb_tasks.get(conn,created['task_id'])
    snapshot=request_snapshot(conn,created['message_id'])
    set_request_approval(conn,task,{'decision':'declined','message_id':snapshot['message_id'],
        'version':task['version'],'revision':snapshot['revision'],'scope_hash':snapshot['scope_hash'],
        'command_id':'owner-declined-command-000001'},'actual-owner')
    sessions.approve_if_auto(conn,task,created['queued'][0])
    assert request_snapshot(conn,created['message_id'])['decision']=='declined'
    assert hb_tasks.get(conn,created['task_id'])['state']=='paused'


def test_auto_session_does_not_widen_a_read_only_invitation_on_continuation(owner_store):
    from core import hb_task_manager
    conn,_=owner_store;created=grant(owner_store,allowed_tools=['read_file','task_context'])
    conn.execute("UPDATE hb_peer_work SET state='failed'")
    queued=hb_task_manager.tick(conn)
    assert queued
    assert hb_tasks.invitation_tools(conn,queued[0])=={'read_file','task_context'}
