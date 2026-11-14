"""A recovered request traverses the real worker and authenticated Flask API."""
from contextlib import closing
import json
import os
import subprocess
import sys
import pytest

from core import hb_executions,hb_tasks,hb_task_manager,peer_bridge
from scripts import hummingbird_peer_worker as worker
from test_hb_task_api import assigned
from test_agent_identity import api,enrolled,headers,connect

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.mark.parametrize('interruption',['before_dispatch','before_write','after_write_before_receipt'])
def test_dead_executor_is_recovered_by_worker_with_one_write_and_correlated_reply(assigned,monkeypatch,interruption):
    client,root,path,rid,task=assigned
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    args={'file_path':'hello.py','exact_old_text':'hello','new_text':'hello\n# recovered once'}
    try:
        with closing(connect(path)) as conn,conn:
            hb_task_manager.register(conn,task,request_id=rid)
            old=hb_executions.claim(conn,task,agent='apex',kind='peer',request_id=rid,pid=child.pid)
            if interruption!='before_dispatch':
                from core import hb_task_operations
                from core.tool_approval import ApprovalStore
                from core.apex_tools import ReadOnlyRepository
                store=ApprovalStore();tx=store.propose(ReadOnlyRepository(root),'propose_patch',args,'owner','session',1)
                hb_task_operations.begin(conn,task,'propose_patch',args,tx,execution_id=old)
                if interruption=='after_write_before_receipt':
                    result=store.decide(tx.id,True,tx.owner,tx.session,tx.csrf,lambda _:True)
                    assert result['status']=='succeeded'  # Deliberately crash before operations.finish.
            assert hb_task_manager.tick(conn)==[]
        child.terminate();child.wait(timeout=5)
        with closing(connect(path)) as conn,conn:
            new=hb_task_manager.tick(conn)[0]
            assert new!=rid

        class LocalAPI:
            def call(self,url,body=None):
                response=client.get(url,headers=headers('apex')) if body is None else client.post(url,headers=headers('apex'),json=body)
                assert response.status_code<300,(url,response.get_json())
                return response.get_json()
            def post(self,conversation,text,**routing):
                return self.call('/api/peer/v1/messages',{'conversation_id':conversation,'text':text,**routing})
        applied=[]
        def local_turn(api,request,context,tools):
            assert request['id']==new and 'propose_patch' in tools
            result=api.call('/api/agent/v1/tools',{'tool':'propose_patch',
                'arguments':args,
                'context':{'request_id':new,'model':'isolated-local-test'}})
            applied.append(result['receipt'])
            return {'answer':'Recovered write verified: '+result['receipt']['transaction_id'],
                'model':'isolated-local-test','tokens':1,'receipts':[]}
        monkeypatch.setattr(worker,'local_turn',local_turn)
        worker.serve('apex',once=True,api_factory=lambda _:LocalAPI())
        worker.serve('apex',once=True,api_factory=lambda _:LocalAPI())
        assert len(applied)==1
        assert applied[0].get('replayed',False)==(interruption=='after_write_before_receipt')
        assert (root/'hello.py').read_text().count('# recovered once')==1
        with closing(connect(path)) as conn:
            assert conn.execute('SELECT state FROM hb_executions WHERE execution_id=?',(old,)).fetchone()[0]=='interrupted'
            replies=conn.execute('SELECT message_id FROM hb_peer_replies WHERE request_id=?',(new,)).fetchall()
            assert len(replies)==1
            assert hb_tasks.for_message(conn,replies[0][0])['task_id']==task['task_id']
            assert conn.execute('SELECT delivered_at FROM peer_messages WHERE id=?',(new,)).fetchone()[0]
    finally:
        if child.poll() is None:child.terminate()
        child.wait(timeout=5)


@pytest.mark.parametrize('crash_point',['during_post','before_ack','after_ack'])
def test_real_process_crash_during_reply_recovers_saved_parts_without_new_inference(assigned,monkeypatch,crash_point):
    import multiprocessing
    client,root,path,rid,task=assigned
    with closing(connect(path)) as conn,conn:
        hb_task_manager.register(conn,task,request_id=rid)
        conn.execute('UPDATE peer_messages SET body=? WHERE id=?',('{"task_type":"hb_managed_continuation"}',rid))
    answer='Saved answer '+('x'*3900)
    class LocalAPI:
        def __init__(self,crash=False):self.crash=crash
        def call(self,url,body=None):
            if self.crash and url.endswith('/inbox/ack') and crash_point=='before_ack':os._exit(41)
            response=client.get(url,headers=headers('apex')) if body is None else client.post(url,headers=headers('apex'),json=body)
            assert response.status_code<300,(url,response.get_json())
            if self.crash and url.endswith('/inbox/ack') and crash_point=='after_ack':os._exit(42)
            return response.get_json()
        def post(self,conversation,text,**routing):
            result=self.call('/api/peer/v1/messages',{'conversation_id':conversation,'text':text,**routing})
            if self.crash and crash_point=='during_post':os._exit(43)
            return result
    def local_turn(api,request,context,tools):
        api.call('/api/agent/v1/tools',{'tool':'propose_patch','arguments':{
            'file_path':'hello.py','exact_old_text':'hello','new_text':'hello\n# one reply effect'},
            'context':{'request_id':rid,'model':'isolated-local-test'}})
        return {'answer':answer,'model':'isolated-local-test','tokens':1,'receipts':[]}
    monkeypatch.setattr(worker,'local_turn',local_turn)
    process=multiprocessing.get_context('fork').Process(target=lambda:worker.serve('apex',once=True,api_factory=lambda _:LocalAPI(crash=True)))
    process.start();process.join(timeout=15)
    if process.is_alive():process.terminate();process.join();pytest.fail('Crash fixture did not exit')
    assert process.exitcode in {41,42,43}
    monkeypatch.setattr(worker,'local_turn',lambda *_:pytest.fail('Saved reply recovery must not rerun inference'))
    worker.serve('apex',once=True,api_factory=lambda _:LocalAPI())
    worker.serve('apex',once=True,api_factory=lambda _:LocalAPI())
    with closing(connect(path)) as conn:
        rows=conn.execute('SELECT m.content FROM hb_peer_replies r JOIN messages m ON m.id=r.message_id WHERE r.request_id=? ORDER BY m.id',(rid,)).fetchall()
        assert len(rows)==2 and ''.join(row[0] for row in rows)==answer
        assert conn.execute('SELECT delivered_at FROM peer_messages WHERE id=?',(rid,)).fetchone()[0]
    assert (root/'hello.py').read_text().count('# one reply effect')==1
