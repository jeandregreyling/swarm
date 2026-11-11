from contextlib import closing
import json
import sqlite3

import pytest

from core import hb_tasks as tasks, peer_bridge as peers, peer_turns
from test_peer_turns import flow, owner, reply, four_handoffs


def studio(conn):
    conn.executescript('''CREATE TABLE projects(project_id TEXT PRIMARY KEY,name TEXT,description TEXT,
        methodology TEXT,status TEXT,owner TEXT,created_at REAL,updated_at REAL);
      CREATE TABLE project_steps(step_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,description TEXT,
        status TEXT,owner TEXT,order_idx INTEGER,created_at REAL,updated_at REAL);
      CREATE TABLE project_blackboard_notes(note_id TEXT PRIMARY KEY,project_id TEXT,author TEXT,
        kind TEXT,content TEXT,status TEXT,created_at REAL,updated_at REAL);''')


def test_owner_tasks_are_distinct_studio_steps_and_interleaved_replies_keep_their_scope(flow):
    conn,p=flow;studio(conn)
    hf=owner(conn)
    first=tasks.for_request(conn,hf)
    gemini=owner(conn,'gemini-advisor')
    second=tasks.for_request(conn,gemini)
    assert first['task_id']!=second['task_id'] and first['step_id']!=second['step_id']
    assert first['project_id']==second['project_id']
    hf_reply=reply(conn,p['codex-instructor'],hf,'Verified HF evidence.')
    queued=hf_reply['handoff']['queued'][0]
    assert tasks.for_request(conn,queued)['task_id']==first['task_id']
    assert peer_turns.route(conn,queued)['owner_message_id']==first['root_message_id']
    assert conn.execute('SELECT COUNT(*) FROM project_blackboard_notes').fetchone()[0]>=4
    inbox=peers.inbox(conn,p['apex'],pending_only=True)
    assert inbox[0]['routing']['task_context']['task_id']==first['task_id']
    assert second['task_id'] not in json.dumps(inbox[0]['routing']['task_context'])


def test_explicit_followup_preserves_objective_and_exact_amendments(flow):
    conn,_=flow;req=owner(conn);task=tasks.for_request(conn,req)
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Only the four approved files; keep everything else paused.')").lastrowid
    tasks.bind(conn,1,mid,task_id=task['task_id'])
    follow=peers.enqueue(conn,1,mid,'Only the four approved files',['apex'],sender='ghost')[0]
    assert tasks.for_request(conn,follow)['task_id']==task['task_id']
    packet=tasks.packet(conn,task)
    assert packet['objective']=='Assess the existing file proposal; keep downloads paused'
    assert packet['instructions'][0]['content']=='Only the four approved files; keep everything else paused.'


def test_cross_room_task_and_reply_switches_are_rejected(flow):
    conn,_=flow;req=owner(conn);task=tasks.for_request(conn,req)
    conn.execute("INSERT INTO conversations VALUES(2,'Other')")
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(2,'user','Other task')").lastrowid
    with pytest.raises(PermissionError):tasks.bind(conn,2,mid,task_id=task['task_id'])


def test_cancelled_task_stops_new_handoffs_without_cancelling_another_task(flow):
    conn,p=flow;first=owner(conn);task=tasks.for_request(conn,first)
    other=owner(conn,'gemini-advisor')
    conn.execute("UPDATE hb_tasks SET state='cancelled' WHERE task_id=?",(task['task_id'],))
    result=reply(conn,p['codex-instructor'],first,'Old result.')
    assert result['handoff']['queued']==[]
    assert tasks.for_request(conn,other)['state']=='active'


def test_invocation_usage_is_once_only_and_survives_history(flow):
    conn,p=flow;req=owner(conn)
    usage={'source':'provider','input_tokens':100,'output_tokens':25,'total_tokens':125}
    first=reply(conn,p['codex-instructor'],req,'Part one',usage=usage,model='configured-model',route_reply=False)
    second=reply(conn,p['codex-instructor'],req,'Part two',route_reply=False)
    assert conn.execute('SELECT COUNT(*) FROM hb_reply_usage').fetchone()[0]==1
    assert tasks.budget(conn,tasks.for_request(conn,req))['used_tokens']==125
    rows=peers.thread(conn,p['codex-instructor'],1)
    assert next(r for r in rows if r['id']==first['message_id'])['usage']==usage
    assert next(r for r in rows if r['id']==second['message_id']).get('usage',{}).get('total_tokens') is None
    with pytest.raises(ValueError):reply(conn,p['codex-instructor'],req,'Bad usage',usage={'source':'provider','total_tokens':-1})


def test_continuation_blocks_repeating_the_same_next_action(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    task=tasks.for_request(conn,decision)
    signature=__import__('hashlib').sha256(b'repeat the same check').hexdigest()
    conn.execute('INSERT INTO hb_task_checkpoints VALUES (?,?)',(task['task_id'],signature))
    result=reply(conn,p['apex'],decision,'Repeat',decision={'action':'continue','reason':'No new approach',
        'next_task':'Repeat the same check','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='needs_review'
    assert result['handoff']['queued']==[]


def test_budget_error_preserves_full_owner_instruction(flow):
    conn,_=flow;req=owner(conn);task=tasks.for_request(conn,req)
    conn.execute('UPDATE hb_tasks SET objective=? WHERE task_id=?',('X'*20000,task['task_id']))
    with pytest.raises(ValueError,match='Pinned task instructions'):
        tasks.packet(conn,tasks.get(conn,task['task_id']))


def test_task_event_memory_delivery_is_private_idempotent_and_after_commit(enrolled,monkeypatch):
    from test_agent_identity import connect
    from core import agent_identity
    path,*_=enrolled
    from utils.db import _connection
    monkeypatch.setattr(_connection,'get_connection',lambda:connect(path))
    with closing(connect(path)) as conn:
        conn.executescript('''CREATE TABLE conversations(id INTEGER PRIMARY KEY,title TEXT);
          CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,content TEXT);
          INSERT INTO conversations VALUES(1,'Memory task');
          INSERT INTO messages VALUES(1,1,'user','Preserve the pinned file scope');''')
        tasks.ensure_schema(conn)
        task=tasks.bind(conn,1,1)
        tasks.event(conn,task,'apex','verified_read',{'receipt':'real-read'},recipients=('codex-instructor',))
        conn.commit()
    tasks.flush_memory();tasks.flush_memory()
    with closing(agent_identity._memory('apex')) as memory:
        assert memory.execute('SELECT COUNT(*) FROM memories WHERE ticket_ref=?',(task['task_id'],)).fetchone()[0]==1
    with closing(agent_identity._memory('gemma')) as memory:
        assert memory.execute('SELECT COUNT(*) FROM memories WHERE ticket_ref=?',(task['task_id'],)).fetchone()[0]==0


from test_agent_identity import enrolled


def test_unverified_studio_change_cannot_be_finished_by_a_model_decision(flow):
    conn,p=flow;studio(conn)
    conn.execute('CREATE TABLE project_test_cases(case_id TEXT,step_id TEXT,status TEXT)')
    decision,evidence=four_handoffs(flow);task=tasks.for_request(conn,decision)
    conn.execute("INSERT INTO project_test_cases VALUES('case',?,'ready')",(task['step_id'],))
    result=reply(conn,p['apex'],decision,'Done',decision={'action':'finish','reason':'I said done',
        'next_task':'','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='continue'
    assert result['handoff']['queued']
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()[0]=='todo'


def test_invalid_arguments_are_repaired_at_checkpoint_instead_of_becoming_permission_blocker(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow);task=tasks.for_request(conn,decision)
    tasks.event(conn,task,'apex','tool_failure',{'category':'ValueError','error':'Read range exceeds 100 lines'})
    result=reply(conn,p['apex'],decision,'Cannot read',decision={'action':'blocked','reason':'Missing file access',
        'next_task':'','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='continue'
    body=json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?',(result['handoff']['queued'][0],)).fetchone()[0])
    assert 'HTTP 400 is not permission denial' in body['next_task']


def test_failed_provider_question_is_not_resubmitted_within_the_same_task(flow,monkeypatch):
    from core import hb_local_jobs
    monkeypatch.setattr(hb_local_jobs,'instructor_gate',lambda *args:None)
    from core import agent_identity
    conn,p=flow;root=owner(conn,'apex')
    actor={'principal':'apex','conversation_id':1,'peer_request_id':root}
    token=agent_identity.CURRENT.set(actor)
    try:
        first=peers.request_help(conn,1,'gemini','Reply only CHECK','Current connection test')
        failed=first['request_ids'][0]
        conn.execute("UPDATE hb_peer_work SET state='failed',stage='provider unavailable (HTTP 503)' WHERE request_id=?",(failed,))
        count=conn.execute('SELECT count(*) FROM peer_messages').fetchone()[0]
        second=peers.request_help(conn,1,'gemini','Reply only CHECK','Same test again')
        assert second['status']=='waiting' and second['request_ids']==[failed]
        assert conn.execute('SELECT count(*) FROM peer_messages').fetchone()[0]==count
        other=owner(conn,'apex');actor['peer_request_id']=other
        fresh=peers.request_help(conn,1,'gemini','Reply only CHECK','Independent explicit task')
        assert fresh['status']=='queued' and fresh['request_ids']!=[failed]
    finally:agent_identity.CURRENT.reset(token)


def test_owner_request_to_stop_online_help_blocks_delegation_not_local_work(flow):
    from core import agent_identity
    conn,p=flow;root=owner(conn,'apex');task=tasks.for_request(conn,root)
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Stop asking online models to do your jobs; use local tools.')").lastrowid
    tasks.bind(conn,1,mid,task_id=task['task_id'])
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':root})
    try:
        result=peers.request_help(conn,1,'gemini','Do my local job','')
        assert result['status']=='not_queued' and result['request_ids']==[]
        assert tasks.get(conn,task['task_id'])['state']=='active'
    finally:agent_identity.CURRENT.reset(token)


def test_large_transport_events_keep_original_evidence_without_recursive_memory(enrolled,monkeypatch):
    from test_agent_identity import connect
    from core import agent_identity
    from utils.db import _connection
    path,*_=enrolled
    monkeypatch.setattr(_connection,'get_connection',lambda:connect(path))
    payload={'tool':'task_memory','output':'repeated history '*2000}
    with closing(connect(path)) as conn:
        conn.executescript("CREATE TABLE conversations(id INTEGER PRIMARY KEY,title TEXT); CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,content TEXT); INSERT INTO conversations VALUES(1,'Compact memory'); INSERT INTO messages VALUES(1,1,'user','Keep original evidence');")
        tasks.ensure_schema(conn);task=tasks.bind(conn,1,1)
        eid=tasks.event(conn,task,'apex','tool_result',payload);conn.commit()
    tasks.flush_memory()
    with closing(agent_identity._memory('apex')) as memory:
        text=memory.execute('SELECT content FROM memories WHERE legacy_id=?',(eid,)).fetchone()[0]
        assert len(text)<1800
        assert json.loads(text)['evidence']['read']['arguments']['evidence_id']==eid
    with closing(connect(path)) as conn:
        assert json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(eid,)).fetchone()[0])==payload


def test_repeated_instructor_coaching_is_referenced_without_losing_owner_constraints(flow):
    conn,_=flow
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','Keep the owner limit exact; only the approved files.')").lastrowid
    task=tasks.bind(conn,1,mid)
    for index in range(8):
        instruction='Earlier source coaching '+str(index)+' '+('read exact source first '*100)
        coach=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'codex-instructor',?)",(instruction,)).lastrowid
        tasks.bind(conn,1,coach,task_id=task['task_id'])
    latest='Now run the verified local tests.'
    coach=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'codex-instructor',?)",(latest,)).lastrowid
    tasks.bind(conn,1,coach,task_id=task['task_id'])
    packet=tasks.packet(conn,tasks.get(conn,task['task_id']))
    assert packet['objective']=='Keep the owner limit exact; only the approved files.'
    assert packet['instructions'][-1]['content']==latest
    assert all('reference' in x for x in packet['instructions'][:-1])
    eid=packet['instructions'][0]['reference']['read']['arguments']['evidence_id']
    original=json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(eid,)).fetchone()[0])['content']
    assert original.startswith('Earlier source coaching 0')


def test_checkpoint_prompt_contains_actual_reply_ids_and_retains_narrowed_scope(flow):
    conn,p=flow
    decision,evidence=four_handoffs(flow);task=tasks.for_request(conn,decision)
    from core import peer_turns
    body=json.loads(peer_turns.decision_body(conn,1,peer_turns.current(conn,1,parent_request_id=decision)))
    assert evidence in [row['message_id'] for row in body['current_round_reply_evidence']]
    assert body['pending_requested_work']
    tasks.event(conn,task,'codex-instructor','tool_scope',{'allowed_tools':['read_file']},request_id=decision)
    result=reply(conn,p['apex'],decision,'Continue the verified task',decision={'action':'continue','reason':'New verified reply evidence', 'next_task':'Inspect a distinct locally verified source path before the next bounded repair','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='continue'
    assert tasks.invitation_tools(conn,result['handoff']['queued'][0])=={'read_file'}
    continued=json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?',(result['handoff']['queued'][0],)).fetchone()[0])
    assert continued['pending_requested_work']
    assert all(item['content'] for item in continued['pending_requested_work'])
