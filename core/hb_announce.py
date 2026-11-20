"""HB says in main chat when anyone starts or stops work (Practice 209; JD 21 Nov 2026: "the tasks should also be posted in main chat by
HB when it's working on something", and "let's name each AI properly").

Every coordinator tick compares what is running now (the HB Live lanes: APEX's and Fred's turns and workflow steps, peer requests to
APEX, Codex and Gemini, Claude Code's runs, JD's admin commands) with the last tick:
    ▶ APEX started: Repair 9: test results survive the peer transport deadline
    ✓ APEX finished: Repair 9: ... (4 min)        ✗ Fred stopped: ... - TimeoutError
A run must be missing on two ticks in a row before it counts as ended. Single model calls and plain chat answers are not announced
(the chat already shows them)."""
import time

NAMES = {'apex': 'APEX', 'fred': 'Fred', 'claude-code': 'Claude Code', 'claude': 'Claude Code', 'codex': 'Codex', 'codex-instructor': 'Codex',
         'gemini': 'Gemini', 'gemini-advisor': 'Gemini', 'hb': 'HB', 'hummingbird': 'HB', 'jd': 'JD', 'ghost': 'JD', 'small': 'HB'}
QUIET = {'model call'}


def name(who):
    w = str(who or '').strip()
    return NAMES.get(w.lower(), w[:1].upper() + w[1:] if w else 'HB')


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_announce(key TEXT PRIMARY KEY, who TEXT, title TEXT, since REAL, misses INTEGER DEFAULT 0)')


def _key(it):
    return it.get('run_id') or f"{it.get('lane')}:{it.get('task_id')}:{it.get('title')}"


def _worth(conn, it):
    if it.get('purpose') in QUIET or not it.get('title'):
        return False
    if it.get('purpose') == 'main-chat turn':
        if not it.get('task_id'):
            return False                     # a plain chat answer: the chat already shows it
        try:
            from core import hb_tasks
            from core.hb_owner_intent import is_chat_task
            return not is_chat_task(hb_tasks.get(conn, it['task_id']))
        except Exception:
            return True
    return True


def current(conn, now):
    from core import hb_live
    items = hb_live._merge(hb_live._log_items(conn, now) + hb_live._peer_items(conn) + hb_live._admin_items(conn))
    return [i for i in items if _worth(conn, i)]


def _outcome(conn, key):
    """(ok, why) for a run that ended: the log's last word, or the peer request's state."""
    try:
        if key.startswith('P-'):
            row = conn.execute('SELECT state, stage FROM hb_peer_work WHERE request_id=?', (int(key[2:]),)).fetchone()
            if row and row[0] in ('failed', 'cancelled', 'needs_review'):
                return False, f'{row[0]}' + (f' - {str(row[1])[:120]}' if row[1] else '')
            return True, ''
        row = conn.execute("SELECT kind, text FROM hb_activity_log WHERE run_id=? AND kind IN ('finish','error') ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        if row and row[0] == 'error':
            return False, str(row[1] or '')[:120]
    except Exception:
        pass
    return True, ''


def tick(conn, now=None, items=None, post=None):
    """Post the start/finish lines since the last tick. Returns the lines."""
    now = now or time.time()
    ensure(conn)
    if items is None:
        items = current(conn, now)
    if post is None:
        from core.hb_model_bench import _post as post
    seen = {_key(i): i for i in items}
    known = {r[0]: r for r in conn.execute('SELECT key, who, title, since, misses FROM hb_announce')}
    said = []
    for k, it in seen.items():
        if k in known:
            if known[k][4]:
                conn.execute('UPDATE hb_announce SET misses=0 WHERE key=?', (k,))
            continue
        who, title = name(it.get('actor') or it.get('lane')), str(it['title'])[:160]
        conn.execute('INSERT INTO hb_announce VALUES (?,?,?,?,0)', (k, who, title, now))
        said.append(f'▶ {who} started: {title}')
    for k, (_, who, title, since, misses) in known.items():
        if k in seen:
            continue
        if not misses:
            conn.execute('UPDATE hb_announce SET misses=1 WHERE key=?', (k,))
            continue
        conn.execute('DELETE FROM hb_announce WHERE key=?', (k,))
        mins = max(0.0, now - (since or now)) / 60
        took = f'{mins:.0f} min' if mins >= 1 else 'under a minute'
        ok, why = _outcome(conn, k)
        said.append(f'✓ {who} finished: {title} ({took})' if ok else f'✗ {who} stopped: {title} ({took})' + (f' - {why}' if why else ''))
    for line in said:
        post(conn, line)
    return said
