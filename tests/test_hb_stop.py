"""Owner Stop interrupts real task processes and fences late results."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys

import pytest
from core import hb_executions as executions,hb_task_manager as manager,hb_tasks,peer_bridge as peers
from core.hb_chat_controls import continuation,owner_text_stop,set_continuation
from test_peer_turns import flow,owner,four_handoffs
from test_hb_chat_controls import control_app,command
from test_agent_identity import api,enrolled,headers,connect
from test_hb_task_api import assigned


@pytest.mark.parametrize('text',['stop','STOP!','@apex stop.','please stop now','stop the current looping'])
def test_direct_stop_commands(text):
    assert owner_text_stop(text)


@pytest.mark.parametrize('text',['do not stop','if it fails stop','"stop"','APEX said stop','> stop','`stop`','could you explain stop?','stop when finished'])
def test_references_are_not_stop_commands(text):
    assert not owner_text_stop(text)


@pytest.fixture
def workers(tmp_path,monkeypatch):
    root=tmp_path/'repo';(root/'scripts').mkdir(parents=True)
    script=root/'scripts/hummingbird_peer_worker.py'
    script.write_text('import time\ntime.sleep(120)\n')
    monkeypatch.setattr(executions,'ROOT',root)
    children=[]
    def start(agent='apex',verified=True):
        args=[str(script),'--agent',agent] if verified else ['-c','import time; time.sleep(120)']
        child=subprocess.Popen([sys.executable,*args]);children.append(child)
        return child
    yield start
    for child in children:
        if child.poll() is None:child.terminate()
        child.wait(timeout=5)


@pytest.mark.parametrize('button',['off','stop','declined'])
def test_button_interrupts_running_process_without_killing_shared_or_unrelated_processes(control_app,workers,button):
    client,task,rid,path,_,_=control_app
    worker=workers();unrelated=workers(verified=False);inline=workers(verified=False)
    with sqlite3.connect(path) as conn:
        executions.claim(conn,task,agent='apex',kind='peer',request_id=rid,pid=worker.pid)
        other_rid=owner(conn,'apex');other=hb_tasks.for_request(conn,other_rid)
        executions.claim(conn,other,agent='apex',kind='peer',request_id=other_rid,pid=unrelated.pid)
        inline_rid=owner(conn,'apex');inline_task=hb_tasks.for_request(conn,inline_rid)
        executions.claim(conn,inline_task,agent='apex',kind='inline',request_id=inline_rid,pid=inline.pid)
        conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id IN (?,?)",(other['task_id'],inline_task['task_id']))
    if button=='stop':
        from frontend.blueprints.chat import chat_bp
        client.application.register_blueprint(chat_bp)
        response=client.post('/api/chat/jobs/cancel',json={'conversation_id':1,'job_ids':[]})
        assert response.get_json()['held_tasks']
    elif button=='declined':
        from test_hb_chat_approvals import decision
        response=client.post('/api/peer/v1/tasks/'+task['task_id']+'/requests/'+str(task['root_message_id'])+'/approval',json=decision(client,task,'declined'))
    else:
        response=client.post('/api/peer/v1/tasks/'+task['task_id']+'/control',json=command(client,task,'off'))
    assert response.status_code==200,response.get_json()
    assert worker.wait(timeout=5)<0
    executions.stop_held_executors()  # A claimed arbitrary PID is never authority to kill it.
    assert unrelated.poll() is None and inline.poll() is None
    with sqlite3.connect(path) as conn:
        executions.reconcile(conn)
        assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='cancelled'
        assert hb_tasks.get(conn,task['task_id'])['state']=='paused'
        assert len(list(conn.execute("SELECT 1 FROM hb_task_events WHERE kind='execution_stop_requested'")))==1


def test_inline_model_result_cannot_execute_tools_after_owner_stop(assigned,monkeypatch):
    from core.agent_identity import CURRENT
    from core.apex_tools import run_apex_tools,ReadOnlyRepository
    client,root,path,rid,task=assigned
    calls=[]
    def model(*args):
        calls.append('inference')
        with closing(connect(path)) as conn,conn:
            conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?",(task['task_id'],))
        return json.dumps({'tool_calls':[{'name':'read_file','arguments':{'path':'hello.py'}}],'answer':''}),1
    token=CURRENT.set({'task_id':task['task_id']})
    try:
        with pytest.raises(PermissionError,match='Owner stopped'):
            run_apex_tools(model,[{'role':'user','content':'Read hello.py'}],lambda:True,
                lambda receipt:calls.append('tool'),repository=ReadOnlyRepository(root))
        assert calls==['inference']
    finally:CURRENT.reset(token)


def test_owner_hold_takes_precedence_over_dependencies(flow):
    conn,_=flow;first=owner(conn);parent=hb_tasks.for_request(conn,first)
    second=owner(conn);task=hb_tasks.for_request(conn,second)
    manager.register(conn,task,request_id=second,dependencies=[parent['task_id']])
    conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?",(task['task_id'],))
    manager.tick(conn)
    assert continuation(conn,hb_tasks.get(conn,task['task_id']))['status']=='held'
    assert conn.execute('SELECT state FROM hb_task_manager WHERE task_id=?',(task['task_id'],)).fetchone()[0]=='held'


def test_chat_stop_holds_all_current_chat_tasks_without_creating_a_task(control_app):
    from frontend.blueprints.chat import chat_bp
    client,task,rid,path,_,_=control_app;client.application.register_blueprint(chat_bp)
    with sqlite3.connect(path) as conn:
        second=owner(conn,'apex');second_task=hb_tasks.for_request(conn,second)
        manager.register(conn,second_task,request_id=second)
        conn.execute("INSERT INTO conversations VALUES(2,'Other conversation')")
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(2,'user','apex','Other work','chat')").lastrowid
        other=peers.enqueue(conn,2,mid,'Other work',['apex'],sender='ghost')[0]
        other_task=hb_tasks.for_request(conn,other)
        before=conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]
    response=client.post('/api/chat',json={'message':'@apex stop.','conversation_id':1})
    assert response.status_code==200,response.get_json()
    result=response.get_json()
    assert result['mode']=='control' and result['pending_jobs']==[]
    assert set(result['held_tasks'])=={task['task_id'],second_task['task_id']}
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==before
        assert hb_tasks.get(conn,other_task['task_id'])['state']=='active'
        assert all(continuation(conn,hb_tasks.get(conn,key))['mode']=='off' for key in result['held_tasks'])
        from core import peer_turns
        assert not peer_turns.ready(conn,rid) and not peer_turns.ready(conn,second)


def test_explicit_stop_cannot_target_another_chat(control_app):
    from frontend.blueprints import peer_bridge as bp
    client,task,_,path,_,_=control_app
    with sqlite3.connect(path) as conn:conn.execute("INSERT INTO conversations VALUES(2,'Other chat')")
    with client.application.test_request_context('/api/chat',method='POST',json={}):
        response,status=bp.maybe_owner_chat_control({'conversation_id':2,'task_id':task['task_id']},'stop')
        assert status==403
    with sqlite3.connect(path) as conn:assert hb_tasks.get(conn,task['task_id'])['state']=='active'


def test_stop_button_requires_authenticated_owner_and_same_origin(control_app):
    from frontend.blueprints.chat import chat_bp
    client,task,_,path,current,_=control_app;client.application.register_blueprint(chat_bp)
    body={'conversation_id':1,'job_ids':[]}
    assert client.post('/api/chat/jobs/cancel',json=body,headers={'Origin':'https://other.example'}).status_code==403
    current[0]=None
    assert client.post('/api/chat/jobs/cancel',json=body).status_code==403
    current[0]={'username':'viewer','role':'viewer'}
    assert client.post('/api/chat/jobs/cancel',json=body).status_code==403
    with sqlite3.connect(path) as conn:assert hb_tasks.get(conn,task['task_id'])['state']=='active'


def test_task_off_leaves_another_verified_task_worker_running(control_app,workers):
    client,task,rid,path,_,_=control_app;worker=workers();sibling=workers()
    with sqlite3.connect(path) as conn:
        executions.claim(conn,task,agent='apex',kind='peer',request_id=rid,pid=worker.pid)
        other_rid=owner(conn,'apex');other=hb_tasks.for_request(conn,other_rid)
        executions.claim(conn,other,agent='apex',kind='peer',request_id=other_rid,pid=sibling.pid)
    response=client.post('/api/peer/v1/tasks/'+task['task_id']+'/control',json=command(client,task,'off'))
    assert response.status_code==200
    assert worker.wait(timeout=5)<0 and sibling.poll() is None


def test_stop_frontend_sends_control_when_only_peer_tasks_exist():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'frontend/static/js/views/chat.js').read_text()
    function=source[source.index('async function stopPendingAgents()'):].split('\n}\n',1)[0]+'\n}\n'
    harness='''
const assert=require('node:assert/strict');
global.window={__fridaysChatConversationId:1};
let sent=[];
global.fetch=async(url,options)=>{sent.push([url,JSON.parse(options.body)]);return {ok:true,json:async()=>({ok:true,count:0,held_tasks:['T-held']})};};
for(const name of ['showToast','_clearPendingChatTracking','_syncThinkingBubbles','_renderThreadRuntimePanel','loadConversationMessages','refreshChatThreadList','pollActiveThreadRuntime'])global[name]=()=>{};
'''
    check="stopPendingAgents().then(()=>{assert.equal(sent.length,1);assert.equal(sent[0][0],'/api/chat/jobs/cancel');assert.equal(sent[0][1].conversation_id,1);assert.deepEqual(sent[0][1].job_ids,[]);}).catch(e=>{console.error(e);process.exitCode=1;});"
    subprocess.run(['node','-e',harness+function+check],check=True,capture_output=True,text=True,timeout=5)


def test_late_failed_decision_cannot_overwrite_owner_hold(flow):
    conn,p=flow;rid,_=four_handoffs(flow);task=hb_tasks.for_request(conn,rid)
    control=continuation(conn,task)
    set_continuation(conn,task,{'mode':'off','message_id':task['root_message_id'],'version':task['version'],
        'revision':control['revision'],'command_id':'test-stop-decision-0001'},'owner')
    count=conn.execute('SELECT COUNT(*) FROM peer_messages').fetchone()[0]
    result=peers.post(conn,p['apex'],1,'Decision failed after owner Stop',reply_to_request_id=rid,outcome='failed')
    assert result['owner_held'] and result['handoff']['queued']==[]
    assert hb_tasks.get(conn,task['task_id'])['state']=='paused'
    assert conn.execute('SELECT COUNT(*) FROM peer_messages').fetchone()[0]==count
    assert conn.execute('SELECT content FROM messages WHERE id=?',(result['message_id'],)).fetchone()[0]=='Decision failed after owner Stop'


@pytest.mark.parametrize('status',['running','failed','completed'])
def test_late_agent_progress_preserves_owner_hold(assigned,status):
    client,_,path,rid,task=assigned
    with closing(connect(path)) as conn,conn:
        conn.execute("UPDATE hb_tasks SET state='paused' WHERE task_id=?",(task['task_id'],))
    response=client.post('/api/agent/v1/progress',headers=headers('apex'),json={
        'conversation_id':1,'request_id':rid,'status':status,'stage':'Late inference result'})
    assert response.status_code==200,response.get_json()
    assert response.get_json()['status']=='cancelled'
    with closing(connect(path)) as conn:
        assert hb_tasks.get(conn,task['task_id'])['state']=='paused'
        assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(rid,)).fetchone()[0]=='cancelled'
        saved=json.loads(conn.execute("SELECT payload FROM hb_task_events WHERE kind='progress'").fetchone()[0])
        assert saved['status']==status and saved['owner_held']

pytestmark = pytest.mark.usefixtures("owner_turned_continuation_on")
