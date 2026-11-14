"""Owner-authorized activation of reviewed HB code; no arbitrary service shell."""
from contextlib import closing
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import time

from core import hb_tasks,hb_owner_sessions,agent_identity
from utils.db._connection import get_connection

ROOT=Path(__file__).resolve().parents[1]
COMMAND=['sudo','-n','/usr/bin/systemctl','restart','swarm-terminal.service']


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_runtime_reloads(task_id TEXT PRIMARY KEY,
        request_id INTEGER,state TEXT NOT NULL,manifest TEXT NOT NULL,old_pid INTEGER,
        requested_at REAL NOT NULL,detail TEXT NOT NULL)''')
    if 'old_identity' not in {r[1] for r in conn.execute('PRAGMA table_info(hb_runtime_reloads)')}:
        conn.execute('ALTER TABLE hb_runtime_reloads ADD COLUMN old_identity TEXT')


def _backend(path):
    return path.endswith('.py') and path.startswith(('core/','frontend/blueprints/','scripts/'))


def _hash(path):
    target=(ROOT/path).resolve()
    if not target.is_relative_to(ROOT.resolve()) or not _backend(path):raise PermissionError('Runtime manifest must contain HB source files')
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _notice(conn,task,text):
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'system',0)",(task['conversation_id'],text)).lastrowid
    hb_tasks.bind(conn,task['conversation_id'],mid,task_id=task['task_id'],kind='runtime_status')


def request_reload():
    actor=agent_identity.CURRENT.get() or {}
    if actor.get('principal') not in agent_identity.INSTRUCTORS or not actor.get('peer_request_id'):
        raise PermissionError('Runtime activation requires the assigned independent instructor')
    with closing(get_connection()) as conn,conn:
        task=hb_tasks.for_request(conn,actor['peer_request_id'])
        recipient=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(actor['peer_request_id'],)).fetchone()
        if not recipient or recipient[0] not in agent_identity.INSTRUCTORS:raise PermissionError('Activation must use the instructor own task invitation')
        grant=hb_owner_sessions.for_task(conn,task['task_id'],active=True) if task else None
        if not grant or not grant.get('runtime_reload'):raise PermissionError('This owner session has no fixed HB runtime reload grant')
        if task['state']!='completed':raise ValueError('Accept the verified component before requesting activation')
        if not conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='accepted' AND agent IN ('codex-instructor','copilot-instructor','owner-host')",(task['task_id'],)).fetchone():
            raise ValueError('The independent acceptance receipt is missing')
        cases=conn.execute('SELECT status FROM project_test_cases WHERE step_id=?',(task['step_id'],)).fetchall()
        if not cases or any(r[0]!='passed' for r in cases):raise ValueError('Activation requires passing defined cases')
        paths=set()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_operations'").fetchone():
            for (raw,) in conn.execute("SELECT paths FROM hb_task_operations WHERE task_id=? AND state='succeeded'",(task['task_id'],)):paths.update(json.loads(raw))
        for (raw,) in conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='mutation'",(task['task_id'],)):
            paths.update(json.loads(raw).get('paths',[]))
        manifest={p:_hash(p) for p in sorted(paths) if _backend(p)}
        if not manifest:return {'status':'not_required','task_id':task['task_id'],'notice':'No backend source change; refresh the browser for frontend assets.'}
        ensure_schema(conn)
        old=conn.execute('SELECT state FROM hb_runtime_reloads WHERE task_id=?',(task['task_id'],)).fetchone()
        if old:return {'status':old[0],'task_id':task['task_id'],'deduplicated':True}
        conn.execute("INSERT OR IGNORE INTO hb_runtime_reloads(task_id,request_id,state,manifest,old_pid,requested_at,detail) VALUES (?,?,'queued',?,NULL,?,'Waiting for the instructor reply to be saved and acknowledged')",(task['task_id'],actor['peer_request_id'],json.dumps(manifest),time.time()))
        hb_tasks.event(conn,task,actor['principal'],'runtime_reload_requested',{'fixed_service':'swarm-terminal.service','manifest':manifest},request_id=actor['peer_request_id'])
        _notice(conn,task,'HB queued runtime activation for '+task['title']+'. The reviewed component and approvals are saved.')
        return {'status':'queued','task_id':task['task_id'],'notice':'HB will activate this approved component after the review reply is saved. The parent project remains open.'}


def _healthy():
    try:
        connection=http.client.HTTPConnection('127.0.0.1',5050,timeout=2)
        try:connection.request('GET','/');return connection.getresponse().status in {200,302}
        finally:connection.close()
    except OSError:return False


def _process_started():
    from core.hb_executions import process_identity
    boot=next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
    return boot+int(process_identity()['start_ticks'])/os.sysconf('SC_CLK_TCK')


def tick(conn,*,pid=None,identity=None,healthy=None,execute=None):
    ensure_schema(conn)
    if identity is None and pid is None:
        from core.hb_executions import process_identity
        actual=process_identity()
        identity=json.dumps({k:actual[k] for k in ('pid','boot_id','start_ticks')},sort_keys=True)
    pid=os.getpid() if pid is None else pid
    identity=identity or str(pid)
    for tid,rid,state,raw,old_pid,requested,detail,old_identity in conn.execute("SELECT task_id,request_id,state,manifest,old_pid,requested_at,detail,old_identity FROM hb_runtime_reloads WHERE state IN ('queued','restarting')").fetchall():
        task=hb_tasks.get(conn,tid)
        try:grant=hb_owner_sessions.for_task(conn,tid,active=True)
        except PermissionError:
            conn.execute("UPDATE hb_runtime_reloads SET state='cancelled',detail='Owner session signature did not verify' WHERE task_id=?",(tid,));continue
        if not task or task['state']!='completed' or not grant or not grant.get('runtime_reload'):
            conn.execute("UPDATE hb_runtime_reloads SET state='cancelled',detail='Owner scope revoked or component no longer accepted' WHERE task_id=?",(tid,));continue
        manifest=json.loads(raw)
        try:matches=all(_hash(path)==digest for path,digest in manifest.items())
        except (OSError,PermissionError):matches=False
        if not matches:
            conn.execute("UPDATE hb_runtime_reloads SET state='waiting_review',detail='Source advanced after the accepted activation request; review the current version' WHERE task_id=?",(tid,));continue
        if state=='restarting':
            if (identity!=old_identity if old_identity is not None else pid!=old_pid) and (healthy or _healthy)():
                conn.execute("UPDATE hb_runtime_reloads SET state='completed',detail='New HB process is healthy with the recorded source manifest' WHERE task_id=?",(tid,))
                hb_tasks.event(conn,task,'hummingbird','runtime_reload_completed',{'previous_pid':old_pid,'current_pid':pid,'manifest':manifest})
                _notice(conn,task,'HB runtime activation verified for '+task['title']+': the new process is healthy and its source matches the saved manifest.')
            continue
        delivered=conn.execute("SELECT 1 FROM peer_messages p JOIN hb_peer_work w ON w.request_id=p.id WHERE p.id=? AND p.delivered_at IS NOT NULL AND w.state='completed'",(rid,)).fetchone()
        if not delivered:continue
        # Never load another component's in-progress backend edits.
        pending=False
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_operations'").fetchone():
            for (paths,) in conn.execute("SELECT o.paths FROM hb_task_operations o JOIN hb_tasks t ON t.task_id=o.task_id WHERE o.updated_at>=? AND t.state<>'completed'",(_process_started(),)):
                if any(_backend(path) for path in json.loads(paths)):pending=True;break
        if not pending:
            for (raw_effect,) in conn.execute("SELECT e.payload FROM hb_task_events e JOIN hb_tasks t ON t.task_id=e.task_id WHERE e.kind='mutation' AND e.created_at>=? AND t.state<>'completed'",(_process_started(),)):
                if any(_backend(path) for path in json.loads(raw_effect).get('paths',[])):pending=True;break
        if pending:
            conn.execute("UPDATE hb_runtime_reloads SET detail='Waiting for other in-progress backend changes to be independently reviewed' WHERE task_id=?",(tid,));continue
        from core.hb_process_lock import ProcessLock
        with ProcessLock('source-write',ROOT):
            if any(_hash(path)!=digest for path,digest in manifest.items()):continue
            conn.execute("UPDATE hb_runtime_reloads SET state='restarting',old_pid=?,old_identity=?,detail='Saved deployment checkpoint; fixed service restart requested' WHERE task_id=?",(pid,identity,tid))
            hb_tasks.event(conn,task,'hummingbird','runtime_reload_checkpoint',{'pid':pid,'fixed_service':'swarm-terminal.service'})
            conn.commit()  # The service can stop this supervisor; next boot verifies the saved checkpoint.
            try:
                outcome=(execute or (lambda command:subprocess.run(command,capture_output=True,text=True,timeout=30)))(COMMAND.copy())
                failed=bool(getattr(outcome,'returncode',0))
            except (OSError,subprocess.TimeoutExpired):failed=True
            if failed:
                conn.execute("UPDATE hb_runtime_reloads SET state='failed',detail='Fixed runtime restart failed; inspect the service log' WHERE task_id=?",(tid,))
                _notice(conn,task,'HB could not activate '+task['title']+'. The fixed service command failed; saved code and task evidence remain available.')
            return
