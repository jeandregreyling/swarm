"""Hummingbird system commands: "/" in main chat (also accepts the older "@hb ...").

These are commands to the wrapper, not chat with a model. Owner only.
A  Fixed commands answered by HB itself (no model, no tokens). See COMMANDS.
C  A near-miss ("/stauts") gets the closest command, run only after "/yes".
B  Plain English after "/" ("/hold the dream build") is mapped by the idle local
   model to ONE fixed command; nothing runs until "/yes".
Consequential commands (cancel) always halt and ask for "/yes" first.
"/stop" stays with the existing owner Stop path (peer_bridge._owner_chat_stop).
"""
import difflib
import hashlib
import json
import re
import sqlite3
import time
import urllib.request
import uuid

# name, usage, description, needs confirmation
COMMANDS = [
    ('help', '/help', 'List every command', False),
    ('status', '/status', 'Workers, APEX server, GPU memory, online providers, queue', False),
    ('tasks', '/tasks', 'Open tasks in this chat and whether Continue is on', False),
    ('stuck', '/stuck', 'Tasks that keep failing or looping, with the exact error', False),
    ('approvals', '/approvals', 'Everything waiting for your decision', False),
    ('queue', '/queue', 'Queued and running agent requests', False),
    ('pause', '/pause T-xxxx', 'Hold a task (same as its Off control)', False),
    ('continue', '/continue T-xxxx', 'Resume a task (same as its On control)', False),
    ('cancel', '/cancel T-xxxx', 'Drop a task that is no longer needed (asks first)', True),
    ('done', '/done T-xxxx what must be true; another check', 'Define what "done" means for a task (DREAM)', False),
    ('clipboard', '/clipboard T-xxxx', "Show HB's DREAM clipboard for a task", False),
    ('clip', '/clip up|down|top|clear S-xxxx · importance S-xxxx 1-5 · doer S-xxxx hb|small|apex|fred', "Edit HB's clipboard (order, importance, who does it)", False),
    ('pick', '/pick S-xxxx N', "Choose option N from HB counsel's review of a vague step; it becomes the step's spec", False),
    ('agents', '/agents [onboard-local | onboard <id> <profile> <about> | examine <id|@handle> | handles <id> <h1,h2> | retire <id> | model <id> <model>]', 'Onboarded HB agents (own memory, KC page, tools); onboard-local makes every benchmarked local model an agent', False),
    ('bench', '/bench [all|model name|status]', 'Benchmark the local models: GPU fit and programmer / researcher / social / useless (results in main chat and Studio)', False),
    ('merits', '/merits', "How each agent is doing: checked successes, fixes for others, tags and badges", False),
    ('downloads', '/downloads', 'Big downloads HB is tracking: progress, connection, Studio step', False),
    ('tidy', '/tidy [yes]', 'Close chat lines HB wrongly made into tasks (remarks, go-aheads); lists them first', False),
    ('drive', '/drive [on|off|status]', 'HB drives the open tasks to the finish (same as saying "go")', False),
    ('workflow', '/workflow on|off|auto on|off|status|next S-xxxx', 'Run the Studio plan step by step: HB picks the next ready step, APEX scopes it, you approve', False),
    ('plan', '/plan T-xxxx', "Approve APEX's proposed plan and done criteria for a task, and start it", False),
    ('accept', '/accept S-xxxx', 'Accept a Studio step waiting for your approval (marks it done)', False),
    ('reject', '/reject S-xxxx reason', 'Send a Studio step back with your reason', False),
    ('online', '/online [codex|gemini|claude on|off]', 'Show or set which online providers HB may use by itself (your own @mentions always go)', False),
    ('dream', '/dream on [seconds]|off|status|report', 'Idle-time DREAM fact reports', False),
    ('nanny', '/nanny on [minutes]|off|status|report', 'The nanny bot (small CPU model) that watches the system', False),
    ('unload', '/unload model-name', 'Unload an HB-managed local model to free memory', False),
    ('stop', '/stop', 'Stop all current work now', False),
    ('yes', '/yes', 'Confirm what HB just asked', False),
    ('no', '/no', 'Decline what HB just asked', False),
]
NAMES = [c[0] for c in COMMANDS]
TASK_RE = re.compile(r'\bT-[0-9A-F]{12}\b', re.I)
STEP_RE = re.compile(r'\bS-[0-9A-F]{10}\b', re.I)
ACCEPTANCE_SQL = "status='partial' AND (residual_risk LIKE '%acceptance pending%' OR residual_risk LIKE '%awaiting owner acceptance%')"
PENDING_TTL = 600
LLAMA = 'http://127.0.0.1:8080'
MAIN_CHAT_ID = 2834


def catalogue():
    """For the "/" popup."""
    return [{'name': n, 'usage': u, 'description': d, 'confirm': c} for n, u, d, c in COMMANDS]


HELP = 'Hummingbird commands (answered by HB itself, no model):\n' + '\n'.join(
    f'- {u}: {d}' for _, u, d, _ in COMMANDS) + '\nAnything else after "/" is read by the local model as a suggestion only; it waits for /yes.'


def is_hb(text):
    """'/word ...' (not a file path) or the older '@hb ...'."""
    if not isinstance(text, str):
        return False
    if re.match(r'\s*@(hb|hummingbird)\b', text, re.I):
        return True
    m = re.match(r'\s*/([A-Za-z]+)(\S*)', text)
    return bool(m) and '/' not in m.group(2)


def _body(text):
    return re.sub(r'^\s*(@(hb|hummingbird)\b[:,]?|/)\s*', '', text, flags=re.I).strip()


def ensure_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_command_pending(id INTEGER PRIMARY KEY, conversation_id INTEGER,"
                 " command TEXT NOT NULL, source TEXT, created_at REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)")


# ------------------------------------------------------------------ parsing
def parse(body):
    words = body.split()
    if not words:
        return ('help', [])
    cmd = words[0].lower().rstrip('.!?')
    if cmd not in NAMES or cmd == 'stop':
        return None
    if cmd in ('pause', 'continue', 'cancel'):
        m = TASK_RE.search(body)
        return (cmd, [m.group(0).upper()]) if m else None
    if cmd == 'done':
        m = TASK_RE.search(body)
        criteria = [c.strip(' .') for c in re.split(r'[;\n]+', body[m.end():]) if c.strip(' .')] if m else []
        return ('done', [m.group(0).upper()] + criteria) if m and criteria else None
    if cmd == 'clipboard':
        m = TASK_RE.search(body)
        return ('clipboard', [m.group(0).upper()]) if m else None
    if cmd == 'clip':
        return ('clip', words[1:]) if len(words) > 2 else None
    if cmd == 'downloads':
        return ('downloads', [])
    if cmd == 'merits':
        return ('merits', [])
    if cmd == 'bench':
        return ('bench', words[1:])
    if cmd == 'agents':
        return ('agents', words[1:])
    if cmd == 'pick':
        m = STEP_RE.search(body)
        n = re.search(r'\b([1-3])\s*$', body)
        return ('pick', [m.group(0).upper(), n.group(1)]) if m and n else None
    if cmd == 'tidy':
        return ('tidy', ['yes'] if len(words) > 1 and words[1].lower() in ('yes', 'confirm') else [])
    if cmd == 'drive':
        sub = words[1].lower() if len(words) > 1 else 'on'
        return ('drive', [sub]) if sub in ('on', 'off', 'status', 'start', 'stop') else None
    if cmd == 'workflow':
        sub = {'start': 'on', 'stop': 'off'}.get(words[1].lower(), words[1].lower()) if len(words) > 1 else 'status'
        if sub in ('on', 'off', 'status'):
            return ('workflow', [sub])
        if sub == 'auto':
            mode = words[2].lower() if len(words) > 2 else 'on'
            return ('workflow', ['auto', mode]) if mode in ('on', 'off') else None
        m = STEP_RE.search(body) if sub == 'next' else None
        return ('workflow', ['next', m.group(0).upper()]) if m else None
    if cmd == 'plan':
        m = TASK_RE.search(body)
        return ('plan', [m.group(0).upper()]) if m else None
    if cmd in ('accept', 'reject'):
        m = STEP_RE.search(body)
        if not m:
            return None
        reason = body[m.end():].strip(' :-')          # reject: the reason; accept: an optional owner comment
        if cmd == 'reject' and not reason:
            return None
        return (cmd, [m.group(0).upper()] + ([reason] if reason else []))
    if cmd == 'dream':
        sub = words[1].lower() if len(words) > 1 else 'status'
        if sub not in ('on', 'off', 'status', 'report'):
            return None
        return ('dream', [sub] + [w for w in words[2:] if w.isdigit()][:1])
    if cmd == 'nanny':
        sub = words[1].lower() if len(words) > 1 else 'status'
        if sub not in ('on', 'off', 'status', 'report'):
            return None
        return ('nanny', [sub] + [w for w in words[2:] if w.isdigit()][:1])
    if cmd == 'unload':
        return ('unload', [words[1]]) if len(words) > 1 and re.fullmatch(r'[A-Za-z0-9_.:\-]{2,80}', words[1]) else None
    if cmd == 'online':
        rest = [w.lower() for w in words[1:]]
        if not rest:
            return ('online', [])
        from core.hb_online import PROVIDERS
        if len(rest) == 2 and rest[0] in PROVIDERS and rest[1] in ('on', 'off'):
            return ('online', rest)
        return None
    return (cmd, [])


def suggest(body):
    words = body.split()
    if not words:
        return None
    close = difflib.get_close_matches(words[0].lower(), [n for n in NAMES if n not in ('yes', 'no', 'stop')], n=1, cutoff=0.6)
    if not close:
        return None
    cmd = close[0]
    rebuilt = ' '.join([cmd] + words[1:])
    if parse(rebuilt):
        return rebuilt if cmd not in ('pause', 'continue', 'cancel') else f'{cmd} {TASK_RE.search(rebuilt).group(0).upper()}'
    return cmd if parse(cmd) else None


# ------------------------------------------------------------------ B: local model
def _llama_idle(base=LLAMA):
    try:
        with urllib.request.urlopen(base + '/slots', timeout=3) as r:
            slots = json.loads(r.read().decode() or '[]')
        return isinstance(slots, list) and not any(s.get('is_processing') for s in slots if isinstance(s, dict))
    except Exception:
        return False


def interpret(body, tasks, base=LLAMA, timeout=60):
    if not _llama_idle(base):
        return None
    listing = '\n'.join(f"{t['task_id']}: {t['title'][:80]}" for t in tasks[:15]) or '(no open tasks)'
    prompt = ("Map the owner's request to exactly one Hummingbird command, or none.\n"
              "Allowed commands:\n"
              "status = workers, APEX server health, GPU VRAM/memory use, online providers, request counts\n"
              "tasks = open tasks and whether Continue is on\n"
              "stuck = tasks that keep failing or looping\n"
              "approvals = things waiting for the owner's decision\n"
              "queue = queued and running agent requests\n"
              "pause <task_id> = hold a task;  continue <task_id> = resume a task\n"
              "cancel <task_id> = drop a task that is no longer needed\n"
              "online = which online providers may be used;  online codex on|off;  online gemini on|off\n"
              "dream on | dream off | dream status | dream report = idle-time DREAM reports\n"
              f"Open tasks:\n{listing}\n"
              'Reply with JSON only: {"command": "<command or none>"}\n'
              f"Owner request: {body[:400]}")
    payload = {'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 40,
               'response_format': {'type': 'json_object'}}
    req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.loads(r.read().decode())['choices'][0]['message']['content']
        cmd = str(json.loads(text).get('command', '')).strip()
    except Exception:
        return None
    parsed = parse(cmd)
    if not parsed or parsed[0] in ('help', 'yes', 'no'):
        return None
    if parsed[0] in ('pause', 'continue', 'cancel') and parsed[1][0] not in {t['task_id'] for t in tasks}:
        return None                                        # never act on a task id the model invented
    return ' '.join([parsed[0]] + parsed[1])


# ------------------------------------------------------------------ actions
def _open_tasks(conn, conversation_id):
    from core.hb_chat_controls import continuation
    from core import hb_tasks
    out = []
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE conversation_id=? AND state NOT IN ('completed','cancelled')"
                               " ORDER BY updated_at DESC LIMIT 40", (conversation_id,)):
        t = hb_tasks.get(conn, tid)
        c = continuation(conn, t)
        out.append({'task_id': tid, 'title': str(t['title'] or '').replace('\n', ' '), 'state': t['state'],
                    'mode': c['mode'], 'status': c['status']})
    return out


def _online_lines(conn):
    from core import hb_online
    lines = []
    for p in hb_online.PROVIDERS:
        s = hb_online.status(conn, p)
        lines.append(f"- {p}: {'authorised' if s['authorised'] else 'not authorised'}, "
                     f"{'available' if s['available'] else 'UNAVAILABLE'} ({s['reason']})"
                     + (' -> HB will use it' if s['usable'] else ' -> HB will not use it automatically'))
    return lines


def _status(conn):
    lines = ['Hummingbird status']
    for name, state in conn.execute("SELECT principal, state FROM hb_peer_workers ORDER BY principal"):
        lines.append(f'- worker {name}: {state}')
    try:
        with urllib.request.urlopen(LLAMA + '/health', timeout=3) as r:
            ok = json.loads(r.read().decode()).get('status') == 'ok'
    except Exception:
        ok = False
    lines.append(f"- APEX server: {'healthy' if ok else 'not answering'}, {'idle' if _llama_idle() else 'busy or unknown'}")
    try:
        import glob
        vals = [int(open(p).read()) // 2**20 for p in glob.glob('/sys/class/drm/card*/device/mem_info_vram_used')]
        if vals:
            lines.append(f'- GPU memory used: {max(vals)} MB')
    except Exception:
        pass
    lines += _online_lines(conn)
    counts = dict(conn.execute("SELECT state, COUNT(*) FROM hb_peer_work WHERE state IN ('queued','running') GROUP BY state").fetchall())
    lines.append(f"- requests: {counts.get('running', 0)} running, {counts.get('queued', 0)} queued")
    return '\n'.join(lines)


def _queue(conn):
    from core.hb_online import may_dispatch
    rows = conn.execute("SELECT w.request_id, w.state, p.recipient, p.sender, COALESCE(r.task_id,'-'), substr(w.stage,1,60) FROM hb_peer_work w "
                        "JOIN peer_messages p ON p.id=w.request_id LEFT JOIN hb_task_requests r ON r.request_id=w.request_id "
                        "WHERE w.state IN ('queued','running') ORDER BY w.request_id").fetchall()
    if not rows:
        return 'Queue is empty.'
    out = ['Queue:']
    for rid, state, recipient, sender, tid, stage in rows:
        ok, why = may_dispatch(conn, recipient, sender)
        out.append(f'- #{rid} {state} -> {recipient} task {tid}: {stage}' + ('' if ok else f' [held: {why}]'))
    return '\n'.join(out)


def _approvals(conn, conversation_id):
    lines = []
    for item in waiting_items(conn, conversation_id):
        if item['kind'] == 'confirm':
            lines.append(f"- HB is waiting for /yes or /no on: {item['title']}")
        elif item['kind'] == 'halted':
            lines.append(f"- {item['task_id']} is halted: {item['why']}. " + ' or '.join(a['command'].strip() for a in item['actions']))
        elif item['kind'] == 'review':
            lines.append(f"- request #{item['request_id']} (task {item['task_id']}) needs review: {item['why'][:90]}")
        elif item['kind'] == 'plan':
            lines.append(f"- {item['task_id']} ({item['step_id']}): APEX's plan waits for you: "
                         + ' or '.join(a['command'].strip() for a in item['actions']))
        elif item['kind'] == 'workflow':
            lines.append(f"- The plan workflow is off. {item['why']}. /workflow on starts it; /workflow off keeps it off")
        elif item['kind'] == 'status':
            continue                                    # information, not a decision (see /workflow)
        else:
            lines.append(f"- Studio {item['step_id']} \"{item['title'][:90]}\" is built and needs your acceptance: "
                         f"/accept {item['step_id']} or /reject {item['step_id']} <reason>")
    return 'Waiting for you:\n' + '\n'.join(lines) if lines else 'Nothing is waiting for you.'


# ------------------------------------------------------------------ "Needs you" bar (owner 12 Nov)
# Everything waiting for the owner, pinned at the top of main chat: hover a tag to see what it is,
# click it to open what it points to. /approvals prints the same list.
_ASK_ACTIONS = (   # commands HB offers in its "needs you" questions -> buttons
    (re.compile(r'/plan (T-[0-9A-F]{12}) approves\b'), 'Approve plan', '/plan {0}', False),
    (re.compile(r'/plan (T-[0-9A-F]{12}) asks APEX again\b'), 'Ask APEX again', '/plan {0}', False),
    (re.compile(r'/accept (S-[0-9A-F]{10})\b'), 'Approve step', '/accept {0}', False),
    (re.compile(r'/continue (T-[0-9A-F]{12})\b'), 'Keep working', '/continue {0}', False),
    (re.compile(r'/online (codex|gemini|claude) on\b'), 'Allow {0}', '/online {0} on', False),
    (re.compile(r'/done (T-[0-9A-F]{12})\b'), 'Say what done means…', '/done {0} ', True),     # the owner finishes the text
    (re.compile(r'/pause (T-[0-9A-F]{12})\b'), 'Pause', '/pause {0}', False),
    (re.compile(r'/cancel (T-[0-9A-F]{12})\b'), 'Cancel task…', '/cancel {0}', False),
)


def _columns(conn, table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}


def _short(title, size=40):
    title = ' '.join(str(title or '').split())
    head = title.split(':', 1)[0].strip()
    if 3 <= len(head) <= size:
        return head
    return title if len(title) <= size else title[:size - 1].rstrip() + '…'


def _ask_actions(text):
    out = []
    for pattern, label, command, fill in _ASK_ACTIONS:
        m = pattern.search(text or '')
        if m:
            out.append({'label': label.format(m.group(1).capitalize()), 'command': command.format(m.group(1)), 'fill': fill})
    return out


def waiting_items(conn, conversation_id=None, *, now=None):
    """Everything waiting for the owner, most urgent kind first: HB's /yes-/no question (it expires),
    halted tasks, agent requests held for review, Studio steps built and waiting for acceptance.
    Requests of finished or cancelled tasks are never listed (HB closes them: close_finished_reviews)."""
    now = time.time() if now is None else now
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    items = []

    def task(task_id):
        if 'hb_tasks' not in tables or not task_id:
            return None
        return conn.execute('SELECT task_id, conversation_id, root_message_id, title, project_id, step_id, state '
                            'FROM hb_tasks WHERE task_id=?', (task_id,)).fetchone()

    if conversation_id and 'hb_command_pending' in tables:
        row = conn.execute('SELECT id, command, created_at FROM hb_command_pending WHERE conversation_id=? AND used=0 AND created_at>? '
                           'ORDER BY id DESC LIMIT 1', (conversation_id, now - PENDING_TTL)).fetchone()
        if row:
            asked = conn.execute("SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent='hummingbird' AND content LIKE '%/yes%'",
                                 (conversation_id,)).fetchone()[0] if 'messages' in tables else None
            tid = (TASK_RE.findall(row[1]) or [None])[0]
            t = task(tid.upper() if tid else None)
            minutes = max(1, int((PENDING_TTL - (now - row[2])) // 60))
            items.append({'key': f'confirm:{row[0]}', 'kind': 'confirm', 'label': f'/{row[1]}'[:44], 'title': f'/{row[1]}',
                          'why': f'HB asked before running this; the question expires in about {minutes} min.',
                          'detail': _confirm_text(conn, row[1]) or f'Run /{row[1]}? Reply /yes or /no.',
                          'task_id': t[0] if t else None, 'step_id': t[5] if t else None, 'project_id': t[4] if t else None,
                          'conversation_id': conversation_id, 'message_ids': [asked] if asked else [],
                          'open': {'type': 'message', 'id': asked, 'conversation_id': conversation_id} if asked else None,
                          'actions': [{'label': 'Yes', 'command': '/yes'}, {'label': 'No', 'command': '/no'}], 'since': row[2]})

    if {'hb_task_manager', 'hb_tasks'} <= tables:
        for task_id, detail, updated in conn.execute("SELECT task_id, COALESCE(detail,''), updated_at FROM hb_task_manager "
                                                     "WHERE enabled=1 AND state='needs_owner' ORDER BY updated_at").fetchall():
            t = task(task_id)
            if not t or t[6] in ('completed', 'cancelled'):
                continue
            ev = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='owner_question' ORDER BY event_id DESC LIMIT 1",
                              (task_id,)).fetchone() if 'hb_task_events' in tables else None
            try:
                asked = json.loads(ev[0]) if ev else {}
            except (TypeError, ValueError):
                asked = {}
            text = asked.get('text') or f'Hummingbird needs you: {detail}'
            mids = [asked['message_id']] if asked.get('message_id') else []
            plan = asked.get('kind') == 'plan'                       # workflow: APEX's plan waiting for approval
            actions = _ask_actions(text) or [{'label': 'Keep working', 'command': f'/continue {task_id}'},
                                             {'label': 'Cancel task…', 'command': f'/cancel {task_id}'}]
            if plan:
                relabel = {'/cancel': 'Skip this step…', '/done': 'Write my own done…'}
                actions = [{**a, 'label': relabel.get(a['command'].split()[0], a['label'])} for a in actions]
            items.append({'key': f"{'plan' if plan else 'halted'}:{task_id}", 'kind': 'plan' if plan else 'halted',
                          'label': _short(re.sub(r'^S-[0-9A-F]{10}\s+', '', str(t[3]))), 'title': str(t[3]), 'why': detail,
                          'detail': text, 'task_id': task_id, 'step_id': t[5], 'project_id': t[4], 'conversation_id': t[1],
                          'message_ids': mids,
                          'open': {'type': 'step', 'id': t[5]} if t[5] else (
                              {'type': 'message', 'id': mids[0], 'conversation_id': t[1]} if mids else None),
                          'actions': actions, 'since': updated})

    if {'hb_peer_work', 'hb_task_requests', 'peer_messages', 'hb_tasks'} <= tables:
        pm = _columns(conn, 'peer_messages')
        pick = lambda name, sql=None: (sql or f'p.{name}') if name in pm else 'NULL'
        for rid, task_id, stage, updated, recipient, sender, mid, conv, body in conn.execute(
                "SELECT w.request_id, r.task_id, COALESCE(w.stage,''), w.updated_at, p.recipient, p.sender, "
                f"{pick('message_id')}, {pick('conversation_id')}, {pick('body', 'substr(p.body,1,1200)')} "
                "FROM hb_peer_work w JOIN hb_task_requests r ON r.request_id=w.request_id "
                "JOIN hb_tasks t ON t.task_id=r.task_id JOIN peer_messages p ON p.id=w.request_id "
                "WHERE w.state='needs_review' AND t.state NOT IN ('completed','cancelled') ORDER BY w.request_id DESC LIMIT 10").fetchall():
            t = task(task_id)
            items.append({'key': f'review:{rid}', 'kind': 'review', 'label': f'Request #{rid} to {recipient}', 'request_id': rid,
                          'title': f'{sender} → {recipient} · {task_id} {t[3] if t else ""}'.strip(), 'why': stage, 'detail': body or '',
                          'task_id': task_id, 'step_id': t[5] if t else None, 'project_id': t[4] if t else None,
                          'conversation_id': conv, 'message_ids': [mid] if mid else [],
                          'open': {'type': 'message', 'id': mid, 'conversation_id': conv} if mid else None,
                          'actions': [], 'since': updated})

    if 'project_steps' in tables:
        ps = _columns(conn, 'project_steps')
        col = lambda name, default='NULL': name if name in ps else default
        order = ', '.join(c for c in ('project_id', 'order_idx', 'updated_at') if c in ps) or 'step_id'
        for step_id, project_id, title, description, note, updated in conn.execute(
                f"SELECT step_id, {col('project_id')}, {col('title', 'step_id')}, COALESCE({col('description', 'NULL')},''), "
                f"COALESCE(residual_risk,''), {col('updated_at', '0')} FROM project_steps WHERE {ACCEPTANCE_SQL} ORDER BY {order}").fetchall():
            t = conn.execute("SELECT task_id, conversation_id, root_message_id FROM hb_tasks WHERE step_id=? ORDER BY created_at DESC LIMIT 1",
                             (step_id,)).fetchone() if 'hb_tasks' in tables else None
            items.append({'key': f'accept:{step_id}', 'kind': 'accept', 'label': _short(title), 'title': str(title), 'why': note,
                          'detail': description[:2400] + ('…' if len(description) > 2400 else ''), 'step_id': step_id,
                          'project_id': project_id, 'task_id': t[0] if t else None, 'conversation_id': t[1] if t else None,
                          'message_ids': [t[2]] if t else [], 'open': {'type': 'step', 'id': step_id},
                          'actions': [{'label': 'Approve', 'decision': 'accept'}, {'label': 'Send back…', 'decision': 'reject'}],
                          'since': updated})

    if {'project_steps', 'hb_tasks', 'hb_task_events'} <= tables:
        try:
            items += _finished_items(conn, items, conversation_id)
        except sqlite3.OperationalError:                # minimal / older Studio schema
            pass

    # 13 Nov: a finished task waiting for Approve is shown once; its halted / review copies only confused the owner.
    accepting = {i.get('task_id') for i in items if i['kind'] == 'accept' and i.get('task_id')}
    items = [i for i in items if not (i['kind'] in ('halted', 'review') and i.get('task_id') in accepting)]

    if {'project_steps', 'hb_tasks'} <= tables:
        try:
            items += _workflow_items(conn, tables)
        except sqlite3.OperationalError:                # minimal / older Studio schema: no plan workflow
            pass
    return items


def _finished_items(conn, items, conversation_id):
    # Owner 13 Nov: finished work must reach the bar even when its task is held (workflow off / Continue off):
    # an open step whose task's latest passing check is newer than its latest change.
    listed = {i['key'] for i in items}
    found = []
    for step_id, project_id, title, description, task_id, conv, root in conn.execute(
            "SELECT s.step_id, s.project_id, s.title, COALESCE(s.description,''), t.task_id, t.conversation_id, t.root_message_id "
            "FROM project_steps s JOIN hb_tasks t ON t.step_id=s.step_id "
            "WHERE s.status IN ('todo','doing','partial') AND t.state IN ('active','paused')").fetchall():
        if f'accept:{step_id}' in listed or (conversation_id is not None and conv != conversation_id):
            continue
        passed, changed = conn.execute(
            "SELECT MAX(CASE WHEN kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass' THEN created_at END), "
            "MAX(CASE WHEN kind='mutation' THEN created_at END) FROM hb_task_events WHERE task_id=?", (task_id,)).fetchone()
        if not passed or not changed or passed < changed:
            continue
        listed.add(f'accept:{step_id}')
        found.append({'key': f'accept:{step_id}', 'kind': 'accept', 'label': _short(title), 'title': str(title),
                      'why': 'Finished: its checks pass after its last change', 'detail': description[:2400],
                      'step_id': step_id, 'project_id': project_id, 'task_id': task_id, 'conversation_id': conv,
                      'message_ids': [root], 'open': {'type': 'step', 'id': step_id},
                      'actions': [{'label': 'Approve', 'decision': 'accept'}, {'label': 'Send back…', 'decision': 'reject'}],
                      'since': passed})
    return found


def _workflow_items(conn, tables):
    """The plan workflow in the bar: "Start the plan?" when it is off and the owner approved something since
    deciding, or a status tag (not counted as needing you) while it runs."""
    from core import hb_plan_workflow as wf
    w = wf.settings(conn)
    project = wf.DEFAULT_PROJECT
    if w and w['enabled']:
        words = {'planning': 'APEX is scoping', 'plan_ready': 'your plan approval', 'running': 'running',
                 'finished': 'nothing ready', 'idle': 'starting', 'starting': 'starting'}
        title = ''
        if w['step_id']:
            row = conn.execute('SELECT title FROM project_steps WHERE step_id=?', (w['step_id'],)).fetchone()
            title = _short(row[0], 32) if row else w['step_id']
        return [{'key': f'workflow-status:{project}', 'kind': 'status', 'info': True,
                 'label': f"{words.get(w['stage'], w['stage'])}" + (f': {title}' if title else ''),
                 'title': f'Plan workflow is on ({project})', 'why': w['note'] or '', 'detail': wf.status_text(conn, project),
                 'step_id': w['step_id'], 'project_id': project, 'task_id': w['task_id'], 'conversation_id': w['conversation_id'],
                 'message_ids': [], 'open': {'type': 'step', 'id': w['step_id']} if w['step_id'] else None,
                 'actions': [{'label': 'Stop the workflow', 'command': '/workflow off'}], 'since': w['decided_at']}]
    approved = conn.execute("SELECT MAX(updated_at) FROM project_steps WHERE project_id=? AND residual_risk LIKE 'Accepted by owner%'",
                            (project,)).fetchone()[0] or 0
    if w and (w['decided_at'] or 0) >= approved:
        return []                                               # the owner said "not now" and approved nothing since
    plan = wf.steps(conn, project)
    ready = [s for s in plan if not s['skip']]
    if not ready:
        return []
    nxt = ready[0]
    detail = ('HB takes one step at a time, in plan order:\n'
              '1. APEX scopes the step with read-only tools and proposes what done means and a short plan.\n'
              '2. You approve the plan here (or write your own done criteria, or skip the step).\n'
              '3. HB runs it, and stops to ask you if it loops, keeps failing the same way, or needs review.\n'
              '4. You approve the finished step here; HB then starts the next one.\n'
              '/workflow off stops it at any time; Continue Off on a task makes the workflow skip that task.\n\n'
              'Ready now: ' + '; '.join(f"{s['step_id']} {s['title'][:70]}" for s in ready[:6]) +
              ('\nSkipped for now: ' + '; '.join(f"{s['step_id']} ({s['skip']})" for s in plan if s['skip'])[:900]
               if any(s['skip'] for s in plan) else ''))
    return [{'key': f'workflow:{project}', 'kind': 'workflow', 'label': 'Start the plan',
             'title': f'Let HB run plan {project} step by step?', 'why': f"Next: {nxt['step_id']} {nxt['title'][:90]}",
             'detail': detail, 'step_id': nxt['step_id'], 'project_id': project, 'task_id': nxt['task_id'],
             'conversation_id': MAIN_CHAT_ID, 'message_ids': [], 'open': {'type': 'step', 'id': nxt['step_id']},
             'actions': [{'label': 'Start', 'command': '/workflow on'}, {'label': 'Not now', 'command': '/workflow off'}],
             'since': approved}]


def close_finished_reviews(conn, now=None):
    """HB housekeeping: a request held for review whose task is finished or cancelled can never be decided
    (the task is gone from every list), so HB closes it instead of listing it for the owner forever."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'hb_peer_work', 'hb_task_requests', 'hb_tasks'} <= tables:
        return 0
    return conn.execute(
        "UPDATE hb_peer_work SET state='cancelled', updated_at=?, stage='Closed by HB: its task is ' || "
        "(SELECT t.state FROM hb_task_requests r JOIN hb_tasks t ON t.task_id=r.task_id WHERE r.request_id=hb_peer_work.request_id LIMIT 1) "
        "WHERE state='needs_review' AND request_id IN (SELECT r.request_id FROM hb_task_requests r JOIN hb_tasks t "
        "ON t.task_id=r.task_id WHERE t.state IN ('completed','cancelled'))", (time.time() if now is None else now,)).rowcount + \
        conn.execute(   # 13 Nov: a turn cut off by a restart is out of date once a later turn of the same task completed
            "UPDATE hb_peer_work SET state='cancelled', updated_at=?, stage='Closed by HB: a later turn of the same task completed' "
            "WHERE state='needs_review' AND request_id IN (SELECT r.request_id FROM hb_task_requests r JOIN hb_task_requests r2 "
            "ON r2.task_id=r.task_id AND r2.request_id>r.request_id JOIN hb_peer_work w2 ON w2.request_id=r2.request_id "
            "WHERE w2.state='completed')", (time.time() if now is None else now,)).rowcount + \
        (conn.execute(   # 13 Nov: a cut-off turn of a task that now waits for its dependencies is moot; the task restarts cleanly later
            "UPDATE hb_peer_work SET state='cancelled', updated_at=?, stage='Closed by HB: its task waits for the tasks it depends on' "
            "WHERE state='needs_review' AND request_id IN (SELECT r.request_id FROM hb_task_requests r JOIN hb_task_manager m "
            "ON m.task_id=r.task_id WHERE m.state='waiting_dependencies')", (time.time() if now is None else now,)).rowcount
         if 'hb_task_manager' in tables else 0)


def _set_mode(conn, task_id, mode, actor):
    from core import hb_tasks
    from core.hb_chat_controls import continuation, set_continuation
    t = hb_tasks.get(conn, task_id)
    if not t:
        return f'No task {task_id}.'
    if t['state'] == 'cancelled':
        return f'{task_id} is cancelled.'
    r = set_continuation(conn, t, {'mode': mode, 'message_id': t['root_message_id'], 'version': t['version'],
                                   'revision': continuation(conn, t)['revision'],
                                   'command_id': 'hb-cmd-' + uuid.uuid4().hex[:16]}, actor)
    extra = f" Queued request(s): {', '.join(map(str, r['queued']))}." if r.get('queued') else ''
    return f"{task_id} is now {'On' if mode == 'on' else 'Off'} ({r['state']}).{extra}"


def cancel_task(conn, task_id, actor, after=None):
    """Owner cancels a task: Off, state cancelled, queued requests cancelled, its Studio step closed."""
    from core import hb_tasks
    t = hb_tasks.get(conn, task_id)
    if not t:
        return f'No task {task_id}.'
    if t['state'] == 'completed':
        return f'{task_id} is already completed and accepted; nothing to cancel.'
    if t['state'] == 'cancelled':
        return f'{task_id} was already cancelled.'
    if t['state'] != 'paused':
        _set_mode(conn, task_id, 'off', actor)
    now = time.time()
    conn.execute("UPDATE hb_tasks SET state='cancelled', updated_at=? WHERE task_id=?", (now, task_id))
    n = conn.execute("UPDATE hb_peer_work SET state='cancelled', stage='Owner cancelled the task', updated_at=? "
                     "WHERE state='queued' AND request_id IN (SELECT request_id FROM hb_task_requests WHERE task_id=?)",
                     (now, task_id)).rowcount
    step = t['step_id'] if 'step_id' in t.keys() and t['step_id'] else 'S-' + hashlib.sha256(task_id.encode()).hexdigest()[:10].upper()
    conn.execute("UPDATE project_steps SET status='skipped', residual_risk=?, updated_at=? WHERE step_id=? "
                 "AND status IN ('todo','doing','partial','blocked')", (f'Owner cancelled task {task_id}', now, step))
    conn.execute("UPDATE hb_task_manager SET state='cancelled', detail='Owner cancelled this task', updated_at=? WHERE task_id=?", (now, task_id))
    hb_tasks.event(conn, hb_tasks.get(conn, task_id), 'user', 'cancelled', {'actor': actor, 'queued_requests_cancelled': n})
    if after is not None:
        def stop():
            from core.hb_executions import stop_held_executors
            stop_held_executors(task_id)
        after.append(stop)
    return f'{task_id} cancelled. {n} queued request(s) cancelled; any running work is being stopped.'


def acceptance_state(conn, step_id):
    """For chat bubbles: is this Studio step waiting for, or decided by, the owner?"""
    if not step_id or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_steps'").fetchone():
        return None
    row = conn.execute('SELECT status, COALESCE(residual_risk,\'\'), title FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
    if not row:
        return None
    status, note, title = row
    if status == 'partial' and re.search(r'acceptance pending|awaiting owner acceptance', note, re.I):
        state = 'pending'
    elif status == 'done' and note.startswith('Accepted by owner'):
        state = 'accepted'
    elif status == 'todo' and note.startswith('Owner rejected'):
        state = 'sent_back'
    else:
        return None
    return {'step_id': step_id, 'state': state, 'note': note[:240], 'title': str(title)[:120]}


def accept_step(conn, step_id, actor, comment=''):
    row = conn.execute('SELECT status, title FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
    if not row:
        return f'No Studio step {step_id}.'
    if row[0] == 'done':
        return f'{step_id} is already accepted.'
    now = time.time()
    comment = ' '.join(str(comment or '').split())[:1000]
    auto = str(actor).startswith('HB auto-approve')
    conn.execute("UPDATE project_steps SET status='done', residual_risk=?, updated_at=? WHERE step_id=?",
                 ((f'Approved automatically by HB (owner policy, workflow auto-approve)' if auto else f'Accepted by owner ({actor}) via /accept')
                  + (f': {comment}' if comment and not auto else ''), now, step_id))
    from core import hb_tasks
    tasks = []
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled')", (step_id,)).fetchall():
        conn.execute("UPDATE hb_tasks SET state='completed', updated_at=? WHERE task_id=?", (now, tid))
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_manager'").fetchone():
            conn.execute("UPDATE hb_task_manager SET state='complete', detail='Owner accepted the Studio step', updated_at=? WHERE task_id=?", (now, tid))
        hb_tasks.event(conn, hb_tasks.get(conn, tid), 'user', 'owner_accepted', {'step_id': step_id, 'actor': actor,
                                                                               **({'comment': comment} if comment else {})})
        tasks.append(tid)
    try:   # owner 14 Nov: credit and applause only for a checked success (core/hb_merits.py)
        from core import hb_merits
        hb_merits.on_accept(conn, step_id, tasks, str(row[1]))
    except Exception:
        pass
    return _accept_record(conn, step_id, str(row[1]), tasks, comment, auto)


def _accept_record(conn, step_id, title, tasks, comment, auto=False):
    """Owner 13 Nov: an approval reads plainly (what is done, who approved, what is next); ids and checks go under Details."""
    from core.hb_plain import message, name
    try:
        desc = conn.execute('SELECT COALESCE(description,\'\'), project_id FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
    except sqlite3.OperationalError:                    # minimal Studio schema
        desc = None
    done_when = [l.strip()[len('done when'):].strip(' :') for l in str(desc[0] if desc else '').splitlines()
                 if l.strip().lower().startswith('done when')][:3]
    verdict = ''
    if tasks:
        test = conn.execute("SELECT json_extract(payload,'$.verdict') FROM hb_task_events WHERE task_id=? AND kind='test_result' "
                            "AND json_extract(payload,'$.alm_run_status')='pass' ORDER BY event_id DESC LIMIT 1", (tasks[0],)).fetchone()
        verdict = test[0] if test and test[0] else ''
    who = ('APEX finished it and its check passed, so HB approved it for you (auto-approve is on).' if auto
           else 'You approved it.' + (' Its check passed.' if verdict else ''))
    lines = [who]
    if comment and not auto:
        lines.append(f'Your comment is saved with it: {comment}')
    try:
        from core import hb_plan_workflow as wf
        w = wf.settings(conn, desc[1] if desc and desc[1] else wf.DEFAULT_PROJECT) if desc else None
        if w:
            nxt = wf.next_ready(conn, w['project_id'], w.get('preferred_step'))
            if w['enabled']:
                lines.append(f'Next: {name(nxt["title"])}.' if nxt else 'Next: nothing else is ready yet; HB waits.')
            else:
                lines.append('The plan is paused' + (f'; next in line: {name(nxt["title"])}.' if nxt else '.'))
    except Exception:
        pass
    return message(f'✅ Done: {name(title)}.', *lines,
                   details=[f'step {step_id}', f'task {", ".join(tasks)}' if tasks else '',
                            ('done when: ' + '; '.join(done_when)) if done_when else '', f'check: {verdict}' if verdict else ''])


def reject_step(conn, step_id, reason, actor):
    row = conn.execute('SELECT status, title FROM project_steps WHERE step_id=?', (step_id,)).fetchone()
    if not row:
        return f'No Studio step {step_id}.'
    conn.execute("UPDATE project_steps SET status='todo', residual_risk=?, updated_at=? WHERE step_id=?",
                 (f'Owner rejected ({actor}): {reason}'[:240], time.time(), step_id))
    from core import hb_tasks
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled')", (step_id,)).fetchall():
        hb_tasks.event(conn, hb_tasks.get(conn, tid), 'user', 'owner_rejected', {'step_id': step_id, 'reason': reason, 'actor': actor})
    return f'Sent {step_id} back to todo with your reason: {reason}'


def run(conn, conversation_id, command, args, actor, after=None):
    if command == 'help':
        return HELP
    if command == 'status':
        return _status(conn)
    if command == 'queue':
        return _queue(conn)
    if command == 'approvals':
        return _approvals(conn, conversation_id)
    if command == 'tasks':
        tasks = _open_tasks(conn, conversation_id)
        if not tasks:
            return 'No open tasks in this chat.'
        total = conn.execute("SELECT COUNT(*) FROM hb_tasks WHERE conversation_id=? AND state NOT IN ('completed','cancelled')", (conversation_id,)).fetchone()[0]
        head = f'Open tasks ({total}' + (f', newest {len(tasks)} shown' if total > len(tasks) else '') + '):\n'
        return head + '\n'.join(f"- {t['task_id']} [{t['state']}, Continue {t['mode']}, {t['status']}] {t['title'][:90]}" for t in tasks)
    if command == 'stuck':
        from core.hb_dream_cycle import build_report
        return build_report(conn)['text']
    if command in ('pause', 'continue'):
        return _set_mode(conn, args[0], 'off' if command == 'pause' else 'on', actor + ' via /' + command)
    if command == 'cancel':
        return cancel_task(conn, args[0], actor + ' via /cancel', after)
    if command in ('done', 'clipboard'):
        from core import hb_tasks, hb_dream_method
        task = hb_tasks.get(conn, args[0])
        if not task:
            return f'No task {args[0]}.'
        if command == 'clipboard':
            return hb_dream_method.card(conn, task)
        criteria = hb_dream_method.set_done(conn, task, args[1:], actor)
        from core import hb_plan_workflow
        if hb_plan_workflow.after_done(conn, task):
            return f"Done criteria for {args[0]} saved: " + '; '.join(criteria) + '. The workflow runs it now.'
        return (f"Done criteria for {args[0]} saved: " + '; '.join(criteria) +
                '. HB can now run it automatically when Continue is On.')
    if command == 'nanny':
        from core import hb_nanny_bot as nanny
        sub = args[0]
        if sub == 'on':
            s_ = nanny.configure(conn, True, int(args[1]) if len(args) > 1 else None)
            return f"Nanny on: it checks every {s_['interval_s'] // 60} min in RAM ({nanny.NANNY_MODEL}) and posts here only when something changes."
        if sub == 'off':
            nanny.configure(conn, False)
            return 'Nanny off.'
        if sub == 'report':
            items = nanny.findings(nanny.facts(conn))
            return 'Nanny check now: ' + nanny.plain_note(items) + ''.join(
                f"\n- {i['text']}" + (f" {i['command']}" if i['command'] else '') for i in items)
        s_ = nanny.settings(conn)
        return f"Nanny {'on' if s_['enabled'] else 'off'}, every {s_['interval_s'] // 60} min." + (
            f" Last check {time.strftime('%H:%M', time.localtime(s_['last_run']))}." if s_['last_run'] else '')
    if command == 'unload':
        from core.hb_hardware import model_processes
        target = next((p for p in model_processes() if p['model'].lower() == args[0].lower()), None)
        if not target:
            return f"{args[0]} is not loaded."
        if target['kind'] != 'managed':
            return f"{args[0]} is a system service; use its Stop switch on the sundial."
        from core.seven_llm import llama_server
        stopped = llama_server.stop(target['model'])
        return f"Unloaded {target['model']} (freed about {target['vram_gb']} GB VRAM, {target['ram_gb']} GB RAM)." if stopped else \
            f"{target['model']} could not be unloaded."
    if command == 'clip':
        from core import hb_clipboard
        return hb_clipboard.edit(conn, args, actor)
    if command == 'pick':
        from core import hb_counsel
        return hb_counsel.pick(conn, args[0], int(args[1]), actor)
    if command == 'agents':
        from core import hb_agents
        if len(args) >= 2 and args[0].lower() == 'retire':
            return hb_agents.retire(conn, args[1], actor)
        if len(args) >= 3 and args[0].lower() == 'model':
            return hb_agents.swap_model(conn, args[1], args[2], actor)
        if len(args) >= 2 and args[0].lower() == 'examine':                 # HB examines an agent itself, through its inbox
            agent_id = hb_agents.resolve(conn, args[1])
            return hb_agents.examine(conn, agent_id, conversation_id, actor, say=lambda _t: None) if agent_id else f'HB does not know {args[1]}.'
        if len(args) >= 3 and args[0].lower() == 'handles':                 # /agents handles copilot-instructor github,copilot
            agent_id = hb_agents.resolve(conn, args[1])
            if not agent_id:
                return f'HB does not know {args[1]}.'
            return f"{agent_id} answers to @" + ', @'.join(hb_agents.set_handles(conn, agent_id, ' '.join(args[2:]).replace(',', ' ').split()))
        if len(args) >= 4 and args[0].lower() == 'onboard':                 # /agents onboard <id> <profile> <what it is for>
            a = hb_agents.onboard(conn, args[1], kind='online', profile=args[2], about=' '.join(args[3:]), actor=actor, say=lambda _t: None)
            return (f"{a['agent_id']} is registered (own login, memory, KC page) as {args[2]}, provisional. "
                    + hb_agents.examine(conn, a['agent_id'], conversation_id, actor, say=lambda _t: None))
        if args and args[0].lower() == 'onboard-local':
            done = hb_agents.onboard_local_models(conn, actor)
            return f"Onboarded {len(done)} local model(s) as HB agents: {', '.join(done) or 'none benchmarked yet'}."
        return hb_agents.status_text(conn)
    if command == 'bench':
        from core import hb_model_bench as mb
        if args and args[0].lower() == 'status':
            return 'A benchmark is running; see main chat and the live activity.' if mb.running() else 'No benchmark is running. /bench all starts one.'
        return mb.request(conn, None if not args or args[0].lower() == 'all' else args, actor)
    if command == 'merits':
        from core import hb_merits
        return hb_merits.status_text(conn)
    if command == 'downloads':
        from core import hb_downloads
        return hb_downloads.status_text(conn)
    if command == 'tidy':
        from core import hb_owner_intent
        return hb_owner_intent.tidy(conn, conversation_id, actor, confirm=bool(args))
    if command == 'drive':
        from core import hb_queue
        return hb_queue.command(conn, conversation_id, args, actor)
    if command == 'workflow':
        from core import hb_plan_workflow
        return hb_plan_workflow.command(conn, conversation_id, args, actor)
    if command == 'plan':
        from core import hb_plan_workflow
        return hb_plan_workflow.approve_plan(conn, args[0], actor)
    if command == 'accept':
        return accept_step(conn, args[0], actor, args[1] if len(args) > 1 else '')
    if command == 'reject':
        return reject_step(conn, args[0], args[1], actor)
    if command == 'online':
        from core import hb_online
        if args:
            hb_online.authorise(conn, args[0], args[1] == 'on', actor)
        return 'Online providers:\n' + '\n'.join(_online_lines(conn))
    if command == 'dream':
        from core import hb_dream_cycle as dc
        sub = args[0]
        if sub == 'on':
            s = dc.configure(conn, True, int(args[1]) if len(args) > 1 else None)
            return f"DREAM on: one facts-only report after {s['idle_after']}s without an owner message."
        if sub == 'off':
            dc.configure(conn, False)
            return 'DREAM off.'
        if sub == 'report':
            return dc.build_report(conn)['text']
        s, last = dc.settings(conn), dc.latest_report(conn)
        return (f"DREAM {'on' if s['enabled'] else 'off'}, idle_after {s['idle_after']}s. "
                + (f"Last cycle #{last['cycle_id']}: {last['state']}." if last else 'No cycles yet.'))
    return HELP


def _remember(conn, conversation_id, command, source):
    ensure_schema(conn)
    conn.execute('UPDATE hb_command_pending SET used=1 WHERE conversation_id=? AND used=0', (conversation_id,))
    conn.execute('INSERT INTO hb_command_pending(conversation_id, command, source, created_at) VALUES(?,?,?,?)',
                 (conversation_id, command, source, time.time()))


def _confirm_text(conn, command):
    parsed = parse(command)
    if parsed and parsed[0] == 'cancel':
        row = conn.execute('SELECT title FROM hb_tasks WHERE task_id=?', (parsed[1][0],)).fetchone()
        title = str(row[0])[:100] if row else '(unknown task)'
        return f'Cancel {parsed[1][0]} "{title}"? Its queued work is dropped and it will not run again. Reply /yes or /no.'
    return None


def handle(conn, conversation_id, text, actor, *, interpreter=interpret, after=None):
    """Return HB's reply for a "/" (or @hb) message. `after` collects work to run after commit."""
    ensure_schema(conn)
    body = _body(text)
    parsed = parse(body)
    if parsed and parsed[0] in ('yes', 'no'):
        row = conn.execute('SELECT id, command FROM hb_command_pending WHERE conversation_id=? AND used=0 AND created_at>? '
                           'ORDER BY id DESC LIMIT 1', (conversation_id, time.time() - PENDING_TTL)).fetchone()
        if not row:
            return 'Nothing is waiting for confirmation (questions expire after 10 minutes).'
        conn.execute('UPDATE hb_command_pending SET used=1 WHERE id=?', (row[0],))
        if parsed[0] == 'no':
            return f'OK, not running /{row[1]}.'
        cmd, args = parse(row[1])
        return f'Running /{row[1]}:\n' + run(conn, conversation_id, cmd, args, actor, after)
    if parsed:
        if dict((n, c) for n, _, _, c in COMMANDS)[parsed[0]]:                # consequential: halt and ask
            command = ' '.join([parsed[0]] + parsed[1])
            _remember(conn, conversation_id, command, 'confirm')
            return _confirm_text(conn, command)
        return run(conn, conversation_id, *parsed, actor, after)
    near = suggest(body)                                                       # C
    if near:
        _remember(conn, conversation_id, near, 'suggest')
        return f'Did you mean "/{near}"? Reply /yes to run it or /no.'
    if len(body.split()) >= 2:                                                 # B
        cmd = interpreter(body, _open_tasks(conn, conversation_id))
        if cmd:
            _remember(conn, conversation_id, cmd, 'local-model')
            extra = ' ' + _confirm_text(conn, cmd) if _confirm_text(conn, cmd) else ' Reply /yes to run it or /no.'
            return f'I read that as "/{cmd}" (local model interpretation; nothing has run).' + extra
        return 'I could not map that to a command (or the local model is busy). Type / to see the list.'
    return HELP
