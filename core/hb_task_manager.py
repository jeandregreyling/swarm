"""HB owns unfinished work across model turns, handoff windows and restarts."""
import json
import re
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


def _plain_name(conn,task):
    from core.hb_plain import step_name,name
    return step_name(conn,task['step_id'],task.get('title')) if task.get('step_id') else name(task.get('title'))


def ask_owner(conn,task,what,options,kind='halt'):
    """HB halts and asks the owner in the task's own chat (posted once per halt by the callers).
    kind 'plan' marks a workflow plan waiting for approval (shown as "Plan" in the Needs-you bar)."""
    # Owner 13 Nov: readable at a glance: plain question first, ids and commands under Details (the buttons still read them).
    from core.hb_plain import message
    text=message(what,details=[f"task {task['task_id']}",f"step {task['step_id']}" if task.get('step_id') else '',options])
    try:
        mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                         "VALUES (?,'hummingbird','user',?,'response',0)",(task['conversation_id'],text)).lastrowid
    except Exception:
        mid=None                                   # minimal test schemas have no messages table
    hb_tasks.event(conn,task,'hummingbird','owner_question',{'text':text,'message_id':mid,'kind':kind})
    return mid


MAX_CHECKPOINTS_WITHOUT_PASS=8      # DREAM stop rule: checkpoints with no passing check
MAX_REPEATED_FAILURES=3             # DREAM stop rule: identical tool error in a row


FRED_HANDS=('FRED TAKES OVER: you are Fred (Mistral Small 3 24B on the CPU). APEX was stuck on this step. Do not advise - act: read the saved plan '
    'and the failed attempts, make the fix yourself with the attached tools, run the step check, and stop when it passes. Your final answer starts with '
    '"Fred:" and says in 2-4 plain lines what you changed (files), what the check said, and the one next action for APEX if anything is left. ')
LOCAL_HELP_QUESTION=('APEX is stuck on this task: its last turns made no change and no passing check. From the recorded evidence, '
    'name the most likely reason and the single next tool call APEX should make (file, exact text or command), and how it checks the result.')


def local_help(conn,task):
    """Ask the larger local model (Fred) once per progress point. Returns 'submitted', or the existing job's status
    ('queued', 'running', 'completed', 'failed', ...), or 'unavailable: <why>'."""
    from core import hb_local_jobs, hb_model_switches
    if hb_model_switches.modes(conn).get(hb_model_switches.FRED)=='off':
        return 'unavailable: Fred is switched Off in Live status'
    hb_local_jobs.ensure_schema(conn)
    progress=conn.execute("SELECT COALESCE(MAX(created_at),0) FROM hb_task_events WHERE task_id=? AND (kind='mutation' OR "
                          "(kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass'))",(task['task_id'],)).fetchone()[0]
    # Owner 14 Nov: "APEX is throwing everything at Fred" - Fred only takes over steps that have a real spec, never vague ones.
    if task.get('step_id'):
        try:
            row=conn.execute('SELECT description FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()
        except Exception:
            row=None
        from core.hb_plan_workflow import vague_step,SPEC_MARK
        if row and (SPEC_MARK in str(row[0] or '') or vague_step(row[0])):
            return 'unavailable: the step is too vague to build - it needs a spec, not Fred'
    # Owner 14 Nov: "instead of just inspecting and reporting, let it make the fix and tell APEX/HB what it's done - give it some teeth".
    # A stalled task gets ONE Fred working turn per progress point: Fred's model runs the same tools and checks APEX has.
    turns=conn.execute("SELECT request_id FROM hb_task_events WHERE task_id=? AND kind='fred_turn' AND created_at>=? ORDER BY event_id DESC",
                       (task['task_id'],progress)).fetchall()
    if turns:
        state=conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(turns[0][0],)).fetchone()
        state=state[0] if state else ''
        # A Fred turn that crashed (setup, memory, context) does not count as Fred's try: one retry. One that ran and did not solve it does.
        if not (state=='failed' and len(turns)<2):
            return {'queued':'queued','running':'running'}.get(state, 'completed')
    row=conn.execute('SELECT * FROM hb_task_manager WHERE task_id=?',(task['task_id'],))
    names=[d[0] for d in row.description];row=dict(zip(names,row.fetchone()))
    try:
        rid=_queue(conn,task,row,'execute','APEX was stuck: Fred takes over this step with the same tools',model='fred-cpu:24b')
    except (PermissionError,ValueError) as exc:
        return 'unavailable: '+str(exc)[:120]
    hb_tasks.event(conn,task,'hummingbird','fred_turn',{'model':'fred-cpu:24b','why':'stalled; Codex cannot be used'},request_id=rid)
    from core.hb_plain import message
    note=message(f"🛠 Fred is taking over {_plain_name(conn,task)}: APEX was stuck.",
                 'Fred (the larger local model, on the CPU) works with the same tools and checks, makes the fix, runs the check and reports what it did. '
                 'It is slow (often 10-20 min); the queue waits for it.',details=[f"task {task['task_id']}",f'request {rid}'])
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (task['conversation_id'],note)).lastrowid
    hb_tasks.bind(conn,task['conversation_id'],mid,task_id=task['task_id'],kind='reply')
    return 'submitted'


EXTRA_TOOLS={'does_rename','git_clear_stale_lock','layout','change_set'}   # tools a plan step may add with a line 'HB extra tools: a, b'


def step_extra_tools(conn,task):
    if not task.get('step_id'):return []
    try:row=conn.execute('SELECT description FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()
    except Exception:return []
    found=re.search(r'(?m)^HB extra tools:\s*(.+)$',str(row[0] or '')) if row else None
    return [t.strip() for t in found.group(1).split(',') if t.strip() in EXTRA_TOOLS] if found else []


def stuck_reason(conn,task_id):
    """Return a short reason if the task is spinning, else None.

    Counts only since the later of the last passing check and the owner's last
    Continue/On control, so the owner can always grant a fresh allowance.
    """
    def last(sql):
        return conn.execute(sql,(task_id,)).fetchone()[0] or 0
    since=max(last("SELECT MAX(event_id) FROM hb_task_events WHERE task_id=? AND kind='test_result' "
                   "AND json_extract(payload,'$.alm_run_status')='pass'"),
              last("SELECT MAX(event_id) FROM hb_task_events WHERE task_id=? AND kind='continuation_control' AND agent='user' "
                   "AND json_extract(payload,'$.mode')='on'"))
    checkpoints=conn.execute("SELECT COUNT(*) FROM hb_task_events WHERE task_id=? AND kind='checkpoint' AND event_id>?",
                             (task_id,since)).fetchone()[0]
    if checkpoints>=MAX_CHECKPOINTS_WITHOUT_PASS:
        return f'{checkpoints} checkpoints since the last passing check or owner Continue'
    recent=conn.execute("SELECT kind,payload FROM hb_task_events WHERE task_id=? AND event_id>? "
                        "AND kind IN ('tool_failure','mutation') ORDER BY event_id DESC LIMIT ?",
                        (task_id,since,MAX_REPEATED_FAILURES)).fetchall()
    if len(recent)==MAX_REPEATED_FAILURES and all(k=='tool_failure' for k,_ in recent):
        keys=set()
        for _,p in recent:
            try:d=json.loads(p)
            except ValueError:d={}
            keys.add((d.get('tool'),str(d.get('error',''))[:120]))
        if len(keys)==1:
            tool,err=keys.pop()
            return f'{tool} failed {MAX_REPEATED_FAILURES} times in a row with the same error: {err}'
    return None


def review_recipient(conn):
    """Independent review goes to Codex when it is usable; otherwise to the attached VS Code instructor
    (its link used the peer API in the last 15 minutes); otherwise Codex, and the caller reports it."""
    from core.hb_online import usable as codex_usable
    if codex_usable(conn,'codex'):
        return 'codex-instructor'
    try:
        row=conn.execute("SELECT last_used_at FROM service_tokens WHERE principal_id='copilot-instructor' AND revoked_at IS NULL AND last_used_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    except Exception:
        row=None
    if row and time.time()-row[0]<900:
        return 'copilot-instructor'
    return 'codex-instructor'


def review_recipient(conn):
    """Independent review goes to Codex when it is usable; otherwise to the attached VS Code instructor
    (its link used the peer API in the last 15 minutes); otherwise Codex, and the caller reports it."""
    from core.hb_online import usable as codex_usable
    if codex_usable(conn,'codex'):
        return 'codex-instructor'
    try:
        row=conn.execute("SELECT last_used_at FROM service_tokens WHERE principal_id='copilot-instructor' AND revoked_at IS NULL AND last_used_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    except Exception:
        row=None
    if row and time.time()-row[0]<900:
        return 'copilot-instructor'
    return 'codex-instructor'


def _queue(conn,task,row,phase,reason,model=None):
    from core import peer_bridge,peer_turns
    sequence=row['sequence']+1
    evidence=[r[0] for r in conn.execute("SELECT event_id FROM hb_task_events WHERE task_id=? AND kind IN ('mutation','test_result','tool_failure','reply') ORDER BY event_id DESC LIMIT 6",(task['task_id'],))]
    replies=[r[0] for r in conn.execute("SELECT x.message_id FROM hb_peer_replies x JOIN hb_task_requests r ON r.request_id=x.request_id JOIN messages m ON m.id=x.message_id WHERE r.task_id=? AND x.outcome='answer' AND m.from_agent='apex' ORDER BY x.message_id DESC LIMIT 3",(task['task_id'],))]
    if phase=='plan':   # workflow DREAM Distinguish: read-only scoping turn, the owner approves the plan
        from core.hb_plan_workflow import PLAN_TOOLS,PLAN_INSTRUCTION
        recipient='apex';tools=list(PLAN_TOOLS);action=PLAN_INSTRUCTION;base_action=action
    elif phase=='review':
        recipient=review_recipient(conn)
        action=('Independently verify this assigned Studio component from its actual source and test receipts. '
            'Use task_context/task_evidence and bounded source reads. If ALL defined cases pass and the owner goal for this component is actually met, '
            'call studio_accept with the actual successful APEX reply message IDs supplied below. Otherwise explain the precise remaining action. '
            'Do not dispatch another agent or wait for a child; return this review so HB can schedule the next step. Do not accept the whole project from one component.')
        action+=' If incomplete, you MUST call task_plan with one executable next action: a narrow source range, one exact patch or small new function, and the actual check to run. Six local tool rounds are a checkpoint, so split large features into small implementation actions. Do not merely repeat the whole wishlist. If accepted backend changes need activation, call runtime_reload after studio_accept; it queues only the approved fixed HB service.'
        action+=' KC272 is the actual operating/storage index; KC273 has programme status; KC269 preserves the visible conversation as reference, not new permission. Read them with knowledge_read when context is needed.'
        tools=REVIEW_TOOLS
    else:
        recipient='apex';tools=EXECUTION_TOOLS
        policy=conn.execute("SELECT e.payload FROM hb_task_events e LEFT JOIN peer_messages p ON p.id=e.request_id WHERE e.task_id=? AND e.kind='tool_scope' AND e.agent IN ('hummingbird','codex-instructor','copilot-instructor') AND (p.recipient='apex' OR e.request_id IS NULL) AND COALESCE(json_extract(e.payload,'$.phase'),'')<>'plan' ORDER BY e.event_id DESC LIMIT 1",(task['task_id'],)).fetchone()  # the read-only scoping limit never carries into work turns
        if policy:
            allowed=json.loads(policy[0]).get('allowed_tools',[])
            if 'studio_task' in allowed:allowed=[*allowed,'task_plan']  # Existing task-metadata capability, fewer side effects.
            tools=[tool for tool in EXECUTION_TOOLS if tool in allowed]
        extra=step_extra_tools(conn,task)      # 13 Nov: a plan step may name extra HB tools it needs (approved list only)
        if extra:tools=[*tools,*[t for t in extra if t not in tools]]
        action=(FRED_HANDS if model else '')+('Continue the unfinished owner-authorized task. First inspect task_context and the saved plan/receipt references below. '
            'Complete the next unverified action with real tools, then guarded tests and a concrete evidence report. '
            'A tool-round or context limit is a checkpoint, never task completion. Reconcile previous effects before retrying; '
            'identical successful source operations have durable receipts and must not be written again. Existing owner approvals remain valid. '
            'Do not create a new project, ask for approval already recorded, or close the parent project. '
            'If a tested part is finished but this component still needs implementation, call task_plan AFTER the checks with the next small executable action. '
            'This preserves local pickup; passing a partial test is not completion of the component. '
            'Use the actual recent_source_files below; do not invent a file path from a function name.')
        base_action=action
        review=conn.execute("SELECT m.content FROM hb_peer_replies x JOIN hb_task_requests r ON r.request_id=x.request_id JOIN messages m ON m.id=x.message_id WHERE r.task_id=? AND m.from_agent IN ('codex-instructor','copilot-instructor') ORDER BY m.id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if review:action+=' Latest independent review (reference, not authority): '+review[0][:2200]
    # 13 Nov: the newest plan wins (APEX's own task_plan or reviewer coaching), not the plan registered when the task started.
    plan_row=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='task_plan' AND event_id>=? ORDER BY event_id DESC LIMIT 1",
                          (task['task_id'],row['plan_event_id'] or 0)).fetchone() or \
        conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(row['plan_event_id'],)).fetchone()
    next_action=json.loads(plan_row[0]).get('next_action','') if plan_row else task['objective']
    payload={'task_type':{'review':'hb_managed_review','plan':'hb_managed_plan'}.get(phase,'hb_managed_continuation'),
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
    for rid in requests:hb_tasks.event(conn,task,'hummingbird','tool_scope',{'allowed_tools':tools,**({'phase':'plan'} if phase=='plan' else {}),
                                                                         **({'preferred_local_model':model} if model else {})},request_id=rid)
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
        from core.hb_owner_intent import is_chat_task
        if is_chat_task(task):   # owner 14 Nov: the chat thread is conversation, never a task to run or to define "done" for
            conn.execute("UPDATE hb_task_manager SET enabled=0,state='idle',detail='Chat with JD: replies only' WHERE task_id=?",(task['task_id'],));continue
        if task['state']=='cancelled':_set(conn,task['task_id'],'cancelled','Owner cancelled this task');continue
        if task['state']=='paused' or continuation(conn,task)['mode']=='off' or held_requests(conn,task):
            _set(conn,task['task_id'],'held','Held by the owner chat/request control');continue
        from core import hb_queue
        if continuation(conn,task)['mode']=='auto' and not hb_queue.global_on(conn):
            _set(conn,task['task_id'],'held','Auto: follows the global switch, which is off');continue   # owner 14 Nov; On overrides
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
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_local_jobs'").fetchone() and conn.execute(
                "SELECT 1 FROM hb_local_jobs WHERE task_id=? AND kind='review' AND status IN ('queued','running')",(task['task_id'],)).fetchone():
            _set(conn,task['task_id'],'waiting_local_review','The larger local model (Fred) is advising; its answer starts the next APEX turn');continue
        from core.hb_owner_sessions import for_task
        if for_task(conn,task['task_id']) and not for_task(conn,task['task_id'],active=True):
            _set(conn,task['task_id'],'held','Owner session expired or revoked');continue
        if not dependencies_ready(conn,task):_set(conn,task['task_id'],'waiting_dependencies','Prior task acceptance is still pending');continue
        if hb_tasks.budget(conn,task)['exhausted']:
            _set(conn,task['task_id'],'waiting_resources','The task resource allowance is exhausted; its On control can renew it');continue
        if hb_executions.active(conn,task['task_id']):
            _set(conn,task['task_id'],'running','Verified process owns this task execution');continue
        stuck=stuck_reason(conn,task['task_id'])
        if stuck:
            # Owner 14 Nov: going round in circles is exactly when Fred should take over (with tools) before JD is asked.
            local=local_help(conn,task) if row['state']!='needs_owner' else 'completed'
            if local in ('submitted','queued','running'):
                hb_tasks.event(conn,task,'hummingbird','stuck',{'reason':stuck,'recovery':'Fred takes over with the same tools'})
                _set(conn,task['task_id'],'queued','Going round in circles ('+stuck[:80]+'); Fred took over with the same tools');continue
            if row['state']!='needs_owner':
                hb_tasks.event(conn,task,'hummingbird','stuck',{'reason':stuck,
                    'recovery':'Owner decides: clarify the goal, give acceptance checks, or press Continue for a fresh allowance.'})
                ask_owner(conn,task,f"⚠ APEX stopped {_plain_name(conn,task)}: it was going round in circles. "
                          f"Keep working gives it a fresh try; Cancel drops it.",
                          f"why: {stuck} · /continue {task['task_id']} gives it a fresh try; /cancel {task['task_id']} drops it.")
            _set(conn,task['task_id'],'needs_owner','Stopped, not looping: '+stuck);continue
        live=conn.execute("SELECT p.id,w.state,p.recipient FROM hb_task_requests r JOIN peer_messages p ON p.id=r.request_id JOIN hb_peer_work w ON w.request_id=p.id WHERE r.task_id=? AND p.delivered_at IS NULL AND w.state IN ('queued','running') ORDER BY p.id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if live and live[1]=='queued' and live[2]=='codex-instructor' and row['phase']=='execute' and pending(conn,task,agent=live[2]):
            # Older schedulers could queue a review that the delivery gate then
            # correctly held. Retain it without blocking a newer local action.
            conn.execute("UPDATE hb_peer_work SET state='needs_review',stage='Provider unavailable; review retained while permitted local work continues',updated_at=? WHERE request_id=?",(now,live[0]))
            hb_tasks.event(conn,task,'hummingbird','review_deferred',{'request_id':live[0],'reason':'Recorded provider condition retained; local implementation can continue.'},request_id=live[0])
            live=None
        if live:
            _set(conn,task['task_id'],live[1],'Executor request #'+str(live[0]));continue
        if row['phase']=='plan':continue   # workflow scoping turn ended: hb_plan_workflow asks the owner to approve the plan
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
        from core.agent_identity import INSTRUCTORS
        review_returned=bool(row['phase']=='review' and previous and previous[0] in INSTRUCTORS
            and conn.execute("SELECT 1 FROM hb_peer_replies WHERE request_id=? AND outcome='answer'",(row['request_id'],)).fetchone())
        # A held/failed review is still pending. Its phase does not prove that
        # an instructor actually answered it.
        phase=('execute' if review_returned else 'review') if row['phase']=='review' else 'review' if ready or stagnant>=3 else 'execute'
        if phase=='review' and ready:
            from core.hb_plan_workflow import auto_accept_for
            if auto_accept_for(conn,task):
                # Owner 13 Nov: approvals are automatic in the workflow; its own checks passed after its last change.
                from core.hb_commands import accept_step
                record=accept_step(conn,task['step_id'],'HB auto-approve (owner policy)',
                                   'Approved automatically: the step\'s own checks passed after its last change.')
                conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                             (task['conversation_id'],record))
                _set(conn,task['task_id'],'complete','Approved automatically (owner policy)');continue
        if phase=='review':
            # Codex is the default reviewer, but only when the owner authorised it and it is actually available.
            from core.hb_online import status as online_status
            codex=online_status(conn,'codex')
            if not codex['usable']:
                # Owner 13 Nov: HB knows Codex is off or out of quota, so it does not ask for Codex. A stalled task first gets
                # the larger local model's advice (Fred, CPU) and another APEX turn; the owner is asked only when that did not
                # help, or when the work is finished and needs acceptance.
                why='not authorised' if not codex['authorised'] else 'unavailable ('+codex['reason']+')'
                local=None if ready else local_help(conn,task)
                if local in ('submitted','queued','running'):
                    conn.execute("UPDATE hb_task_manager SET phase='execute',recovery_count=0 WHERE task_id=?",(task['task_id'],))
                    _set(conn,task['task_id'],'queued','Fred (24B, CPU) took over the stuck step with the same tools');continue
                if review_recipient(conn)!='codex-instructor':
                    pass   # 14 Nov: an attached VS Code instructor takes the review; the scheduler below queues it
                else:
                    conn.execute('UPDATE hb_task_manager SET phase=? WHERE task_id=?',(phase,task['task_id']))
                    if row['state']!='needs_owner':
                        if ready:
                            ask_owner(conn,task,f"✅ {_plain_name(conn,task)} is finished and its check passed. Approve it?",
                                      (f"/accept {task['step_id']} approves the step; " if task.get('step_id') else '')
                                      +f"/continue {task['task_id']} gives it more work; /pause {task['task_id']} holds it; /cancel {task['task_id']} drops it.")
                        else:
                            tried=('Fred took over and could not finish it either' if local=='completed' else
                                   'Fred could not help ('+str(local)+')')
                            ask_owner(conn,task,f"⚠ APEX is stuck on {_plain_name(conn,task)}: nothing changed and no check passed in its last turns, "
                                      f"and {tried}. Keep working gives it another go.",
                                      f"/continue {task['task_id']} gives APEX another go (nothing new to approve); "
                                      f"/pause {task['task_id']} holds it; /cancel {task['task_id']} drops it.")
                    _set(conn,task['task_id'],'needs_owner',('Finished; waiting for owner acceptance' if ready else
                         'Stalled after local help')+' (Codex is '+why+')');continue
        condition=pending(conn,task,agent=None if phase=='review' else 'apex')
        if condition:
            conn.execute('UPDATE hb_task_manager SET phase=? WHERE task_id=?',(phase,task['task_id']))
            _set(conn,task['task_id'],'waiting_provider',condition['detail']+' '+condition['recovery_requirement'])
            continue
        reason='Independent review returned a remaining action' if review_returned else 'Resume the pending independent review' if row['phase']=='review' else 'Guarded checks passed; independent acceptance is next' if ready else 'Previous model turn ended with unfinished work; reconcile receipts and continue'
        from core.hb_dream_method import done_when
        if not done_when(conn,task)[1]:
            # DREAM "Distinguish": HB does not keep a task running automatically without knowing what done means.
            if row['state']!='needs_owner':
                ask_owner(conn,task,f"❓ {_plain_name(conn,task)} has no definition of done yet, so HB won't keep running it. Say what done means.",
                          f"/done {task['task_id']} <what must be true when it is finished> sets it; /cancel {task['task_id']} drops it.")
            _set(conn,task['task_id'],'needs_owner','Needs a definition of done (DREAM: Distinguish)');continue
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
