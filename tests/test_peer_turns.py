import json
import sqlite3

import pytest
from core import peer_bridge as peers, peer_turns as turns


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(peers,'HANDOFF_DELAY_S',0)
    conn=sqlite3.connect(':memory:')
    conn.executescript('''CREATE TABLE conversations(id INTEGER PRIMARY KEY,title TEXT);
        INSERT INTO conversations VALUES(1,'Owner task');
        CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id INTEGER,from_agent TEXT,to_agent TEXT,
        content TEXT,message_type TEXT,tokens_used INTEGER DEFAULT 0,created_at TEXT);''')
    peers.ensure_schema(conn)
    principals={name:peers.authenticate(conn,peers.issue_token(conn,name))
                for name in ['apex','codex-instructor','gemini-advisor']}
    yield conn,principals
    conn.close()


def owner(conn,target='codex-instructor'):
    message=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(1,'user',?,'Assess the existing file proposal; keep downloads paused','chat')",(target,)).lastrowid
    return peers.enqueue(conn,1,message,'Assess the existing file proposal; keep downloads paused',[target],sender='ghost')[0]


def reply(conn,principal,request,text,**kwargs):
    result=peers.post(conn,principal,1,text,reply_to_request_id=request,**kwargs)
    state='failed' if kwargs.get('outcome')=='failed' else 'completed'
    conn.execute('UPDATE hb_peer_work SET state=? WHERE request_id=?',(state,request))
    peers.acknowledge(conn,principal,[request]) if state=='completed' else None
    return result


def four_handoffs(flow):
    conn,p=flow
    first=owner(conn)
    one=reply(conn,p['codex-instructor'],first,'Here is the reviewed shortlist.')
    second=one['handoff']['queued'][0]
    two=reply(conn,p['apex'],second,'Please verify the remaining evidence @codex')
    third=two['handoff']['queued'][0]
    three=reply(conn,p['codex-instructor'],third,'The records show three pending candidates.')
    fourth=three['handoff']['queued'][0]
    four=reply(conn,p['apex'],fourth,'One more check is needed @codex')
    return four['handoff']['queued'][0],three['message_id']


def test_plain_instructor_reply_returns_to_apex_without_transport_mentions(flow):
    conn,p=flow;first=owner(conn)
    result=reply(conn,p['codex-instructor'],first,'Review of the file proposal: these entries are pending.')
    inbox=peers.inbox(conn,p['apex'],pending_only=True)
    assert [row['id'] for row in inbox]==result['handoff']['queued']
    assert inbox[0]['routing']['parent_request_id']==first
    assert inbox[0]['routing']['turn']==2
    assert conn.execute('SELECT from_agent FROM messages WHERE id=?',(result['message_id'],)).fetchone()[0]=='codex-instructor'


def test_a_quoted_online_mention_cannot_swallow_the_correlated_apex_return(flow):
    conn,p=flow;first=owner(conn)
    result=reply(conn,p['codex-instructor'],first,'The earlier @gemini request failed; use this evidence.')
    request=result['handoff']['queued'][0]
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(request,)).fetchone()[0]=='apex'
    assert 'gemini-advisor' in result['handoff']['refused']


def test_status_messages_observers_and_multipart_replies_do_not_spend_handoffs(flow):
    conn,p=flow;first=owner(conn)
    for n in range(20):
        peers.post(conn,p['codex-instructor'],1,'Status '+str(n),reply_to_request_id=first,route_reply=False)
    peers.enqueue(conn,1,99,'[TEAM COPY, observe: do not execute]', ['gemini-advisor'])
    assert turns.current(conn,1)['turns']==1
    result=reply(conn,p['codex-instructor'],first,'Final part of the reviewed result.')
    assert turns.current(conn,1)['turns']==2
    assert len(result['handoff']['queued'])==1


def test_four_handoffs_queue_one_decision_and_never_require_a_retyped_owner_prompt(flow):
    conn,p=flow;decision,_=four_handoffs(flow)
    info=turns.route(conn,decision)
    assert info['kind']=='decision' and info['turn']==4
    assert turns.current(conn,1)['state']=='awaiting_decision'
    assert conn.execute('SELECT count(*) FROM hb_peer_routes WHERE kind=\'work\'').fetchone()[0]==4
    assert conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(decision,)).fetchone()[0]=='apex'
    assert peers.inbox(conn,p['apex'],pending_only=True)[0]['id']==decision
    extra=peers.post(conn,p['codex-instructor'],1,'A second late result also needs review.')
    assert extra['handoff']['queued']==[decision]
    assert conn.execute("SELECT count(*) FROM hb_peer_routes WHERE kind='decision'").fetchone()[0]==1


def test_decision_waits_for_all_prior_requests_to_settle(flow):
    conn,p=flow;decision,_=four_handoffs(flow)
    old=conn.execute("SELECT request_id FROM hb_peer_routes WHERE kind='work' LIMIT 1").fetchone()[0]
    conn.execute("UPDATE hb_peer_work SET state='running' WHERE request_id=?",(old,))
    assert not turns.ready(conn,decision)
    assert decision not in [r['id'] for r in peers.inbox(conn,p['apex'],pending_only=True)]
    conn.execute("UPDATE hb_peer_work SET state='completed' WHERE request_id=?",(old,))
    assert turns.ready(conn,decision)


def test_finish_is_a_recorded_round_decision_without_marking_studio_tasks_complete(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    result=reply(conn,p['apex'],decision,'I have finished reviewing this exchange.',decision={
        'action':'finish','reason':'The available evidence has been reported.','next_task':'','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='finish' and not result['handoff']['queued']
    assert turns.current(conn,1)['state']=='finished'
    assert 'HB round outcome: finish' in conn.execute('SELECT content FROM messages WHERE id=?',(result['message_id'],)).fetchone()[0]
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_steps'").fetchone()


def test_progress_backed_decision_starts_a_new_bounded_round_with_the_same_owner_scope(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    original=turns.current(conn,1)['owner_message_id']
    result=reply(conn,p['apex'],decision,'Continue with one bounded check.',decision={
        'action':'continue','reason':'The last review supplied new candidate evidence.',
        'next_task':'Compare the two remaining filenames. Keep downloads paused.','evidence_message_ids':[evidence]})
    state=turns.current(conn,1)
    assert state['cycle']==2 and state['turns']==1 and state['owner_message_id']==original
    request=result['handoff']['queued'][0]
    assert turns.route(conn,request)['cycle']==2
    body=json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?',(request,)).fetchone()[0])
    assert body['owner_message_id']==original and 'existing grants' in body['constraints']
    assert conn.execute("SELECT count(*) FROM messages WHERE from_agent='user'").fetchone()[0]==1


def test_failed_provider_is_returned_to_apex_but_cannot_be_replayed_by_a_continuation(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    old=conn.execute("SELECT request_id FROM hb_peer_routes WHERE kind='work' LIMIT 1").fetchone()[0]
    conn.execute("UPDATE hb_peer_work SET state='failed' WHERE request_id=?",(old,))
    result=reply(conn,p['apex'],decision,'Continue.',decision={'action':'continue','reason':'Try again',
        'next_task':'Retry the failed request','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='continue' and result['handoff']['queued']
    assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(old,)).fetchone()[0]=='failed'
    assert result['handoff']['queued'][0]!=old


def test_decision_requires_real_progress_but_advisory_token_counts_do_not_end_work(flow,monkeypatch):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    from core import hb_tasks
    task=hb_tasks.for_request(conn,decision)
    conn.execute('UPDATE hb_tasks SET token_budget=0 WHERE task_id=?',(task['task_id'],))
    result=reply(conn,p['apex'],decision,'Continue.',decision={'action':'continue','reason':'More work',
        'next_task':'One more check','evidence_message_ids':[evidence]})
    assert result['decision']['action']=='continue' and result['handoff']['queued']


def test_a_new_owner_topic_preserves_an_earlier_tasks_reply_scope(flow):
    conn,p=flow;first=owner(conn)
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content) VALUES(1,'user','apex','Stop that work and inspect a different task')")
    result=reply(conn,p['codex-instructor'],first,'This was the old result.')
    assert result['handoff']['queued']
    from core import hb_tasks
    assert hb_tasks.for_request(conn,result['handoff']['queued'][0])['root_message_id']==hb_tasks.for_request(conn,first)['root_message_id']
    assert turns.current(conn,1)['turns']==0


def test_reply_correlation_cannot_impersonate_another_agent_or_thread(flow):
    conn,p=flow;first=owner(conn)
    with pytest.raises(peers.PeerError) as error:
        peers.post(conn,p['gemini-advisor'],1,'Forged result',reply_to_request_id=first)
    assert error.value.status==403


def test_an_invited_peer_still_cannot_reply_as_another_request_owner(flow):
    conn,p=flow;first=owner(conn)
    message=conn.execute("INSERT INTO messages(conversation_id,from_agent,content) VALUES(1,'apex','Separate Gemini question')").lastrowid
    conn.execute("UPDATE messages SET content=content || ' @gemini explicit question' WHERE id=(SELECT MAX(id) FROM messages WHERE from_agent='user')")
    peers.enqueue(conn,1,message,'Separate question',['gemini-advisor'],sender='apex')
    with pytest.raises(peers.PeerError,match='correlation') as error:
        peers.post(conn,p['gemini-advisor'],1,'Forged result',reply_to_request_id=first)
    assert error.value.status==403


def test_unrelated_instructor_status_can_explicitly_opt_out_of_automatic_routing(flow):
    conn,p=flow;owner(conn)
    result=peers.post(conn,p['codex-instructor'],1,'A display-only status.',route_reply=False)
    assert result['handoff']=={'queued':[],'locked':False}


def test_a_second_round_remains_four_handoffs_and_can_continue_to_a_third_with_evidence(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow)
    initial=reply(conn,p['apex'],decision,'Continue the comparison.',decision={
        'action':'continue','reason':'New evidence is available.','next_task':'Compare the remaining entries.',
        'evidence_message_ids':[evidence]})
    first=initial['handoff']['queued'][0]
    two=reply(conn,p['apex'],first,'Review this concrete finding @codex')['handoff']['queued'][0]
    three=reply(conn,p['codex-instructor'],two,'There is new verified file evidence.')
    fourth=three['handoff']['queued'][0]
    next_request=reply(conn,p['apex'],fourth,'One more review @codex')['handoff']['queued'][0]
    last=reply(conn,p['codex-instructor'],next_request,'The final review is available.')
    decision2=last['handoff']['queued'][0]
    assert turns.route(conn,decision2)['kind']=='decision' and turns.current(conn,1)['turns']==4
    result=reply(conn,p['apex'],decision2,'Continue again.',decision={'action':'continue','reason':'More review',
        'next_task':'Repeat the process','evidence_message_ids':[last['message_id']]})
    assert result['decision']['action']=='continue' and result['handoff']['queued']
    assert turns.route(conn,result['handoff']['queued'][0])['cycle']==3
    assert conn.execute("SELECT count(*) FROM hb_peer_routes WHERE kind='work'").fetchone()[0]==9
    assert conn.execute("SELECT count(*) FROM hb_peer_routes WHERE kind='decision'").fetchone()[0]==2


def test_a_continuation_cannot_use_only_the_original_operator_message_as_progress(flow):
    conn,p=flow;decision,_=four_handoffs(flow)
    original=turns.current(conn,1)['owner_message_id']
    result=reply(conn,p['apex'],decision,'Continue.',decision={'action':'continue','reason':'More work',
        'next_task':'Repeat the original request','evidence_message_ids':[original]})
    assert result['decision']['action']=='needs_review' and result['handoff']['queued']==[]


def test_invalid_decision_rolls_back_without_ghost_memory_or_a_fresh_round(flow):
    conn,p=flow;decision,evidence=four_handoffs(flow);conn.commit()
    before=conn.execute('SELECT count(*) FROM messages').fetchone()[0]
    memory=conn.execute('SELECT count(*) FROM service_memory').fetchone()[0]
    with pytest.raises(peers.PeerError):
        with conn:
            peers.post(conn,p['apex'],1,'Invalid decision',reply_to_request_id=decision,decision={
                'action':[], 'reason':'Invalid action type','next_task':'','evidence_message_ids':[evidence]})
    assert conn.execute('SELECT count(*) FROM messages').fetchone()[0]==before
    assert conn.execute('SELECT count(*) FROM service_memory').fetchone()[0]==memory
    assert turns.current(conn,1)['state']=='awaiting_decision'
