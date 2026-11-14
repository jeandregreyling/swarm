"""Durable HB handoff rounds, independent of prose/message counts."""
import json
import time

MAX_CYCLES = None  # Tasks use visible resource/progress budgets, not a two-round expiry.


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_rounds(
        conversation_id INTEGER,owner_message_id INTEGER,cycle INTEGER DEFAULT 1,
        turns INTEGER DEFAULT 0,state TEXT DEFAULT 'active',decision_request_id INTEGER,
        evidence_floor INTEGER DEFAULT 0,updated_at REAL,
        PRIMARY KEY(conversation_id,owner_message_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_routes(
        request_id INTEGER PRIMARY KEY,owner_message_id INTEGER,cycle INTEGER,turn INTEGER,
        kind TEXT,parent_request_id INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_replies(
        message_id INTEGER PRIMARY KEY,request_id INTEGER,outcome TEXT)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_hb_peer_replies_request ON hb_peer_replies(request_id)')
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_deferred(
        conversation_id INTEGER,owner_message_id INTEGER,cycle INTEGER,message_id INTEGER,
        recipient TEXT,parent_request_id INTEGER,
        UNIQUE(conversation_id,owner_message_id,cycle,message_id,recipient))''')


def owner_message(conn, conversation_id):
    return conn.execute("SELECT COALESCE(MAX(id),0) FROM messages WHERE conversation_id=? AND from_agent='user'",
                        (conversation_id,)).fetchone()[0]


def route(conn, request_id):
    row = conn.execute('SELECT owner_message_id,cycle,turn,kind,parent_request_id FROM hb_peer_routes WHERE request_id=?',
                       (request_id,)).fetchone()
    return dict(zip(('owner_message_id','cycle','turn','kind','parent_request_id'),row)) if row else None


def current(conn, conversation_id, *, message_id=None, parent_request_id=None):
    from core import hb_tasks
    task=hb_tasks.scope(conn,conversation_id,message_id,parent_request_id)
    owner = task['root_message_id'] if task else owner_message(conn, conversation_id)
    conn.execute('INSERT OR IGNORE INTO hb_peer_rounds(conversation_id,owner_message_id,updated_at) VALUES (?,?,?)',
                 (conversation_id,owner,time.time()))
    row = conn.execute('SELECT cycle,turns,state,decision_request_id,evidence_floor FROM hb_peer_rounds WHERE conversation_id=? AND owner_message_id=?',
                       (conversation_id,owner)).fetchone()
    return dict(zip(('cycle','turns','state','decision_request_id','evidence_floor'),row)) | {'owner_message_id':owner}


def plan(conn, conversation_id, message_id, recipient, parent_request_id, limit, *, kind='work'):
    from core.peer_bridge import PeerError
    state = current(conn, conversation_id,message_id=message_id,parent_request_id=parent_request_id)
    from core import hb_tasks
    task=hb_tasks.scope(conn,conversation_id,message_id,parent_request_id)
    from core.hb_task_manager import can_continue
    continuing=can_continue(conn,task) if task else False
    if task and task['state'] in {'cancelled','paused','completed'}:
        raise PeerError(409,'Task is '+task['state'])
    if parent_request_id is not None:
        parent = route(conn,parent_request_id)
        if not parent or parent['owner_message_id'] != state['owner_message_id']:
            raise PeerError(409,'Reply belongs to an earlier or untracked task; saved without replaying it')
        live_parent=conn.execute("SELECT 1 FROM peer_messages p LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.id=? AND p.delivered_at IS NULL AND COALESCE(w.state,'queued') IN ('queued','running')",(parent_request_id,)).fetchone()
        if parent['cycle'] != state['cycle'] and not (continuing and live_parent):
            raise PeerError(409,'Reply belongs to an earlier HB round; saved without replaying it')
    if state['state'] in {'finished','blocked','needs_review'}:
        if not continuing:raise PeerError(409,'HB round has ended: '+state['state'])
        conn.execute("UPDATE hb_peer_rounds SET state='active',cycle=cycle+1,turns=0,decision_request_id=NULL,updated_at=? WHERE conversation_id=? AND owner_message_id=?",(time.time(),conversation_id,state['owner_message_id']))
        hb_tasks.event(conn,task,'hummingbird','turn_checkpoint',{'reason':'New scoped work continues an unfinished managed task','previous_state':state['state']})
        state=current(conn,conversation_id,message_id=message_id,parent_request_id=parent_request_id)
    if kind == 'decision':
        return state | {'kind':'decision','parent_request_id':parent_request_id}
    # Several targets in one explicit dispatch share one handoff turn.
    prior = conn.execute('''SELECT r.turn FROM hb_peer_routes r JOIN peer_messages p ON p.id=r.request_id
        WHERE p.conversation_id=? AND p.message_id=? AND r.owner_message_id=? AND r.cycle=? AND r.kind='work'
        ORDER BY p.id DESC LIMIT 1''',(conversation_id,message_id,state['owner_message_id'],state['cycle'])).fetchone()
    if prior:
        return state | {'turns':prior[0],'kind':'work','parent_request_id':parent_request_id}
    if state['turns'] >= limit or state['state'] == 'awaiting_decision':
        if continuing:
            conn.execute("UPDATE hb_peer_rounds SET state='active',cycle=cycle+1,turns=1,decision_request_id=NULL,updated_at=? WHERE conversation_id=? AND owner_message_id=?",(time.time(),conversation_id,state['owner_message_id']))
            hb_tasks.event(conn,task,'hummingbird','turn_checkpoint',{'handoffs':state['turns'],'previous_cycle':state['cycle'],'reason':'Handoff window checkpoint; task and approval remain active'})
            updated=current(conn,conversation_id,message_id=message_id,parent_request_id=parent_request_id)
            return updated | {'kind':'work','parent_request_id':parent_request_id}
        conn.execute('INSERT OR IGNORE INTO hb_peer_deferred VALUES (?,?,?,?,?,?)',
                     (conversation_id,state['owner_message_id'],state['cycle'],message_id,recipient,parent_request_id))
        if state['decision_request_id']:
            return {'existing_request_id':state['decision_request_id']}
        return state | {'kind':'decision','parent_request_id':parent_request_id}
    state['turns'] += 1
    conn.execute("UPDATE hb_peer_rounds SET turns=?,updated_at=? WHERE conversation_id=? AND owner_message_id=?",
                 (state['turns'],time.time(),conversation_id,state['owner_message_id']))
    return state | {'kind':'work','parent_request_id':parent_request_id}


def decision_body(conn, conversation_id, state):
    owner = conn.execute('SELECT content FROM messages WHERE id=? AND conversation_id=?',
                         (state['owner_message_id'],conversation_id)).fetchone()
    evidence=[dict(zip(('message_id','outcome','content'),row)) for row in conn.execute('''SELECT x.message_id,x.outcome,substr(m.content,1,1000)
        FROM hb_peer_replies x JOIN hb_peer_routes r ON r.request_id=x.request_id JOIN messages m ON m.id=x.message_id
        WHERE r.owner_message_id=? AND r.cycle=? AND x.message_id>? AND x.outcome IN ('answer','failed') ORDER BY x.message_id DESC LIMIT 8''',
        (state['owner_message_id'],state['cycle'],state.get('evidence_floor',0)))]
    pending=[dict(zip(('message_id','recipient','content'),row)) for row in conn.execute('''SELECT d.message_id,d.recipient,substr(m.content,1,1800)
        FROM hb_peer_deferred d JOIN messages m ON m.id=d.message_id WHERE d.conversation_id=? AND d.owner_message_id=? AND d.cycle=? ORDER BY d.message_id LIMIT 4''',
        (conversation_id,state['owner_message_id'],state['cycle']))]
    return json.dumps({'task_type':'hb_peer_decision','owner_message_id':state['owner_message_id'],
        'cycle':state['cycle'],'handoffs_used':state['turns'],
        'current_round_reply_evidence':evidence,'pending_requested_work':pending,
        'owner_objective':str(owner[0] if owner else '')[:1500],
        'instruction':'HB has reached this round\'s handoff budget. Decide finish, blocked, or continue in a fresh bounded round. '
        'Use actual saved reply message IDs from current_round_reply_evidence or the current thread, never the owner instruction ID as progress. Preserve the pending requested action when continuing. No operational tools run in this decision. Preserve the owner objective and existing grants. '
        'Do not replay a historical failed or interrupted request ID. A fresh bounded repair is allowed within the task grants; continuation grants no new permission.'})


def record(conn, request_id, conversation_id, state):
    conn.execute('INSERT INTO hb_peer_routes VALUES (?,?,?,?,?,?)',
                 (request_id,state['owner_message_id'],state['cycle'],state['turns'],state['kind'],state['parent_request_id']))
    if state['kind'] == 'decision':
        conn.execute("UPDATE hb_peer_rounds SET state='awaiting_decision',decision_request_id=?,updated_at=? WHERE conversation_id=? AND owner_message_id=?",
                     (request_id,time.time(),conversation_id,state['owner_message_id']))


def ready(conn, request_id):
    from core import hb_tasks
    task=hb_tasks.for_request(conn,request_id)
    if task and task['state'] in {'paused','cancelled'}:return False
    # Online providers: automatic requests need owner authorisation and current availability.
    peer=conn.execute('SELECT recipient,sender FROM peer_messages WHERE id=?',(request_id,)).fetchone()
    if peer:
        from core.hb_online import may_dispatch
        if not may_dispatch(conn,peer[0],peer[1])[0]:return False
    if task:
        from core.hb_provider_conditions import pending
        recipient=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(request_id,)).fetchone()
        if pending(conn,task,agent=recipient[0] if recipient else None):return False
        from core.hb_chat_controls import continuation,held_requests
        if held_requests(conn,task):return False
        if continuation(conn,task)['mode']=='off':
            # Off stops automatic continuation (owner rule S-437AC764CB); the owner's own request still runs.
            # An explicit owner Off pauses the task, which is held above regardless of sender.
            from core.hb_online import OWNER_SENDERS
            if not peer or peer[1] not in OWNER_SENDERS:return False
        from core.hb_task_manager import dependencies_ready
        if not dependencies_ready(conn,task):return False
    info = route(conn,request_id)
    if not info or info['kind'] != 'decision':
        return True
    return not conn.execute('''SELECT 1 FROM hb_peer_routes r JOIN peer_messages p ON p.id=r.request_id
        LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.conversation_id=(SELECT conversation_id FROM peer_messages WHERE id=?)
        AND r.owner_message_id=? AND r.cycle=? AND r.kind='work' AND COALESCE(w.state,'queued') IN ('queued','running') LIMIT 1''',
        (request_id,info['owner_message_id'],info['cycle'])).fetchone()


def validate_reply(conn, conversation_id, author, request_id):
    from core.peer_bridge import PeerError
    if type(request_id) is not int or request_id <= 0:
        raise PeerError(400,'reply_to_request_id must be positive')
    row = conn.execute('SELECT recipient FROM peer_messages WHERE id=? AND conversation_id=?',
                       (request_id,conversation_id)).fetchone()
    if not row or row[0] != author:
        raise PeerError(403,'Reply correlation must name this agent\'s request in this thread')


def decide(conn, conversation_id, request_id, message_id, value):
    from core import peer_bridge as peers
    info = route(conn,request_id)
    from core import hb_tasks
    state = current(conn,conversation_id,parent_request_id=request_id)
    if (not info or info['kind'] != 'decision' or state['decision_request_id'] != request_id
            or info['owner_message_id'] != state['owner_message_id'] or state['state'] != 'awaiting_decision'):
        raise peers.PeerError(409,'Decision does not belong to the current pending HB round')
    if (not isinstance(value,dict) or set(value) != {'action','reason','next_task','evidence_message_ids'}
            or not isinstance(value['action'],str) or value['action'] not in {'finish','blocked','continue'}
            or not isinstance(value['reason'],str) or not 0 < len(value['reason']) <= 1000
            or not isinstance(value['next_task'],str) or len(value['next_task']) > 1500
            or not isinstance(value['evidence_message_ids'],list) or len(value['evidence_message_ids']) > 8
            or any(type(i) is not int or i <= 0 for i in value['evidence_message_ids'])):
        raise peers.PeerError(400,'Invalid HB decision envelope')
    evidence = value['evidence_message_ids']
    for item in evidence:
        if not conn.execute('SELECT 1 FROM messages WHERE id=? AND conversation_id=? AND id<?',
                            (item,conversation_id,message_id)).fetchone():
            raise peers.PeerError(400,'Decision cited a message absent from this thread')
    action, reason = value['action'], value['reason']
    requested_action=action
    blocked_reasons=[]
    measured_budget=None
    if action == 'finish' and not evidence:
        raise peers.PeerError(400,'A finish decision requires actual message evidence')
    task=hb_tasks.for_request(conn,request_id)
    if action=='finish' and hb_tasks.needs_verification(conn,task):
        action='continue'
        value['next_task']='Verify the linked Studio step with guarded tests and return the actual results for independent instructor acceptance. Do not claim completion from prose.'
        reason='Studio change acceptance is still pending; continuing verification rather than closing the task'
    if action=='blocked' and task:
        recent=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='tool_failure' ORDER BY event_id DESC LIMIT 1",(task['task_id'],)).fetchone()
        if recent and json.loads(recent[0]).get('category')=='ValueError':
            action='continue'
            value['next_task']='Read the task error evidence and correct the invalid tool arguments using the actual attached schema. HTTP 400 is not permission denial.'
            reason='The recorded blocker is invalid tool arguments, which need correction'
    if action == 'continue':
        failed = conn.execute('''SELECT 1 FROM hb_peer_routes r JOIN hb_peer_work w ON w.request_id=r.request_id
            JOIN peer_messages p ON p.id=r.request_id WHERE p.conversation_id=? AND r.owner_message_id=?
            AND r.cycle=? AND w.state IN ('failed','needs_review','cancelled') LIMIT 1''',
            (conversation_id,state['owner_message_id'],state['cycle'])).fetchone()
        progress = any(item > state['evidence_floor'] and conn.execute('''SELECT 1 FROM hb_peer_replies x
            JOIN hb_peer_routes r ON r.request_id=x.request_id WHERE x.message_id=?
            AND r.owner_message_id=? AND r.cycle=? AND x.outcome IN ('answer','failed') ''',
            (item,state['owner_message_id'],state['cycle'])).fetchone() for item in evidence)
        task=hb_tasks.for_request(conn,request_id)
        signature=__import__('hashlib').sha256(value['next_task'].strip().casefold().encode()).hexdigest()
        repeated=task and conn.execute('SELECT 1 FROM hb_task_checkpoints WHERE task_id=? AND signature=?',(task['task_id'],signature)).fetchone()
        measured_budget=hb_tasks.budget(conn,task) if task else None
        exhausted=measured_budget and measured_budget['exhausted']
        if not progress:blocked_reasons.append('no_new_reply_evidence')
        if not value['next_task'].strip():blocked_reasons.append('missing_next_action')
        if repeated:blocked_reasons.append('repeated_next_action')
        if exhausted:
            if measured_budget.get('token_exhausted'):blocked_reasons.append('task_token_budget_exhausted')
            if measured_budget.get('time_exhausted'):blocked_reasons.append('task_time_budget_exhausted')
            if not any(item.endswith('_budget_exhausted') for item in blocked_reasons):blocked_reasons.append('task_budget_exhausted')
        if blocked_reasons:
            action = 'needs_review'
            reason = 'Continuation not queued: '+', '.join(blocked_reasons)+'. Saved work remains open.'
        else:
            if task:
                conn.execute('INSERT INTO hb_task_checkpoints VALUES (?,?)',(task['task_id'],signature))
            conn.execute("UPDATE hb_peer_rounds SET cycle=cycle+1,turns=0,state='active',decision_request_id=NULL,evidence_floor=?,updated_at=? WHERE conversation_id=? AND owner_message_id=?",
                         (max(evidence),time.time(),conversation_id,state['owner_message_id']))
            deferred=[r[0] for r in conn.execute('SELECT DISTINCT message_id FROM hb_peer_deferred WHERE conversation_id=? AND owner_message_id=? AND cycle=? ORDER BY message_id LIMIT 10',
                                                (conversation_id,state['owner_message_id'],state['cycle']))]
            body = json.dumps({'task_type':'hb_peer_continuation','owner_message_id':state['owner_message_id'],
                'next_task':value['next_task'],
                'evidence_message_ids':evidence,
                'pending_reply_message_ids':deferred,
                'pending_requested_work':[dict(zip(('message_id','from_agent','content'),row)) for row in conn.execute(
                    'SELECT id,from_agent,content FROM messages WHERE id IN ('+','.join('?' for _ in deferred)+') ORDER BY id',deferred)] if deferred else [],
                'constraints':'Continue only the original owner-authorized task with existing grants. No failed work is replayed.'})
            if task and not hb_tasks.for_message(conn,message_id):
                hb_tasks.bind(conn,conversation_id,message_id,task_id=task['task_id'],kind='checkpoint')
            queued = peers.enqueue(conn,conversation_id,message_id,body,['apex'],sender='hummingbird',not_before=time.time()+peers.HANDOFF_DELAY_S)
            inherited=hb_tasks.invitation_tools(conn,request_id) if task else None
            if inherited is not None:
                source_policy=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND request_id=? AND kind='tool_scope' AND agent IN ('codex-instructor','copilot-instructor','hummingbird') ORDER BY event_id DESC LIMIT 1",(task['task_id'],request_id)).fetchone()
                source_policy=json.loads(source_policy[0]) if source_policy else {}
                policy={key:source_policy[key] for key in ('preferred_local_model','owner_authorized_provider_probe') if key in source_policy}
                policy.update(allowed_tools=sorted(inherited),inherited_from_request_id=request_id)
                for next_request in queued:hb_tasks.event(conn,task,'hummingbird','tool_scope',policy,request_id=next_request)
            return {'action':'continue','queued':queued,'cycle':state['cycle']+1,'reason':reason}
    conn.execute('UPDATE hb_peer_rounds SET state=?,updated_at=? WHERE conversation_id=? AND owner_message_id=?',
                 ('finished' if action == 'finish' else action,time.time(),conversation_id,state['owner_message_id']))
    if task:=hb_tasks.for_request(conn,request_id):
        task_state='awaiting_acceptance' if action=='finish' else action
        conn.execute('UPDATE hb_tasks SET state=?,updated_at=? WHERE task_id=?',(task_state,time.time(),task['task_id']))
        hb_tasks.event(conn,task,'apex','checkpoint',{'action':action,'requested_action':requested_action,'reason':reason,'blocked_reasons':blocked_reasons,'budget':measured_budget,'next_task':value['next_task'],'evidence_message_ids':evidence},message_id=message_id,request_id=request_id)
    return {'action':action,'requested_action':requested_action,'queued':[],'cycle':state['cycle'],'reason':reason,'blocked_reasons':blocked_reasons,'budget':measured_budget}


def status(conn, conversation_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_rounds'").fetchone():
        return []
    return [dict(zip(('owner_message_id','cycle','handoffs','state'),r)) for r in conn.execute(
        'SELECT owner_message_id,cycle,turns,state FROM hb_peer_rounds WHERE conversation_id=? ORDER BY owner_message_id DESC LIMIT 3',
        (conversation_id,))]
