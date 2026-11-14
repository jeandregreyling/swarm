"""Durable task identity, Studio links, evidence and attributable memory delivery."""
from contextlib import closing
import hashlib
import re
import json
import time
import uuid


def ensure_schema(conn):
    schema = '''CREATE TABLE IF NOT EXISTS hb_tasks(
      task_id TEXT PRIMARY KEY,conversation_id INTEGER NOT NULL,root_message_id INTEGER NOT NULL,
      title TEXT NOT NULL,objective TEXT NOT NULL,project_id TEXT,step_id TEXT,
      state TEXT DEFAULT 'active',created_at REAL,updated_at REAL,version INTEGER DEFAULT 1,
      token_budget INTEGER DEFAULT 250000,time_budget INTEGER DEFAULT 14400,
      UNIQUE(conversation_id,root_message_id));
    CREATE TABLE IF NOT EXISTS hb_task_messages(message_id INTEGER PRIMARY KEY,task_id TEXT NOT NULL,
      parent_message_id INTEGER,kind TEXT);
    CREATE TABLE IF NOT EXISTS hb_task_requests(request_id INTEGER PRIMARY KEY,task_id TEXT NOT NULL,task_version INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS hb_task_events(event_id INTEGER PRIMARY KEY,task_id TEXT NOT NULL,
      agent TEXT NOT NULL,kind TEXT NOT NULL,message_id INTEGER,request_id INTEGER,payload TEXT,created_at REAL);
    CREATE TABLE IF NOT EXISTS hb_task_deliveries(event_id INTEGER,agent TEXT,delivered INTEGER DEFAULT 0,
      PRIMARY KEY(event_id,agent));
    CREATE TABLE IF NOT EXISTS hb_reply_usage(request_id INTEGER PRIMARY KEY,model TEXT,
      usage_json TEXT NOT NULL,message_id INTEGER,total_tokens INTEGER);
    CREATE TABLE IF NOT EXISTS hb_task_checkpoints(task_id TEXT,signature TEXT,
      PRIMARY KEY(task_id,signature));
    CREATE INDEX IF NOT EXISTS idx_hb_task_events_message ON hb_task_events(message_id,kind);
    CREATE INDEX IF NOT EXISTS idx_hb_task_events_task_kind ON hb_task_events(task_id,kind,event_id);
    CREATE INDEX IF NOT EXISTS idx_hb_task_messages_task ON hb_task_messages(task_id,kind);
    CREATE INDEX IF NOT EXISTS idx_hb_task_requests_task ON hb_task_requests(task_id);
    CREATE INDEX IF NOT EXISTS idx_hb_reply_usage_message ON hb_reply_usage(message_id)'''
    # 12 Nov: without these, rebuilding chat 2834's task view scanned 22k events ~19k times (11 s per refresh).
    for statement in schema.split(';'):
        if statement.strip():
            conn.execute(statement)


def _dict(cursor):
    row = cursor.fetchone()
    return dict(zip([col[0] for col in cursor.description], row)) if row else None


def get(conn, task_id):
    return _dict(conn.execute('SELECT * FROM hb_tasks WHERE task_id=?', (task_id,)))


def for_message(conn, message_id):
    return _dict(conn.execute('SELECT t.* FROM hb_tasks t JOIN hb_task_messages m ON m.task_id=t.task_id WHERE m.message_id=?', (message_id,)))


def for_request(conn, request_id):
    return _dict(conn.execute('SELECT t.* FROM hb_tasks t JOIN hb_task_requests r ON r.task_id=t.task_id WHERE r.request_id=?', (request_id,)))


_ACTION_WORDS = re.compile(r'\b(build|fix|implement|create|make|add|update|change|install|write|run|test|repair|delete|remove|deploy|'
                           r'refactor|connect|enable|disable|set ?up|configure|download|index|train|cancel|rename|migrate|start|stop|'
                           r'restart|finish|complete|continue|approve|merge|move|clean)\b', re.I)
_QUESTION_START = re.compile(r'^(what|why|how|when|where|who|which|is|are|can|could|do|does|did|should|would|will|have|has)\b', re.I)


def is_plain_question(text):
    """A short question with no requested action does not need a Studio step (12 Nov: Studio clutter)."""
    body = re.sub(r'^(\s*@[\w.-]+[,:]?\s*)+', '', str(text or '')).strip()
    if not body or len(body) > 300 or _ACTION_WORDS.search(body):
        return False
    return body.endswith('?') or bool(_QUESTION_START.match(body))


_SHORT_REPLY = re.compile(r'^\s*(yes|yep|yeah|yup|ok|okay|sure|go ahead|do it|please do|continue|carry on|proceed|'
                          r'no|nope|not now|thanks|thank you)\b[\s!.,]*(please)?[\s!.]*$', re.I)


def reply_target(conn, conversation_id, text, hours=6):
    """B39: a bare "yes" / "ok" / "go ahead" belongs to the task of the latest agent reply, not a new empty task."""
    if not _SHORT_REPLY.match(str(text or '')):
        return None
    row = conn.execute("""SELECT t.task_id FROM hb_task_messages tm JOIN hb_tasks t ON t.task_id=tm.task_id
        JOIN messages m ON m.id=tm.message_id WHERE t.conversation_id=? AND t.state NOT IN ('completed','cancelled')
        AND m.from_agent NOT IN ('user','ghost') AND m.created_at>=datetime('now', ?) ORDER BY m.id DESC LIMIT 1""",
        (conversation_id, f'-{int(hours)} hours')).fetchone()
    return row[0] if row else None


def _hb_room_project(conversation_id):
    return 'P-' + hashlib.sha256(f'hb-room:{conversation_id}'.encode()).hexdigest()[:10].upper()


def sync_studio_steps(conn):
    """Close the auto-created Studio step of every finished HB task (done / skipped). Returns steps closed.

    Only steps in the automatic "HB tasks - chat N" projects are closed here; steps in curated plans
    are accepted by the owner (Approve / /accept)."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'project_steps', 'hb_tasks'} <= tables:
        return 0
    closed = 0
    for task_id, conversation_id, state, project_id, step_id in conn.execute(
            "SELECT t.task_id, t.conversation_id, t.state, t.project_id, t.step_id FROM hb_tasks t JOIN project_steps s ON s.step_id=t.step_id "
            "WHERE t.state IN ('completed','cancelled') AND s.status IN ('todo','doing','partial','blocked')").fetchall():
        if project_id != _hb_room_project(conversation_id):
            continue
        status = 'done' if state == 'completed' else 'skipped'
        conn.execute('UPDATE project_steps SET status=?, residual_risk=?, updated_at=? WHERE step_id=?',
                     (status, f'Closed automatically: HB task {task_id} {state}', time.time(), step_id))
        closed += 1
    return closed


def close_tasks_of_closed_steps(conn):
    """A Studio step closed outside its task (accepted, done or skipped in Studio) closes the HB task that carries it,
    so main chat and Studio agree. Returns the tasks closed. Queued work of a skipped step is cancelled."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'project_steps', 'hb_tasks'} <= tables:
        return []
    closed = []
    now = time.time()
    for task_id, status in conn.execute(
            "SELECT t.task_id, s.status FROM hb_tasks t JOIN project_steps s ON s.step_id=t.step_id "
            "WHERE t.state NOT IN ('completed','cancelled') AND s.status IN ('done','skipped')").fetchall():
        state = 'completed' if status == 'done' else 'cancelled'
        conn.execute('UPDATE hb_tasks SET state=?, updated_at=? WHERE task_id=?', (state, now, task_id))
        if state == 'cancelled' and {'hb_peer_work', 'hb_task_requests'} <= tables:
            conn.execute("UPDATE hb_peer_work SET state='cancelled', stage='Its Studio step was skipped', updated_at=? WHERE state='queued' "
                         "AND request_id IN (SELECT request_id FROM hb_task_requests WHERE task_id=?)", (now, task_id))
        if 'hb_task_manager' in tables:
            conn.execute('UPDATE hb_task_manager SET state=?, detail=?, updated_at=? WHERE task_id=?',
                         ('complete' if state == 'completed' else 'cancelled', f'Its Studio step is {status}', now, task_id))
        event(conn, get(conn, task_id), 'hummingbird', 'closed_with_step', {'step_status': status, 'task_state': state})
        closed.append(task_id)
    return closed


def _studio(conn, conversation_id, task_id, title, objective, project_id=None, step_id=None):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # Minimal test/recovery stores may lack Studio. Main HB initializes its
    # existing Studio schema before this layer; never invent completion there.
    if not {'projects', 'project_steps'} <= tables:
        return None, None
    if step_id:
        row = conn.execute('SELECT project_id,owner FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
        if not row or project_id and row[0] != project_id:
            raise ValueError('Studio step must belong to the selected project')
        if row[1]!='apex':raise PermissionError('Selected Studio step is not assigned to APEX')
        return row[0], step_id
    now = time.time()
    if project_id:
        if not conn.execute('SELECT 1 FROM projects WHERE project_id=?', (project_id,)).fetchone():
            raise ValueError('Unknown Studio project')
    elif is_plain_question(objective):
        return None, None                        # a question is a chat task, not a Studio step
    else:
        project_id = _hb_room_project(conversation_id)
        conn.execute('''INSERT OR IGNORE INTO projects(project_id,name,description,methodology,status,owner,created_at,updated_at)
          VALUES (?,?,?,'agile','active','apex',?,?)''',
          (project_id, f'HB tasks — chat {conversation_id}', 'Task-linked conversation and execution evidence.', now, now))
    step_id = 'S-' + hashlib.sha256(task_id.encode()).hexdigest()[:10].upper()
    conn.execute('''INSERT INTO project_steps(step_id,project_id,title,description,status,owner,order_idx,created_at,updated_at)
      VALUES (?,?,?,?,'todo','apex',0,?,?)''', (step_id, project_id, title, objective, now, now))
    return project_id, step_id


def bind(conn, conversation_id, message_id, *, task_id=None, parent_message_id=None,
         objective=None, title=None, project_id=None, step_id=None, kind='instruction', studio=True):
    existing = for_message(conn, message_id)
    if existing:
        if task_id and task_id != existing['task_id']:
            raise ValueError('Message is already linked to another task')
        return existing
    row = conn.execute('SELECT content,from_agent FROM messages WHERE id=? AND conversation_id=?',
                       (message_id, conversation_id)).fetchone()
    if not row:
        raise ValueError('Task message must exist in this conversation')
    task = get(conn, task_id) if task_id else None
    if task_id and (not task or task['conversation_id'] != conversation_id):
        raise PermissionError('Task belongs to another conversation or does not exist')
    continuation=bool(task)
    if not task:
        task_id = 'T-' + uuid.uuid4().hex[:12].upper()
        objective = str(objective if objective is not None else row[0])
        title = str(title or objective.strip().split('\n')[0])[:140] or 'HB task'
        project_id, step_id = (_studio(conn, conversation_id, task_id, title, objective, project_id, step_id) if studio
                               else (None, None))   # owner 14 Nov: "Chat with JD" (core/hb_owner_intent) has no Studio step
        now = time.time()
        conn.execute('''INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,
          project_id,step_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)''',
          (task_id, conversation_id, message_id, title, objective, project_id, step_id, now, now))
        task = get(conn, task_id)
    if continuation and kind=='instruction':
        conn.execute('UPDATE hb_tasks SET version=version+1,updated_at=? WHERE task_id=?',(time.time(),task['task_id']))
        task=get(conn,task['task_id'])
    conn.execute('INSERT INTO hb_task_messages VALUES (?,?,?,?)',
                 (message_id, task['task_id'], parent_message_id, kind))
    event(conn, task, str(row[1]), kind,
          {'content': str(row[0])}, message_id=message_id)
    return task


def event(conn, task, agent, kind, payload, *, message_id=None, request_id=None, recipients=()):
    cur = conn.execute('INSERT INTO hb_task_events(task_id,agent,kind,message_id,request_id,payload,created_at) VALUES (?,?,?,?,?,?,?)',
        (task['task_id'], agent, kind, message_id, request_id, json.dumps(payload, ensure_ascii=True), time.time()))
    for recipient in set(recipients) | ({agent} if agent not in {'user','hummingbird'} else set()):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='service_principals'").fetchone() and conn.execute('SELECT 1 FROM service_principals WHERE id=?', (recipient,)).fetchone():
            conn.execute('INSERT OR IGNORE INTO hb_task_deliveries VALUES (?,?,0)', (cur.lastrowid, recipient))
    if task.get('project_id') and conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_blackboard_notes'").fetchone():
        now=time.time()
        note_id='B-'+hashlib.sha256(f"task-event:{cur.lastrowid}".encode()).hexdigest()[:10].upper()
        conn.execute('''INSERT OR IGNORE INTO project_blackboard_notes(note_id,project_id,author,kind,content,status,created_at,updated_at)
          VALUES (?,?,?,'trace',?,'active',?,?)''',(note_id,task['project_id'],agent,
          json.dumps({'task_id':task['task_id'],'step_id':task['step_id'],'event_id':cur.lastrowid,
                      'kind':kind,'message_id':message_id,'request_id':request_id,'evidence':payload}),now,now))
    return cur.lastrowid


def prepare(conn, conversation_id, message_id, parent_request_id=None):
    task = scope(conn,conversation_id,message_id,parent_request_id)
    if task:
        if not for_message(conn,message_id):
            source=conn.execute('SELECT message_id FROM peer_messages WHERE id=?',(parent_request_id,)).fetchone() if parent_request_id else None
            bind(conn,conversation_id,message_id,task_id=task['task_id'],parent_message_id=source[0] if source else None,kind='relay')
        return task
    root=conn.execute("SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent='user'",(conversation_id,)).fetchone()[0]
    if not conn.execute('SELECT 1 FROM messages WHERE id=? AND conversation_id=?',(root or message_id,conversation_id)).fetchone():
        return None
    task=bind(conn,conversation_id,root or message_id)
    if (root or message_id)!=message_id:
        bind(conn,conversation_id,message_id,task_id=task['task_id'],kind='relay')
    return task


def attach_request(conn, request_id, conversation_id, message_id, sender, recipient, parent_request_id=None):
    task = prepare(conn,conversation_id,message_id,parent_request_id)
    if not task:
        return None
    conn.execute('INSERT OR IGNORE INTO hb_task_requests(request_id,task_id,task_version) VALUES (?,?,?)', (request_id, task['task_id'],task['version']))
    conn.execute("INSERT OR IGNORE INTO hb_task_deliveries(event_id,agent,delivered) SELECT event_id,?,0 FROM hb_task_events WHERE task_id=? AND kind='instruction'",(recipient,task['task_id']))
    event(conn, task, sender, 'dispatch', {'recipient': recipient}, message_id=message_id,
          request_id=request_id, recipients=(recipient,))
    return task


def scope(conn, conversation_id, message_id=None, parent_request_id=None):
    task = for_request(conn, parent_request_id) if parent_request_id else None
    linked = for_message(conn, message_id) if message_id else None
    if task and linked and task['task_id'] != linked['task_id']:
        raise PermissionError('A reply cannot switch tasks')
    return linked or task


def history(conn,task,limit=8):
    rows=conn.execute('''SELECT m.from_agent,m.to_agent,m.content FROM messages m
      JOIN hb_task_messages tm ON tm.message_id=m.id WHERE tm.task_id=? ORDER BY m.id DESC LIMIT ?''',
      (task['task_id'],limit)).fetchall()
    return [dict(zip(('from_agent','to_agent','content'),row)) for row in reversed(rows)]


def list_tasks(conn, conversation_id):
    result=[]
    for row in conn.execute('SELECT task_id FROM hb_tasks WHERE conversation_id=? ORDER BY updated_at DESC',(conversation_id,)):
        task=get(conn,row[0])
        item={key:task[key] for key in ('task_id','title','project_id','step_id','state','root_message_id','version')}
        from core.hb_chat_controls import continuation
        item['continuation']=continuation(conn,task)
        round_state=conn.execute('SELECT cycle,turns,state FROM hb_peer_rounds WHERE conversation_id=? AND owner_message_id=?',(conversation_id,task['root_message_id'])).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_rounds'").fetchone() else None
        if round_state:item['round']=dict(zip(('cycle','handoffs','state'),round_state))
        item['budget']=budget(conn,task)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_local_jobs'").fetchone():
            item['jobs']=[dict(zip(('job_id','kind','status','stage','updated'),r)) for r in conn.execute('SELECT job_id,kind,status,stage,updated FROM hb_local_jobs WHERE task_id=? ORDER BY created DESC LIMIT 3',(task['task_id'],))]
        result.append(item)
    return result


def enrich(conn, messages):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_messages'").fetchone():
        return messages
    controls={}
    kc_docs={}
    for row in messages:
        task = for_message(conn, row['id'])
        if task:
            row['task'] = {k: task[k] for k in ('task_id','title','project_id','step_id','state','root_message_id','version')}
            from core.hb_chat_controls import continuation
            if task['task_id'] not in controls:controls[task['task_id']]=continuation(conn,task)
            row['task']['continuation']=controls[task['task_id']]
            try:  # DOES: the KC documents this task and its chat are saved in (shown as tags on the bubble)
                from core.hb_kc_records import document_ids
                if task['task_id'] not in kc_docs:kc_docs[task['task_id']]=document_ids(conn,task['conversation_id'],task['task_id'])
                if kc_docs[task['task_id']]:row['task']['kc']=kc_docs[task['task_id']]
            except Exception:
                pass
            if task['step_id'] and row['id']==task['root_message_id']:
                from core.hb_commands import acceptance_state
                accept=acceptance_state(conn,task['step_id'])
                if accept:row['task']['acceptance']=accept
            from core.hb_chat_controls import request_snapshot
            approval=request_snapshot(conn,row['id'])
            if approval:row['request_control']=approval
            row['reply_to_message_id'] = conn.execute('SELECT parent_message_id FROM hb_task_messages WHERE message_id=?', (row['id'],)).fetchone()[0]
        usage = conn.execute('SELECT usage_json FROM hb_reply_usage WHERE message_id=?', (row['id'],)).fetchone()
        if usage:
            row['usage'] = json.loads(usage[0])
        else:
            shared=conn.execute('SELECT 1 FROM hb_reply_usage u JOIN hb_peer_replies r ON r.request_id=u.request_id WHERE r.message_id=?',(row['id'],)).fetchone() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_replies'").fetchone() else None
            if shared:row['usage']={'shared':True}
    return messages


def usage(conn, request_id, message_id, model, value):
    if value is None:
        return
    allowed = {'input_tokens','output_tokens','cached_tokens','reasoning_tokens','total_tokens','source'}
    if (not isinstance(value, dict) or set(value) - allowed or value.get('source') not in {'provider','measured'}
        or any(type(v) is not int or not 0 <= v <= 100_000_000 for k,v in value.items() if k != 'source')):
        raise ValueError('Usage requires nonnegative measured counts and a source; unknown counts must be omitted')
    if request_id is None:
        raise ValueError('Usage must be correlated with an authenticated request')
    previous = conn.execute('SELECT usage_json FROM hb_reply_usage WHERE request_id=?', (request_id,)).fetchone()
    if previous and json.loads(previous[0]) != value:
        raise ValueError('Conflicting usage for the same invocation')
    conn.execute('INSERT OR IGNORE INTO hb_reply_usage VALUES (?,?,?,?,?)',
                 (request_id, model[:160], json.dumps(value), message_id, value.get('total_tokens')))
    if 'total_tokens' in value:
        conn.execute('UPDATE messages SET tokens_used=? WHERE id=?', (value['total_tokens'], message_id))


def recent_source_paths(conn,task,limit=4):
    """Actual scoped effects, rather than guessed paths derived from prose."""
    paths=[]
    def collect(rows):
        for (raw,) in rows:
            try:value=json.loads(raw)
            except (ValueError,TypeError):continue
            values=value.get('paths',[]) if isinstance(value,dict) else value
            if not isinstance(values,list):continue
            for path in values:
                if isinstance(path,str) and path not in paths:
                    paths.append(path)
                    if len(paths)>=limit:return
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_operations'").fetchone():
        collect(conn.execute("SELECT paths FROM hb_task_operations WHERE task_id=? AND state='succeeded' ORDER BY updated_at DESC LIMIT 16",(task['task_id'],)))
    if not paths:
        collect(conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='mutation' ORDER BY event_id DESC LIMIT 16",(task['task_id'],)))
    return paths[:limit]


def packet(conn, task, limit=10000):
    # Exact instruction text is pinned, not rewritten or silently truncated.
    instructions = [dict(zip(('message_id','content','from_agent'), r)) for r in conn.execute('''SELECT m.id,m.content,m.from_agent FROM messages m
      JOIN hb_task_messages tm ON tm.message_id=m.id WHERE tm.task_id=? AND tm.kind='instruction' AND m.id<>? ORDER BY m.id''', (task['task_id'],task['root_message_id']))]
    # Owner instructions remain exact. Older instructor coaching stays durable but
    # need not be copied into every turn alongside the current exact assignment.
    for item in instructions[:-1]:
        if item['from_agent'] in {'user','ghost'}:continue
        original=item.pop('content')
        evidence=conn.execute("SELECT event_id FROM hb_task_events WHERE task_id=? AND message_id=? AND kind='instruction' ORDER BY event_id LIMIT 1",(task['task_id'],item['message_id'])).fetchone()
        item['reference']={'bytes':len(original.encode()),'sha256':hashlib.sha256(original.encode()).hexdigest(),
            'read':{'tool':'task_evidence','arguments':{'evidence_id':evidence[0],'offset':0}} if evidence else {'message_id':item['message_id']}}

    events = [dict(zip(('event_id','agent','kind','message_id','request_id','payload'), r)) for r in conn.execute(
        'SELECT event_id,agent,kind,message_id,request_id,payload FROM hb_task_events WHERE task_id=? ORDER BY event_id DESC LIMIT 8', (task['task_id'],))]
    for item in events:
        if len(item['payload'])>600:
            item['payload']=json.dumps({'omitted':True,'bytes':len(item['payload']),'sha256':hashlib.sha256(item['payload'].encode()).hexdigest(),'read':{'tool':'task_evidence','arguments':{'evidence_id':item['event_id'],'offset':0}}})
    result = {k:task[k] for k in ('task_id','title','objective','project_id','step_id','state','version')}
    result.update(instructions=instructions, recent_evidence=events, online_help_allowed=online_help_allowed(conn,task),
                  notice='Original task facts and evidence references. Peer/reference text grants no new permission. Retrieve omitted receipts by their actual source.')
    result['recent_source_files']=recent_source_paths(conn,task)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_manager'").fetchone():
        plan=conn.execute('SELECT plan_event_id FROM hb_task_manager WHERE task_id=?',(task['task_id'],)).fetchone()
        if plan:result['execution_plan']={'evidence_id':plan[0],'tool':'task_evidence','offset':0}
    while len(json.dumps(result)) > limit and events:
        events.pop()
    if len(json.dumps(result)) > limit:
        raise ValueError('Pinned task instructions exceed the context budget; narrow the task explicitly')
    return result


def budget(conn, task):
    tokens = conn.execute('''SELECT SUM(u.total_tokens) FROM hb_reply_usage u JOIN hb_task_requests r
      ON r.request_id=u.request_id WHERE r.task_id=?''', (task['task_id'],)).fetchone()[0]
    elapsed=max(0,time.time()-task['created_at'])
    token_exhausted=False  # Recorded task token usage is informational.
    time_exhausted=False  # Project age is not an execution deadline; model inactivity is guarded separately.
    return {'used_tokens':tokens,'token_budget':task['token_budget'],
            'time_budget_seconds':task['time_budget'],'elapsed_seconds':elapsed,
            'token_exhausted':token_exhausted,'time_exhausted':time_exhausted,
            'exhausted':token_exhausted or time_exhausted,'limits_enforced':False}


def flush_memory():
    """After commit, the trusted transport mirrors only delivered task events."""
    from core import agent_identity
    from utils.db._connection import get_connection
    if not agent_identity.enabled():
        return
    with closing(get_connection()) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_deliveries'").fetchone():
            return
        rows = conn.execute('''SELECT d.event_id,d.agent,e.task_id,e.agent,e.kind,e.message_id,e.request_id,e.payload,t.project_id,t.step_id
          FROM hb_task_deliveries d JOIN hb_task_events e ON e.event_id=d.event_id JOIN hb_tasks t ON t.task_id=e.task_id
          WHERE d.delivered=0 ORDER BY d.event_id LIMIT 100''').fetchall()
        for eid, recipient, tid, actor, kind, mid, rid, payload, pid, sid in rows:
            evidence=json.loads(payload)
            if len(payload)>600:
                evidence={'bytes':len(payload.encode('utf-8')),'sha256':hashlib.sha256(payload.encode()).hexdigest(),
                          'read':{'tool':'task_evidence','arguments':{'evidence_id':eid,'offset':0}}}
            text = json.dumps({'task_id':tid,'project_id':pid,'step_id':sid,'actor':actor,'kind':kind,
                               'message_id':mid,'request_id':rid,'evidence':evidence}, ensure_ascii=True)
            with closing(agent_identity._memory(recipient)) as memory:
                memory.execute('''INSERT OR IGNORE INTO memories(subject,content,tags,importance,source,ticket_ref,legacy_store,legacy_id)
                  VALUES (?,?,?,5,?,?,?,?)''',
                  (f'Task {tid}: {kind}', text, 'hb-task,'+tid, 'hb-transport:task-event', tid, 'hb_task_events', eid))
                memory.commit()
            conn.execute('UPDATE hb_task_deliveries SET delivered=1 WHERE event_id=? AND agent=?', (eid, recipient))
            conn.commit()


def online_help_allowed(conn,task):
    allowed=True
    rows=conn.execute("""SELECT m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id
      WHERE tm.task_id=? AND tm.kind='instruction' AND m.from_agent='user' ORDER BY m.id""",(task['task_id'],))
    import re
    for (text,) in rows:
        if re.search(r"(?is)\b(?:stop|do not|don't)\b.{0,100}\b(?:online models|online agents|asking for online|ask an instructor)\b",text):
            allowed=False
        elif re.search(r'(?i)@(?:codex|gemini|instructor|copilot)\b|\bask (?:codex|gemini|instructor|copilot)\b',text):
            allowed=True
    return allowed


def needs_verification(conn,task):
    if not task or not task['step_id']:
        return False
    row=conn.execute('SELECT status FROM project_steps WHERE step_id=?',(task['step_id'],)).fetchone()
    if row and row[0]=='done':return False
    mutations=conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)).fetchone()
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cases=conn.execute('SELECT 1 FROM project_test_cases WHERE step_id=?',(task['step_id'],)).fetchone() if 'project_test_cases' in tables else None
    return bool(mutations or cases)


def call(tool, args):
    from core import agent_identity
    from core.knowledge import projects
    from utils.db._connection import get_connection
    actor = agent_identity.CURRENT.get()
    if not actor or not (actor.get('peer_request_id') or actor.get('task_id')):
        raise PermissionError('Task tools require a pending authenticated task invitation')
    with closing(get_connection()) as conn:
        ensure_schema(conn)
        task = for_request(conn, actor.get('peer_request_id')) if actor.get('peer_request_id') else get(conn,actor['task_id'])
        if not task or task['conversation_id'] != actor.get('conversation_id'):
            raise PermissionError('No task belongs to this invitation')
        if tool == 'task_context':
            if args:
                raise ValueError('task_context takes no arguments')
            if actor.get('peer_request_id'):
                conn.execute('UPDATE hb_task_requests SET task_version=? WHERE request_id=?',(task['version'],actor['peer_request_id']))
                conn.commit()
            return {'task':packet(conn, task), 'budget':budget(conn, task)}
        if tool == 'task_memory':
            if args:
                raise ValueError('task_memory takes no arguments')
            agent_identity._check_memory_identity(actor['principal'])
            with closing(agent_identity._memory(actor['principal'])) as memory:
                rows = memory.execute("SELECT id,subject,content,source,legacy_id FROM memories WHERE ticket_ref=? AND archived=0 ORDER BY CASE WHEN source='hb-transport:task-event' OR source LIKE 'peer:peer_message:%' THEN 1 ELSE 0 END,id DESC LIMIT 8", (task['task_id'],)).fetchall()
            return {'task_id':task['task_id'],'memories':[agent_identity.memory_record(r) for r in rows]}
        if tool == 'task_evidence':
            if (set(args)-{'evidence_id','offset'} or type(args.get('evidence_id')) is not int
                or type(args.get('offset',0)) is not int or args.get('offset',0)<0):
                raise ValueError('task_evidence requires evidence_id and optional nonnegative offset')
            row=conn.execute('SELECT payload FROM hb_task_events WHERE event_id=? AND task_id=?',(args['evidence_id'],task['task_id'])).fetchone()
            if not row:raise PermissionError('Evidence does not belong to this task')
            offset=args.get('offset',0)
            text=row[0][offset:offset+2000]
            return {'task_id':task['task_id'],'evidence_id':args['evidence_id'],'content':text,
                    'next_offset':offset+len(text) if offset+len(text)<len(row[0]) else None}
        if tool == 'task_plan':
            if actor['principal'] not in {'apex','codex-instructor','copilot-instructor'}:raise PermissionError('Only the assigned executor or instructor can update its plan')
            if set(args)-{'next_action','base_plan_event_id'} or not isinstance(args.get('next_action'),str) or not 40<=len(args['next_action'])<=3500:
                raise ValueError('task_plan requires one concrete next_action of40-3500 characters')
            if 'base_plan_event_id' in args and (type(args['base_plan_event_id']) is not int or args['base_plan_event_id']<=0):
                raise ValueError('base_plan_event_id must be a positive actual plan event ID')
            if task['state'] in {'completed','cancelled','paused'}:raise PermissionError('This task cannot be replanned in its current state')
            from core import hb_task_manager
            hb_task_manager.register(conn,task)
            current=conn.execute('SELECT e.event_id,e.request_id FROM hb_task_manager m JOIN hb_task_events e ON e.event_id=m.plan_event_id WHERE m.task_id=?',(task['task_id'],)).fetchone()
            base=args.get('base_plan_event_id')
            if base is None and actor.get('peer_request_id'):
                invitation=conn.execute('SELECT body FROM peer_messages WHERE id=?',(actor['peer_request_id'],)).fetchone()
                try:invitation_packet=json.loads(invitation[0]) if invitation else {}
                except (ValueError,TypeError):invitation_packet={}
                if isinstance(invitation_packet,dict) and invitation_packet.get('task_type') in {'hb_managed_continuation','hb_managed_review'}:
                    base=invitation_packet.get('plan',{}).get('arguments',{}).get('evidence_id')
            if current and base is not None and current[0]!=base and not ('base_plan_event_id' not in args and current[1]==actor.get('peer_request_id') and current[1] is not None):
                raise ValueError(f'The task plan advanced to evidence {current[0]}. Read it with task_evidence, preserve its remaining work, then use base_plan_event_id={current[0]} to save a reconciled next action.')
            eid=event(conn,task,actor['principal'],'task_plan',{'next_action':args['next_action'],
                'previous_plan_event_id':current[0] if current else None,
                'notice':'Execution checkpoint only; no new permission, budget, project or acceptance.'},request_id=actor.get('peer_request_id'))
            conn.execute('UPDATE hb_task_manager SET plan_event_id=?,next_due=? WHERE task_id=?',(eid,time.time(),task['task_id']))
            if actor['principal'] in ('codex-instructor','copilot-instructor'):
                # A concrete review correction resumes local implementation. It
                # neither clears a provider condition nor retries that provider.
                conn.execute("UPDATE hb_task_manager SET phase='execute',recovery_count=0 WHERE task_id=?",(task['task_id'],))
            conn.commit()
            return {'task_id':task['task_id'],'plan_event_id':eid,'state':'saved','notice':'Perform this action with real tools. Saving the plan is not completion.'}
        if tool == 'studio_accept':
            from core.agent_identity import INSTRUCTORS
            if actor['principal'] not in INSTRUCTORS:raise PermissionError('Independent acceptance belongs to the authenticated instructor')
            evidence=args.get('evidence_message_ids')
            if set(args)!={'evidence_message_ids'} or not isinstance(evidence,list) or not 1<=len(evidence)<=8 or any(type(mid) is not int for mid in evidence):
                raise ValueError('studio_accept requires actual task reply evidence_message_ids')
            for mid in evidence:
                if not conn.execute("SELECT 1 FROM hb_task_messages tm JOIN hb_peer_replies r ON r.message_id=tm.message_id JOIN messages m ON m.id=tm.message_id WHERE tm.task_id=? AND tm.message_id=? AND r.outcome='answer' AND m.from_agent='apex'",(task['task_id'],mid)).fetchone():
                    raise PermissionError('Acceptance evidence must be an actual successful reply in this task')
            if not task['step_id']:raise PermissionError('Acceptance requires a Studio task step')
            cases=projects.list_test_cases(task['project_id'],step_id=task['step_id'])
            if not cases or any(case['status']!='passed' for case in cases):
                raise ValueError('All defined task cases need recorded passing runs before acceptance')
            latest_mutation=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)).fetchone()[0]
            latest_instruction=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='instruction'",(task['task_id'],)).fetchone()[0]
            latest_pass=conn.execute("SELECT MAX(started_at) FROM test_runs WHERE step_id=? AND status='pass'",(task['step_id'],)).fetchone()[0]
            verification_floor=max(latest_mutation or 0,latest_instruction or 0)
            if verification_floor and (not latest_pass or latest_pass<verification_floor):raise ValueError('Task changed after verification; run checks again')
            if not projects.update_step_status(task['step_id'],'done'):raise RuntimeError('Acceptance could not be saved')
            conn.execute("UPDATE hb_tasks SET state='completed',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
            event(conn,task,actor['principal'],'accepted',{'evidence_message_ids':evidence},request_id=actor.get('peer_request_id'))
            conn.commit()
            result={'task_id':task['task_id'],'step_id':task['step_id'],'state':'completed','evidence_message_ids':evidence}
            from core.hb_owner_sessions import for_task
            grant=for_task(conn,task['task_id'],active=True)
            if grant and grant.get('runtime_reload'):
                try:
                    from core.hb_runtime_reload import request_reload
                    result['runtime_activation']=request_reload()
                except (OSError,ValueError,PermissionError) as exc:
                    result['runtime_activation']={'status':'not_queued','detail':str(exc)[:500]}
                    event(conn,task,'hummingbird','runtime_reload_not_queued',result['runtime_activation'])
                    conn.commit()
            return result
        if actor['principal'] != 'apex':
            raise PermissionError('Studio mutation is attached only to the assigned APEX executor')
        if tool == 'studio_status':
            if set(args)!={'status'} or args['status'] not in {'todo','doing','blocked','partial'}:
                raise ValueError('studio_status accepts todo, doing, blocked or partial; completion requires independent acceptance')
            if not task['step_id'] or not projects.update_step_status(task['step_id'],args['status']):
                raise RuntimeError('Assigned Studio step status was not updated')
            state='needs_review' if args['status']=='partial' else args['status']
            conn.execute('UPDATE hb_tasks SET state=?,updated_at=? WHERE task_id=?',(state,time.time(),task['task_id']))
            event(conn,task,actor['principal'],'studio_status',args,request_id=actor.get('peer_request_id'))
            conn.commit()
            return {'project_id':task['project_id'],'step_id':task['step_id'],'status':args['status']}
        if tool == 'studio_task':
            if set(args)!={'title','content'} or not isinstance(args['title'],str) or not 1<=len(args['title'])<=140 or not isinstance(args['content'],str) or not 1<=len(args['content'])<=1500:
                raise ValueError('studio_task requires title (140) and content (1500)')
            if not task['project_id']:raise PermissionError('No Studio project is linked')
            for (previous,) in conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='studio_task' ORDER BY event_id DESC LIMIT 30",(task['task_id'],)):
                prior=json.loads(previous)
                if all(' '.join(str(prior.get(key,'')).casefold().split())==' '.join(args[key].casefold().split()) for key in ('title','content')):
                    return {'project_id':task['project_id'],'step_id':prior['step_id'],'case_id':prior['case_id'],'state':'planned','deduplicated':True,'notice':'This child step already exists. Execute the next authorized action instead of creating it again.'}
            sid=projects.add_step(task['project_id'],args['title'],description=args['content']+'\nDerived from '+task['task_id']+'; existing owner scope/grants only.',owner='apex')
            if not sid:raise RuntimeError('Studio child step was not saved')
            cid=projects.add_test_case(task['project_id'],'Verify: '+args['title'],step_id=sid,owner='apex')
            event(conn,task,actor['principal'],'studio_task',{'step_id':sid,'case_id':cid,**args},request_id=actor.get('peer_request_id'))
            conn.commit()
            return {'project_id':task['project_id'],'step_id':sid,'case_id':cid,'state':'planned','notice':'Logged child step; not automatically executed or newly authorized.'}
        if tool == 'studio_note':
            if set(args) != {'content'} or not isinstance(args['content'], str) or not 1 <= len(args['content']) <= 2000:
                raise ValueError('studio_note requires content of 1-2000 characters')
            if not task['project_id']:
                raise PermissionError('Task has no registered Studio project')
            note = projects.add_blackboard_note(task['project_id'], args['content'], author=actor['principal'], kind='trace')
            if not note:
                raise RuntimeError('Studio note was not saved')
            event(conn, task, actor['principal'], 'studio_note', {'note_id':note,'content':args['content']}, request_id=actor.get('peer_request_id'))
            conn.commit()
            return {'note_id':note, 'project_id':task['project_id'], 'step_id':task['step_id']}
        raise ValueError('Unknown task tool')


def _resume_body(conn,task):
    from core import peer_bridge
    deferred=[dict(zip(('message_id','recipient','content'),row)) for row in conn.execute('''
        SELECT d.message_id,d.recipient,m.content FROM hb_peer_deferred d
        JOIN messages m ON m.id=d.message_id WHERE d.conversation_id=? AND d.owner_message_id=?
        ORDER BY d.message_id DESC LIMIT 4''',(task['conversation_id'],task['root_message_id']))]
    checkpoint=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='checkpoint' ORDER BY event_id DESC LIMIT 1",
        (task['task_id'],)).fetchone()
    saved=json.loads(checkpoint[0]) if checkpoint else {}
    next_task=saved.get('next_task') or 'Inspect saved receipts and complete the next unverified owner-authorised action; preserve existing scope.'
    # 13 Nov: a resume carries the task's current plan (owner-approved plan or reviewer coaching), so Keep working continues
    # from it instead of re-investigating from scratch.
    plan=conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='task_plan' ORDER BY event_id DESC LIMIT 1",
        (task['task_id'],)).fetchone()
    try:plan_action=str(json.loads(plan[0]).get('next_action') or '') if plan else ''
    except (TypeError,ValueError):plan_action=''
    if plan_action:next_task=('Current plan (do this first): '+plan_action)[:2500]
    body=json.dumps({'task_type':'hb_owner_resumed','task_id':task['task_id'],
        'next_task':next_task,'pending_requested_work':list(reversed(deferred)),
        'constraints':'Owner resumed this existing task. Preserve its original scope, grants and acceptance checks. Review receipts before repeating any side effect.'})
    if len(body)>peer_bridge.MAX_BODY:
        references=[]
        for item in deferred:
            source=conn.execute('SELECT event_id FROM hb_task_events WHERE task_id=? AND message_id=? ORDER BY event_id LIMIT 1',
                (task['task_id'],item['message_id'])).fetchone()
            references.append({'message_id':item['message_id'],'recipient':item['recipient'],
                'evidence_id':source[0] if source else None})
        packet=json.loads(body);packet['pending_requested_work']=list(reversed(references))
        body=json.dumps(packet)
    return body


def resume_by_owner(conn,task):
    """Owner-authenticated handler only: renew headroom and enqueue one scoped attempt."""
    from core import peer_bridge,peer_turns
    if task['state']=='completed':raise ValueError('Accepted tasks cannot be resumed')
    pending=[row[0] for row in conn.execute('''SELECT p.id FROM hb_task_requests r
        JOIN peer_messages p ON p.id=r.request_id LEFT JOIN hb_peer_work w ON w.request_id=p.id
        WHERE r.task_id=? AND p.delivered_at IS NULL
        AND COALESCE(w.state,'queued') IN ('queued','running') ORDER BY p.id''',(task['task_id'],))]
    measured=budget(conn,task)
    if pending and task['state']=='active' and not measured['exhausted']:
        return {'queued':pending,'deduplicated':True,'version':task['version']}
    if pending and task['state']=='paused' and not measured['exhausted']:
        conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
        conn.execute("UPDATE hb_peer_rounds SET state='active',updated_at=? WHERE conversation_id=? AND owner_message_id=?",(time.time(),task['conversation_id'],task['root_message_id']))
        return {'queued':pending,'deduplicated':True,'version':task['version']}
    # A renewed allowance is above usage already recorded, not above the old limit.
    conn.execute('''UPDATE hb_tasks SET state='active',updated_at=?,
        token_budget=?,time_budget=?,version=version+1 WHERE task_id=?''',
        (time.time(),max(task['token_budget'],measured['used_tokens'] or 0)+250000,
         max(task['time_budget'],int(measured['elapsed_seconds']))+14400,task['task_id']))
    updated=get(conn,task['task_id'])
    if pending:
        conn.execute("UPDATE hb_peer_rounds SET state='active',updated_at=? WHERE conversation_id=? AND owner_message_id=?",
            (time.time(),task['conversation_id'],task['root_message_id']))
        return {'queued':pending,'deduplicated':True,'version':updated['version']}
    peer_turns.current(conn,task['conversation_id'],message_id=task['root_message_id'])
    conn.execute('''UPDATE hb_peer_rounds SET state='active',cycle=cycle+1,turns=0,
        decision_request_id=NULL,updated_at=? WHERE conversation_id=? AND owner_message_id=?''',
        (time.time(),task['conversation_id'],task['root_message_id']))
    body=_resume_body(conn,task)
    mid=conn.execute('''INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used)
        VALUES (?,'hummingbird','apex',?,'handoff',0)''',(task['conversation_id'],body)).lastrowid
    bind(conn,task['conversation_id'],mid,task_id=task['task_id'],kind='checkpoint')
    queued=peer_bridge.enqueue(conn,task['conversation_id'],mid,body,['apex'],sender='hummingbird')
    policy=conn.execute("SELECT request_id,payload FROM hb_task_events WHERE task_id=? AND kind='tool_scope' AND agent IN ('codex-instructor','copilot-instructor','hummingbird') ORDER BY event_id DESC LIMIT 1",
        (task['task_id'],)).fetchone()
    if policy:
        inherited=json.loads(policy[1])
        inherited={key:inherited[key] for key in ('allowed_tools','preferred_local_model','owner_authorized_provider_probe') if key in inherited}
        inherited['inherited_from_request_id']=policy[0]
        for rid in queued:event(conn,updated,'hummingbird','tool_scope',inherited,request_id=rid)
    event(conn,updated,'user','resume_queued',{'queued':queued,'budget_before':measured,'version':updated['version']})
    return {'queued':queued,'deduplicated':False,'version':updated['version']}


def invitation_tools(conn,request_id):
    row=conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='tool_scope' AND agent IN ('codex-instructor','hummingbird') ORDER BY event_id DESC LIMIT 1",(request_id,)).fetchone()
    if not row:return None
    names=json.loads(row[0]).get('allowed_tools')
    if not isinstance(names,list) or not names or len(names)>24 or any(not isinstance(name,str) for name in names):raise ValueError('Invalid bounded invitation tool scope')
    return set(names)


def invitation_model(conn,request_id):
    row=conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='tool_scope' AND agent IN ('codex-instructor','hummingbird') ORDER BY event_id DESC LIMIT 1",(request_id,)).fetchone()
    value=json.loads(row[0]).get('preferred_local_model') if row else None
    if value is not None and value!='fred-cpu:24b':raise PermissionError('Invalid assigned local model')
    return value
