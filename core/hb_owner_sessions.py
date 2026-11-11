"""Explicit, signed owner-host session grants for a bounded DEOS override.

Only native owner control or an owner-authenticated handler can create a grant.
Peer text cannot create one. A grant approves requests in its recorded task;
it never accepts completion, clears an owner hold, or authorizes other projects.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
KEY_FILE=Path.home()/'.local/share/hummingbird/owner-control/session-key'
SOURCE_PREFIXES=('core/','frontend/','scripts/','tests/','docs/','utils/','lib/','agents/','deploy/','ops/')


@dataclass(frozen=True)
class OwnerHostAuthority:
    uid:int
    source:str


def native_owner_authority():
    from core.agent_identity import CURRENT
    if CURRENT.get() or os.geteuid()!=ROOT.stat().st_uid:
        raise PermissionError('Owner-host control is not an agent tool')
    return OwnerHostAuthority(os.geteuid(),'explicit IDE owner instruction')


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_owner_sessions(
        session_id TEXT PRIMARY KEY,task_id TEXT UNIQUE,payload TEXT NOT NULL,signature TEXT NOT NULL,
        evidence_text TEXT NOT NULL,revoked_at REAL)''')


def _key(create=False):
    if create:
        KEY_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if KEY_FILE.parent.is_symlink():raise PermissionError('Owner control directory cannot be a symlink')
        os.chmod(KEY_FILE.parent,0o700)
        try:
            fd=os.open(KEY_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(fd,'wb') as stream:stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
    try:fd=os.open(KEY_FILE,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:return None
    with os.fdopen(fd,'rb') as stream:
        stat=os.fstat(stream.fileno())
        if stat.st_uid!=ROOT.stat().st_uid or stat.st_mode&0o077:raise PermissionError('Owner signing key permissions are invalid')
        key=stream.read(33)
    if len(key)!=32:raise PermissionError('Owner signing key is invalid')
    return key


def for_task(conn,task_id,*,active=False):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_owner_sessions'").fetchone():return None
    row=conn.execute('SELECT payload,signature,revoked_at FROM hb_owner_sessions WHERE task_id=?',(task_id,)).fetchone()
    if not row:return None
    key=_key()
    if key is None or not hmac.compare_digest(hmac.new(key,row[0].encode(),hashlib.sha256).hexdigest(),row[1]):
        raise PermissionError('Owner session signature did not verify')
    value=json.loads(row[0])
    value['revoked_at']=row[2]
    if active and (row[2] is not None or value['expires_at'] is not None and time.time()>=value['expires_at']):return None
    return value


def grant(conn,authority,*,conversation_id,project_id,objective,evidence_text,reason,
          session_id=None,step_id=None,lifetime_seconds=None,allowed_tools=None,dependencies=(),source_prefixes=None):
    from core import hb_tasks,peer_bridge
    if authority!=native_owner_authority():raise PermissionError('Native owner authorization required')
    if not isinstance(evidence_text,str) or not 20<=len(evidence_text)<=12000:
        raise ValueError('Record the actual owner instruction as evidence')
    if not isinstance(objective,str) or not 1<=len(objective)<=3500:raise ValueError('A bounded objective of at most3500 characters is required')
    if lifetime_seconds is not None and (type(lifetime_seconds) is not int or not 60<=lifetime_seconds<=14400):raise ValueError('An optional explicit session lease must be between one minute and four hours')
    if not reason or len(reason)>1000:raise ValueError('A concrete instructor-override reason is required')
    ensure_schema(conn);hb_tasks.ensure_schema(conn)
    session_id=session_id or uuid.uuid4().hex
    existing=conn.execute('SELECT task_id,evidence_text FROM hb_owner_sessions WHERE session_id=?',(session_id,)).fetchone()
    if existing:
        if existing[1]!=evidence_text:raise ValueError('Session ID was already used for different owner evidence')
        return {'session_id':session_id,'task_id':existing[0],'deduplicated':True}
    content='Owner-authorized HB session handover.\n'+objective+'\nAuthorization source: '+authority.source+'. Approval mode: Auto, within this recorded task and lease. Completion still requires verified tests and instructor acceptance.'
    mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','apex',?,'owner_authorization',0)",(conversation_id,content)).lastrowid
    task=hb_tasks.bind(conn,conversation_id,mid,objective=objective,title=objective.split('\n')[0][:140],project_id=project_id,step_id=step_id)
    now=time.time()
    payload={'session_id':session_id,'task_id':task['task_id'],'conversation_id':conversation_id,
        'project_id':task['project_id'],'root_message_id':mid,'owner_uid':authority.uid,'source':authority.source,
        'mode':'auto','started_at':now,'expires_at':now+lifetime_seconds if lifetime_seconds is not None else None,'reason':reason,
        'source_prefixes':list(source_prefixes or SOURCE_PREFIXES),'evidence_sha256':hashlib.sha256(evidence_text.encode()).hexdigest()}
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
    signature=hmac.new(_key(create=True),encoded.encode(),hashlib.sha256).hexdigest()
    conn.execute('INSERT INTO hb_owner_sessions VALUES (?,?,?,?,?,NULL)',(session_id,task['task_id'],encoded,signature,evidence_text))
    hb_tasks.event(conn,task,'owner-host','owner_session_granted',payload,message_id=mid)
    queued=peer_bridge.enqueue(conn,conversation_id,mid,objective,['apex'],sender='hummingbird') if not dependencies else []
    if allowed_tools:
        if len(allowed_tools)>20 or any(not isinstance(t,str) for t in allowed_tools):raise ValueError('Use at most twenty explicit tools')
        for rid in queued:hb_tasks.event(conn,task,'hummingbird','tool_scope',{'allowed_tools':allowed_tools},request_id=rid)
    from core.hb_task_manager import register
    register(conn,task,request_id=queued[0] if queued else None,next_action=objective,dependencies=dependencies)
    return {'session_id':session_id,'task_id':task['task_id'],'project_id':task['project_id'],
            'step_id':task['step_id'],'message_id':mid,'queued':queued,'expires_at':payload['expires_at'],'deduplicated':False}


def approve_if_auto(conn,task,request_id):
    from core.hb_chat_controls import request_snapshot,set_request_approval
    grant=for_task(conn,task['task_id'],active=True)
    if not grant:return
    row=conn.execute('SELECT message_id FROM peer_messages WHERE id=?',(request_id,)).fetchone()
    control=request_snapshot(conn,row[0]) if row else None
    if not control or control['revision']:return  # An explicit owner decision always wins.
    data={'decision':'approved','message_id':row[0],'version':task['version'],
          'revision':0,'scope_hash':control['scope_hash'],'command_id':'auto-'+grant['session_id']+'-'+str(row[0])}
    set_request_approval(conn,task,data,'owner-host (session Auto)',owner_message_id=grant['root_message_id'],authorization_source=grant['session_id'])


def authorize_runtime_reload(conn,authority,task_id,reason):
    if authority!=native_owner_authority():raise PermissionError('Only the actual native owner instruction can enable service activation')
    grant=for_task(conn,task_id,active=True)
    if not grant or not isinstance(reason,str) or len(reason)<40:raise ValueError('An active owner session and concrete authorization reason are required')
    raw=conn.execute('SELECT payload FROM hb_owner_sessions WHERE task_id=?',(task_id,)).fetchone()[0]
    value=json.loads(raw);value['runtime_reload']=True
    encoded=json.dumps(value,sort_keys=True,separators=(',',':'))
    signature=hmac.new(_key(),encoded.encode(),hashlib.sha256).hexdigest()
    conn.execute('UPDATE hb_owner_sessions SET payload=?,signature=? WHERE task_id=?',(encoded,signature,task_id))
    from core import hb_tasks
    hb_tasks.event(conn,hb_tasks.get(conn,task_id),'owner-host','runtime_reload_authorized',
        {'fixed_service':'swarm-terminal.service','reason':reason,'session_id':value['session_id']})


def enforce_write_scope(conn,task,request_id,tool,args):
    grant=for_task(conn,task['task_id'])
    if not grant:return
    if not for_task(conn,task['task_id'],active=True):
        raise PermissionError('The recorded owner session has expired or been revoked')
    from core.hb_chat_controls import request_snapshot
    row=conn.execute('SELECT message_id FROM peer_messages WHERE id=?',(request_id,)).fetchone()
    control=request_snapshot(conn,row[0]) if row else None
    if not control or control['decision'] not in {'approved','try_again'}:
        raise PermissionError('Use the actual request bubble approval before changing source')
    paths=args.get('paths',[]) if tool=='propose_commit' else [args.get('file_path') or args.get('path')]
    if tool=='propose_commit':raise PermissionError('Session Auto does not authorize commits; review an explicit commit request')
    if any(not isinstance(path,str) or not any(path==prefix or prefix.endswith('/') and path.startswith(prefix) for prefix in grant['source_prefixes']) for path in paths):
        raise PermissionError('This path is outside the recorded session source scope')


def accept_instructor_override(conn,authority,*,task_id,review_event_id,evidence_message_ids,assessment):
    """Native instructor can finish a reviewed component during a provider capacity outage.

    This is deliberately not an agent tool. It preserves the provider condition,
    requires an independent local review and fresh guarded tests, and records the
    real host override instead of pretending the unavailable provider accepted it.
    """
    from core import hb_tasks
    from core.hb_chat_controls import continuation,held_requests
    if authority!=native_owner_authority():raise PermissionError('Native owner-host instructor required')
    task=hb_tasks.get(conn,task_id)
    if not task or not for_task(conn,task_id,active=True):raise PermissionError('An active signed owner session is required')
    if not isinstance(assessment,str) or not 40<=len(assessment)<=2000:raise ValueError('Record the concrete instructor assessment')
    if task['state'] in {'paused','cancelled','completed'} or continuation(conn,task)['mode']=='off' or held_requests(conn,task):
        raise PermissionError('Owner hold, cancellation or prior acceptance prevents this override')
    condition=conn.execute('SELECT kind FROM hb_provider_conditions WHERE task_id=? AND resolved_event_id IS NULL',(task_id,)).fetchone()
    if not condition or condition[0]!='provider_capacity':raise PermissionError('This override applies only to a recorded provider capacity outage')
    review=conn.execute("SELECT payload,created_at FROM hb_task_events WHERE event_id=? AND task_id=? AND agent='owner-host' AND kind='independent_local_review'",(review_event_id,task_id)).fetchone()
    result=json.loads(review[0]).get('actual_result',{}) if review else {}
    if result.get('model')!='fred-cpu:24b' or result.get('need_online') is not False or not result.get('advice'):
        raise ValueError('A completed independent local source review is required')
    cases=conn.execute('SELECT status FROM project_test_cases WHERE step_id=?',(task['step_id'],)).fetchall()
    if not cases or any(row[0]!='passed' for row in cases):raise ValueError('Every defined case needs an actual passing run')
    mutation=conn.execute("SELECT payload,created_at FROM hb_task_events WHERE task_id=? AND kind='mutation' ORDER BY event_id DESC LIMIT 1",(task_id,)).fetchone()
    last_pass=conn.execute("SELECT MAX(started_at) FROM test_runs WHERE step_id=? AND status='pass'",(task['step_id'],)).fetchone()[0]
    if not mutation or not last_pass or last_pass<mutation[1] or review[1]<last_pass:raise ValueError('Source and independent review need fresh passing verification')
    manifest=json.loads(mutation[0]).get('after_sha256')
    if not manifest:raise ValueError('The native source change needs a complete saved hash manifest')
    for path,digest in manifest.items():
        target=ROOT/path
        if not target.resolve().is_relative_to(ROOT.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
            raise ValueError('Source changed after the reviewed verification; retest before acceptance')
    if not isinstance(evidence_message_ids,list) or not 1<=len(evidence_message_ids)<=8:raise ValueError('Provide actual successful APEX reply IDs')
    for mid in evidence_message_ids:
        if not conn.execute("SELECT 1 FROM hb_task_messages t JOIN hb_peer_replies r ON r.message_id=t.message_id JOIN messages m ON m.id=t.message_id WHERE t.task_id=? AND t.message_id=? AND r.outcome='answer' AND m.from_agent='apex'",(task_id,mid)).fetchone():
            raise ValueError('Acceptance evidence must be an actual successful APEX reply in this task')
    now=time.time()
    if not conn.execute("UPDATE project_steps SET status='done',updated_at=? WHERE step_id=? AND project_id=?",(now,task['step_id'],task['project_id'])).rowcount:
        raise ValueError('The canonical Studio step is missing')
    conn.execute("UPDATE hb_tasks SET state='completed',updated_at=? WHERE task_id=?",(now,task_id))
    eid=hb_tasks.event(conn,task,'owner-host','accepted',{'mode':'native_instructor_override',
        'reason':'External reviewer capacity unavailable; native instructor assessed independent local review and actual APEX verification.',
        'review_event_id':review_event_id,'evidence_message_ids':evidence_message_ids,'assessment':assessment,
        'provider_condition_preserved':True,'parent_project_accepted':False})
    return {'task_id':task_id,'step_id':task['step_id'],'state':'completed','receipt_id':eid,'mode':'native_instructor_override'}
