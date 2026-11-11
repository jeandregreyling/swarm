import json
import os
import subprocess
import sys

import pytest
from core import hb_executions as executions,hb_task_manager as manager,hb_tasks
from core import hb_task_operations as operations
from core.tool_approval import ApprovalStore
from test_peer_turns import flow,owner
from test_apex_final_answer import repository


@pytest.fixture
def process():
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    yield child
    if child.poll() is None:child.terminate()
    child.wait(timeout=5)


def test_live_process_prevents_duplicate_execution_and_pid_reuse_is_detected(flow):
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    key=executions.claim(conn,task,agent='apex',kind='peer',request_id=rid)
    assert executions.verify(conn,key,task['task_id'])
    with pytest.raises(ValueError,match='live executor'):executions.claim(conn,task,agent='apex',kind='peer')
    identity=executions.process_identity();identity['start_ticks']='not-the-same-process'
    assert executions.alive(identity) is False


def test_orphan_requeues_only_after_process_death_and_fences_old_executor(flow,process):
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    manager.register(conn,task,request_id=rid)
    key=executions.claim(conn,task,agent='apex',kind='peer',request_id=rid,pid=process.pid)
    assert manager.tick(conn)==[]
    process.terminate();process.wait(timeout=5)
    queued=manager.tick(conn)
    assert len(queued)==1 and queued[0]!=rid
    assert hb_tasks.for_request(conn,queued[0])['task_id']==task['task_id']
    with pytest.raises(PermissionError,match='stale'):executions.verify(conn,key,task['task_id'])
    assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='needs_review'
    assert manager.tick(conn)==[]


def test_unavailable_process_probe_is_not_treated_as_death(flow,monkeypatch):
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    key=executions.claim(conn,task,agent='apex',kind='peer',request_id=rid)
    monkeypatch.setattr(executions,'alive',lambda _:None)
    assert executions.reconcile(conn)==[]
    assert executions.active(conn,task['task_id'])[0]['execution_id']==key


def test_inline_implementation_registers_and_retains_restricted_tools(flow,process):
    from core import hb_inline_tasks
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    conn.execute("UPDATE hb_peer_work SET state='completed'")
    key=hb_inline_tasks.start(conn,task,owner='real-owner',allow_writes=False)
    assert manager.managed(conn,task) and executions.verify(conn,key,task['task_id'])
    assert manager.tick(conn)==[]
    executions.release(conn,key)
    queued=manager.tick(conn)
    assert queued
    assert 'propose_patch' not in hb_tasks.invitation_tools(conn,queued[0])
    assert hb_inline_tasks.implementation_request('please fix the terminal')
    assert not hb_inline_tasks.implementation_request('How do I fix the terminal?')


def test_owner_hold_prevents_claim(flow):
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    conn.execute("UPDATE hb_tasks SET state='paused'");task=hb_tasks.get(conn,task['task_id'])
    with pytest.raises(PermissionError,match='held'):executions.claim(conn,task,agent='apex',kind='inline')


def test_pending_write_before_crash_is_retryable_only_after_verified_death(flow,repository,process):
    conn,_=flow;rid=owner(conn,'apex');task=hb_tasks.for_request(conn,rid)
    key=executions.claim(conn,task,agent='apex',kind='peer',request_id=rid,pid=process.pid)
    args={'file_path':'sample.py','exact_old_text':'hello','new_text':'hello\n# recovered once'}
    store=ApprovalStore();tx=store.propose(repository,'propose_patch',args,'owner','session',1)
    operations.begin(conn,task,'propose_patch',args,tx,execution_id=key)
    with pytest.raises(ValueError,match='pending'):operations.replay(conn,repository,task,'propose_patch',args)
    process.terminate();process.wait(timeout=5)
    assert operations.replay(conn,repository,task,'propose_patch',args) is None
    store=ApprovalStore();tx=store.propose(repository,'propose_patch',args,'owner','new-session',1)
    op=operations.begin(conn,task,'propose_patch',args,tx)
    result=store.decide(tx.id,True,tx.owner,tx.session,tx.csrf,lambda _:True)
    operations.finish(conn,op,result)
    assert operations.replay(conn,repository,task,'propose_patch',args)['replayed']
    assert (repository.root/'sample.py').read_text().count('# recovered once')==1
