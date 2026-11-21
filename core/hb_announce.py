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
    # Conversation records can appear through peer, workflow or activity lanes.
    # None is an unfinished work assignment, irrespective of its display purpose.
    if str(it.get('title') or '').strip().casefold() == 'chat with jd':
        return False
    task_id = it.get('task_id') or _task_of(conn, _key(it))
    if task_id:
        try:
            from core import hb_tasks
            from core.hb_owner_intent import is_chat_task
            if is_chat_task(hb_tasks.get(conn, task_id)):
                return False
        except Exception:
            pass
    return not (it.get('purpose') == 'main-chat turn' and not task_id)


def current(conn, now):
    from core import hb_live
    items = hb_live._merge(hb_live._log_items(conn, now) + hb_live._peer_items(conn) + hb_live._admin_items(conn))
    return [i for i in items if _worth(conn, i)]


def _task_of(conn, key):
    try:
        if key.startswith('P-'):
            row = conn.execute('SELECT task_id FROM hb_task_requests WHERE request_id=?', (int(key[2:]),)).fetchone()
        else:
            row = conn.execute("SELECT task_id FROM hb_activity_log WHERE run_id=? AND task_id IS NOT NULL LIMIT 1", (key,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _accepted(conn, task_id):
    """The task's own record says the work is done: task completed, its step done, or an acceptance event."""
    if not task_id:
        return False
    try:
        row = conn.execute('SELECT state, step_id FROM hb_tasks WHERE task_id=?', (task_id,)).fetchone()
        if not row:
            return False
        if row[0] == 'completed':
            return True
        if row[1] and conn.execute("SELECT 1 FROM project_steps WHERE step_id=? AND status='done'", (row[1],)).fetchone():
            return True
        return bool(conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind IN ('accepted','owner_accepted') LIMIT 1",
                                 (task_id,)).fetchone())
    except Exception:
        return False


def _outcome(conn, key):
    """('done'|'failed'|'unknown', why) for a run that ended (Practice 214, Codex's phone flow 3: at 07:45 HB said "✗ APEX stopped: Repair 10
    ... cancelled" after JD had accepted it - the peer transport ended 'cancelled' because acceptance closed it). The task's own record wins
    over the transport; a genuine failure of unfinished work stays a failure; a run with no terminal record is never called a success."""
    if _accepted(conn, _task_of(conn, key)):
        return 'done', ''
    try:
        if key.startswith('P-'):
            row = conn.execute('SELECT state, stage FROM hb_peer_work WHERE request_id=?', (int(key[2:]),)).fetchone()
            if not row:
                return 'unknown', ''
            if row[0] == 'completed':
                return ('turn', '') if _task_of(conn, key) else ('done', '')
            from core.hb_calm import interrupted
            if row[0] in ('failed', 'needs_review') and interrupted(row[1]):   # Practice 220: a restart is a pause, not a failure
                return 'paused', 'HB restarted during the turn; the work carries on in the next turn'
            if row[0] in ('failed', 'cancelled', 'needs_review'):
                return 'failed', f'{row[0]}' + (f' - {str(row[1])[:120]}' if row[1] else '')
            return 'unknown', ''
        row = conn.execute("SELECT kind, text FROM hb_activity_log WHERE run_id=? AND kind IN ('finish','error') ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        if not row:
            return 'unknown', ''
        return ('failed', str(row[1] or '')[:120]) if row[0] == 'error' else (('turn', '') if _task_of(conn, key) else ('done', ''))
    except Exception:
        return 'unknown', ''


def _lit(conn, key):
    """Practice 272: a finished APEX turn's DOES and DREAM lights, and what was not lit, under its finished line ('' when none)."""
    try:
        from core import hb_lights
        request = int(key[2:]) if key.startswith('P-') and key[2:].isdigit() else None
        lights = hb_lights.turn(conn, request_id=request, run_id=key if key.startswith('R-P') else None)
        if not lights.get('request_id') or all(l['state'] == 'off' for l in lights['turn']):
            return ''
        why = hb_lights.why_line(lights)
        return '\n' + hb_lights.chat_line(lights) + (f' ({why})' if why else '')
    except Exception:
        return ''


def tick(conn, now=None, items=None, post=None):
    """Post the start/finish lines since the last tick. Returns the lines."""
    now = now or time.time()
    ensure(conn)
    if items is None:
        items = current(conn, now)
    if post is None:
        from core.hb_model_bench import _post as post
    seen = {_key(i): i for i in items if _worth(conn, i)}
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
        if str(title or '').strip().casefold() == 'chat with jd':
            conn.execute('DELETE FROM hb_announce WHERE key=?', (k,))
            continue
        if k in seen:
            continue
        if not misses:
            conn.execute('UPDATE hb_announce SET misses=1 WHERE key=?', (k,))
            continue
        conn.execute('DELETE FROM hb_announce WHERE key=?', (k,))
        mins = max(0.0, now - (since or now)) / 60
        took = f'{mins:.0f} min' if mins >= 1 else 'under a minute'
        state, why = _outcome(conn, k)
        said.append((f'✓ {who} finished: {title} ({took})' if state == 'done' else
                    f'■ {who} finished a turn: {title} ({took}) - task remains open' if state == 'turn' else
                    f'⏸ {who} paused: {title} ({took}) - {why}' if state == 'paused' else
                    f'✗ {who} stopped: {title} ({took})' + (f' - {why}' if why else '') if state == 'failed' else
                    f'■ {who} ended: {title} ({took}) - no result recorded') + _lit(conn, k))
    for line in said:
        post(conn, line)
    return said
