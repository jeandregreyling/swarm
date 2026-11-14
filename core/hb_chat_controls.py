"""Saved main-chat execution controls, backed by the existing task/ALM ledger."""
import json
import hashlib
import re
import time

from core import hb_tasks


class StaleControl(ValueError):
    pass


def owner_text_decision(text):
    """Recognize explicit owner decisions, never quoted/conditional authorization."""
    value=str(text).strip().lower().replace('\u2019',"'")
    if not value or any(c in value for c in ('`','"','“','”','?')) or re.search(r'(^|\n)\s*>',value):return None
    if re.search(r"(?:^|\s)['‘][^\n]+['’](?:\s|[.!?,]|$)",value):return None
    if re.search(r'\b(if|unless|provided|after|once|when|maybe|hypothetically)\b',value):return None
    if re.search(r"\b(?:not|never|don't|do not|won't|cannot)\b.{0,25}\b(?:approve|approved|approval|go ahead|proceed|execute)\b",value):return None
    value=re.sub(r'\b(?:request|proposal)\s*#\s*\d+\b','',value).strip()
    if re.fullmatch(r'(?:please\s+)?(?:needs? review|hold (?:it|this)|declined|decline (?:it|this)|try again)[.!\s]*',value):
        return 'try_again' if 'try again' in value else 'declined' if 'declin' in value else 'needs_review'
    if (re.search(r"\b(?:i approve|it's approved|it is approved|you have my approval|you have my permission to (?:execute|implement|apply)|i'm giving you my approval|i want you to go ahead)\b",value)
            or re.search(r'(?:^|[,!.]\s*)(?:ok[,\s]+)?(?:please\s+)?go ahead\b',value)
            or re.fullmatch(r'(?:ok[,!\s]+)?(?:approved|proceed|do it|execute the changes)[.!\s]*',value)):
        return 'approved'
    return None


def request_snapshot(conn, message_id):
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'peer_messages','hb_peer_routes','hb_task_events'}<=tables:return None
    task=hb_tasks.for_message(conn,message_id)
    if not task:return None
    message=conn.execute('SELECT content,from_agent FROM messages WHERE id=? AND conversation_id=?',(message_id,task['conversation_id'])).fetchone()
    if not message:return None
    requests=conn.execute("SELECT p.id,p.body,p.recipient,COALESCE(w.state,'queued') FROM peer_messages p JOIN hb_peer_routes r ON r.request_id=p.id LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.message_id=? AND r.kind='work' ORDER BY p.id",(message_id,)).fetchall()
    if not requests:return None
    # Instruction content identifies scope; a Resume version increment is not a new proposal.
    instructions=conn.execute("SELECT m.content FROM messages m JOIN hb_task_messages t ON t.message_id=m.id WHERE t.task_id=? AND t.kind='instruction' AND m.from_agent IN ('user','ghost') ORDER BY m.id",(task['task_id'],)).fetchall()
    digest=hashlib.sha256(json.dumps([task['task_id'],message_id,message[0],[r[0] for r in instructions]],ensure_ascii=True).encode()).hexdigest()
    row=conn.execute("SELECT event_id,payload FROM hb_task_events WHERE kind='request_approval' AND message_id=? ORDER BY event_id DESC LIMIT 1",(message_id,)).fetchone()
    saved=json.loads(row[1]) if row else {}
    revised=bool(saved and saved.get('scope_hash')!=digest)
    historical=bool(revised and saved.get('decision') in {'approved','try_again'} and all(r[3] in {'completed','cancelled'} for r in requests) and any(r[3]=='completed' for r in requests))
    source=conn.execute("SELECT event_id FROM hb_task_events WHERE message_id=? AND kind IN ('instruction','relay') ORDER BY event_id LIMIT 1",(message_id,)).fetchone()
    return {'message_id':message_id,'task_id':task['task_id'],'version':task['version'],'request_evidence_id':source[0] if source else None,
            'scope_hash':digest,'revision':row[0] if row else 0,
            'decision':'executed' if historical else 'needs_review' if revised else saved.get('decision','unrecorded'),
            'actor':saved.get('actor',''),'revised':revised,
            'attempts':[{'request_id':r[0],'agent':r[2],'state':r[3]} for r in requests]}


def held_requests(conn, task, except_message_id=None):
    result=[]
    for (mid,) in conn.execute("SELECT DISTINCT message_id FROM hb_task_events WHERE task_id=? AND kind='request_approval'",(task['task_id'],)):
        if mid==except_message_id:continue
        snapshot=request_snapshot(conn,mid)
        if snapshot and snapshot['decision'] in {'needs_review','declined'}:result.append(mid)
    return result


def set_request_approval(conn,task,data,actor,*,owner_message_id=None,authorization_source=None):
    required={'decision','message_id','version','revision','scope_hash','command_id'}
    if (set(data)!=required or data['decision'] not in {'approved','needs_review','declined','try_again'}
            or any(type(data[k]) is not int for k in ('message_id','version','revision'))
            or not isinstance(data['scope_hash'],str) or len(data['scope_hash'])!=64 or any(c not in '0123456789abcdef' for c in data['scope_hash'])
            or not isinstance(data['command_id'],str) or not 16<=len(data['command_id'])<=80):
        raise ValueError('Approval requires decision, message ID, version, revision, scope hash and command ID')
    snapshot=request_snapshot(conn,data['message_id'])
    if not snapshot or snapshot['task_id']!=task['task_id']:
        raise PermissionError('This bubble has no request in the selected task')
    for eid,payload in conn.execute("SELECT event_id,payload FROM hb_task_events WHERE task_id=? AND kind='request_approval' AND message_id=? ORDER BY event_id DESC LIMIT 100",(task['task_id'],data['message_id'])):
        old=json.loads(payload)
        if old.get('command_id')==data['command_id']:
            if old.get('request')!=data or old.get('actor')!=actor:raise StaleControl('Command ID belongs to another approval')
            return {**old['result'],'receipt_id':eid,'replayed':True}
    if (task['version']!=data['version'] or snapshot['revision']!=data['revision'] or snapshot['scope_hash']!=data['scope_hash']):
        raise StaleControl('This request changed; refresh its bubble before deciding')
    if task['state']=='completed':raise StaleControl('Accepted work needs a new request')
    if data['decision']=='try_again':
        approved=any(json.loads(row[0]).get('scope_hash')==snapshot['scope_hash'] and json.loads(row[0]).get('decision')=='approved'
                     for row in conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND message_id=? AND kind='request_approval'",(task['task_id'],data['message_id'])))
        if not approved:raise StaleControl('Approve this request before retrying its reviewed scope')
    result={'queued':[],'decision':data['decision'],'message_id':data['message_id']}
    owner_off=continuation(conn,task)['mode']=='off'
    if data['decision'] in {'needs_review','declined'}:
        # Pause the current instruction stream at its next checkpoint. Other project tasks remain intact.
        conn.execute("UPDATE hb_tasks SET state='paused',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
    elif held_requests(conn,task,except_message_id=data['message_id']):
        result['held_by_message_ids']=held_requests(conn,task,except_message_id=data['message_id'])
    elif data['decision']=='approved' and any(a['state']=='completed' for a in snapshot['attempts']):
        result['already_executed']=True
        if task['state']=='paused' and not owner_off:
            conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
    else:
        from core import peer_bridge,peer_turns
        live=[a['request_id'] for a in snapshot['attempts'] if a['state'] in {'queued','running'}]
        if live:
            if not owner_off:conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
            result.update(queued=live,deduplicated=True)
        else:
            # Reconcile completed effects first. The model receives the exact reviewed request and saved receipt references.
            conn.execute("UPDATE hb_tasks SET state='active',version=version+1,updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
            task=hb_tasks.get(conn,task['task_id'])
            peer_turns.current(conn,task['conversation_id'],message_id=task['root_message_id'])
            conn.execute("UPDATE hb_peer_rounds SET state='active',cycle=cycle+1,turns=0,decision_request_id=NULL,updated_at=? WHERE conversation_id=? AND owner_message_id=?",(time.time(),task['conversation_id'],task['root_message_id']))
            if not snapshot['request_evidence_id']:raise StaleControl('The original request evidence is missing; review a fresh request')
            prior=snapshot['attempts'][-1]
            content=json.dumps({'task_type':'reviewed_request_retry' if data['decision']=='try_again' else 'reviewed_request_execution',
                'request_message_id':data['message_id'],'attempt_command_id':data['command_id'],
                'read_exact_request':{'tool':'task_evidence','arguments':{'evidence_id':snapshot['request_evidence_id'],'offset':0}},
                'instruction':'Retrieve the original request and reconcile its previous saved mutation/test receipts before executing. Never repeat a successful side effect; preserve the reviewed scope and assigned agent.'})
            result['queued']=peer_bridge.enqueue(conn,task['conversation_id'],data['message_id'],content,[prior['agent']],sender='hummingbird')
            policy=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND request_id=? AND kind='tool_scope' AND agent IN ('hummingbird','codex-instructor') ORDER BY event_id DESC LIMIT 1",(task['task_id'],prior['request_id'])).fetchone()
            if policy:
                inherited=json.loads(policy[0])
                inherited={key:inherited[key] for key in ('allowed_tools','preferred_local_model','owner_authorized_provider_probe') if key in inherited}
                inherited['inherited_from_request_id']=prior['request_id']
                for rid in result['queued']:hb_tasks.event(conn,task,'hummingbird','tool_scope',inherited,request_id=rid)
            hb_tasks.event(conn,task,'hummingbird','approved_pickup',result,message_id=data['message_id'])
        if owner_off:
            conn.execute("UPDATE hb_tasks SET state='paused',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
            result['held_by_continuation']=True
    # One immutable canonical ALM decision includes the actual queue receipt.
    task=hb_tasks.get(conn,task['task_id'])
    eid=hb_tasks.event(conn,task,'hummingbird' if authorization_source else 'user','request_approval',{'decision':data['decision'],'actor':actor,
        'scope_hash':snapshot['scope_hash'],'command_id':data['command_id'],'request':data,'result':result,
        'owner_message_id':owner_message_id,'authorization_source':authorization_source},message_id=data['message_id'])
    return {**result,'receipt_id':eid,'replayed':False}


def continuation(conn, task):
    row = conn.execute("SELECT event_id,payload FROM hb_task_events WHERE task_id=? AND kind='continuation_control' AND agent='user' ORDER BY event_id DESC LIMIT 1", (task['task_id'],)).fetchone()
    saved = json.loads(row[1]) if row else {}
    checkpoint = conn.execute("SELECT agent,payload FROM hb_task_events WHERE task_id=? AND kind='checkpoint' ORDER BY event_id DESC LIMIT 1", (task['task_id'],)).fetchone()
    decision = json.loads(checkpoint[1]) if checkpoint else {}
    agent_on = decision.get('requested_action', decision.get('action', 'continue')) == 'continue'
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    jobs = conn.execute("SELECT p.id,p.recipient,w.state FROM hb_task_requests r JOIN peer_messages p ON p.id=r.request_id JOIN hb_peer_work w ON w.request_id=p.id WHERE r.task_id=? AND p.delivered_at IS NULL AND w.state IN ('queued','running') ORDER BY p.id", (task['task_id'],)).fetchall() if {'peer_messages','hb_peer_work'} <= tables else []
    mode=saved.get('mode') or 'off'
    actor=saved.get('actor', 'user' if row else 'hummingbird')
    if not row:
        # Owner never set Continue on this task: the plan workflow the owner turned on may be running it (/workflow on).
        from core.hb_plan_workflow import grant
        workflow=grant(conn,task)
        if workflow:mode,actor='on',f"{workflow['actor']} via /workflow"
    held=held_requests(conn,task)
    effective = ('off' if mode=='off' or task['state'] in {'paused', 'cancelled', 'completed', 'awaiting_acceptance'}
                 else 'blocked' if held
                 else 'blocked' if task['state'] in {'needs_review', 'blocked', 'failed'} else 'on')
    status = 'held' if held or mode=='off' or task['state']=='paused' else 'running' if any(r[2] == 'running' for r in jobs) else 'queued' if jobs else 'idle' if task['state'] in {'active','doing','todo'} else task['state']
    manager=conn.execute('SELECT state,detail FROM hb_task_manager WHERE task_id=? AND enabled=1',(task['task_id'],)).fetchone() if 'hb_task_manager' in tables else None
    from core.hb_task_manager import dependencies_ready
    if manager and status!='held' and not dependencies_ready(conn,task):status='waiting_dependencies'
    if manager and not jobs and status not in {'held','completed','cancelled'}:status=manager[0]
    return {'mode': mode, 'actor': actor,
            'revision': row[0] if row else 0, 'agent_choice': 'on' if agent_on else 'off',
            'agent': checkpoint[0] if checkpoint else 'apex', 'reason': decision.get('reason', ''),
            'effective': effective, 'status': status,
            'held_by_message_ids':held,
            'manager':{'state':manager[0],'detail':manager[1]} if manager else None,
            'pickups': [{'request_id': r[0], 'agent': r[1], 'state': r[2]} for r in jobs]}


def owner_text_stop(text):
    """Only a direct Stop command is authority; references remain ordinary text."""
    import re
    return isinstance(text,str) and bool(re.fullmatch(
        r'\s*(?:@(?:apex|codex|gemini|hummingbird|hb)\s+)?(?:please\s+)?(?:stop'
        r'(?:\s+(?:now|all|everything|(?:all\s+)?(?:the\s+)?(?:current\s+)?(?:work|tasks?|loop|looping)))?'
        r'|cancel\s+(?:everything|all(?:\s+(?:the\s+)?(?:open\s+)?(?:work|tasks?|taks))?))[.!]?\s*',   # owner 14 Nov: "cancel all open tasks"
        text,re.I))


def set_continuation(conn, task, data, actor):
    required = {'mode', 'message_id', 'version', 'revision', 'command_id'}
    if (set(data) != required or data['mode'] not in {'auto', 'on', 'off'}
            or any(type(data[k]) is not int for k in ('message_id', 'version', 'revision'))
            or not isinstance(data['command_id'], str) or not 16 <= len(data['command_id']) <= 80):
        raise ValueError('Continuation requires mode, message ID, version, revision and command ID')
    linked = hb_tasks.for_message(conn, data['message_id'])
    if not linked or linked['task_id'] != task['task_id']:
        raise PermissionError('This bubble is not linked to the selected task')
    # A retry of the same browser command returns its original receipt, even after a version increment.
    for eid, payload in conn.execute("SELECT event_id,payload FROM hb_task_events WHERE task_id=? AND kind='continuation_control' ORDER BY event_id DESC LIMIT 100", (task['task_id'],)):
        previous = json.loads(payload)
        if previous.get('command_id') == data['command_id']:
            if previous.get('request') != data or previous.get('actor') != actor:
                raise StaleControl('Command ID belongs to another control decision')
            return {**previous['result'], 'receipt_id': eid, 'replayed': True}
    current = continuation(conn, task)
    if task['version'] != data['version'] or current['revision'] != data['revision']:
        raise StaleControl('The task changed; refresh this bubble before changing it')
    if task['state'] == 'completed':
        raise StaleControl('Accepted work cannot be resumed; create a new task')
    result = {}
    if data['mode'] == 'off':
        conn.execute("UPDATE hb_tasks SET state='paused',updated_at=? WHERE task_id=?", (time.time(), task['task_id']))
    else:
        held=held_requests(conn,task)
        if held:raise PermissionError('Review the approval controls on request bubble(s) '+', '.join(map(str,held)))
        from core import hb_queue
        if data['mode']=='auto' and (not hb_queue.global_on(conn) or task.get('project_id')==hb_queue.PROJECT):
            # Owner 14 Nov: per-task Auto follows the global switch. Off globally: it waits. A plan task: it takes its turn in the queue.
            conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=? AND state='paused'",(time.time(),task['task_id']))
            result = {'queued': [], 'follows_global': True, 'global_on': hb_queue.global_on(conn)}
        else:
            result = hb_tasks.resume_by_owner(conn, task)
    task = hb_tasks.get(conn, task['task_id'])
    result.update(task_id=task['task_id'], version=task['version'], state=task['state'])
    from core.hb_task_manager import register
    register(conn,task,request_id=(result.get('queued') or [None])[0])
    if result.get('follows_global') and task.get('project_id'):
        from core import hb_queue
        if task['project_id']==hb_queue.PROJECT:          # the queue starts it in its turn, not the task manager on its own
            conn.execute("UPDATE hb_task_manager SET enabled=0,state='queued',detail=? WHERE task_id=?",("Auto: waits its turn in HB's queue",task['task_id']))
    if data['mode'] in ('on','auto'):
        # The owner's Keep working means back to work: a task stopped at the review gate for lack of progress
        # gets a fresh execution phase, not one turn and the same review question again (13 Nov, practice 1).
        conn.execute("UPDATE hb_task_manager SET phase='execute',recovery_count=0 WHERE task_id=? AND phase='review'",(task['task_id'],))
    eid = hb_tasks.event(conn, task, 'user', 'continuation_control',
        {'mode': data['mode'], 'actor': actor, 'command_id': data['command_id'], 'request': data, 'result': result},
        message_id=data['message_id'])
    return {**result, 'receipt_id': eid, 'replayed': False}
