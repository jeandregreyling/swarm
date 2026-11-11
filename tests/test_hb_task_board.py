import sqlite3
import subprocess
import threading
from pathlib import Path

import pytest
from core import hb_tasks,hb_task_manager
from test_peer_turns import flow
from test_hb_chat_controls import control_app,command


@pytest.fixture
def board(control_app):
    client,task,rid,path,current,_=control_app
    project='P-ABCDEF0123'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE projects(project_id TEXT PRIMARY KEY)')
        conn.execute('INSERT INTO projects VALUES (?)',(project,))
        conn.execute('UPDATE hb_tasks SET project_id=?',(project,))
        hb_task_manager.register(conn,hb_tasks.get(conn,task['task_id']),request_id=rid)
    return client,task,path,current,project


def test_board_reads_actual_status_agent_and_evidence_and_is_owner_only(board):
    client,task,path,current,project=board;url='/api/peer/v1/projects/'+project+'/tasks'
    data=client.get(url).get_json()
    assert data['ok'] and len(data['tasks'])==1
    row=data['tasks'][0]
    assert row['assigned_to']==['codex-instructor'] and row['continuation']['status']=='queued'
    assert row['last_evidence']['event_id'] and row['next_action']
    off=command(client,task,'off')
    assert client.post('/api/peer/v1/tasks/'+task['task_id']+'/control',json=off).status_code==200
    assert client.get(url).get_json()['tasks'][0]['continuation']['status']=='held'
    current[0]={'role':'viewer','username':'viewer'}
    assert client.get(url).status_code==403


def test_unknown_projects_and_unbounded_pages_are_rejected(board):
    client,_,_,_,project=board
    url='/api/peer/v1/projects/'+project+'/tasks'
    assert client.get('/api/peer/v1/projects/P-0000000000/tasks').status_code==404
    for query in ['limit=101','limit=-1','offset=-1','limit=nan']:
        assert client.get(url+'?'+query).status_code==400
    assert client.get(url+'?offset=1').get_json()['tasks']==[]


def test_real_browser_opens_main_chat_workflow_from_canonical_api(board,tmp_path):
    from werkzeug.serving import make_server
    client,task,path,_,project=board
    browser=Path.home()/'.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'
    if not browser.is_file():pytest.skip('Local Chromium is not installed')
    prefix=(Path(__file__).resolve().parents[1]/'frontend/static/js/views/chat.js').read_text().split('// Chat engine —',1)[0]
    with sqlite3.connect(path) as conn:conn.execute("UPDATE hb_tasks SET title='<img src=x onerror=alert(1)> real task'")
    @client.application.get('/board-check')
    def page():
        return '''<!doctype html><body><div id="workflow"></div><script>
        function _escapeHtml(value){const d=document.createElement('span');d.textContent=String(value??'');return d.innerHTML.replace(/"/g,'&quot;');}
        </script><script>'''+prefix+'''</script><script>
        (async()=>{await hbOpenTaskBoard('''+repr(project)+''',document.getElementById('workflow'));
        const panel=document.querySelector('[data-hb-project-board]');
        if(!panel.querySelector('[data-board-task]'))throw Error(panel.textContent);
        if(panel.querySelector('img'))throw Error('Unescaped task title');
        if(!panel.textContent.includes('codex-instructor') || !panel.textContent.includes('Evidence #'))throw Error('Actual evidence or agent missing');
        const buttons=Array.from(panel.querySelectorAll('button')).map(b=>b.textContent);
        if(!buttons.includes('Off') || !buttons.includes('Open task in chat'))throw Error('Workflow controls missing');
        document.body.dataset.result='pass';})().catch(e=>{document.body.dataset.result='fail';document.body.dataset.error=e.message;});
        </script></body>'''
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run=subprocess.run([str(browser),'--headless','--no-sandbox','--disable-gpu','--user-data-dir='+str(tmp_path/'browser'),
            '--virtual-time-budget=5000','--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/board-check'],capture_output=True,text=True,timeout=30)
        assert 'data-result="pass"' in run.stdout,run.stdout[:1800]
    finally:server.shutdown();thread.join(timeout=5)
