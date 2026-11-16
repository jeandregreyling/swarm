"""Daily summary (owner 14 Nov 2026): once a day in main chat - what got done, what stalled and why, which model did best,
what needs JD. Plain words, short. Built from HB's own records (no model): Studio steps, the task manager, merits and the
waiting-for-you list. tick() posts it once per calendar day, at or after HOUR local time."""
import time

PLAN = 'P-2AB8250A87'
MAIN_CHAT = 2834
from core.hb_chat import owner_chat   # Practice 105: the chat JD is using, not old chat 2834
HOUR = 18


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _name(title):
    try:
        from core.hb_plain import name
        return name(title)
    except Exception:
        return str(title or '')[:140]


def facts(conn, now=None, project_id=PLAN):
    """{'done': [...], 'stalled': [(title, why)], 'best': (model, points) | None, 'needs_you': [...]} for the last 24 hours."""
    now = time.time() if now is None else now
    since = now - 86400
    tables = _tables(conn)
    done = [_name(r[0]) for r in conn.execute("SELECT title FROM project_steps WHERE project_id=? AND status='done' AND updated_at>=? "
                                              "ORDER BY updated_at", (project_id, since))] if 'project_steps' in tables else []
    stalled = []
    if {'hb_task_manager', 'hb_tasks'} <= tables:
        for title, why in conn.execute("SELECT t.title, m.detail FROM hb_task_manager m JOIN hb_tasks t ON t.task_id=m.task_id "
                                       "WHERE t.state NOT IN ('completed','cancelled') AND m.state IN ('needs_owner','held','waiting_resources') "
                                       "ORDER BY m.updated_at DESC LIMIT 8"):
            stalled.append((_name(title), ' '.join(str(why or 'no reason recorded').split())[:140]))
    best = None
    if 'hb_merits' in tables:
        row = conn.execute("SELECT model, SUM(points) FROM hb_merits WHERE at>=? AND COALESCE(model,'')<>'' GROUP BY model "
                           "ORDER BY SUM(points) DESC LIMIT 1", (since,)).fetchone()
        best = (row[0], int(row[1])) if row and row[1] else None
    needs = []
    try:
        from core.hb_commands import waiting_items
        needs = [str(i.get('title') or i.get('label') or '')[:120] for i in waiting_items(conn, owner_chat(conn), now=now)][:6]
    except Exception:
        needs = []
    return {'done': done, 'stalled': stalled, 'best': best, 'needs_you': [n for n in needs if n]}


def text(f, now=None):
    day = time.strftime('%A %d %b', time.localtime(now))
    lines = [f'🗓 Daily summary, {day}.',
             f"Done ({len(f['done'])}): " + ('; '.join(f['done'][:8]) + (f" and {len(f['done']) - 8} more" if len(f['done']) > 8 else '') if f['done'] else 'nothing finished in the last 24 hours') + '.',
             'Stalled: ' + ('; '.join(f'{t} - {why}' for t, why in f['stalled'][:5]) if f['stalled'] else 'nothing') + '.',
             'Best model: ' + (f"{f['best'][0]} ({f['best'][1]} points)" if f['best'] else 'no checked work yet') + '.',
             'Needs you: ' + ('; '.join(f['needs_you']) if f['needs_you'] else 'nothing') + '.']
    return '\n'.join(lines)


def tick(conn, now=None, conversation_id=None):
    """Post today's summary once, at or after HOUR. Returns the message id, or None when it is not time or already posted."""
    now = time.time() if now is None else now
    conversation_id = conversation_id or owner_chat(conn)
    local = time.localtime(now)
    if local.tm_hour < HOUR:
        return None
    conn.execute('CREATE TABLE IF NOT EXISTS hb_daily_summary(day TEXT PRIMARY KEY, message_id INTEGER, created_at REAL NOT NULL)')
    day = time.strftime('%Y-%m-%d', local)
    if conn.execute('SELECT 1 FROM hb_daily_summary WHERE day=?', (day,)).fetchone():
        return None
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                       "VALUES (?,'hummingbird','user',?,'response',0)", (conversation_id, text(facts(conn, now), now))).lastrowid
    conn.execute('INSERT INTO hb_daily_summary(day,message_id,created_at) VALUES (?,?,?)', (day, mid, now))
    return mid
