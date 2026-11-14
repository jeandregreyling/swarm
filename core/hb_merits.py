"""Credit, corrections and capability tags (owner 14 Nov 2026).

"Applause should only be given when an actual task is successful ... if one does something wrong the other models should correct that
behaviour and record their reason and actions to correct it instead of saying 'you failed' ... they all learn through experience and live
feedback without competing for top dog ... the little quip goes to the model that contributed most to making the system work better on a
daily basis ... categories like coder, generalist, scientist, actor ... badges that show how much a model has learned. It's not a race to
the top, it's pushing the rock up the hill until JD is happy."

  success     a Studio step is accepted AND its own check passed after its last change: every agent/model that changed something or
              ran the passing check gets credit in the step's category; HB posts one short applause line. No check, no applause.
  correction  Fred (or any helper) takes over a stuck step and makes progress: recorded as "what went wrong -> the better way" for the
              one who was stuck (a lesson, not a minus) and credit for the helper. The lesson is shown to APEX on later tasks.
  try_better  JD's negative remark about the work: recorded against the role working at that moment as "try better next time";
              nothing stops.
  tags        coder / scientist / actor / generalist, earned from real successes; badges I-IV at 1 / 5 / 15 / 40 successes in a category.
  daily       once a day HB names the model that helped most (successes and fixes) - a thank-you, not a ranking.
"""
import json
import re
import time

MAIN_CHAT = 2834
POINTS = {'success': 3, 'correction': 2, 'try_better': 0, 'lesson': 0, 'asked_needed': 1, 'asked_unneeded': 0}
CATEGORIES = ('coder', 'scientist', 'actor', 'generalist')
BADGES = ((40, 'IV'), (15, 'III'), (5, 'II'), (1, 'I'))
CODE = re.compile(r'\.(py|js|css|html|json|sh|yaml|yml|toml|service)\b')
DAILY_HOUR = 19


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_merits(id INTEGER PRIMARY KEY, at REAL NOT NULL, role TEXT NOT NULL, model TEXT,
        kind TEXT NOT NULL, category TEXT, points INTEGER NOT NULL DEFAULT 0, task_id TEXT, step_id TEXT, ref TEXT, note TEXT,
        UNIQUE(kind, role, model, ref))''')


def _role(agent, model):
    if model and 'fred' in model:
        return 'Fred'
    return {'apex': 'APEX', 'codex-instructor': 'Codex', 'gemini-advisor': 'Gemini'}.get(agent, agent or 'HB')


def _post(conn, text):
    from core.hb_plain import message
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                        "VALUES (?,'hummingbird','user',?,'response',0)", (MAIN_CHAT, message(text))).lastrowid


def _add(conn, kind, role, model, *, category=None, task_id=None, step_id=None, ref=None, note=''):
    ensure_schema(conn)
    return conn.execute('INSERT OR IGNORE INTO hb_merits(at,role,model,kind,category,points,task_id,step_id,ref,note) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (time.time(), role, model or '', kind, category, POINTS[kind], task_id, step_id, ref, str(note)[:600])).rowcount


def _model_of(conn, request_id):
    row = conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='progress' AND payload LIKE '%Local model selected%' "
                       "ORDER BY event_id DESC LIMIT 1", (request_id,)).fetchone()
    return json.loads(row[0])['stage'].split(': ', 1)[1] if row else ''


def contributors(conn, task_id):
    """[(role, model, request_id)] that changed something or ran a passing check in this task."""
    out, seen = [], set()
    for rid, agent in conn.execute("""SELECT DISTINCT e.request_id, p.recipient FROM hb_task_events e JOIN peer_messages p ON p.id=e.request_id
            WHERE e.task_id=? AND (e.kind='mutation' OR (e.kind='test_result' AND json_extract(e.payload,'$.alm_run_status')='pass'))""", (task_id,)):
        model = _model_of(conn, rid)
        key = (_role(agent, model), model)
        if key not in seen:
            seen.add(key)
            out.append((*key, rid))
    return out


def category(conn, task_id, title=''):
    t = str(title).lower()
    if re.search(r'\b(research|investigat|benchmark|compare|study|explore)\w*', t):
        return 'scientist'
    if re.search(r'\b(design|story|creative|write up|wording|style|animation|look)\w*', t):
        return 'actor'
    for (payload,) in conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='mutation'", (task_id,)):
        if CODE.search(payload or ''):
            return 'coder'
    return 'generalist'


def _check_passed(conn, task_id):
    last_change = conn.execute("SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=? AND kind='mutation'", (task_id,)).fetchone()[0]
    return bool(conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='test_result' AND event_id>? "
                             "AND json_extract(payload,'$.alm_run_status')='pass'", (task_id, last_change)).fetchone())


def on_accept(conn, step_id, task_ids, title):
    """A step was accepted. Credit and one applause line only when its own check passed after its last change."""
    lines = []
    for tid in task_ids:
        if not _check_passed(conn, tid):
            continue
        cat = category(conn, tid, title)
        people = contributors(conn, tid)
        for role, model, rid in people:
            _add(conn, 'success', role, model, category=cat, task_id=tid, step_id=step_id, ref=tid, note=title)
        if people:
            from core.hb_plain import name
            who = ' and '.join(f"{r} ({m})" if m else r for r, m, _ in people)
            lines.append(f"🌺 HB gives {who} a flower: {name(title)} is done and its check passed. (+{POINTS['success']} {cat})")
    return [_post(conn, line) for line in lines]


def corrections(conn):
    """Fred (or another helper) turns that made progress on a stuck task become a recorded correction: the lesson for the one who
    was stuck and credit for the helper. Idempotent. Returns the number recorded."""
    ensure_schema(conn)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_work'").fetchone():
        return 0
    done = 0
    for tid, rid in conn.execute("SELECT task_id, request_id FROM hb_task_events WHERE kind='fred_turn' AND request_id IS NOT NULL").fetchall():
        state = conn.execute('SELECT state FROM hb_peer_work WHERE request_id=?', (rid,)).fetchone()
        if not state or state[0] in ('queued', 'running'):
            continue
        progress = conn.execute("SELECT 1 FROM hb_task_events WHERE request_id=? AND (kind='mutation' OR (kind='test_result' AND "
                                "json_extract(payload,'$.alm_run_status')='pass'))", (rid,)).fetchone()
        if not progress:
            continue
        wrong = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='tool_failure' AND request_id<? ORDER BY event_id DESC LIMIT 1",
                             (tid, rid)).fetchone()
        better = conn.execute("SELECT payload FROM hb_task_events WHERE request_id=? AND kind='reply' ORDER BY event_id DESC LIMIT 1", (rid,)).fetchone()
        what = json.loads(wrong[0]).get('error', '') if wrong else 'no progress in its last turns'
        how = json.loads(better[0]).get('content', '') if better else 'Fred changed the files and ran the check'
        note = f"What went wrong: {str(what)[:200]} | The better way: {str(how)[:300]}"
        model = _model_of(conn, rid)
        if _add(conn, 'correction', 'Fred', model, task_id=tid, ref=str(rid), note=note):
            _add(conn, 'lesson', 'APEX', '', task_id=tid, ref=str(rid), note=note)
            title = conn.execute('SELECT title FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()
            from core.hb_plain import name
            _post(conn, f"🌺 APEX gives Fred a flower for the fix on {name(title[0] if title else tid)}. The better way: {str(how)[:200]}")
            done += 1
    return done


def try_better(conn, text):
    """JD's negative remark: recorded for the role working right now as 'try better next time'. Nothing stops."""
    row = conn.execute("SELECT w.request_id, p.recipient, t.task_id FROM hb_peer_work w JOIN peer_messages p ON p.id=w.request_id "
                       "LEFT JOIN hb_task_requests t ON t.request_id=w.request_id WHERE w.state IN ('running','queued') ORDER BY w.request_id DESC LIMIT 1").fetchone()
    if not row:
        return 0
    model = _model_of(conn, row[0])
    return _add(conn, 'try_better', _role(row[1], model), model, task_id=row[2], ref=f'remark:{int(time.time())}', note=text)


def lessons(conn, limit=2):
    """Recent corrections as lines for APEX's DREAM card."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_merits'").fetchone():
        return []
    return [r[0] for r in conn.execute("SELECT note FROM hb_merits WHERE kind='lesson' ORDER BY id DESC LIMIT ?", (limit,))]


def profile(conn):
    """Per role+model: tags (categories with 2+ successes), badges per category, successes, fixes, try-better notes."""
    ensure_schema(conn)
    out = {}
    for role, model, kind, cat, n in conn.execute("SELECT role, model, kind, category, COUNT(*) FROM hb_merits GROUP BY role, model, kind, category"):
        p = out.setdefault((role, model), {'role': role, 'model': model, 'success': {}, 'fixes': 0, 'try_better': 0, 'lessons': 0,
                                           'asked_needed': 0, 'asked_unneeded': 0})
        if kind == 'success':
            p['success'][cat] = p['success'].get(cat, 0) + n
        elif kind == 'correction':
            p['fixes'] += n
        elif kind == 'try_better':
            p['try_better'] += n
        elif kind == 'lesson':
            p['lessons'] += n
        elif kind in ('asked_needed', 'asked_unneeded'):
            p[kind] += n
    for p in out.values():
        p['tags'] = sorted(c for c, n in p['success'].items() if n >= 2)
        p['badges'] = {c: next(level for need, level in BADGES if n >= need) for c, n in p['success'].items() if n >= 1}
    return list(out.values())


def today(conn, now=None):
    now = time.time() if now is None else now
    start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    ensure_schema(conn)
    return conn.execute("SELECT role, model, SUM(points), SUM(kind='success'), SUM(kind='correction') FROM hb_merits WHERE at>=? "
                        "GROUP BY role, model ORDER BY SUM(points) DESC", (start,)).fetchall()


def daily(conn, now=None):
    """Once a day after DAILY_HOUR: thank the model that helped most today. Returns the message id or None."""
    now = time.time() if now is None else now
    if time.localtime(now).tm_hour < DAILY_HOUR:
        return None
    ensure_schema(conn)
    stamp = time.strftime('%Y-%m-%d', time.localtime(now))
    if conn.execute("SELECT 1 FROM hb_merits WHERE kind='lesson' AND ref=?", (f'daily:{stamp}',)).fetchone():
        return None
    rows = [r for r in today(conn, now) if r[2] or r[3] or r[4]]
    conn.execute("INSERT OR IGNORE INTO hb_merits(at,role,model,kind,points,ref,note) VALUES(?,?,?,?,0,?,?)",
                 (now, 'HB', '', 'lesson', f'daily:{stamp}', 'daily thank-you posted'))
    if not rows:
        return None
    # Owner 14 Nov: every model that did anything gets its own thank-you; the one that helped most gets the extra mention.
    thanks = '; '.join(f"{role}{' (' + model + ')' if model else ''}: {wins} task(s) done, {fixes} fix(es) for others"
                       for role, model, pts, wins, fixes in rows)
    best = rows[0]
    return _post(conn, f"🌺 End-of-day flowers from HB - thank you, {thanks}. Biggest help today: {best[0]}. "
                       "Everyone pushed the rock a bit further up the hill.")


def tick(conn):
    corrections(conn)
    daily(conn)


def status_text(conn):
    rows = profile(conn)
    if not rows:
        return 'No credit recorded yet: it starts with the next task whose check passes.'
    lines = ['How each agent is doing (credit only for checked successes; fixes for others count too):']
    for p in sorted(rows, key=lambda p: -sum(p['success'].values()) - p['fixes']):
        badges = ', '.join(f'{c} {lvl}' for c, lvl in sorted(p['badges'].items())) or 'no badges yet'
        lines.append(f"- {p['role']}{' (' + p['model'] + ')' if p['model'] else ''}: tags {', '.join(p['tags']) or '-'}; badges {badges}; "
                     f"{sum(p['success'].values())} successes, {p['fixes']} fixes for others, {p['lessons']} lessons learned, {p['try_better']} try-better notes, "
                     f"questions back: {p.get('asked_needed', 0)} needed / {p.get('asked_unneeded', 0)} unneeded")
    best = today(conn)
    if best and best[0][2]:
        lines.append(f"Today so far: {best[0][0]} has helped most.")
    return '\n'.join(lines)
