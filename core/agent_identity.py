"""Per-agent application credentials, private memory and attributable tool execution.

Credentials use the existing Hummingbird service-token store. They are consumed
by the host, never inserted in model prompts. This is application isolation;
processes still run under the service's Unix account.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import contextvars
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import sqlite3
import stat
import time
import uuid

STATE = Path(os.environ.get('HUMMINGBIRD_AGENT_STATE',
    str(Path.home() / '.local/share/hummingbird/agent-identities')))
CURRENT = contextvars.ContextVar('hummingbird_agent_execution', default=None)
SCOPES = {'agent.identity', 'agent.memory', 'agent.tools', 'agent.api'}
SOURCE_TOOLS = {'git_status', 'list_files', 'read_file', 'grep_repo', 'get_diff'}
WRITE_TOOLS = {'propose_write_file', 'propose_patch'}


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise PermissionError('Invalid agent identity')
    return value


def enabled():
    return (STATE / 'enabled').is_file()


def directory(agent):
    path = STATE / name(agent)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if STATE.is_symlink() or path.is_symlink():
        raise PermissionError('Agent identity directories cannot be symlinks')
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _private_file(path, content):
    if path.is_symlink():
        raise PermissionError('Agent identity file cannot be a symlink')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def credentials(agent):
    path = STATE / name(agent) / 'credentials.json'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > 4096):
            raise PermissionError('Agent credential file must be private and host-owned')
        value = json.load(stream)
    if value.get('principal') != agent or not isinstance(value.get('token'), str):
        raise PermissionError('Agent credential identity mismatch')
    return value


def authenticate(conn, raw, claimed=None, scope='agent.identity'):
    from core import peer_bridge as peers
    principal = peers.authenticate(conn, raw)
    if not principal or scope not in principal['scopes']:
        raise PermissionError('Invalid, revoked or insufficient agent credential')
    if claimed and claimed != principal['id']:
        raise PermissionError('Claimed agent does not match authenticated login')
    row = conn.execute('SELECT id FROM service_tokens WHERE token_sha256=?',
                       (hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
    return {**principal, 'credential_id': row[0]}


def _memory(agent):
    path = directory(agent) / 'memory.sqlite'
    if path.is_symlink():
        raise PermissionError('Agent memory file cannot be a symlink')
    conn = sqlite3.connect(path, timeout=10)
    os.chmod(path, 0o600)
    # Keep damaged legacy TEXT bytes on disk; render replacement characters only on read.
    conn.text_factory = lambda raw: raw.decode("utf-8", errors="replace")
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY, subject TEXT NOT NULL, content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '', importance INTEGER NOT NULL DEFAULT 5,
            source TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ticket_ref TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0, legacy_store TEXT, legacy_id INTEGER,
            UNIQUE(legacy_store,legacy_id));
        CREATE TABLE IF NOT EXISTS actions (
            event_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, payload TEXT NOT NULL);
    ''')
    if 'ticket_ref' not in {row[1] for row in conn.execute('PRAGMA table_info(memories)')}:
        conn.execute("ALTER TABLE memories ADD COLUMN ticket_ref TEXT NOT NULL DEFAULT ''")
        conn.commit()
    return conn


def _check_memory_identity(agent):
    principal = CURRENT.get()
    if principal and principal['principal'] != agent:
        raise PermissionError('Agent may access only its own private memory')


def save_memory(agent, subject, content, tags='', importance=5, source='learned', *, ticket_ref=''):
    _check_memory_identity(agent)
    if not all(isinstance(v, str) for v in (subject, content, tags, source)):
        raise ValueError('Memory fields must be text')
    identity = CURRENT.get()
    if identity and not ticket_ref:
        if identity.get('task_id'):
            ticket_ref=identity['task_id']
        elif identity.get('peer_request_id'):
            from utils.db._connection import get_connection
            from core import hb_tasks
            with closing(get_connection()) as main:
                if main.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_requests'").fetchone():
                    task=hb_tasks.for_request(main,identity['peer_request_id'])
                    if task:ticket_ref=task['task_id']
    action = uuid.uuid4().hex
    event(identity,action,'memory.save','started',result={'content_sha256':hashlib.sha256(content.encode()).hexdigest()})
    with closing(_memory(agent)) as conn:
        cur = conn.execute('INSERT INTO memories(subject,content,tags,importance,source,ticket_ref) VALUES (?,?,?,?,?,?)',
            (subject[:200], content, tags[:500], int(importance), source[:200],ticket_ref))
        conn.commit()
        record = cur.lastrowid
    event(identity,action,'memory.save','succeeded',result={'memory_id':record})
    return record


def memory_record(row):
    """Render transport history as bounded source handles, including older rows."""
    result=dict(row)
    evidence_id=result.pop('legacy_id',None)
    if result.get('source')=='hb-transport:task-event' and len(result.get('content',''))>1800:
        try:
            original=json.loads(result['content'])
        except (TypeError,ValueError):
            original={}
        value={key:original[key] for key in ('task_id','project_id','step_id','actor','kind','message_id','request_id') if key in original}
        value['notice']='Full original receipt remains in task evidence; transport copies are not recursively loaded.'
        value['read']={'tool':'task_evidence','arguments':{'evidence_id':evidence_id,'offset':0}}
        result['content']=json.dumps(value,ensure_ascii=True)
    return result


def read_memory(agent, query='', limit=5):
    _check_memory_identity(agent)
    if not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Memory query must be text; limit must be 1-100')
    with closing(_memory(agent)) as conn:
        rows=conn.execute('''SELECT id,subject,content,tags,importance,source,created_at,ticket_ref,legacy_id
            FROM memories WHERE archived=0 AND (instr(lower(subject),lower(?))>0
            OR instr(lower(content),lower(?))>0 OR instr(lower(tags),lower(?))>0)
            ORDER BY CASE WHEN source='hb-transport:task-event' OR source LIKE 'peer:peer_message:%' THEN 1 ELSE 0 END,
            importance DESC,id DESC LIMIT ?''', (query, query, query, limit)).fetchall()
        return [memory_record(row) for row in rows]


def private_memory_call(agent,operation,callback):
    """Authenticated host adapter for older specialist memory maintenance code."""
    with execution(agent) as identity:
        action = uuid.uuid4().hex
        event(identity,action,operation,'started')
        with closing(_memory(agent)) as conn:
            before = {row[0]:(row[1],row[2]) for row in conn.execute('SELECT id,archived,importance FROM memories')}
            result = callback(conn)
            conn.commit()
            after = {row[0]:(row[1],row[2]) for row in conn.execute('SELECT id,archived,importance FROM memories')}
        event(identity,action,operation,'succeeded',result={
            'memory_ids':[record for record in before.keys() | after.keys() if before.get(record)!=after.get(record)],
            'result_sha256':hashlib.sha256(str(result).encode()).hexdigest()})
        return result


def _migrate_memory(conn, agent):
    from utils.db._connection import AGENT_POOL_MAP
    candidates = {AGENT_POOL_MAP.get(agent), 'memory_' + agent.replace('-', '_')}
    registry_columns = {row[1] for row in conn.execute('PRAGMA table_info(agents)')}
    if 'memory_table' in registry_columns:
        configured = conn.execute('SELECT memory_table FROM agents WHERE name=?',(agent,)).fetchone()
        if configured:
            candidates.add(configured[0])
    count = 0
    with closing(_memory(agent)) as memory:
        for table in sorted(candidate for candidate in candidates if isinstance(candidate,str)
                            and re.fullmatch(r'[a-z_]+',candidate)):
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if not {'id', 'agent', 'subject', 'content'} <= columns:
                continue
            fields = ['id','subject','content','tags','importance','source','created_at','archived','ticket_ref']
            expressions = [field if field in columns else ('5' if field == 'importance' else
                '0' if field == 'archived' else "''") for field in fields]
            expressions = [f'CAST({expression} AS BLOB)' if field not in {'id','importance','archived'}
                           else expression for field,expression in zip(fields,expressions)]
            for row in conn.execute(f'SELECT {",".join(expressions)} FROM {table} WHERE lower(agent)=?', (agent,)):
                cur = memory.execute('''INSERT OR IGNORE INTO memories
                    (subject,content,tags,importance,source,created_at,archived,ticket_ref,legacy_store,legacy_id)
                    VALUES (CAST(? AS TEXT),CAST(? AS TEXT),CAST(? AS TEXT),?,CAST(? AS TEXT),
                            CAST(? AS TEXT),?,CAST(? AS TEXT),?,?)''',
                    (row[1] or '',row[2] or '',row[3] or '',row[4] or 5,row[5] or '',
                     row[6] or '',row[7] or 0,row[8] or '',table,row[0]))
                count += cur.rowcount
        memory.commit()
    return count


def mirror_peer_memory(agent, kind, content, receipt, legacy_id=None):
    """Trusted transport writes an attributable delivery into the recipient's file."""
    with closing(_memory(agent)) as memory:
        cur = memory.execute('''INSERT OR IGNORE INTO memories(subject,content,source,legacy_store,legacy_id)
            VALUES (?,?,?,'service_memory',?)''',(kind[:200],content,'peer:'+receipt[:180],legacy_id))
        memory.commit()
        return cur.lastrowid


def _migrate_peer_memory(conn, agent):
    count = 0
    with closing(_memory(agent)) as memory:
        for row in conn.execute('''SELECT id,CAST(kind AS BLOB),CAST(content AS BLOB),CAST(source_receipt AS BLOB),CAST(created_at AS BLOB)
                FROM service_memory WHERE principal_id=?''',(agent,)):
            cur = memory.execute('''INSERT OR IGNORE INTO memories
                (subject,content,source,created_at,legacy_store,legacy_id)
                VALUES (CAST(? AS TEXT),CAST(? AS TEXT),CAST(? AS TEXT),CAST(? AS TEXT),'service_memory',?)''',
                (row[1],row[2],row[3],row[4],row[0]))
            count += cur.rowcount
        memory.commit()
    return count


def provision(conn, *, activate=False):
    """Idempotently enroll registered machines without revoking existing peer clients."""
    from core import peer_bridge as peers
    peers.ensure_schema(conn)
    columns = {row[1] for row in conn.execute('PRAGMA table_info(agents)')}
    registered = {}
    if {'name','tier'} <= columns:
        for row in conn.execute("SELECT name,tier FROM agents WHERE COALESCE(tier,'')!='human'"):
            registered[name(row[0])] = row[0]
    for row in conn.execute('SELECT id,display_name FROM service_principals'):
        registered[name(row[0])] = row[1]
    registered['fridays'] = 'Fridays runtime'
    result = []
    for agent, display in sorted(registered.items()):
        conn.execute('''INSERT OR IGNORE INTO service_principals
            (id,display_name,role,enabled,created_at) VALUES (?,?,'service',1,?)''', (agent,display,time.time()))
        path = directory(agent) / 'credentials.json'
        valid = False
        try:
            existing = credentials(agent)
            stored = conn.execute('''SELECT scopes FROM service_tokens WHERE principal_id=?
                AND token_sha256=? AND revoked_at IS NULL''',
                (agent,hashlib.sha256(existing['token'].encode()).hexdigest())).fetchone()
            required = SCOPES | ({'agent.write'} if agent=='apex' else set())
            valid = stored is not None and required <= set(json.loads(stored[0]))
        except (OSError,ValueError,PermissionError):
            pass
        if not valid:
            raw = peers.TOKEN_PREFIX + secrets.token_urlsafe(32)
            scopes = SCOPES | {scope for scope in peers.SCOPES.get(agent, ('peer.read','peer.post','peer.memory'))
                if scope in {'peer.read','peer.post','peer.memory'} or scope.startswith('peer.relay:')}
            if agent=='apex':
                scopes.add('agent.write')
            conn.execute('''INSERT INTO service_tokens(principal_id,token_sha256,scopes,created_at)
                VALUES (?,?,?,?)''', (agent,hashlib.sha256(raw.encode()).hexdigest(),json.dumps(sorted(scopes)),time.time()))
            _private_file(path,json.dumps({'principal':agent,'token':raw,
                'endpoint':'http://127.0.0.1:5050','memory_file':str(path.parent/'memory.sqlite')},indent=2)+'\n')
        # This enables a machine login; it does not enable a disabled inference provider.
        conn.execute('UPDATE service_principals SET enabled=1 WHERE id=?',(agent,))
        profile_columns = {row[1] for row in conn.execute('PRAGMA table_info(user_profiles)')}
        if {'username','display_name','user_type','linked_agent','role','approved'} <= profile_columns:
            conn.execute('''INSERT OR IGNORE INTO user_profiles
                (username,display_name,user_type,linked_agent,role,approved)
                VALUES (?,?,'agent',?,'viewer',1)''',(agent,display,agent))
        permission_columns = {row[1] for row in conn.execute('PRAGMA table_info(user_skill_permissions)')}
        if {'username','skill_name','allowed'} <= permission_columns:
            conn.execute('''INSERT OR IGNORE INTO user_skill_permissions(username,skill_name,allowed)
                VALUES (?,'fs_readonly',1)''',(agent,))
            conn.execute('''INSERT OR IGNORE INTO user_skill_permissions(username,skill_name,allowed)
                VALUES (?,'knowledge_search',1)''',(agent,))
        migrated = _migrate_memory(conn,agent) + _migrate_peer_memory(conn,agent)
        with closing(_memory(agent)):
            pass
        result.append({'principal':agent,'memory_file':str(path.parent/'memory.sqlite'),'imported':migrated})
    conn.commit()
    if activate:
        _private_file(STATE/'enabled','Individual agent authentication and attribution enabled.\n')
    return result


@contextmanager
def execution(agent, *, model='', requested_by='', conversation_id=None, principal=None):
    """Bind execution to a real machine login, including host-delegated local runs."""
    if not enabled():
        yield None
        return
    agent = name(agent)
    current = CURRENT.get()
    if current:
        if current['principal'] != agent:
            raise PermissionError('Execution cannot impersonate another agent')
        if not identity_is_active(current):
            raise PermissionError('Agent execution login has been revoked')
        yield current
        return
    if principal is None:
        from flask import has_request_context
        if has_request_context():
            from services.auth import get_current_user
            operator = get_current_user()
            if not operator or operator.get('role') != 'owner':
                raise PermissionError('Authenticated owner delegation or agent login required')
            requested_by = requested_by or operator['username']
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            principal = authenticate(conn,credentials(agent)['token'],agent)
            conn.commit()
    if principal['id'] != agent or 'agent.identity' not in principal['scopes']:
        raise PermissionError('Authenticated agent execution required')
    identity = {'principal':agent,'credential_id':principal['credential_id'],
        'run_id':uuid.uuid4().hex,'model':model,'requested_by':requested_by,
        'conversation_id':conversation_id}
    token = CURRENT.set(identity)
    try:
        yield identity
    finally:
        CURRENT.reset(token)


def identity_is_active(identity):
    from utils.db._connection import get_connection
    with closing(get_connection()) as conn:
        row = conn.execute('''SELECT 1 FROM service_tokens t JOIN service_principals p
            ON p.id=t.principal_id WHERE t.id=? AND t.principal_id=?
            AND t.revoked_at IS NULL AND p.enabled=1''',
            (identity['credential_id'],identity['principal'])).fetchone()
    return row is not None


def _ledger():
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    path = STATE/'actions.sqlite'
    if path.is_symlink():
        raise PermissionError('Audit store cannot be a symlink')
    conn = sqlite3.connect(path,timeout=10)
    os.chmod(path,0o600)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS events (
        sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
        action_id TEXT NOT NULL, principal TEXT NOT NULL, run_id TEXT NOT NULL,
        status TEXT NOT NULL, created_at REAL NOT NULL, payload TEXT NOT NULL)''')
    return conn


def event(identity, action_id, tool, status, *, paths=None, before=None, after=None, result=None):
    if not identity:
        return None
    item = {**identity,'event_id':uuid.uuid4().hex,'action_id':action_id,'tool':tool,
        'status':status,'created_at':time.time(),'paths':paths or [],
        'before':before or {},'after':after or {},'result':result or {}}
    payload = json.dumps(item,sort_keys=True)
    try:
        with closing(_ledger()) as conn:
            conn.execute('''INSERT INTO events(event_id,action_id,principal,run_id,status,created_at,payload)
                VALUES (?,?,?,?,?,?,?)''', (item['event_id'],action_id,identity['principal'],
                identity['run_id'],status,item['created_at'],payload))
            conn.commit()
        with closing(_memory(identity['principal'])) as conn:
            conn.execute('INSERT INTO actions(event_id,action_id,payload) VALUES (?,?,?)',
                         (item['event_id'],action_id,payload))
            conn.commit()
    except (OSError,sqlite3.Error) as exc:
        raise RuntimeError('Agent audit could not be persisted; inspect action '+action_id) from exc
    return item['event_id']


def path_hashes(repository, paths):
    values = {}
    for relative in paths:
        path = repository._source_path(relative)
        if not path.exists():
            values[relative] = None
            continue
        fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024*1024:
                raise ValueError('Audit target must be bounded source text')
            values[relative] = hashlib.sha256(stream.read(1024*1024+1)).hexdigest()
    return values


def audit_rows(*, agent=None, limit=50):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Audit limit must be 1-200')
    with closing(_ledger()) as conn:
        if agent:
            rows = conn.execute('SELECT payload FROM events WHERE principal=? ORDER BY sequence DESC LIMIT ?',
                                (name(agent),limit)).fetchall()
        else:
            rows = conn.execute('SELECT payload FROM events ORDER BY sequence DESC LIMIT ?',(limit,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def authenticated_skill_call(skill, args, agent, conversation_id, invoke):
    """Shared legacy tool entry: distinct machine login, durable attempt and outcome."""
    if not enabled():
        return invoke()
    actor = 'fridays' if agent == 'ghost' else name(agent)
    with execution(actor,conversation_id=conversation_id) as identity:
        action_id = uuid.uuid4().hex
        repository = None
        paths = []
        if skill in {'fs_write','fs_append','fs_patch','fs_patch_lines','fs_insert_before','fs_insert_after'}:
            from core.apex_tools import ReadOnlyRepository
            repository = ReadOnlyRepository()
            parts = shlex.split(str(args).splitlines()[0]) if str(args).strip() else []
            if parts:
                paths = [parts[0]]
        before = path_hashes(repository,paths) if paths else {}
        # Record argument hashes, not file payloads, secrets or model prompts.
        argument_hash = hashlib.sha256(str(args).encode()).hexdigest()
        event(identity,action_id,skill,'started',paths=paths,before=before,
              result={'arguments_sha256':argument_hash})
        try:
            result = invoke()
        except Exception as exc:
            event(identity,action_id,skill,'failed',paths=paths,before=before,
                  after=path_hashes(repository,paths) if paths else {},
                  result={'error_type':type(exc).__name__})
            raise
        event(identity,action_id,skill,'succeeded' if result[0] else 'failed',
              paths=paths,before=before,after=path_hashes(repository,paths) if paths else {},
              result={'output_sha256':hashlib.sha256(str(result[1]).encode()).hexdigest()})
        return result


def main():
    import argparse
    from utils.db._connection import get_connection
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['provision','status','revoke'])
    parser.add_argument('--agent',help='Agent login to revoke')
    args = parser.parse_args()
    with closing(get_connection()) as conn:
        if args.command == 'provision':
            rows = provision(conn,activate=True)
            print(json.dumps({'enabled':True,'agents':rows,'audit_store':str(STATE/'actions.sqlite')},indent=2))
        elif args.command == 'revoke':
            agent = name(args.agent)
            conn.execute('UPDATE service_principals SET enabled=0 WHERE id=?',(agent,))
            conn.execute('UPDATE service_tokens SET revoked_at=? WHERE principal_id=? AND revoked_at IS NULL',
                         (time.time(),agent))
            conn.commit()
            print(json.dumps({'principal':agent,'login_enabled':False}))
        else:
            rows = conn.execute('''SELECT p.id,p.enabled,max(t.last_used_at)
                FROM service_principals p LEFT JOIN service_tokens t ON t.principal_id=p.id
                AND t.revoked_at IS NULL GROUP BY p.id,p.enabled ORDER BY p.id''').fetchall()
            print(json.dumps({'enabled':enabled(),'agents':[
                {'principal':row[0],'login_enabled':bool(row[1]),'last_authenticated_contact':row[2],
                 'memory_file_exists':(STATE/row[0]/'memory.sqlite').is_file()} for row in rows]},indent=2))


if __name__ == '__main__':
    main()
