from contextlib import closing
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest
from core import hb_tasks,hb_owner_sessions as sessions,hb_runtime_reload as reload,agent_identity,peer_bridge as peers
from utils.db import _connection
from test_peer_turns import flow
from test_hb_owner_sessions import owner_store,grant

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.fixture
def accepted(owner_store,tmp_path,monkeypatch):
    conn,principals=owner_store;created=grant(owner_store);task=hb_tasks.get(conn,created['task_id'])
    (sessions.ROOT/'core').mkdir();source=sessions.ROOT/'core/feature.py';source.write_text('value=1\n')
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'hummingbird','Review this component')").lastrowid
    hb_tasks.bind(conn,1,mid,task_id=task['task_id'],kind='relay')
    rid=peers.enqueue(conn,1,mid,'Review component',['codex-instructor'],sender='hummingbird')[0]
    conn.execute("UPDATE hb_tasks SET state='completed' WHERE task_id=?",(task['task_id'],))
    conn.execute('CREATE TABLE project_test_cases(step_id TEXT,status TEXT)')
    conn.execute('INSERT INTO project_test_cases VALUES (?,\'passed\')',(task['step_id'],))
    hb_tasks.event(conn,task,'apex','mutation',{'paths':['core/feature.py']})
    hb_tasks.event(conn,task,'codex-instructor','accepted',{'evidence_message_ids':[]})
    sessions.authorize_runtime_reload(conn,sessions.native_owner_authority(),task['task_id'],
        'Actual fixture owner authorizes only the fixed HB service after independent acceptance.')
    conn.commit();path=tmp_path/'runtime.sqlite'
    with sqlite3.connect(path) as copy:conn.backup(copy)
    monkeypatch.setattr(_connection,'DB_PATH',str(path))
    monkeypatch.setattr(reload,'ROOT',sessions.ROOT)
    monkeypatch.setattr(reload.subprocess,'run',lambda *_a,**_k:pytest.fail('Tests must not restart the actual service'))
    token=agent_identity.CURRENT.set({'principal':'codex-instructor','peer_request_id':rid,'conversation_id':1})
    yield task,rid,source,principals
    agent_identity.CURRENT.reset(token)


def finish_review(conn,rid,principals):
    conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(rid,))
    peers.acknowledge(conn,principals['codex-instructor'],[rid])


def test_reload_waits_for_saved_review_and_verifies_new_process(accepted):
    task,rid,source,principals=accepted
    assert reload.request_reload()['status']=='queued'
    assert reload.request_reload()['deduplicated']
    calls=[]
    with closing(_connection.get_connection()) as conn,conn:
        reload.tick(conn,pid=10,execute=lambda cmd:calls.append(cmd))
        assert not calls
        finish_review(conn,rid,principals)
        reload.tick(conn,pid=10,execute=lambda cmd:calls.append(cmd) or SimpleNamespace(returncode=0))
        assert calls==[reload.COMMAND]
        reload.tick(conn,pid=10,healthy=lambda:True,execute=lambda _:pytest.fail('No repeated restart'))
        assert conn.execute('SELECT state FROM hb_runtime_reloads').fetchone()[0]=='restarting'
        reload.tick(conn,pid=11,healthy=lambda:True,execute=lambda _:pytest.fail('No repeated restart'))
        assert conn.execute('SELECT state FROM hb_runtime_reloads').fetchone()[0]=='completed'
        assert conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='runtime_reload_completed'").fetchone()[0]==1


@pytest.mark.parametrize('boundary',['not_accepted','wrong_role','revoked','no_grant','failed_case'])
def test_reload_cannot_bypass_owner_scope_or_independent_acceptance(accepted,boundary):
    task,rid,_,_=accepted
    with closing(_connection.get_connection()) as conn,conn:
        if boundary=='not_accepted':conn.execute("UPDATE hb_tasks SET state='active'")
        elif boundary=='revoked':conn.execute('UPDATE hb_owner_sessions SET revoked_at=?',(time.time(),))
        elif boundary=='no_grant':conn.execute('DELETE FROM hb_owner_sessions')
        elif boundary=='failed_case':conn.execute("UPDATE project_test_cases SET status='failed'")
    if boundary=='wrong_role':agent_identity.CURRENT.get()['principal']='apex'
    with pytest.raises((PermissionError,ValueError)):reload.request_reload()


def test_changed_source_is_held_and_revoked_scope_cancels_queued_reload(accepted):
    task,rid,source,principals=accepted;reload.request_reload()
    source.write_text('value=2\n')
    with closing(_connection.get_connection()) as conn,conn:
        finish_review(conn,rid,principals)
        reload.tick(conn,execute=lambda _:pytest.fail('Unreviewed code must not activate'))
        assert conn.execute('SELECT state FROM hb_runtime_reloads').fetchone()[0]=='waiting_review'


def test_other_unaccepted_source_work_prevents_activation(accepted):
    task,rid,source,principals=accepted;reload.request_reload()
    with closing(_connection.get_connection()) as conn,conn:
        finish_review(conn,rid,principals)
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Implement another component')").lastrowid
        other=hb_tasks.bind(conn,1,mid,project_id=task['project_id'])
        hb_tasks.event(conn,other,'apex','mutation',{'paths':['core/feature.py']})
        reload.tick(conn,execute=lambda _:pytest.fail('Another component still needs review'))
        assert conn.execute('SELECT state FROM hb_runtime_reloads').fetchone()[0]=='queued'


def test_new_boot_with_reused_pid_is_recognized_as_a_new_runtime(accepted):
    task,rid,_,principals=accepted;reload.request_reload()
    with closing(_connection.get_connection()) as conn,conn:
        finish_review(conn,rid,principals)
        reload.tick(conn,pid=10,identity='boot-one-start-one',execute=lambda _:SimpleNamespace(returncode=0))
        reload.tick(conn,pid=10,identity='boot-two-start-two',healthy=lambda:True)
        assert conn.execute('SELECT state FROM hb_runtime_reloads').fetchone()[0]=='completed'
