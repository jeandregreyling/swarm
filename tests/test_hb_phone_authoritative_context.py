"""Phone replies use accepted facts and never expose owner history to enrolled users."""
import json
import sqlite3
import pytest
from core import hb_channels as c, hb_tasks, hb_change_sets
from test_practice_193_channels import conn, _Shared  # noqa: F401

T = 'T-0123456789AB'
S = 'S-0123456789'


def state_db(conn, monkeypatch):
    hb_tasks.ensure_schema(conn)
    conn.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,project_id,step_id,state,created_at,updated_at) VALUES (?,7,1,'Approval timeout repair','bounded repair','P-X',?,'completed',1,2)", (T,S))
    task = hb_tasks.get(conn,T)
    hb_tasks.event(conn,task,'apex','test_result',{'alm_run_id':'real-run','alm_run_status':'pass','summary':'23 passed','exit_code':0,'tests':['tests/test_timeout.py']})
    hb_tasks.event(conn,task,'codex-instructor','accepted',{'evidence_message_ids':[11]})
    monkeypatch.setattr(hb_change_sets,'record', lambda step: {'state':'applied','commit':{'commit':'abc123'}})


def job(key='telegram:999', question='Is the approval repair completed?'):
    return {'channel':'telegram','key':key,'message_id':99,'question':question,'reply':{}}


def test_owner_gets_actual_accepted_result_and_commit_before_connection_release(conn, monkeypatch):
    state_db(conn,monkeypatch)
    conn.execute("INSERT INTO messages VALUES (1,7,'user','apex','owner private context','chat',0)")
    history=[]
    assert c.work_one(job(), connect=lambda:_Shared(conn), answer=lambda q,h:history.extend(h) or 'done') == 'done'
    snapshot=json.loads(next(h['content'] for h in history if h['role']=='system').removeprefix(c.PHONE_STATE_PREFIX))
    record=snapshot['tasks'][0]
    assert record['state']=='completed' and record['latest_test']['summary']=='23 passed'
    assert record['acceptance']['agent']=='codex-instructor'
    assert record['change_set']['commit']['commit']=='abc123'


def test_enrolled_user_never_receives_owner_history_or_task_records(conn, monkeypatch):
    state_db(conn,monkeypatch)
    conn.execute("INSERT INTO messages VALUES (1,7,'user','apex','OWNER SECRET','chat',0)")
    monkeypatch.setattr(c,'telegram_send', lambda *a:True)
    seen=[]
    c.work_one(job('telegram:111', T+' status?'),connect=lambda:_Shared(conn),answer=lambda q,h:seen.append(h) or 'public answer')
    assert seen == [[]]


def test_revoked_queued_identity_does_not_run_model_or_deliver(conn):
    assert c.work_one(job('telegram:404'),connect=lambda:_Shared(conn),answer=lambda *a:pytest.fail('revoked user ran model')) == ''


def test_unrelated_research_has_no_task_snapshot(conn,monkeypatch):
    state_db(conn,monkeypatch)
    assert c._owner_task_state(conn,job(question='What is wage type /XQE?')) == ''


def test_cited_task_does_not_select_other_work(conn,monkeypatch):
    state_db(conn,monkeypatch)
    assert T in c._owner_task_state(conn,job(question=T+' what happened?'))
    assert c._owner_task_state(conn,job(question='T-FFFFFFFFFFFF what happened?')) == ''


def test_answer_system_keeps_authoritative_facts_when_fresh_research_resets_history(monkeypatch):
    from core import apex_tools,apex_routing,apex_context
    from core.hb_agent_tools import ground_answer
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda q:apex_routing.LocalRoute('test','voice',16384,'test'))
    seen=[]
    def turn(model,msgs,*a,**k):
        seen.extend(msgs)
        return 'recorded complete',0,[]
    monkeypatch.setattr(apex_tools,'run_apex_tools',turn)
    monkeypatch.setattr('core.hb_agent_tools.ground_answer',lambda a,r:a)
    facts=c.PHONE_STATE_PREFIX+'{"tasks":[{"state":"completed"}]}'
    c._answer_only('Explain the approval repair status', [{'role':'user','content':'old wrong claim'},{'role':'system','content':facts}])
    assert facts in seen[0]['content']
    assert not any('old wrong claim' in m['content'] for m in seen)
    assert 'execution rights' in seen[0]['content']
