import json
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask
from core import hb_tasks,peer_bridge as peers,peer_turns
from core.hb_chat_controls import continuation
from test_peer_turns import flow,owner


@pytest.fixture
def control_app(flow,tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'frontend'))
    from frontend.blueprints import peer_bridge as bp
    conn,principals=flow
    rid=owner(conn);task=hb_tasks.for_request(conn,rid);conn.commit()
    path=tmp_path/'controls.sqlite'
    with sqlite3.connect(path) as target:conn.backup(target)
    monkeypatch.setattr(bp,'get_connection',lambda:sqlite3.connect(path))
    from utils.db import _connection
    monkeypatch.setattr(_connection,'get_connection',lambda:sqlite3.connect(path))
    monkeypatch.setattr(bp,'_publish',lambda *a,**kw:None)
    monkeypatch.setattr(hb_tasks,'flush_memory',lambda:None)
    current=[{'username':'test-owner','role':'owner'}]
    auth=sys.modules[bp.require_owner.__module__]
    monkeypatch.setattr(auth,'get_current_user',lambda:current[0])
    monkeypatch.setattr(bp,'get_current_user',lambda:current[0])
    app=Flask('bubble-control-test');app.register_blueprint(bp.peer_bridge_bp)
    yield app.test_client(),task,rid,path,current,principals


def command(client,task,mode,**override):
    saved=client.get('/api/peer/v1/tasks/'+task['task_id']+'/control').get_json()['task']
    data={'mode':mode,'message_id':task['root_message_id'],'version':saved['version'],
          'revision':saved['continuation']['revision'],'command_id':'test-command-'+mode+'-0001'}
    return {**data,**override}


def test_default_off_is_visible_on_saved_message(control_app):
    client,task,rid,path,_,_=control_app
    with sqlite3.connect(path) as conn:
        row=hb_tasks.enrich(conn,[{'id':task['root_message_id']}])[0]
        assert row['task']['continuation']['mode']=='off'
        assert row['task']['continuation']['agent_choice']=='on'
        assert row['task']['continuation']['status']=='held'
        assert row['task']['continuation']['effective']=='off'
        assert row['task']['version']==task['version']
        assert row['task']['continuation']['effective']=='off'


def test_off_holds_real_work_and_on_reuses_its_attempt(control_app):
    client,task,rid,path,_,_=control_app
    url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    stopped=client.post(url,json=command(client,task,'off'))
    assert stopped.status_code==200,stopped.get_json()
    assert stopped.get_json()['task']['continuation']['status']=='held'
    with sqlite3.connect(path) as conn:
        assert not peer_turns.ready(conn,rid)
    resumed=client.post(url,json=command(client,task,'on')).get_json()
    assert resumed['queued']==[rid] and resumed['deduplicated']
    assert resumed['task']['version']==task['version']
    assert resumed['task']['continuation']['mode']=='on'
    assert resumed['task']['continuation']['actor']=='test-owner'


def test_on_after_stall_queues_apex_and_double_click_reuses_receipt(control_app):
    client,task,rid,path,_,principals=control_app
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(rid,))
        peers.acknowledge(conn,principals['codex-instructor'],[rid])
        conn.execute("UPDATE hb_tasks SET state='needs_review' WHERE task_id=?",(task['task_id'],))
        conn.execute("UPDATE hb_peer_rounds SET state='needs_review'")
    url='/api/peer/v1/tasks/'+task['task_id']+'/control';data=command(client,task,'on')
    first=client.post(url,json=data).get_json();second=client.post(url,json=data).get_json()
    assert first['queued']==second['queued'] and second['replayed']
    assert first['receipt_id']==second['receipt_id']
    assert first['task']['continuation']['status']=='queued'
    with sqlite3.connect(path) as conn:
        assert [row['id'] for row in peers.inbox(conn,principals['apex'],pending_only=True)]==first['queued']


def test_stale_or_unlinked_decision_cannot_change_task(control_app):
    client,task,rid,path,_,_=control_app;url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    stale=command(client,task,'on')
    assert client.post(url,json=command(client,task,'off')).status_code==200
    assert client.post(url,json=stale).status_code==409
    bad=command(client,task,'on',message_id=999999)
    assert client.post(url,json=bad).status_code==403
    assert client.get(url).get_json()['task']['state']=='paused'


def test_replay_does_not_overwrite_later_off(control_app):
    client,task,rid,path,_,_=control_app;url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    on=command(client,task,'on');assert client.post(url,json=on).status_code==200
    assert client.post(url,json=command(client,task,'off')).status_code==200
    assert client.post(url,json=on).get_json()['task']['continuation']['mode']=='off'
    changed={**on,'mode':'off'}
    assert client.post(url,json=changed).status_code==409


def test_reconnect_reads_saved_actor_mode_and_revision(control_app):
    client,task,rid,path,_,_=control_app;url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    saved=client.post(url,json=command(client,task,'off')).get_json()['task']['continuation']
    with sqlite3.connect(path) as new_connection:
        fresh=continuation(new_connection,hb_tasks.get(new_connection,task['task_id']))
        assert (fresh['mode'],fresh['actor'],fresh['revision'])==(saved['mode'],saved['actor'],saved['revision'])


def test_request_scope_supports_production_sqlite_rows(control_app):
    from core.hb_chat_controls import request_snapshot
    _,task,_,path,_,_=control_app
    with sqlite3.connect(path) as conn:
        expected=request_snapshot(conn,task['root_message_id'])
        conn.row_factory=sqlite3.Row
        assert request_snapshot(conn,task['root_message_id'])==expected


def test_only_owner_same_origin_json_may_flip(control_app):
    client,task,_,_,current,_=control_app;url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    data=command(client,task,'off')
    assert client.post(url,json=data,headers={'Origin':'https://untrusted.example'}).status_code==403
    assert client.post(url,data='off').status_code==400
    assert client.post(url,json={**data,'actor':'owner'}).status_code==400
    current[0]={'username':'viewer','role':'viewer'}
    assert client.post(url,json=data).status_code==403
    current[0]=None
    assert client.get(url).status_code==403


def test_real_browser_clicks_hold_resume_and_reconstruct(control_app,tmp_path):
    import subprocess
    import threading
    from werkzeug.serving import make_server
    client,task,rid,path,_,principals=control_app
    browser=Path.home()/'.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'
    if not browser.is_file():pytest.skip('Local Chromium is not installed')
    source=(Path(__file__).resolve().parents[1]/'frontend/static/js/views/chat.js').read_text()
    prefix=source.split('// Chat engine —',1)[0]
    assert len(prefix)<20000
    url='/api/peer/v1/tasks/'+task['task_id']+'/control'
    approval_url='/api/peer/v1/tasks/'+task['task_id']+'/requests/'+str(task['root_message_id'])+'/approval'
    script="""
    const url=URL_VALUE;
    const approvalUrl=APPROVAL_URL_VALUE;
    function _escapeHtml(value){const d=document.createElement('span');d.textContent=String(value??'');return d.innerHTML.replace(/"/g,'&quot;');}
    async function saved(){const r=await fetch(url);return (await r.json()).task;}
    async function approval(){return (await (await fetch(approvalUrl)).json()).request_control;}
    function draw(task,control){for(const id of ['home','tile'])document.getElementById(id).innerHTML=hbTaskBadge(task,1,null,task.root_message_id)+hbRequestControl(control,1);}
    async function waitFor(fn){const deadline=Date.now()+4000;while(!fn()){if(Date.now()>deadline)throw Error('control did not settle');await new Promise(r=>setTimeout(r,30));}}
    (async()=>{
      draw(await saved(),await approval());
      const button=label=>Array.from(document.querySelectorAll('#home .hb-bubble-controls button')).find(b=>b.textContent===label);
      if(button('Auto').getAttribute('aria-pressed')!=='true')throw Error('Auto is not default');
      button('Off').click();
      await waitFor(()=>document.querySelector('#home .hb-bubble-controls [role=status]').textContent.includes('held'));
      if((await saved()).state!=='paused')throw Error('Off did not hold backend');
      if(!document.querySelector('#tile .hb-bubble-controls [role=status]').textContent.includes('held'))throw Error('second surface stale');
      button('On').click();
      await waitFor(()=>document.querySelector('#home .hb-bubble-controls [role=status]').textContent.includes('queued'));
      const restored=await saved();
      if(restored.continuation.pickups.length!==1)throw Error('duplicate pickup');
      draw(restored,await approval());
      if(button('On').getAttribute('aria-pressed')!=='true')throw Error('reconnect lost On');
      const approveButton=label=>Array.from(document.querySelectorAll('#home .hb-request-controls button')).find(b=>b.textContent===label);
      approveButton('Needs review').click();
      await waitFor(()=>approveButton('Needs review').getAttribute('aria-pressed')==='true');
      if((await saved()).state!=='paused')throw Error('review did not hold backend');
      approveButton('Declined').click();
      await waitFor(()=>approveButton('Declined').getAttribute('aria-pressed')==='true');
      if((await approval()).decision!=='declined')throw Error('decline was not saved');
      approveButton('Approved').click();
      await waitFor(()=>approveButton('Approved').getAttribute('aria-pressed')==='true');
      if((await saved()).state!=='active')throw Error('approval did not release backend');
      await fetch('/fixture-finish',{method:'POST'});
      approveButton('Try again').click();
      await waitFor(()=>approveButton('Try again').getAttribute('aria-pressed')==='true');
      const finalTask=await saved();
      if(finalTask.continuation.pickups.length!==1 || finalTask.continuation.pickups[0].agent!=='codex-instructor')throw Error('retry did not preserve the assigned agent and one scoped pickup');
      draw(finalTask,await approval());
      if(approveButton('Try again').getAttribute('aria-pressed')!=='true')throw Error('reconnect lost approval');
      document.body.dataset.result='pass';
    })().catch(error=>{document.body.dataset.result='fail';document.body.dataset.error=error.message;});
    """.replace('APPROVAL_URL_VALUE',json.dumps(approval_url)).replace('URL_VALUE',json.dumps(url))
    app=client.application
    @app.route('/browser-check')
    def browser_page():
        return '<!doctype html><html><body><div id="home" class="hc-bubble"></div><div id="tile" class="chat-bubble"></div><script>'+prefix+'</script><script>'+script+'</script></body></html>'
    @app.post('/fixture-finish')
    def finish_fixture_attempt():
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(rid,))
            peers.acknowledge(conn,principals['codex-instructor'],[rid])
        return {'ok':True}
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run=subprocess.run([str(browser),'--headless','--no-sandbox','--disable-gpu',
            '--user-data-dir='+str(tmp_path/'browser-profile'),'--virtual-time-budget=10000',
            '--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/browser-check'],capture_output=True,text=True,timeout=30)
        (tmp_path/'browser-controls.html').write_text(run.stdout)
        assert run.returncode==0,run.stderr[-1500:]
        assert 'data-result="pass"' in run.stdout,run.stdout[-2000:]
    finally:
        server.shutdown();thread.join(timeout=5)
