from contextlib import closing
import json
import pytest
from core import hb_local_jobs as jobs,hb_tasks,peer_bridge as peers,agent_identity
from test_hb_task_api import assigned,invoke
from test_agent_identity import api,enrolled,connect,headers

# These suites test HB after the owner's go-ahead. Since 11-12 Nov the owner's rules are: Continue off by default,
# online providers only when authorised, no automatic run without a definition of done. State them explicitly.
pytestmark = pytest.mark.usefixtures('owner_turned_continuation_on', 'online_providers_authorised', 'owner_defined_done')



@pytest.fixture(autouse=True)
def no_live_progress(monkeypatch):
    monkeypatch.setattr(jobs,'publish_progress',lambda *args:None)

def test_larger_local_review_is_queued_once_without_an_online_request(assigned):
    client,_,path,rid,task=assigned
    args={'question':'How should this local source error be repaired?','evidence':'Actual404 receipt'}
    first=invoke(assigned,'local_review',args);assert first.status_code==200,first.get_json()
    a=json.loads(first.get_json()['output']);b=json.loads(invoke(assigned,'local_review',args).get_json()['output'])
    assert a['status']=='queued' and a['job_id']==b['job_id']
    with closing(connect(path)) as conn:
        assert conn.execute('SELECT count(*) FROM hb_local_jobs').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM peer_messages').fetchone()[0]==1


def test_instructor_request_uses_actual_local_review_before_online(assigned):
    client,_,path,rid,task=assigned
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':rid})
    try:
        with closing(connect(path)) as conn,conn:
            gate=peers.request_help(conn,1,'gemini','Explain the missing source','Actual404')
            assert gate['status']=='local_review_queued' and gate['request_ids']==[]
            jid=gate['local_job_id']
        assert jobs.run_one('review',reviewer=lambda *args:{'advice':'Use source discovery.','need_online':False,'reason':'Local tools suffice.','model':'fred-cpu:24b'})
        with closing(connect(path)) as conn,conn:
            second=peers.request_help(conn,1,'gemini','Explain the missing source','Actual404')
            assert second['status']=='not_queued' and second['local_job_id']==jid
            assert not conn.execute("SELECT 1 FROM peer_messages WHERE recipient='gemini-advisor'").fetchone()
            assert conn.execute('SELECT notification_request_id FROM hb_local_jobs').fetchone()[0]
        assert jobs.run_one('review',reviewer=lambda *args:pytest.fail('Re-executed completed review')) is False
    finally:agent_identity.CURRENT.reset(token)


def test_recorded_local_review_can_allow_a_remaining_online_need(assigned):
    client,_,path,rid,task=assigned
    invoke(assigned,'local_review',{'question':'Explicit Gemini connection test','evidence':'Local worker ready'})
    jobs.run_one('review',reviewer=lambda *args:{'advice':'One fresh provider request is needed.','need_online':True,'reason':'Owner requested actual connectivity.','model':'fred-cpu:24b'})
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':rid})
    try:
        with closing(connect(path)) as conn,conn:
            result=peers.request_help(conn,1,'gemini','Explicit Gemini connection test','Local worker ready')
            assert result['status']=='queued' and result['request_ids']
            assert conn.execute("SELECT count(*) FROM peer_messages WHERE recipient='gemini-advisor'").fetchone()[0]==1
    finally:agent_identity.CURRENT.reset(token)


def test_local_job_cancelled_before_start_cannot_infer_or_notify(assigned):
    _,_,path,rid,task=assigned
    invoke(assigned,'local_review',{'question':'Review exact evidence'})
    with closing(connect(path)) as conn,conn:conn.execute("UPDATE hb_tasks SET state='cancelled' WHERE task_id=?",(task['task_id'],))
    jobs.run_one('review',reviewer=lambda *args:pytest.fail('Cancelled job inferred'))
    with closing(connect(path)) as conn:
        row=conn.execute('SELECT status,notification_request_id FROM hb_local_jobs').fetchone()
        assert tuple(row)==('cancelled',None)


def test_changed_instructions_discard_late_job_notification(assigned):
    _,_,path,rid,task=assigned
    invoke(assigned,'local_review',{'question':'Review original facts'})
    def change(*args):
        with closing(connect(path)) as conn,conn:conn.execute('UPDATE hb_tasks SET version=version+1 WHERE task_id=?',(task['task_id'],))
        return {'advice':'Old advice','need_online':False,'reason':'Original facts'}
    jobs.run_one('review',reviewer=change)
    with closing(connect(path)) as conn:assert conn.execute('SELECT notification_request_id FROM hb_local_jobs').fetchone()[0] is None


def test_archive_tool_is_restricted_to_the_owner_approved_studio_step(assigned):
    response=invoke(assigned,'archive_acquire',{})
    assert response.status_code==403
    assert 'approved six-file' in response.get_json()['error']


def test_explicit_direct_gemini_address_does_not_create_a_local_review(assigned):
    _,_,path,_,_=assigned
    with closing(connect(path)) as conn,conn:
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','@gemini explicit question')").lastrowid
        requests=peers.enqueue(conn,1,mid,'@gemini explicit question',['gemini-advisor'],sender='user')
        assert requests
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_local_jobs'").fetchone()


def test_instructor_can_narrow_an_invitation_without_granting_other_tools(assigned):
    _,_,path,rid,task=assigned
    with closing(connect(path)) as conn,conn:
        hb_tasks.event(conn,task,'codex-instructor','tool_scope',{'allowed_tools':['task_context','read_file']},request_id=rid)
    denied=invoke(assigned,'studio_task',{'title':'Unrequested plan','content':'No source work'})
    assert denied.status_code==403 and 'focused invitation' in denied.get_json()['error']
    assert invoke(assigned,'task_context',{}).status_code==200


def test_identical_child_planning_does_not_create_duplicate_steps(assigned):
    args={'title':'One bounded child step','content':'Verify one local change.'}
    a=json.loads(invoke(assigned,'studio_task',args).get_json()['output'])
    b=json.loads(invoke(assigned,'studio_task',args).get_json()['output'])
    assert a['step_id']==b['step_id'] and b['deduplicated'] is True


def test_automatic_apex_dispatch_cannot_bypass_the_larger_local_gate(assigned):
    _,_,path,rid,task=assigned
    with closing(connect(path)) as conn,conn:
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'apex','@gemini help with a local source error')").lastrowid
        hb_tasks.bind(conn,1,mid,task_id=task['task_id'],kind='relay')
        requests=peers.enqueue(conn,1,mid,'@gemini help with a local source error',['gemini-advisor'],sender='apex',parent_request_id=rid)
        assert requests==[]
        assert conn.execute("SELECT count(*) FROM hb_local_jobs WHERE kind='review'").fetchone()[0]==1
        assert not conn.execute("SELECT 1 FROM peer_messages WHERE recipient='gemini-advisor'").fetchone()


def test_job_return_preserves_its_focused_tool_scope(assigned):
    _,_,path,rid,task=assigned
    tools=['task_context','local_review','local_job_status']
    with closing(connect(path)) as conn,conn:hb_tasks.event(conn,task,'codex-instructor','tool_scope',{'allowed_tools':tools},request_id=rid)
    assert invoke(assigned,'local_review',{'question':'Review local facts'}).status_code==200
    jobs.run_one('review',reviewer=lambda *args:{'advice':'Use local source','need_online':False,'reason':'Known facts'})
    with closing(connect(path)) as conn:
        notified=conn.execute('SELECT notification_request_id FROM hb_local_jobs').fetchone()[0]
        assert hb_tasks.invitation_tools(conn,notified)==set(tools)


def test_prior_gemini_address_does_not_bypass_local_review_for_later_local_request(assigned):
    _,_,path,_,task=assigned
    with closing(connect(path)) as conn,conn:
        first=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','@gemini check your connection')").lastrowid
        hb_tasks.bind(conn,1,first,task_id=task['task_id'])
        assert jobs.explicitly_requested(conn,task,'gemini-advisor') is True
        later=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','APEX inspect the existing local files')").lastrowid
        hb_tasks.bind(conn,1,later,task_id=task['task_id'])
        assert jobs.explicitly_requested(conn,task,'gemini-advisor') is False


def test_other_task_can_read_completed_approved_acquisition_in_same_chat(assigned,monkeypatch):
    from core import hf_acquisition
    _,_,path,rid,task=assigned
    monkeypatch.setattr(hf_acquisition,'manifest',lambda:{'project_id':task['project_id'],'step_id':task['step_id'],'sha256':'fixed-approved-hash'})
    first=json.loads(invoke(assigned,'archive_acquire',{}).get_json()['output'])
    with closing(connect(path)) as conn,conn:
        conn.execute("UPDATE hb_local_jobs SET status='completed',result=? WHERE job_id=?",(json.dumps({'status':'verified_and_indexed'}),first['job_id']))
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'user','What happened to the HF files?')").lastrowid
        other=hb_tasks.bind(conn,1,mid)
        second_rid=peers.enqueue(conn,1,mid,'Inspect the existing HF job',['apex'],sender='user')[0]
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':second_rid})
    try:result=jobs.call('archive_acquire',{})
    finally:agent_identity.CURRENT.reset(token)
    assert result['job_id']==first['job_id'] and result['read_only_existing_result'] is True
    assert result['task_id']==task['task_id'] and other['task_id']!=task['task_id']
    with closing(connect(path)) as conn:
        assert conn.execute('SELECT count(*) FROM hb_local_jobs').fetchone()[0]==1


def test_local_gate_return_preserves_exact_question_peer_and_resume_scope(assigned):
    _,_,path,rid,task=assigned
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':rid})
    question='Reply only CURRENT_PROVIDER_CHECK'
    try:
        with closing(connect(path)) as conn,conn:
            hb_tasks.event(conn,task,'codex-instructor','tool_scope',{'allowed_tools':['ask_instructor']},request_id=rid)
            result=peers.request_help(conn,1,'gemini',question,'Actual local tests passed')
            assert result['status']=='local_review_queued'
            payload=json.loads(conn.execute('SELECT payload FROM hb_local_jobs').fetchone()[0])
            assert payload['question']==question and payload['requested_peer']=='gemini-advisor'
        assert jobs.run_one('review',reviewer=lambda *_:{'advice':'Only a live provider reply proves this test.','need_online':True,'reason':'Actual connection check','model':'fred-cpu:24b'})
        with closing(connect(path)) as conn:
            reply_id=conn.execute('SELECT notification_request_id FROM hb_local_jobs').fetchone()[0]
            body=conn.execute('SELECT body FROM peer_messages WHERE id=?',(reply_id,)).fetchone()[0]
            assert question in body and 'gemini-advisor' in body and 'resume ask_instructor once' in body
            assert hb_tasks.invitation_tools(conn,reply_id)=={'ask_instructor'}
    finally:agent_identity.CURRENT.reset(token)


def test_larger_review_reads_real_source_facts_without_its_own_queue_status(assigned):
    from core import hb_local_review
    _,_,path,_,task=assigned
    with closing(connect(path)) as conn,conn:
        hb_tasks.event(conn,task,'apex','tool_result',{'tool':'ask_instructor','status':'succeeded','output':'Wait for a local review; the review is queued'})
        hb_tasks.event(conn,task,'apex','progress',{'stage':'Local review queued'})
        hb_tasks.event(conn,task,'apex','test_result',{'verdict':'PASS:23 passed','alm_run_id':'actual-local-test'})
        result=hb_local_review._task_packet(conn,task)
    text=json.dumps(result)
    assert 'actual-local-test' in text and '23 passed' in text
    assert 'Wait for a local review' not in text and 'Local review queued' not in text


def test_exact_host_authorized_provider_probe_is_direct_but_unrelated_questions_are_local(assigned):
    _,_,path,rid,task=assigned
    question='Reply only VERIFIED_PROVIDER_PROBE'
    with closing(connect(path)) as conn,conn:
        hb_tasks.event(conn,task,'codex-instructor','tool_scope',{'allowed_tools':['ask_instructor'],'owner_authorized_provider_probe':{'peer':'gemini-advisor','question':question}},request_id=rid)
        assert jobs.explicitly_requested(conn,task,'gemini-advisor',question,rid)
        assert not jobs.explicitly_requested(conn,task,'gemini-advisor','Do a local source lookup',rid)
        assert not jobs.explicitly_requested(conn,task,'codex-instructor',question,rid)
        token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'peer_request_id':rid})
        try:result=peers.request_help(conn,1,'gemini',question,'Owner asked for one real Google reply')
        finally:agent_identity.CURRENT.reset(token)
        assert result['status']=='queued' and result['request_ids']
        exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_local_jobs'").fetchone()
        assert not exists or not conn.execute("SELECT 1 FROM hb_local_jobs WHERE kind='review'").fetchone()


def test_fred_sees_instructions_coaching_and_failed_attempts_and_must_propose_a_call(assigned):
    """Owner 13 Nov: Fred guessed instead of proposing code because it never saw the step, the coaching or APEX's failed patches."""
    from pathlib import Path
    from core import hb_local_review
    _,_,path,_,task=assigned
    with closing(connect(path)) as conn,conn:
        conn.execute("UPDATE hb_tasks SET objective='Do: patch X\\nexact_old_text: foo' WHERE task_id=?",(task['task_id'],))
        hb_tasks.event(conn,task,'claude-code','task_plan',{'next_action':'Coaching: only patch 3 is left'})
        hb_tasks.event(conn,task,'apex','tool_failure',{'tool':'propose_patch','error':'Exact patch text matched 0 locations'})
        packet=hb_local_review._task_packet(conn,hb_tasks.get(conn,task['task_id']))
    text=json.dumps(packet)
    assert 'exact_old_text: foo' in packet['step_instructions'] and 'only patch 3 is left' in packet['latest_reviewer_coaching']
    assert 'matched 0 locations' in text
    source=(Path(__file__).resolve().parents[1]/'core'/'hb_local_review.py').read_text()
    assert "'required':['advice','proposed_call','need_online','reason']" in source and 'Mistral Small 3' in source
