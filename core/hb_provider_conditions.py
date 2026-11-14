"""Retain genuine provider conditions without repeating rejected operations."""
import json
import hashlib
import re
import math
import time
from contextlib import closing


def instruction_scope(conn,task):
    rows=conn.execute("SELECT m.content FROM hb_task_messages t JOIN messages m ON m.id=t.message_id WHERE t.task_id=? AND t.kind='instruction' AND m.from_agent IN ('user','ghost') ORDER BY m.id",(task['task_id'],)).fetchall()
    return hashlib.sha256(json.dumps([task['objective'],[r[0] for r in rows]]).encode()).hexdigest()


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_provider_conditions(
        task_id TEXT PRIMARY KEY,request_id INTEGER,task_version INTEGER,kind TEXT,
        detail TEXT,recovery_requirement TEXT,event_id INTEGER,resolved_event_id INTEGER)''')


def record_failure(conn,task,request_id,error):
    text=str(error)
    if re.search(r'potentially unintended activity|safety review|policy.violation|provider.*reject',text,re.I):
        kind='provider_policy';requirement='A revised owner instruction or independently verified provider recovery is required; the rejected operation will not be retried unchanged.'
    elif re.search(r'usage.?limit.?exceeded|rate.limit|quota.exceed|insufficient.quota|exhausted.*(?:credit|balance)',text,re.I):
        kind='provider_capacity';requirement='Record a verified provider availability change before retrying this operation; other local tasks may continue.'
    else:return None
    ensure_schema(conn)
    from core import hb_tasks
    payload={'request_id':request_id,'kind':kind,'detail':text[:1000],'recovery_requirement':requirement}
    eid=hb_tasks.event(conn,task,'hummingbird','provider_condition',payload,request_id=request_id)
    conn.execute('''INSERT INTO hb_provider_conditions VALUES (?,?,?,?,?,?,?,NULL)
        ON CONFLICT(task_id) DO UPDATE SET request_id=excluded.request_id,task_version=excluded.task_version,
        kind=excluded.kind,detail=excluded.detail,recovery_requirement=excluded.recovery_requirement,
        event_id=excluded.event_id,resolved_event_id=NULL''',
        (task['task_id'],request_id,instruction_scope(conn,task),kind,text[:1000],requirement,eid))
    return payload


def pending(conn,task,*,agent=None):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_provider_conditions'").fetchone():return None
    row=conn.execute('SELECT task_version,kind,detail,recovery_requirement,event_id,request_id FROM hb_provider_conditions WHERE task_id=? AND resolved_event_id IS NULL',(task['task_id'],)).fetchone()
    if not row:return None
    if row[1]=='provider_capacity':
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'hb_reply_usage' in tables:
            success=conn.execute('''SELECT p.id FROM peer_messages p JOIN hb_peer_work w ON w.request_id=p.id
                JOIN hb_reply_usage u ON u.request_id=p.id
                WHERE p.recipient=(SELECT recipient FROM peer_messages WHERE id=?)
                AND w.state='completed' AND p.delivered_at IS NOT NULL
                AND json_extract(u.usage_json,'$.source')='provider'
                AND w.updated_at>(SELECT created_at FROM hb_task_events WHERE event_id=?)
                ORDER BY w.updated_at DESC LIMIT 1''',(row[5],row[4])).fetchone()
            if success:
                from core import hb_tasks
                eid=hb_tasks.event(conn,task,'hummingbird','provider_capacity_recovered',{'condition_event_id':row[4],
                    'successful_request_id':success[0],'reason':'A later authenticated same-provider request completed with a saved reply and provider usage.'})
                conn.execute('UPDATE hb_provider_conditions SET resolved_event_id=? WHERE task_id=?',(eid,task['task_id']))
                return None
    if agent:
        recipient=conn.execute('SELECT recipient FROM peer_messages WHERE id=?',(row[5],)).fetchone()
        if recipient and recipient[0]!=agent:return None
    if instruction_scope(conn,task)!=row[0]:
        from core import hb_tasks
        eid=hb_tasks.event(conn,task,'hummingbird','provider_condition_revised',{'previous_condition':row[4],'reason':'Actual owner instruction scope changed; reconcile the new request before execution'})
        conn.execute('UPDATE hb_provider_conditions SET resolved_event_id=? WHERE task_id=?',(eid,task['task_id']))
        return None
    return dict(zip(('kind','detail','recovery_requirement','event_id'),row[1:5]))


def _capacity_snapshot(data):
    """Accept only explicit Codex allowance windows, never credentials or prose."""
    main=data.get('rateLimits',{}) if isinstance(data,dict) else {}
    if not isinstance(main,dict) or main.get('limitId')!='codex':return None
    groups=data.get('rateLimitsByLimitId') or {'codex':main}
    if not isinstance(groups,dict) or 'codex' not in groups:return None
    result={}
    for name,value in groups.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',name) or not isinstance(value,dict):return None
        if value.get('limitId',name)!=name:return None
        windows={}
        for key in ('primary','secondary'):
            window=value.get(key)
            if not isinstance(window,dict):return None
            used=window.get('usedPercent');reset=window.get('resetsAt')
            if type(used) not in {int,float} or not math.isfinite(used) or not 0<=used<=100 or type(reset) is not int:return None
            windows[key]={'usedPercent':used,'resetsAt':reset}
        result[name]=windows
    for key,window in result['codex'].items():
        observed=main.get(key)
        if not isinstance(observed,dict) or any(observed.get(field)!=value for field,value in window.items()):return None
    return result


def _capacity_available(snapshot,now):
    return bool(snapshot) and all(w['usedPercent']<100 and w['resetsAt']>now for group in snapshot.values() for w in group.values())


def _capacity_improved(previous,current,now):
    if not previous:return True  # The prior evidence was an actual capacity rejection.
    for name,group in current.items():
        for key,window in group.items():
            old=previous.get(name,{}).get(key)
            if old and (window['usedPercent']<old['usedPercent'] or
                        window['resetsAt']>old['resetsAt'] and now>=old['resetsAt']):return True
    return False


def probe_codex_capacity(*,now=None,client_factory=None):
    """HB's bounded status read; no inference, quota reset or permission change."""
    from core import agent_identity,hb_tasks,hb_owner_sessions
    from core.hb_chat_controls import continuation,held_requests
    from utils.db._connection import get_connection
    if agent_identity.CURRENT.get():raise PermissionError('Provider status observation belongs to the HB coordinator')
    now=time.time() if now is None else now
    def eligible(conn,tid):
        task=hb_tasks.get(conn,tid)
        return task if (task and task['state']=='active' and hb_owner_sessions.for_task(conn,tid,active=True)
            and continuation(conn,task)['mode']!='off' and not held_requests(conn,task)) else None
    with closing(get_connection()) as conn,conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_provider_conditions'").fetchone():return {'state':'idle'}
        candidates=[(tid,eid) for tid,eid in conn.execute("""SELECT c.task_id,c.event_id FROM hb_provider_conditions c
            JOIN peer_messages p ON p.id=c.request_id WHERE c.kind='provider_capacity'
            AND c.resolved_event_id IS NULL AND p.recipient='codex-instructor'""") if eligible(conn,tid)]
        if not candidates:return {'state':'idle'}
        conn.execute('''CREATE TABLE IF NOT EXISTS hb_provider_probes(provider TEXT PRIMARY KEY,
            last_probe REAL,observed TEXT,accepted TEXT,outcome TEXT,detail TEXT)''')
        old=conn.execute("SELECT last_probe,accepted FROM hb_provider_probes WHERE provider='codex'").fetchone()
        if old and now-old[0]<300:return {'state':'not_due'}
        previous=json.loads(old[1]) if old and old[1] else None
        conn.execute("INSERT INTO hb_provider_probes VALUES('codex',?,NULL,NULL,'checking','Read-only account/rateLimits/read') ON CONFLICT(provider) DO UPDATE SET last_probe=excluded.last_probe,outcome='checking'",(now,))
    # No SQLite write lock is held during the external status request.
    client=None;snapshot=None;error=''
    try:
        if client_factory is None:
            from core.hb_codex_runtime import CodexRuntime
            client=CodexRuntime(timeout=20)
        else:client=client_factory()
        snapshot=_capacity_snapshot(client.call('account/rateLimits/read',{}))
    except Exception as exc:
        from core.hb_agent_tools import public_error
        error=type(exc).__name__+': '+public_error(exc)
    finally:
        if client:
            try:client.close()
            except Exception:pass
    available=_capacity_available(snapshot,now)
    improved=available and _capacity_improved(previous,snapshot,now)
    state='verified_available' if improved else 'observed_no_recovery_change' if available else 'limited' if snapshot else 'unknown'
    resolved=[]
    with closing(get_connection()) as conn,conn:
        conn.execute("UPDATE hb_provider_probes SET observed=?,outcome=?,detail=? WHERE provider='codex'",(json.dumps(snapshot) if snapshot else None,state,error))
        if improved:
            for tid,eid in candidates:
                task=eligible(conn,tid)
                if not task:continue
                current=conn.execute("SELECT 1 FROM hb_provider_conditions WHERE task_id=? AND event_id=? AND kind='provider_capacity' AND resolved_event_id IS NULL",(tid,eid)).fetchone()
                if not current:continue
                verified=hb_tasks.event(conn,task,'hummingbird','provider_capacity_recovered',{
                    'condition_event_id':eid,'source':'Authenticated Codex app-server account/rateLimits/read',
                    'checked_at':now,'allowance_windows':snapshot,
                    'reason':'Fresh usable allowance observed; later retries require a measured improvement or a verified successful provider reply. No quota or owner control was changed.'})
                conn.execute('UPDATE hb_provider_conditions SET resolved_event_id=? WHERE task_id=? AND event_id=?',(verified,tid,eid))
                resolved.append(tid)
            if resolved:conn.execute("UPDATE hb_provider_probes SET accepted=? WHERE provider='codex'",(json.dumps(snapshot),))
    return {'state':state,'resolved_task_ids':resolved,'allowance_windows':snapshot}
