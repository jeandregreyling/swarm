"""Daily grounding (owner 14 Nov 2026): on the first owner message of a day HB opens with a self-check (hardware, models,
connections, queue), confirms the real date and what needs to happen today, and a short grounding checkpoint.
No model: everything comes from the machine and HB's own records. /today shows it again at any time."""
import os
import shutil
import time

MAIN_CHAT = 2834
from core.hb_chat import owner_chat   # Practice 105: the chat JD is using, not old chat 2834
PLAN = 'P-2AB8250A87'


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def self_check(conn, now=None, *, memory=None, disk=None, listeners=None):
    """Facts for the opening: {'day', 'ram_gb', 'disk_gb', 'model_server', 'models', 'open', 'done_24h', 'next', 'needs_you'}."""
    now = time.time() if now is None else now
    tables = _tables(conn)
    if memory is None:
        try:
            with open('/proc/meminfo') as handle:
                memory = {l.split(':')[0]: int(l.split()[1]) * 1024 for l in handle if l.startswith('MemAvailable')}
        except Exception:
            memory = {}
    if disk is None:
        try:
            disk = shutil.disk_usage(os.environ.get('SWARM_ROOT') or '/').free
        except Exception:
            disk = 0
    if listeners is None:
        try:
            from core.hb_service_truth import listeners as live
            listeners = live()
        except Exception:
            listeners = {}
    models = conn.execute("SELECT COUNT(*) FROM hb_agents WHERE kind='local' AND status='active'").fetchone()[0] if 'hb_agents' in tables else 0
    open_steps, done, nxt = 0, 0, ''
    if 'project_steps' in tables:
        open_steps = conn.execute("SELECT COUNT(*) FROM project_steps WHERE project_id=? AND status IN ('todo','doing','partial')", (PLAN,)).fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM project_steps WHERE project_id=? AND status='done' AND updated_at>=?", (PLAN, now - 86400)).fetchone()[0]
    try:
        from core import hb_queue
        ready = [r for r in hb_queue.items(conn, PLAN) if r['state'] in ('now', 'next')]
        nxt = ready[0]['title'] if ready else ''
    except Exception:
        nxt = ''
    try:
        from core.hb_commands import waiting_items
        needs = len(waiting_items(conn, owner_chat(conn), now=now))
    except Exception:
        needs = 0
    return {'day': time.strftime('%A %d %B %Y', time.localtime(now)), 'ram_gb': round(memory.get('MemAvailable', 0) / 1024 ** 3, 1),
            'disk_gb': round(disk / 1024 ** 3), 'model_server': 8080 in listeners, 'models': models, 'open': open_steps, 'done_24h': done,
            'next': nxt, 'needs_you': needs}


def text(f):
    return '\n'.join([
        f"☀ Today is {f['day']}.",
        f"Self-check: {f['ram_gb']} GB memory free, {f['disk_gb']} GB disk free, APEX model server {'up' if f['model_server'] else 'DOWN'}, "
        f"{f['models']} local models ready.",
        f"Work: {f['open']} steps open, {f['done_24h']} finished in the last 24 hours" + (f"; {f['needs_you']} waiting for you" if f['needs_you'] else '') + '.',
        'Today: ' + (f"the next step is {f['next']}." if f['next'] else 'nothing is ready to start; say what matters today.'),
        'Checkpoint: one step at a time. What is finished stays finished. What is not ready today can wait for tomorrow.'])


def tick(conn, now=None, conversation_id=None):
    """Post the opening once per calendar day, after the owner's first message of that day. Returns the message id or None."""
    now = time.time() if now is None else now
    conversation_id = conversation_id or owner_chat(conn)
    day = time.strftime('%Y-%m-%d', time.localtime(now))
    conn.execute('CREATE TABLE IF NOT EXISTS hb_grounding(day TEXT PRIMARY KEY, message_id INTEGER, created_at REAL NOT NULL)')
    if conn.execute('SELECT 1 FROM hb_grounding WHERE day=?', (day,)).fetchone():
        return None
    midnight = time.mktime(time.strptime(day, '%Y-%m-%d'))
    here = conn.execute("SELECT 1 FROM messages WHERE conversation_id=? AND from_agent='user' AND created_at>=datetime(?, 'unixepoch') LIMIT 1",
                        (conversation_id, midnight)).fetchone()
    if not here:
        return None
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                       "VALUES (?,'hummingbird','user',?,'response',0)", (conversation_id, text(self_check(conn, now)))).lastrowid
    conn.execute('INSERT INTO hb_grounding(day,message_id,created_at) VALUES (?,?,?)', (day, mid, now))
    return mid
