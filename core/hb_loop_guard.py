"""No self-looping, ever (owner 14 Nov 2026): "same answer, same request: immediate red flag and termination of the process. I don't care if
it's updating, it should never loop." Precisely (JD): the same answer CONSECUTIVELY in the same task to the same AUTOMATIC request with nothing
changed between - not "never the same answer again": if JD asks for an IP address or a task number twice, the right answer is the same twice.

  replies   an agent gives the same answer to the same request in a task, with no change and no passing check in between -> HB stops that
            task at once: held, its queued work cancelled, a red flag in main chat naming what looped, a lesson in the agent's memory.
  restarts  HB refuses a restart with the same reason as one in the last RESTART_REPEAT_S (core/hb_plan_workflow.restart_tick) and flags it.
  HB itself a database trigger drops an identical AUTOMATIC HB notice (one that starts with a status marker) to JD in the same chat within
            REPEAT_S. Answers to JD's own commands always go through (asking /downloads twice gets two answers).
"""
import hashlib
import json
import re
import time

REPEAT_S = 600
RESTART_REPEAT_S = 900
_NOISE = re.compile(r'\[Backend[^\]]*\]|\b[0-9a-f]{12,}\b|\b(request|receipt|run|event|message|job)[ #:_-]*\w*\d\w*\b|\s+', re.I)


def normalize(text):
    return _NOISE.sub(' ', str(text or '')).strip().lower()


def _request_signature(conn, request_id):
    row = conn.execute('SELECT body FROM peer_messages WHERE id=?', (request_id,)).fetchone() if request_id else None
    body = str(row[0] if row else '')
    try:
        data = json.loads(body)
        if isinstance(data, dict):               # an HB continuation: the same instruction and next action is the same request
            body = json.dumps({k: data.get(k) for k in ('task_type', 'task_id', 'instruction', 'next_action', 'next_task')}, sort_keys=True)
    except ValueError:
        pass
    return hashlib.sha256(normalize(body).encode()).hexdigest()


def check_reply(conn, task, agent, text, request_id):
    """Called when an agent's reply is recorded. Returns the red flag text when it stopped a loop, else None."""
    if not task or not normalize(text):
        return None
    sender = conn.execute('SELECT sender FROM peer_messages WHERE id=?', (request_id,)).fetchone() if request_id else None
    if not sender or sender[0] in ('user', 'ghost', 'owner'):
        return None                                   # JD's own question: the same right answer twice is not a loop
    prev = conn.execute("SELECT event_id, request_id, payload FROM hb_task_events WHERE task_id=? AND agent=? AND kind='reply' AND request_id IS NOT NULL "
                        "AND request_id<>? ORDER BY event_id DESC LIMIT 1", (task['task_id'], agent, request_id or -1)).fetchone()
    if not prev:
        return None
    try:
        before = json.loads(prev[2]).get('content', '')
    except ValueError:
        return None
    if normalize(before) != normalize(text) or _request_signature(conn, prev[1]) != _request_signature(conn, request_id):
        return None
    moved = conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND event_id>? AND (kind='mutation' OR (kind='test_result' AND "
                         "json_extract(payload,'$.alm_run_status')='pass'))", (task['task_id'], prev[0])).fetchone()
    if moved:
        return None
    return stop(conn, task, agent, f'{agent} gave the same answer to the same request twice: "{str(text).strip()[:120]}"')


def stop(conn, task, agent, why):
    now = time.time()
    from core import hb_tasks
    conn.execute("UPDATE hb_tasks SET state='paused', updated_at=? WHERE task_id=?", (now, task['task_id']))
    hb_tasks.event(conn, task, 'user', 'continuation_control', {'mode': 'off', 'via': 'loop', 'actor': 'HB loop guard', 'why': why})
    hb_tasks.event(conn, task, 'hummingbird', 'loop_stopped', {'agent': agent, 'why': why})
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if {'hb_peer_work', 'hb_task_requests'} <= tables:
        conn.execute("UPDATE hb_peer_work SET state='cancelled', stage='Loop stopped by HB', updated_at=? WHERE state='queued' AND request_id IN "
                     "(SELECT request_id FROM hb_task_requests WHERE task_id=?)", (now, task['task_id']))
    if 'hb_task_manager' in tables:
        conn.execute("UPDATE hb_task_manager SET state='needs_owner', detail=?, updated_at=? WHERE task_id=?", ('Loop stopped: ' + why[:180], now, task['task_id']))
    try:
        from core import hb_merits
        hb_merits._add(conn, 'lesson', 'APEX' if agent == 'apex' else agent, '', task_id=task['task_id'], ref=f'loop:{int(now)}',
                       note=f'What went wrong: {why[:300]} | The better way: when an answer did not move the task, the next answer in that task must change the approach or say what blocks it - do not repeat it consecutively. (Repeating a correct answer to a repeated question is fine.)')
    except Exception:
        pass
    from core.hb_plain import message, name
    text = message(f"🔴 Loop stopped: {name(task.get('title'))}.", f'{why}. HB stopped it at once and cancelled its queued work.',
                   f"/continue {task['task_id']} restarts it once something has changed.", details=[f"task {task['task_id']}"])
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                 (task['conversation_id'], text))
    return text


TRIGGER = '''CREATE TRIGGER IF NOT EXISTS hb_no_repeat_messages BEFORE INSERT ON messages
WHEN NEW.from_agent='hummingbird' AND NEW.to_agent='user' AND NEW.message_type='response'
  AND substr(NEW.content,1,1) IN ('🔴','⏸','▶','📋','🌱','📝','🔎','🧪','🌺','⬇','📜','↺','⚠','✅','☰','🤔','🛠','❓')
  AND EXISTS(
  SELECT 1 FROM messages m WHERE m.conversation_id=NEW.conversation_id AND m.from_agent='hummingbird' AND m.to_agent='user'
  AND m.message_type='response' AND m.content=NEW.content AND COALESCE(m.created_at, datetime('now'))>=datetime('now','-10 minutes'))
BEGIN SELECT RAISE(IGNORE); END'''


def install(conn):
    """HB cannot post the identical message to JD twice within 10 minutes (any code path)."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='messages'").fetchone():
        old = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='hb_no_repeat_messages'").fetchone()
        if old and old[0] != TRIGGER:
            conn.execute('DROP TRIGGER hb_no_repeat_messages')
        conn.execute(TRIGGER)
