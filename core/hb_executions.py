"""Durable execution ownership tied to a kernel process identity, not a timer."""
import json
import os
import signal
from pathlib import Path
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_executions(
        execution_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,request_id INTEGER,
        agent TEXT NOT NULL,kind TEXT NOT NULL,identity TEXT NOT NULL,
        state TEXT NOT NULL,started_at REAL NOT NULL,updated_at REAL NOT NULL)''')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS hb_one_executor_per_task ON hb_executions(task_id) WHERE state='running'")


def process_identity(pid=None):
    pid=os.getpid() if pid is None else pid
    if type(pid) is not int or pid<=0:raise ValueError('A positive local process ID is required')
    proc=Path('/proc')/str(pid)
    if proc.stat().st_uid!=os.geteuid():raise PermissionError('Executor belongs to another host user')
    fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'start_ticks':fields[19],'process_state':fields[0]}


def alive(identity):
    try:current=process_identity(identity['pid'])
    except (FileNotFoundError,ProcessLookupError):return False
    except (OSError,PermissionError):return None  # An unavailable probe never proves death.
    return (current['boot_id']==identity['boot_id'] and current['start_ticks']==identity['start_ticks']
            and current['process_state'] not in {'Z','X'})


def active(conn,task_id=None,request_id=None):
    ensure_schema(conn)
    rows=conn.execute("SELECT execution_id,task_id,request_id,agent,kind,identity FROM hb_executions WHERE state='running'"+
        (' AND task_id=?' if task_id is not None else '')+(' AND request_id=?' if request_id is not None else ''),
        (*([task_id] if task_id is not None else []),*([request_id] if request_id is not None else []))).fetchall()
    return [dict(zip(('execution_id','task_id','request_id','agent','kind','identity'),r)) for r in rows]


def claim(conn,task,*,agent,kind,request_id=None,pid=None):
    ensure_schema(conn)
    from core.hb_chat_controls import continuation,held_requests
    if task['state'] in {'paused','cancelled','completed'} or continuation(conn,task)['mode']=='off' or held_requests(conn,task):
        raise PermissionError('Task execution is held, cancelled or accepted')
    identity=process_identity(pid)
    reconcile(conn)
    if active(conn,task['task_id']):raise ValueError('This task already has a live executor; no second execution started')
    if request_id is not None and conn.execute('SELECT 1 FROM hb_executions WHERE request_id=?',(request_id,)).fetchone():
        raise ValueError('This attempt already ran; recovery must use a fresh scoped request')
    key=uuid.uuid4().hex;now=time.time()
    conn.execute('INSERT INTO hb_executions VALUES (?,?,?,?,?,?,\'running\',?,?)',
        (key,task['task_id'],request_id,agent,kind,json.dumps(identity),now,now))
    return key


def verify(conn,execution_id,task_id):
    ensure_schema(conn)
    row=conn.execute('SELECT task_id,state,identity FROM hb_executions WHERE execution_id=?',(execution_id,)).fetchone()
    if not row or row[0]!=task_id or row[1]!='running' or alive(json.loads(row[2])) is not True:
        raise PermissionError('Executor is stale or no longer owns this task; no further side effect is allowed')
    return True


def for_request(conn,request_id):
    ensure_schema(conn)
    row=conn.execute('SELECT execution_id FROM hb_executions WHERE request_id=? ORDER BY started_at DESC LIMIT 1',(request_id,)).fetchone()
    return row[0] if row else None


def release(conn,execution_id,state='completed'):
    if state not in {'completed','failed','interrupted'}:raise ValueError('Invalid execution outcome')
    ensure_schema(conn)
    conn.execute("UPDATE hb_executions SET state=?,updated_at=? WHERE execution_id=? AND state='running'",(state,time.time(),execution_id))


def reconcile(conn):
    ensure_schema(conn);recovered=[]
    from core import hb_tasks
    for execution in active(conn):
        if alive(json.loads(execution['identity'])) is not False:continue
        release(conn,execution['execution_id'],'interrupted');recovered.append(execution['execution_id'])
        task=hb_tasks.get(conn,execution['task_id'])
        if execution['request_id'] is not None:
            conn.execute("UPDATE hb_peer_work SET state='needs_review',stage='Executor process ended; effects retained for reconciliation',updated_at=? WHERE request_id=? AND state IN ('running','queued')",(time.time(),execution['request_id']))
        if task:hb_tasks.event(conn,task,'hummingbird','execution_interrupted',
            {'execution_id':execution['execution_id'],'request_id':execution['request_id'],'reason':'Recorded process identity is no longer alive'})
    return recovered


def authorized(actor):
    """Recheck current task control immediately before a physical source write."""
    if not actor or not (actor.get('task_id') or actor.get('peer_request_id')):return True
    from contextlib import closing
    from utils.db._connection import get_connection
    from core import hb_tasks
    from core.hb_chat_controls import continuation,held_requests
    with closing(get_connection()) as conn:
        task=hb_tasks.get(conn,actor['task_id']) if actor.get('task_id') else hb_tasks.for_request(conn,actor['peer_request_id'])
        if not task or task['state'] in {'paused','cancelled','completed'}:return False
        from core.hb_owner_sessions import for_task
        if for_task(conn,task['task_id']) and not for_task(conn,task['task_id'],active=True):return False
        control=continuation(conn,task)
        if held_requests(conn,task):return False
        if control['mode']=='off':
            # Off stops automatic continuation (owner rule S-437AC764CB). The owner's own direct
            # turn records the control revision it started under and is stopped only if the owner
            # changes the control during that turn; worker/automatic turns are always held.
            if actor.get('peer_request_id'):
                from core.hb_online import OWNER_SENDERS
                sender=conn.execute('SELECT sender FROM peer_messages WHERE id=?',(actor['peer_request_id'],)).fetchone() \
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='peer_messages'").fetchone() else None
                if not sender or sender[0] not in OWNER_SENDERS:return False
            else:
                started=actor.get('control_revision')
                if started is None or control['revision']!=started:return False
        if actor.get('task_version') is not None and task['version']!=actor['task_version']:return False
        if actor.get('execution_id'):verify(conn,actor['execution_id'],task['task_id'])
    return True


def stop_held_executors(task_id=None):
    """Interrupt only verified HB peer workers; never signal the web server."""
    from contextlib import closing
    from utils.db._connection import get_connection
    from core import hb_tasks
    from core.hb_chat_controls import continuation,held_requests
    from core.hb_process_lock import ProcessLock
    def held(conn,task):
        return task and (task['state'] in {'paused','cancelled'} or continuation(conn,task)['mode']=='off' or held_requests(conn,task))
    with closing(get_connection()) as conn:
        candidates=[r for r in active(conn,task_id) if held(conn,hb_tasks.get(conn,r['task_id']))]
    results=[]
    for record in candidates:
        if record['kind']!='peer':continue  # Inline leases identify the shared HTTP server.
        identity=json.loads(record['identity'])
        if alive(identity) is not True:continue
        try:
            args=(Path('/proc')/str(identity['pid'])/'cmdline').read_bytes().decode().split('\0')
            expected=str(ROOT/'scripts/hummingbird_peer_worker.py')
            if len(args)<4 or args[1]!=expected or args[2:4]!=['--agent',record['agent']]:continue
        except (OSError,UnicodeError):continue
        with ProcessLock('source-write',ROOT),closing(get_connection()) as conn,conn:
            task=hb_tasks.get(conn,record['task_id'])
            if not held(conn,task) or alive(identity) is not True:continue
            current=conn.execute("SELECT 1 FROM hb_executions WHERE execution_id=? AND state='running'",(record['execution_id'],)).fetchone()
            if not current:continue
            # Stop this worker's own Codex app-server, never another IDE or a
            # shared model resident. Closing it also drops its inference stream.
            children=[]
            if record['agent']=='codex-instructor':
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():continue
                    try:
                        fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                        command=(proc/'cmdline').read_bytes().decode().split('\0')
                        if int(fields[1])!=identity['pid'] or 'app-server' not in command:continue
                        if not any(Path(part).name in {'codex','codex.js'} for part in command[:3]):continue
                        children.append(process_identity(int(proc.name)))
                    except (OSError,ValueError,UnicodeError):continue
            conn.execute("UPDATE hb_peer_work SET state='cancelled',stage='Owner stopped the running attempt; receipts retained',updated_at=? WHERE request_id=?",(time.time(),record['request_id']))
            eid=hb_tasks.event(conn,task,'hummingbird','execution_stop_requested',{'execution_id':record['execution_id'],
                'request_id':record['request_id'],'identity':identity,'children':children,'reason':'Owner control is held; terminate only its verified peer executor.'},request_id=record['request_id'])
            conn.commit()  # Persist the control before interrupting the client.
            for target in [*children,identity]:
                try:
                    if alive(target) is True:os.kill(target['pid'],signal.SIGTERM)
                except ProcessLookupError:pass
            results.append({'request_id':record['request_id'],'receipt_id':eid})
    return results
