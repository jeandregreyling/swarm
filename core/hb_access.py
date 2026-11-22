"""Access requests (Practice 270, JD 22 Nov 00:5x: "give HB and APEX permission to ask me or any other owner level for access").

  request(conn, agent, tool, task_id, why)  APEX/HB asks; every owner sees it in main chat, Needs-you and on Telegram
  decide(conn, rid, grant, actor)            an owner answers with /grant A-xxxx or /deny A-xxxx (or '/permissions granted to request A-xxxx')
  granted_tools(conn, task_id)               tools an owner granted for that task - added to its next work turn

A grant is narrow: one known APEX tool, on one task. Nobody grants themselves - only owner commands decide.
"""
import re
import time
import uuid

RID = re.compile(r'\bA-[0-9A-F]{6}\b', re.I)


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_access_requests(id TEXT PRIMARY KEY, agent TEXT, tool TEXT, task_id TEXT, why TEXT, '
                 "state TEXT DEFAULT 'pending', decided_by TEXT, at REAL, decided_at REAL)")


def _known(tool):
    from core import apex_tools
    return tool in set(apex_tools.TOOL_SCHEMAS) | set(apex_tools.TEST_TOOL_SCHEMAS) | set(apex_tools.WEB_TOOL_SCHEMAS)


def request(conn, agent, tool, task_id, why):
    ensure(conn)
    tool, why = str(tool or '').strip(), str(why or '').strip()
    if not _known(tool):
        raise ValueError(f'{tool!r} is not one of APEX\'s tools; ask for a real tool by name')
    if len(why) < 10:
        raise ValueError('say why you need it (10+ characters): what you will do with it on this task')
    old = conn.execute("SELECT id FROM hb_access_requests WHERE tool=? AND COALESCE(task_id,'')=COALESCE(?,'') AND state='pending'",
                       (tool, task_id)).fetchone()
    if old:
        return {'request_id': old[0], 'state': 'pending', 'note': 'already asked - waiting for an owner'}
    rid = 'A-' + uuid.uuid4().hex[:6].upper()
    conn.execute('INSERT INTO hb_access_requests(id,agent,tool,task_id,why,at) VALUES (?,?,?,?,?,?)', (rid, agent, tool, task_id, why[:400], time.time()))
    text = (f"🔑 {agent.upper() if agent == 'apex' else agent} asks for access: {tool}" + (f' on {task_id}' if task_id else '') +
            f" - {why[:300]}\nOwners: /grant {rid} or /deny {rid}")
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'hummingbird','user',?,'response',0)", (text,))
    try:   # every owner on Telegram (JD, and partners with owner rights)
        from core.hb_channels import telegram_send
        for (key,) in conn.execute("SELECT key FROM hb_channel_identities WHERE role='owner' AND key LIKE 'telegram:%'").fetchall():
            telegram_send(key.split(':', 1)[1], text)
    except Exception:
        pass
    return {'request_id': rid, 'state': 'pending', 'note': 'asked every owner; carry on with other work until it is granted'}


def decide(conn, rid, grant, actor):
    ensure(conn)
    rid = str(rid or '').upper()
    row = conn.execute('SELECT agent, tool, task_id, state FROM hb_access_requests WHERE id=?', (rid,)).fetchone()
    if not row:
        return f'No access request {rid}.'
    if row[3] != 'pending':
        return f'{rid} was already {row[3]}.'
    conn.execute('UPDATE hb_access_requests SET state=?, decided_by=?, decided_at=? WHERE id=?',
                 ('granted' if grant else 'denied', actor, time.time(), rid))
    where = f' on {row[2]}' if row[2] else ''
    return (f'✔ {rid}: {row[1]} granted to {row[0]}{where} by {actor}. It is attached from the next turn.' if grant else
            f'✘ {rid}: {row[1]} denied to {row[0]}{where} by {actor}.')


def granted_tools(conn, task_id):
    try:
        ensure(conn)
        return [r[0] for r in conn.execute("SELECT DISTINCT tool FROM hb_access_requests WHERE task_id=? AND state='granted'", (task_id,))]
    except Exception:
        return []


def pending(conn):
    ensure(conn)
    return conn.execute("SELECT id, agent, tool, task_id, why FROM hb_access_requests WHERE state='pending' ORDER BY at").fetchall()
