import json
import sqlite3
from pathlib import Path
from contextlib import closing
import pytest

from core import hb_workflow as workflow,apex_knowledge as kc


@pytest.fixture
def database(tmp_path,monkeypatch):
    path=tmp_path/'hb.sqlite'
    def connect():
        conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row;return conn
    monkeypatch.setattr(workflow,'get_connection',connect)
    monkeypatch.setattr(kc,'get_connection',connect)
    return connect


def test_real_library_and_legacy_documents_have_distinct_readable_ids(database):
    with database() as c:
        c.executescript('''CREATE TABLE project_docs(id INTEGER PRIMARY KEY,doc_name TEXT,content TEXT,tags TEXT);
            CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY,title TEXT,raw_text TEXT,domain_tags TEXT,source_ref TEXT,status TEXT);
            CREATE TABLE knowledge_chunks(source_id INTEGER,chunk_index INTEGER,chunk_text TEXT);
            INSERT INTO project_docs VALUES(1,'old reference','old content','legacy');
            INSERT INTO knowledge_sources VALUES(1,'Mistral card','retrieval and context window','[]','hf-archive:model/revision','active');
            INSERT INTO knowledge_sources VALUES(2,'archived','Mistral','[]','private','archived');
            INSERT INTO knowledge_chunks VALUES(1,0,'Measured local Mistral guidance');''')
    found=kc.search('Mistral')['items']
    assert len(found)==1 and found[0]['document_id']==kc.LIBRARY_ID+1
    assert found[0]['source_ref']=='hf-archive:model/revision'
    assert kc.read(found[0]['document_id'])['content']=='retrieval and context window'
    assert kc.read(1)['content']=='old content'
    assert kc.search('%%')['items']==[]


def test_backlog_returns_real_statuses_owners_blockers_and_pages(database):
    with database() as c:
        c.executescript('''CREATE TABLE projects(project_id TEXT PRIMARY KEY,name TEXT);
          CREATE TABLE project_steps(step_id TEXT,project_id TEXT,title TEXT,status TEXT,owner TEXT,updated_at REAL);
          INSERT INTO projects VALUES('P-1','HB recovery');''')
        for i in range(18):
            c.execute('INSERT INTO project_steps VALUES (?,?,?,?,?,?)',
                (f'S-{i}', 'P-1',f'Task {i}','blocked' if i==0 else 'todo','apex',i))
        c.execute("INSERT INTO project_steps VALUES ('S-done','P-1','Already done','done','codex',100)")
    page=workflow.backlog()
    assert len(page['items'])==15 and page['next_offset']==15
    assert page['items'][0]['status']=='blocked'
    assert all(row['title']!='Already done' for row in page['items'])
    assert len(workflow.backlog(15)['items'])==3
    assert {'status':'done','count':1} in page['step_counts']
    with pytest.raises(ValueError):workflow.backlog(True)


def test_measurements_record_failures_and_preserve_host_scope(database,monkeypatch):
    snapshots=iter([{'SwapTotal_bytes':0,'scope':'whole_host_visible_to_this_process'},
                    {'SwapTotal_bytes':1024,'scope':'whole_host_visible_to_this_process'},{}])
    monkeypatch.setattr(workflow,'memory_snapshot',lambda:next(snapshots))
    monkeypatch.setattr(workflow.time,'monotonic',lambda:5)
    workflow.record_run(2833,'local-coder','coder','failed',1,{},0,[{'id':'r1','tool':'read_file','status':'failed'}])
    workflow.record_run(2833,'local-coder','coder','completed',3,{},14,[])
    history=workflow.runtime_history()
    assert len(history['recent_runs'])==2
    assert {r['status'] for r in history['comparisons']}=={'failed','completed'}
    assert 'host-wide' in history['notice']
    assert {r['elapsed_seconds'] for r in history['recent_runs']}=={2,4}


def test_terminal_diagnostics_use_existing_grants_without_shell_composition(monkeypatch):
    from core import agent_identity
    from fridays import shell_agent
    import database as permissions
    monkeypatch.setattr(permissions,'can_user_invoke_skill',lambda *_a,**_k:True)
    calls=[]
    monkeypatch.setattr(shell_agent,'run',lambda command,**kwargs:(calls.append((command,kwargs)) or (True,'measured host RAM')))
    token=agent_identity.CURRENT.set({'principal':'apex'})
    try:
        assert workflow.call_control('terminal_run',{'command':'free -h'})['ok']
        assert calls==[('free -h',{'agent':'apex','notify_ghost':False})]
        for command in ['free -h; touch /tmp/should-not-exist','free -h\nwhoami',
                        'cat /etc/shadow','sudo systemctl restart swarm-terminal.service',
                        'journalctl -u --directory -n 10']:
            with pytest.raises(ValueError):workflow.call_control('terminal_run',{'command':command})
        monkeypatch.setattr(permissions,'can_user_invoke_skill',lambda *_a,**_k:False)
        with pytest.raises(PermissionError):workflow.call_control('terminal_run',{'command':'free -h'})
        assert len(calls)==1
    finally:agent_identity.CURRENT.reset(token)
