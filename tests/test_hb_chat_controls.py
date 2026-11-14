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
      if(button('Off').getAttribute('aria-pressed')!=='true')throw Error('Off is not the default (owner rule S-437AC764CB)');
      button('On').click();
      await waitFor(()=>document.querySelector('#home .hb-bubble-controls [role=status]').textContent.includes('queued'));
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


def test_hb_commands_answer_as_hummingbird_without_creating_work(control_app):
    from frontend.blueprints import peer_bridge as bp
    client,task,rid,path,current,_=control_app
    app=client.application
    conv=task['conversation_id']
    before=sqlite3.connect(path).execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]
    with app.test_request_context('/api/chat',method='POST'):
        response=bp.maybe_owner_chat_control({'conversation_id':conv},'@hb tasks')
    body=response.get_json()
    assert body['mode']=='control' and body['responses'][0]['agent']=='hummingbird'
    assert task['task_id'] in body['response']
    with app.test_request_context('/api/chat',method='POST'):
        paused=bp.maybe_owner_chat_control({'conversation_id':conv},'@hb pause '+task['task_id']).get_json()
    assert 'is now Off' in paused['response']
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_tasks').fetchone()[0]==before          # no task/Studio step for @hb
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE from_agent='hummingbird'").fetchone()[0]>=2
        assert conn.execute("SELECT state FROM hb_tasks WHERE task_id=?",(task['task_id'],)).fetchone()[0]=='paused'
    current[0]={'username':'someone','role':'viewer'}
    with app.test_request_context('/api/chat',method='POST'):
        assert bp.maybe_owner_chat_control({'conversation_id':conv},'@hb tasks') is None   # owner only


def test_studio_acceptance_buttons_record_owner_decision(control_app):
    from frontend.blueprints import peer_bridge as bp
    from core.hb_commands import acceptance_state
    client,task,rid,path,current,_=control_app
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,status TEXT,residual_risk TEXT,updated_at REAL)')
        step='S-ACCE000001'
        conn.execute("INSERT INTO project_steps VALUES(?,'P-TEST','@HB commands','partial','Built and tested; awaiting owner acceptance',0)",(step,))
        conn.execute('UPDATE hb_tasks SET step_id=? WHERE task_id=?',(step,task['task_id']))
        assert acceptance_state(conn,step)['state']=='pending'
        row=hb_tasks.enrich(conn,[{'id':task['root_message_id']}])[0]
        assert row['task']['acceptance']['state']=='pending'
    url='/api/peer/v1/studio/steps/'+step+'/decision'
    assert client.post(url,json={'decision':'reject'}).status_code==400               # a reason is required
    sent=client.post(url,json={'decision':'reject','reason':'popup missing in full chat'}).get_json()
    assert sent['acceptance']['state']=='sent_back'
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE project_steps SET status='partial',residual_risk='awaiting owner acceptance' WHERE step_id=?",(step,))
    ok=client.post(url,json={'decision':'accept'}).get_json()
    assert ok['ok'] and ok['acceptance']['state']=='accepted'
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM project_steps WHERE step_id=?',(step,)).fetchone()[0]=='done'
        assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?',(task['task_id'],)).fetchone()[0]=='completed'
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE from_agent='hummingbird' AND content LIKE '✅ Done:%'").fetchone()[0]==1
    current[0]={'username':'someone','role':'viewer'}
    assert client.post(url,json={'decision':'accept'}).status_code in (401,403)


def test_needs_you_bar_lists_what_waits_for_the_owner_and_is_owner_only(control_app):
    client,task,rid,path,current,_=control_app
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,description TEXT,'
                     'status TEXT,owner TEXT,order_idx INT,created_at REAL,updated_at REAL,residual_risk TEXT)')
        conn.execute("INSERT INTO project_steps VALUES('S-ACCE000002','P-TEST','Sundial: live view','Built: GPU from sysfs','partial',"
                     "'apex',1,0,0,'Built and tested; awaiting owner acceptance')")
        conn.execute("UPDATE hb_tasks SET step_id='S-ACCE000002' WHERE task_id=?",(task['task_id'],))
    data=client.get('/api/peer/v1/hb/needs-you?conversation_id='+str(task['conversation_id'])).get_json()
    item=next(i for i in data['items'] if i['kind']=='accept')
    assert data['ok'] and item['step_id']=='S-ACCE000002' and item['label']=='Sundial'
    assert item['detail']=='Built: GPU from sysfs' and item['message_ids']==[task['root_message_id']]
    assert client.get('/api/peer/v1/hb/needs-you?conversation_id=abc').status_code==400
    current[0]={'username':'someone','role':'viewer'}
    assert client.get('/api/peer/v1/hb/needs-you').status_code in (401,403)


def test_real_browser_needs_you_bar_hover_shows_and_lights_click_opens_approve_clears(control_app,tmp_path):
    """Owner 12 Nov: approvals hover at the top of main chat; hovering a tag shows what is being approved and lights
    its chat message; clicking opens the Studio step; Approve in the card clears it from the bar."""
    import subprocess
    import threading
    from werkzeug.serving import make_server
    client,task,rid,path,_,_=control_app
    browser=Path.home()/'.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'
    if not browser.is_file():pytest.skip('Local Chromium is not installed')
    root=Path(__file__).resolve().parents[1]/'frontend/static'
    script=(root/'js/views/hb-needs-you.js').read_text()
    css=(root/'css/views/chat.css').read_text()
    prefix=(root/'js/views/chat.js').read_text().split('// Chat engine —',1)[0]
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,description TEXT,'
                     'status TEXT,owner TEXT,order_idx INT,created_at REAL,updated_at REAL,residual_risk TEXT)')
        conn.execute("INSERT INTO project_steps VALUES('S-ACCE000003','P-TEST','Sundial: live view','<b>Built</b>: GPU from sysfs',"
                     "'partial','apex',1,0,0,'Built and tested; awaiting owner acceptance')")
        conn.execute("UPDATE hb_tasks SET step_id='S-ACCE000003' WHERE task_id=?",(task['task_id'],))
    conv,mid=task['conversation_id'],task['root_message_id']
    @client.application.get('/needs-check')
    def page():
        return '''<!doctype html><html><head><style>'''+css+'''</style></head><body>
        <div class="home-chat-section"><div id="home-chat-main">
          <section class="chat-team" data-chat-participants="home" data-conversation-id="'''+str(conv)+'''">APEX banner</section>
          <div id="home-chat-messages"><div class="hc-bubble" data-message-id="'''+str(mid)+'''">Studio task S-ACCE000003: Sundial
            <div class="hb-acceptance-controls" data-hb-step="S-ACCE000003"><span><strong>Approve Studio S-ACCE000003</strong></span></div></div></div>
          <textarea id="home-chat-input"></textarea><button id="home-chat-send-btn">Send</button>
        </div></div>
        <script>function _escapeHtml(v){const d=document.createElement('span');d.textContent=String(v??'');return d.innerHTML.replace(/"/g,'&quot;');}</script>
        <script>'''+prefix+'''</script>
        <script>window.projectsOpenStep=id=>{window.__opened=id;};window.showToast=()=>{};</script>
        <script>'''+script+'''</script>
        <script>
        const wait=ms=>new Promise(r=>setTimeout(r,ms));
        const until=async(f,what)=>{for(let i=0;i<60;i++){if(f())return;await wait(50);}throw Error('Timed out: '+what);};
        const over=(el,to)=>el.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,relatedTarget:to||null}));
        const out=(el,to)=>el.dispatchEvent(new MouseEvent('mouseout',{bubbles:true,relatedTarget:to||null}));
        (async()=>{
          await until(()=>document.querySelector('.hb-needs-chip.hb-needs-accept'),'bar');
          const chip=document.querySelector('.hb-needs-chip.hb-needs-accept');
          const bar=chip.closest('[data-hb-needs-you]');
          if(bar.previousElementSibling!==document.querySelector('.chat-team'))throw Error('bar is not pinned under the banner');
          if(!chip.textContent.includes('Sundial'))throw Error('chip label '+chip.textContent);
          over(chip);
          const card=document.getElementById('hb-needs-card')||{};
          await until(()=>document.getElementById('hb-needs-card')&&!document.getElementById('hb-needs-card').hidden,'card on hover');
          const c=document.getElementById('hb-needs-card');
          if(!c.querySelector('.hb-needs-detail').textContent.includes('<b>Built</b>: GPU from sysfs'))throw Error('details not shown as text');
          if(c.querySelector('.hb-needs-detail b'))throw Error('unescaped details');
          const bubble=document.querySelector('[data-message-id="'''+str(mid)+'''"]');
          if(bubble.dataset.hbNeedsLit!=='accept')throw Error('chat message not lit');
          out(chip,document.body);
          await until(()=>c.hidden&&!bubble.dataset.hbNeedsLit,'card hides and light goes off');
          over(document.querySelector('.hb-acceptance-controls strong'));
          await until(()=>!c.hidden,'card on inline approval row');
          document.querySelector('.hb-acceptance-controls strong').click();
          if(window.__opened!=='S-ACCE000003')throw Error('label click did not open the step');
          window.__opened=null;chip.click();
          if(window.__opened!=='S-ACCE000003')throw Error('chip click did not open the step');
          over(chip);
          await until(()=>!c.hidden,'card again');
          [...c.querySelectorAll('button')].find(b=>b.textContent==='Approve').click();
          await until(()=>c.querySelector('.hb-needs-feedback').textContent.includes('Done:'),'approve saved');
          await until(()=>!document.querySelector('.hb-needs-chip.hb-needs-accept'),'bar cleared after approval');
          document.body.dataset.result='pass';
        })().catch(e=>{document.body.dataset.result='fail';document.body.dataset.error=e.message;});
        </script></body></html>'''
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run=subprocess.run([str(browser),'--headless','--no-sandbox','--disable-gpu','--user-data-dir='+str(tmp_path/'browser'),
            '--virtual-time-budget=15000','--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/needs-check'],
            capture_output=True,text=True,timeout=60)
        import re
        assert 'data-result="pass"' in run.stdout,(re.findall(r'<body[^>]*>',run.stdout) or [run.stdout[-1500:]])[0]
    finally:server.shutdown();thread.join(timeout=5)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-ACCE000003'").fetchone()[0]=='done'


def test_real_browser_step_window_shows_hbs_question_with_the_same_buttons(control_app,tmp_path):
    """Owner 12 Nov: hovering a tag showed the right buttons, but opening the task (the Studio step window) did not."""
    import subprocess
    import threading
    from werkzeug.serving import make_server
    from core import hb_task_manager as tm
    client,task,rid,path,_,_=control_app
    browser=Path.home()/'.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'
    if not browser.is_file():pytest.skip('Local Chromium is not installed')
    root=Path(__file__).resolve().parents[1]/'frontend/static'
    tid=task['task_id']
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,description TEXT,'
                     'status TEXT,owner TEXT,order_idx INT,created_at REAL,updated_at REAL,residual_risk TEXT)')
        conn.execute("INSERT INTO project_steps VALUES('S-ACCE000004','P-TEST','Learning L1','Harvest examples','doing','apex',1,0,0,'')")
        conn.execute("UPDATE hb_tasks SET step_id='S-ACCE000004' WHERE task_id=?",(tid,))
        tm.ensure_schema(conn)
        conn.execute("INSERT INTO hb_task_manager(task_id,enabled,state,phase,detail,next_due,updated_at) VALUES(?,1,'needs_owner','plan','APEX proposed a plan',0,0)",(tid,))
        tm.ask_owner(conn,hb_tasks.get(conn,tid),'APEX scoped S-ACCE000004 "Learning L1" (workflow).\nDone when:\n- the dataset is re-exported',
                     f'/plan {tid} approves this plan and starts the work; /done {tid} <your own criteria> replaces the criteria; /cancel {tid} skips this step.',kind='plan')
    step={'step_id':'S-ACCE000004','project_id':'P-TEST','title':'Learning L1','status':'doing','description':'Harvest examples',
          'test_cases':[],'test_runs':[],'hb_tasks':[],'acceptance':None}
    @client.application.get('/step-check')
    def page():
        return '''<!doctype html><body><textarea id="home-chat-input"></textarea><button id="home-chat-send-btn" onclick="window.__sent=document.getElementById('home-chat-input').value">Send</button>
        <script>function _escapeHtml(v){const d=document.createElement('span');d.textContent=String(v??'');return d.innerHTML.replace(/"/g,'&quot;');}
        const realFetch=window.fetch;window.fetch=(u,o)=>String(u).startsWith('/api/knowledge/steps/')?Promise.resolve(new Response(JSON.stringify({ok:true,step:'''+json.dumps(step)+'''}))):realFetch(u,o);
        window.showToast=()=>{};</script>
        <script>'''+(root/'js/views/projects.js').read_text()+'''</script>
        <script>'''+(root/'js/views/hb-needs-you.js').read_text()+'''</script>
        <script>
        const wait=ms=>new Promise(r=>setTimeout(r,ms));
        (async()=>{
          window.projectsOpenStep('S-ACCE000004');
          for(let i=0;i<80&&!document.querySelector('.hb-needs-panel-item');i++)await wait(50);
          const box=document.querySelector('#alm-detail-body .hb-needs-panel-item');
          if(!box)throw Error('no question in the step window');
          const labels=[...box.querySelectorAll('button')].map(b=>b.textContent);
          if(labels.join('|')!=='Approve plan|Write my own done…|Skip this step…')throw Error('buttons '+labels.join('|'));
          if(!box.textContent.includes('the dataset is re-exported'))throw Error('details missing');
          box.querySelector('button').click();
          if(window.__sent!=='/plan '''+tid+'''')throw Error('sent '+window.__sent);
          document.body.dataset.result='pass';
        })().catch(e=>{document.body.dataset.result='fail';document.body.dataset.error=e.message;});
        </script></body>'''
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run=subprocess.run([str(browser),'--headless','--no-sandbox','--disable-gpu','--user-data-dir='+str(tmp_path/'browser'),
            '--virtual-time-budget=10000','--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/step-check'],
            capture_output=True,text=True,timeout=60)
        import re
        assert 'data-result="pass"' in run.stdout,(re.findall(r'<body[^>]*>',run.stdout) or [run.stdout[-1500:]])[0]
    finally:server.shutdown();thread.join(timeout=5)
