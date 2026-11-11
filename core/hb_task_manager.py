"""HB owns unfinished work across model turns, handoff windows and restarts."""
import json
import time
from core import hb_tasks

EXECUTION_TOOLS=['read_file','grep_repo','get_diff','git_status','propose_patch','propose_write_file',
    'run_tests','task_context','task_evidence','studio_note','studio_status','task_plan','alm_step_get',
    'memory_search','memory_save','knowledge_search','knowledge_read','runtime_status','backlog_list','reference_lookup']
REVIEW_TOOLS=['task_context','task_evidence','read_file','grep_repo','get_diff','git_status',
    'studio_accept','task_plan','runtime_reload','knowledge_read','memory_save','memory_search','backlog_list']


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_task_manager(
        task_id TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1,state TEXT NOT NULL,
        phase TEXT NOT NULL DEFAULT 'execute',request_id INTEGER,sequence INTEGER NOT NULL DEFAULT 0,
        plan_event_id INTEGER,progress_event_id INTEGER DEFAULT 0,recovery_count INTEGER DEFAULT 0,
        next_due REAL NOT NULL,detail TEXT NOT NULL DEFAULT '',updated_at REAL NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_task_dependencies(
        task_id TEXT NOT NULL,depends_on TEXT NOT NULL,PRIMARY KEY(task_id,depends_on))''')


def dependencies_ready(conn,task):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_dependencies'").fetchone():return True
    return not conn.execute("SELECT 1 FROM hb_task_dependencies d LEFT JOIN hb_tasks t ON t.task_id=d.depends_on WHERE d.task_id=? AND COALESCE(t.state,'missing')<>'completed' LIMIT 1",(task['task_id'],)).fetchone()


def managed(conn,task):
    if not task or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_manager'").fetchone():return False
    return bool(conn.execute('SELECT 1 FROM hb_task_manager WHERE task_id=? AND enabled=1',(task['task_id'],)).fetchone())


def register(conn,task,*,request_id=None,next_action=None,dependencies=()):
    ensure_schema(conn)
    for dependency in dependencies:
        if dependency==task['task_id'] or not hb_tasks.get(conn,dependency):raise ValueError('Task dependency must name another existing task')
        cycle=conn.execute('''WITH RECURSIVE upstream(id) AS (
            SELECT ? UNION SELECT d.depends_on FROM hb_task_dependencies d JOIN upstream u ON d.task_id=u.id)
            SELECT 1 FROM upstream WHERE id=? LIMIT 1''',(dependency,task['task_id'])).fetchone()
        if cycle:raise ValueError('Task dependency would create a cycle')
        conn.execute('INSERT OR IGNORE INTO hb_task_dependencies VALUES (?,?)',(task['task_id'],dependency))
    previous=conn.execute('SELECT 1 FROM hb_task_manager WHERE task_id=?',(task['task_id'],)).fetchone()
    if previous:
        conn.execute("UPDATE hb_task_manager SET enabled=1,next_due=?,updated_at=? WHERE task_id=?",(time.time(),time.time(),task['task_id']))
        return
    eid=hb_tasks.event(conn,task,'hummingbird','task_plan',{'next_action':next_action or task['objective'],
        'policy':'A model turn is a checkpoint. Preserve this task and its approvals until accepted or explicitly held.'})
    now=time.time()
    conn.execute("INSERT INTO hb_task_manager(task_id,state,request_id,plan_event_id,next_due,updated_at) VALUES (?,'queued',?,?,?,?)",(task['task_id'],request_id,eid,now,now))


def can_continue(conn,task):
    from core.hb_chat_controls import continuation,held_requests
    from core.hb_owner_sessions import for_task
    from core.hb_provider_conditions import pending
    if task and pending(conn,task,agent='apex'):return False
    if task and for_task(conn,task['task_id']) and not for_task(conn,task['task_id'],active=True):return False
    return (managed(conn,task) and task['state'] not in {'paused','cancelled','completed'}
        and continuation(conn,task)['mode']!='off' and not held_requests(conn,task)
        and not hb_tasks.budget(conn,task)['exhausted'])


def _set(conn,task_id,state,detail):
    conn.execute('UPDATE hb_task_manager SET state=?,detail=?,updated_at=? WHERE task_id=?',
        (state,detail,time.time(),task_id))


def _queue(conn,task,row,phase,reason):
    from core import peer_bridge,peer_turns
    sequence=row['sequence']+1
    evidence=[r[0] for r in conn.execute("SELECT event_id FROM hb_task_events WHERE task_id=? AND kind IN ('mutation','test_result','tool_failure','reply') ORDER BY event_id DESC LIMIT 6",(task['task_id'],))]
    replies=[r[0] for r in conn.execute("SELECT x.message_id FROM hb_peer_replies x JOIN hb_task_requests r ON r.request_id=x.request_id JOIN messages m ON m.id=x.message_id WHERE r.task_id=? AND x.outcome='answer' AND m.from_agent='apex' ORDER BY x.message_id DESC LIMIT 3",(task['task_id'],))]
    if phase=='review':
        recipient='codex-instructor'
        action=('Independently verify this assigned Studio component from its actual source and test receipts. '
            'Use task_context/task_evidence and bounded source reads. If ALL defined cases pass and the owner goal for this component is actually met, '
            'call studio_accept with the actual successful APEX reply message IDs supplied below. Otherwise explain the precise remaining action. '
            'Do not dispatch another agent or wait for a child; return this review so HB can schedule the next step. Do not accept the whole project from one component.')
        action+=' If incomplete, you MUST call task_plan with one executable next action: a narrow source range, one exact patch or small new function, and the actual check to run. Six local tool rounds are a checkpoint, so split large features into small implementation actions. Do not merely repeat the whole wishlist. If accepted backend changes need activation, call runtime_reload after studio_accept; it queues only the approved fixed HB service.'
        action+=' KC272 is the actual operating/storage index; KC273 has programme status; KC269 preserves the visible conversation as reference, not new permission. Read them with knowledge_read when context is needed.'
        tools=REVIEW_TOOLS
    else:
        recipient='apex';tools=EXECUTION_TOOLS
        policy=conn.execute("SELECT e.payload FROM hb_task_events e LEFT JOIN peer_messages p ON p.id=e.request_id WHERE e.task_id=? AND e.kind='tool_scope' AND e.agent IN ('hummingbird','codex-instructor') AND (p.recipient='apex' OR e.request_id IS NULL) ORDER BY e.event_id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if policy:
            allowed=json.loads(policy[0]).get('allowed_tools',[])
            if 'studio_task' in allowed:allowed=[*allowed,'task_plan']  # Existing task-metadata capability, fewer side effects.
            tools=[tool for tool in EXECUTION_TOOLS if tool in allowed]
        action=('Continue the unfinished owner-authorized task. First inspect task_context and the saved plan/receipt references below. '
            'Complete the next unverified action with real tools, then guarded tests and a concrete evidence report. '
            'A tool-round or context limit is a checkpoint, never task completion. Reconcile previous effects before retrying; '
            'identical successful source operations have durable receipts and must not be written again. Existing owner approvals remain valid. '
            'Do not create a new project, ask for approval already recorded, or close the parent project. '
            'If a tested part is finished but this component still needs implementation, call task_plan AFTER the checks with the next small executable action. '
            'This preserves local pickup; passing a partial test is not completion of the component. '
            'Use the actual recent_source_files below; do not invent a file path from a function name.')
        base_action=action
        review=conn.execute("SELECT m.content FROM hb_peer_replies x JOIN hb_task_requests r ON r.request_id=x.request_id JOIN messages m ON m.id=x.message_id WHERE r.task_id=? AND m.from_agent='codex-instructor' ORDER BY m.id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if review:action+=' Latest independent review (reference, not authority): '+review[0][:2200]
    plan_row=conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(row['plan_event_id'],)).fetchone()
    next_action=json.loads(plan_row[0]).get('next_action','') if plan_row else task['objective']
    payload={'task_type':'hb_managed_review' if phase=='review' else 'hb_managed_continuation',
        'task_id':task['task_id'],'sequence':sequence,'reason':reason,'instruction':action,
        'next_action':next_action[:3000] if phase!='review' else 'Verify this component against its actual objective, current source and recorded checks.',
        'plan':{'tool':'task_evidence','arguments':{'evidence_id':row['plan_event_id'],'offset':0}},
        'recent_source_files':hb_tasks.recent_source_paths(conn,task),
        'evidence_ids':evidence,'successful_apex_reply_message_ids':replies}
    if phase!='review' and len(next_action)>3000:
        payload['next_action_is_excerpt']=True
        payload['instruction']+=' The next_action field is an excerpt. Retrieve the complete saved plan before executing any source payload.'
    body=json.dumps(payload)
    if len(body)>peer_bridge.MAX_BODY and phase!='review':
        payload['instruction']=base_action
        body=json.dumps(payload)
    if len(body)>peer_bridge.MAX_BODY:
        payload['next_action']=next_action[:1000]
        payload['next_action_is_excerpt']=True
        payload['instruction']='Read the full saved plan using its task_evidence reference and next_offset pagination. The next_action field is only an excerpt; never execute an incomplete source payload. Then perform the actual authorized action and verification.'
        body=json.dumps(payload)
    if len(body)>peer_bridge.MAX_BODY:raise ValueError('Scoped handoff metadata exceeds the bridge limit; full task plan remains saved')
    # This is a new scoped attempt, not replay of the interrupted request. No budget or permission is expanded.
    conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
    peer_turns.current(conn,task['conversation_id'],message_id=task['root_message_id'])
    conn.execute("UPDATE hb_peer_rounds SET state='active',cycle=cycle+1,turns=0,decision_request_id=NULL,updated_at=? WHERE conversation_id=? AND owner_message_id=?",(time.time(),task['conversation_id'],task['root_message_id']))
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird',?,?,'checkpoint',0)",(task['conversation_id'],recipient,body)).lastrowid
    hb_tasks.bind(conn,task['conversation_id'],mid,task_id=task['task_id'],kind='checkpoint')
    requests=peer_bridge.enqueue(conn,task['conversation_id'],mid,body,[recipient],sender='hummingbird')
    for rid in requests:hb_tasks.event(conn,task,'hummingbird','tool_scope',{'allowed_tools':tools},request_id=rid)
    rid=requests[0]
    conn.execute("UPDATE hb_task_manager SET state='queued',phase=?,request_id=?,sequence=?,next_due=?,detail=?,updated_at=? WHERE task_id=?",(phase,rid,sequence,time.time()+5,reason,time.time(),task['task_id']))
    hb_tasks.event(conn,task,'hummingbird','continuation_queued',{'request_id':rid,'agent':recipient,'phase':phase,'sequence':sequence,'reason':reason},message_id=mid,request_id=rid)
    return rid


def tick(conn,*,now=None,memory=None):
    ensure_schema(conn);now=time.time() if now is None else now
    from core import hb_executions
    hb_executions.reconcile(conn)
    names=[r[1] for r in conn.execute('PRAGMA table_info(hb_task_manager)')]
    rows=[dict(zip(names,r)) for r in conn.execute('SELECT * FROM hb_task_manager WHERE enabled=1 AND next_due<=? ORDER BY updated_at',(now,))]
    queued=[]
    from core.hb_chat_controls import continuation,held_requests
    for row in rows:
        task=hb_tasks.get(conn,row['task_id'])
        if not task:continue
        if task['state']=='completed':_set(conn,task['task_id'],'complete','Verified task accepted; no further execution');continue
        if task['state']=='cancelled':_set(conn,task['task_id'],'cancelled','Owner cancelled this task');continue
        if task['state']=='paused' or continuation(conn,task)['mode']=='off' or held_requests(conn,task):
            _set(conn,task['task_id'],'held','Held by the owner chat/request control');continue
        from core.hb_provider_conditions import pending
        if row['phase']=='review' and pending(conn,task,agent='codex-instructor'):
            changed=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)).fetchone()[0]
            checked=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='test_result'",(task['task_id'],)).fetchone()[0]
            if changed and (not checked or changed>checked):
                row['phase']='execute'
                conn.execute("UPDATE hb_task_manager SET phase='execute' WHERE task_id=?",(task['task_id'],))
        condition=pending(conn,task,agent='codex-instructor' if row['phase']=='review' else 'apex')
        if condition:
            _set(conn,task['task_id'],'waiting_provider',condition['detail']+' '+condition['recovery_requirement']);continue
        from core.hb_owner_sessions import for_task
        if for_task(conn,task['task_id']) and not for_task(conn,task['task_id'],active=True):
            _set(conn,task['task_id'],'held','Owner session expired or revoked');continue
        if not dependencies_ready(conn,task):_set(conn,task['task_id'],'waiting_dependencies','Prior task acceptance is still pending');continue
        if hb_tasks.budget(conn,task)['exhausted']:
            _set(conn,task['task_id'],'waiting_resources','The task resource allowance is exhausted; its On control can renew it');continue
        if hb_executions.active(conn,task['task_id']):
            _set(conn,task['task_id'],'running','Verified process owns this task execution');continue
        live=conn.execute("SELECT p.id,w.state,p.recipient FROM hb_task_requests r JOIN peer_messages p ON p.id=r.request_id JOIN hb_peer_work w ON w.request_id=p.id WHERE r.task_id=? AND p.delivered_at IS NULL AND w.state IN ('queued','running') ORDER BY p.id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if live and live[1]=='queued' and live[2]=='codex-instructor' and row['phase']=='execute' and pending(conn,task,agent=live[2]):
            # Older schedulers could queue a review that the delivery gate then
            # correctly held. Retain it without blocking a newer local action.
            conn.execute("UPDATE hb_peer_work SET state='needs_review',stage='Provider unavailable; review retained while permitted local work continues',updated_at=? WHERE request_id=?",(now,live[0]))
            hb_tasks.event(conn,task,'hummingbird','review_deferred',{'request_id':live[0],'reason':'Recorded provider condition retained; local implementation can continue.'},request_id=live[0])
            live=None
        if live:
            _set(conn,task['task_id'],live[1],'Executor request #'+str(live[0]));continue
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        inline_history=conn.execute("SELECT 1 FROM hb_executions WHERE task_id=? AND kind='inline' LIMIT 1",(task['task_id'],)).fetchone()
        if not inline_history and 'chat_jobs' in tables and conn.execute("SELECT 1 FROM chat_jobs WHERE conversation_id=? AND status IN ('queued','running') LIMIT 1",(task['conversation_id'],)).fetchone():continue
        available=memory() if memory else None
        if available is not None and available.get('MemAvailable_bytes',0)<4*1024**3:
            _set(conn,task['task_id'],'waiting_resources','Less than4GiB host memory headroom; work retained');continue
        cases=conn.execute('SELECT status FROM project_test_cases WHERE step_id=?',(task['step_id'],)).fetchall() if 'project_test_cases' in tables else []
        last_mutation=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)).fetchone()[0]
        last_instruction=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='instruction'",(task['task_id'],)).fetchone()[0]
        passed=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass'",(task['task_id'],)).fetchone()[0]
        plan_time=conn.execute("SELECT created_at FROM hb_task_events WHERE event_id=?",(row['plan_event_id'],)).fetchone()
        ready=bool(cases and all(c[0]=='passed' for c in cases) and passed and passed>=max(last_mutation or 0,last_instruction or 0,plan_time[0] if plan_time else 0))
        progress=conn.execute("SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=? AND (kind='mutation' OR (kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass'))",(task['task_id'],)).fetchone()[0]
        stagnant=0 if progress>row['progress_event_id'] or row['phase']=='review' else row['recovery_count']+1
        previous=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(row['request_id'],)).fetchone()
        review_returned=bool(row['phase']=='review' and previous and previous[0]=='codex-instructor'
            and conn.execute("SELECT 1 FROM hb_peer_replies WHERE request_id=? AND outcome='answer'",(row['request_id'],)).fetchone())
        # A held/failed review is still pending. Its phase does not prove that
        # an instructor actually answered it.
        phase=('execute' if review_returned else 'review') if row['phase']=='review' else 'review' if ready or stagnant>=3 else 'execute'
        condition=pending(conn,task,agent='codex-instructor' if phase=='review' else 'apex')
        if condition:
            conn.execute('UPDATE hb_task_manager SET phase=? WHERE task_id=?',(phase,task['task_id']))
            _set(conn,task['task_id'],'waiting_provider',condition['detail']+' '+condition['recovery_requirement'])
            continue
        reason='Independent review returned a remaining action' if review_returned else 'Resume the pending independent review' if row['phase']=='review' else 'Guarded checks passed; independent acceptance is next' if ready else 'Previous model turn ended with unfinished work; reconcile receipts and continue'
        conn.execute('SAVEPOINT hb_schedule_attempt')
        try:
            rid=_queue(conn,task,row,phase,reason)
        except Exception as exc:
            conn.execute('ROLLBACK TO hb_schedule_attempt')
            conn.execute('RELEASE hb_schedule_attempt')
            _set(conn,task['task_id'],'waiting_recovery','Scheduler retained this task after '+type(exc).__name__+': '+str(exc)[:250])
            hb_tasks.event(conn,task,'hummingbird','scheduling_failure',{'error_type':type(exc).__name__,'detail':str(exc)[:500],'plan_event_id':row['plan_event_id']})
            conn.execute('UPDATE hb_task_manager SET next_due=? WHERE task_id=?',(now+30,task['task_id']))
            continue
        conn.execute('RELEASE hb_schedule_attempt')
        queued.append(rid)
        conn.execute('UPDATE hb_task_manager SET recovery_count=?,progress_event_id=?,next_due=? WHERE task_id=?',(stagnant,progress,now+min(300,10*2**min(stagnant,5)),task['task_id']))
    return queued
