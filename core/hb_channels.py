"""HB channels (plan 20 Nov 3/8; owner: "Telegram and Discord need to be wired back in so I can use either email, Discord or Telegram to
talk to the system if I'm away from the screen ... duplicating the main chat into those apps and show me what is needed from me to continue
working on open tasks ... listening and executing when I send a request, or any other user registered and enrolled in the system").

The old bots (fridays/telegram_bot.py, fridays/discord_bot.py, core/pipeline/listener.py) still ran the pre-HB "Fridays" debate pipeline
and their services pointed at the retired /home/seven/swarm; they have not run since April. This module puts the channels into HB:

  inbound(conn, channel, key, name, text, reply)  one message from Telegram / email / Discord, from a known identity:
      /command    the safe list (SAFE_COMMAND) runs through hb_commands like a main-chat command, as "JD via Telegram";
                  commands that change the machine, run sudo or spend money answer "needs the screen"
      question    an answer-only APEX turn with the research tools (answer_only) - never waits behind a workflow task
      request     from the owner: an APEX task, exactly like an owner's message in main chat (changes still need his approval)
      Every inbound message is also posted in main chat; unknown senders get nothing run and JD is told.
  mirror_once(conn)  new main-chat posts and new Needs-you items to the owner's Telegram (tool noise and raw JSON left out)
  from_email(...)    called by core/hb_email_intake.ingest for mail from a known identity; a request runs only when Gmail's
                     Authentication-Results show the sender passed DKIM or SPF
  tick(conn)         from HB's coordinator: seeds identities once, starts the Telegram poller, the mirror and the answer worker

Identities (hb_channel_identities): role 'owner' for JD's own Telegram chat / Discord user / email addresses, 'user' for enrolled
people (questions only). Seeded from utils.config and the existing trusted_senders list; /channels trust|untrust changes them."""
import json
import queue
import re
import threading
import time
import urllib.parse
import urllib.request

SAFE_COMMANDS = {'help', 'status', 'tasks', 'stuck', 'approvals', 'queue', 'pause', 'continue', 'cancel', 'done', 'clipboard', 'clip',
                 'workflow', 'plan', 'accept', 'reject', 'today', 'drive', 'yes', 'no', 'examples', 'merits', 'downloads', 'scorecards',
                 'consult', 'choose', 'pick', 'note', 'notes', 'email', 'channels', 'board', 'train', 'chunks'}
USER_COMMANDS = {'help', 'about', 'mine', 'start'}   # Practice 212: guest commands (core/hb_guest.py)
WELCOME_IN_TESTS = False   # Practice 212: no real Telegram welcome from a test
HB_OWN = ('sevenpotato9@', 'ninepotato7@')           # HB's own mailboxes: never a request (no loops)
TITLE = {'telegram': 'Telegram', 'email': 'Email', 'discord': 'Discord'}
QUESTION = re.compile(r"^\s*(what|how|why|when|where|who|which|whose|is|are|was|were|can|could|does|do|did|should|would|will|tell me|"
                      r"explain|describe|show me|list|give me|any)\b|\?\s*$", re.I)
TELEGRAM_CHUNK = 3800
SENDER_LABEL = {'apex': 'APEX', 'hummingbird': 'HB', 'fred': 'Fred', 'claude-code': 'Claude Code', 'codex-instructor': 'Codex',
                'gemini-advisor': 'Gemini', 'copilot-instructor': 'Copilot', 'user': 'You'}
JOBS = queue.Queue()
_STARTED = {'threads': False}


def _connect():
    from utils.db._connection import get_connection
    return get_connection()


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_channel_identities(key TEXT PRIMARY KEY, role TEXT NOT NULL, name TEXT, added_by TEXT, at REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_channel_cursor(name TEXT PRIMARY KEY, value TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_channel_log(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, channel TEXT, direction TEXT, '
                 'sender TEXT, message_id INTEGER, text TEXT)')


def cursor(conn, name, default=None):
    ensure(conn)
    row = conn.execute('SELECT value FROM hb_channel_cursor WHERE name=?', (name,)).fetchone()
    return row[0] if row else default


def set_cursor(conn, name, value):
    ensure(conn)
    conn.execute('INSERT OR REPLACE INTO hb_channel_cursor VALUES (?,?)', (name, str(value)))


# ------------------------------------------------------------------ identities
def _owner_like(key, note):
    text = f'{key} {note}'.lower()
    return 'jeandre' in text or 'ghost' in text or 'swarm owner' in text


def seed(conn, config=None):
    """JD's identities from config (owner) and the old trusted_senders list (owner when it names JD, else user). Never overwrites."""
    ensure(conn)
    if config is None:
        from utils import config
    now = time.time()
    rows = []
    try:
        rows.append((f'telegram:{config.GHOST_TELEGRAM_CHAT_ID}', 'owner', 'JD', 'config'))
        rows.append((f'email:{config.GHOST_EMAIL.lower()}', 'owner', 'JD', 'config'))
    except Exception:
        pass
    try:
        for sender, note in conn.execute('SELECT email, notes FROM trusted_senders'):
            key = str(sender or '').strip().lower()
            if not key or any(own in key for own in HB_OWN):
                continue
            key = key if ':' in key else 'email:' + key
            rows.append((key, 'owner' if _owner_like(key, note or '') else 'user', (note or '')[:60], 'trusted_senders'))
    except Exception:
        pass
    for key, role, name, by in rows:
        conn.execute('INSERT OR IGNORE INTO hb_channel_identities VALUES (?,?,?,?,?)', (key, role, name, by, now))


def role(conn, key):
    ensure(conn)
    row = conn.execute('SELECT role FROM hb_channel_identities WHERE key=?', (str(key).lower(),)).fetchone()
    return row[0] if row else None


def owner_keys(conn, channel):
    ensure(conn)
    return [r[0] for r in conn.execute("SELECT key FROM hb_channel_identities WHERE role='owner' AND key LIKE ?", (channel + ':%',))]


# ------------------------------------------------------------------ inbound
def _chat(conn):
    from core.hb_chat import owner_chat
    return owner_chat(conn)


def _post(conn, sender, text, to='user', kind='response'):
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,?,?,?,?,0)",
                        (_chat(conn), sender, to, text, kind)).lastrowid


def _log(conn, channel, direction, sender, mid, text):
    ensure(conn)
    conn.execute('INSERT INTO hb_channel_log(at, channel, direction, sender, message_id, text) VALUES (?,?,?,?,?,?)',
                 (time.time(), channel, direction, sender, mid, str(text)[:500]))


def kind_of(text, is_owner):
    text = str(text or '').strip()
    if text.startswith('/'):
        return 'command'
    # Practice 197 (emergency 20 Nov): every owner message that was not a question ("Hey", "Fix it", "Love you") became its own APEX task
    # through the peer queue - fifteen tasks in minutes, each refused with HTTP 403 because a phone message carries no owner session
    # grant. Everything that is not a /command now gets APEX's answer-only turn in main chat; work tasks stay a main-chat action.
    return 'question'


_RESUME_EXISTING = re.compile(
    r'^(?:please\s+)?(?:continue|resume|proceed|retry|keep going|keep working|go ahead|finish|fix|repair|work on)'
    r'\b(?:\s+(?:please|now|with|on|the|this|that|current|existing|task|step|it|work|repair))*[.!?]*$', re.I)


def _owner_operating_request(conn, text, mid, title):
    """A verified owner can control existing scoped work; prose grants no new scope.

    Keep arbitrary new requests in the answer lane rather than restoring the old
    peer enqueue branch that manufactured unscoped tasks for every phone remark.
    """
    from core import hb_tasks, hb_task_manager, hb_owner_sessions, hb_commands
    from core.hb_chat_controls import continuation, held_requests
    from core.hb_dream_method import done_when
    from core.hb_owner_intent import classify, status_text
    from core.apex_tools import research_question
    from core.apex_permissions import autonomous_writes_allowed
    if classify(text) == 'status' and not research_question(text):
        return status_text(conn, _chat(conn))
    refs = list(dict.fromkeys(r.upper() for r in _TASK_REF.findall(text)))
    body = re.sub(r'^\s*@(?:apex|hb|hummingbird)[,:]?\s*', '', text, flags=re.I)
    body = _TASK_REF.sub('', body).strip()
    if not _RESUME_EXISTING.fullmatch(body):
        return None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_tasks'").fetchone():
        return 'HB has no bounded task to resume. /tasks shows existing work; no new task was created.'
    candidates = []
    if refs:
        for ref in refs:
            rows = conn.execute('SELECT task_id FROM hb_tasks WHERE conversation_id=? AND '+
                                ('task_id=?' if ref.startswith('T-') else 'step_id=?'), (_chat(conn), ref)).fetchall()
            candidates += [hb_tasks.get(conn,r[0]) for r in rows]
    else:
        candidates = [hb_tasks.get(conn,r[0]) for r in conn.execute(
            "SELECT task_id FROM hb_tasks WHERE conversation_id=? AND step_id IS NOT NULL AND state='active' ORDER BY updated_at DESC", (_chat(conn),))]
    candidates = list({t['task_id']:t for t in candidates}.values())
    if len(candidates) != 1:
        choices = ' · '.join('/continue '+t['task_id'] for t in candidates[:6])
        return ('Choose the existing task: '+choices if choices else 'No matching existing task. /tasks shows the exact task IDs.')
    task = candidates[0]
    if task['state'] == 'completed':
        return f"{task['task_id']} is already completed: {task['title']}. No work was repeated."
    controls = continuation(conn,task)
    if task['state'] in ('paused','cancelled') or held_requests(conn,task) or controls['mode']=='off':
        return f"{task['task_id']} is held ({task['state']}, Continue {controls['mode']}). The hold is preserved; /tasks shows its controls."
    if not task.get('step_id') or not done_when(conn,task)[1] or not hb_task_manager.managed(conn,task):
        return f"{task['task_id']} has no runnable bounded plan and check. No duplicate task was created."
    if not hb_task_manager.dependencies_ready(conn,task):
        return f"{task['task_id']} is waiting for its recorded dependencies. Nothing was queued."
    grant = hb_owner_sessions.for_task(conn,task['task_id'])
    if grant:
        authorised = bool(hb_owner_sessions.for_task(conn,task['task_id'],active=True))
    else:
        # Standing machine write authority plus an explicitly enabled, bounded
        # task is existing authority. The phone line does not create that grant.
        authorised = autonomous_writes_allowed('ghost') and controls.get('revision',0)>0
    if not authorised:
        return f"{task['task_id']} has no active recorded execution grant. Its scope and holds were preserved."
    hb_tasks.bind(conn,_chat(conn),mid,task_id=task['task_id'],kind='phone_control')
    after=[]
    said=hb_commands.handle(conn,_chat(conn),'/continue '+task['task_id'],f'JD via {title}',
                            interpreter=lambda *a:None,after=after)
    conn.commit()
    for callback in after:
        callback()
    return str(said)


def inbound(conn, channel, key, name, text, reply=None, commands=None, enqueue=None):
    """Handle one message. Returns the text to send straight back on that channel."""
    key, text = str(key).lower(), str(text or '').strip()
    who = role(conn, key)
    title = TITLE.get(channel, channel)
    if not text:
        return ''
    if who is None:
        seen = conn.execute("SELECT MAX(at) FROM hb_channel_log WHERE sender=? AND direction='unknown'", (key,)).fetchone()[0]
        if not seen or time.time() - seen > 3600:
            _post(conn, 'hummingbird', f'📱 Someone HB does not know wrote on {title}: {name} ({key}): "{text[:200]}". Nothing was run. '
                                       f'/channels trust {key} lets them ask questions; /channels trust {key} owner gives them your rights.')
            _log(conn, channel, 'unknown', key, None, text)
        return 'HB does not know you yet - its owner has been told.'
    sender = 'user' if who == 'owner' else f'{channel}:{name}'[:40]
    mid = _post(conn, sender, f'📱 {title}: {text}', to='hummingbird', kind='chat')
    _log(conn, channel, 'in', key, mid, text)
    kind = kind_of(text, who == 'owner')
    if kind == 'command':
        verb, *args = text[1:].split()
        verb = verb.lower()
        allowed = SAFE_COMMANDS if who == 'owner' else USER_COMMANDS
        if who != 'owner':   # Practice 212: a guest gets the guest list (/help /about /mine), never the owner's commands
            from core import hb_guest
            said = hb_guest.command(conn, key, verb)
        elif verb not in allowed:
            said = (f'/{verb} needs the screen (it changes the machine, runs as admin or spends money) - use main chat.'
                    if who == 'owner' else 'Enrolled users can ask questions; commands are for the owner.')
        else:
            after = []
            from core import hb_commands
            # Use the same parser/confirmations as main chat. A malformed phone
            # command must not reach run() with missing arguments or bypass /yes.
            said = str(commands(conn, _chat(conn), verb, args, f'JD via {title}', after) if commands else
                       hb_commands.handle(conn, _chat(conn), text, f'JD via {title}',
                                          interpreter=lambda *a: None, after=after))
            conn.commit()  # executor callbacks may open another writer or use the network
            for job in after:
                try:
                    job()
                except Exception:
                    pass
        _log(conn, channel, 'delivered', 'hummingbird', _post(conn, 'hummingbird', said), said)
        return said
    if who == 'owner':
        said = _owner_operating_request(conn, text, mid, title)
        if said is not None:
            _log(conn, channel, 'delivered', 'hummingbird', _post(conn, 'hummingbird', said), said)
            conn.commit()
            return said
    conn.commit()  # the queued reader must see its input, with no transaction held
    JOBS.put({'channel': channel, 'key': key, 'question': text, 'message_id': mid, 'reply': reply or {}})
    return '🔎 APEX is on it - the answer comes here and in main chat (research questions take a few minutes).'


# ------------------------------------------------------------------ answers (answer-only APEX turn with the research tools)
def answer_only(question, history=()):
    """Practice 201: one APEX at a time - a phone answer queues on main chat's own APEX turn lock ('apex-turn') instead of taking the model
    directly (at 22:33 three phone answers made JD's main-chat turn fail with "model busy: queue wait exceeded 1s")."""
    from core.hb_process_lock import ProcessLock, ForegroundWaiter
    turn = ProcessLock('apex-turn')
    with ForegroundWaiter(turn):
        if not turn.acquire(1260):
            return 'APEX was busy for too long; this message was not answered. Please send it again.'
        try:
            return _answer_only(question, history)
        finally:
            turn.release()


def _guest_turn():
    try:
        from core import hb_guest
        return bool(hb_guest.GUEST_TURN.get())
    except Exception:
        return False


_CLAIMS = re.compile(r'\b(?:cancel(?:l?ed)?|paused|resumed|continued|closed|removed|cleared|turned (?:on|off))\b', re.I)


def link_phone_receipts(answer, receipts):
    """Practice 254 (JD 21 Nov 23:5x: "build the tool for phone interactions, they should be linked"): a phone turn's task changes are
    real only with a receipt. Each successful hb_tasks change is listed under the answer (the answer is mirrored to main chat), and an
    answer that claims changes with no successful change behind it is replaced by what actually happened (23:47: APEX claimed five
    cancels and made none)."""
    import json as _json
    changes, failures = [], []
    for r in receipts or []:
        if r.get('tool') != 'hb_tasks':
            continue
        args = r.get('arguments') or {}
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except ValueError:
                args = {}
        action = str(args.get('action') or 'list').lower()
        if action == 'list':
            continue
        line = f"{action} {str(args.get('task_id') or '?').upper()}"
        if r.get('status') == 'succeeded':
            changes.append(line + ' - done')
        else:
            failures.append(line + ' - ' + str(r.get('output') or r.get('status'))[:140])
    if _CLAIMS.search(str(answer or '')) and not changes:
        text = 'No task was changed this turn (no successful hb_tasks change).'
        if failures:
            text += ' Tried: ' + '; '.join(failures)
        return text
    if not changes and not failures:
        return answer
    out = str(answer or '').rstrip() + '\n\nReceipts (hb_tasks): ' + '; '.join(changes + failures)
    return out


def _answer_only(question, history=()):
    """One APEX turn like a main-chat research turn, without task tools: knowledge_search/read and web search. Returns the answer."""
    import time as _t
    from core import llm
    from core.chat_continuity import APEX_AGENT, apex_system_prompt, apex_request_history
    from core.apex_tools import run_apex_tools, response_format_for_turn, TURN_SECONDS
    from core.apex_context import APEX_REASONING_EFFORT, context_tokens, generation_budget, time_budget, prepare_context, budget_receipts
    from core.apex_routing import choose_local_model, use_model
    from core.apex_knowledge import search, read
    from core.hb_agent_tools import ground_answer
    from core.hb_apex_swap import turn_seconds
    from core.hb_learning import research_method
    from core.apex_tools import research_question
    from lib.search.internet import search_provider
    route = choose_local_model(question)
    deadline = _t.monotonic() + turn_seconds(TURN_SECONDS)

    def model(name, msgs):
        remaining = int(deadline - _t.monotonic())
        opts = {'num_ctx': context_tokens(), 'num_predict': min(generation_budget(msgs), time_budget(remaining)),
                'require_complete_output': True, 'reasoning_effort': APEX_REASONING_EFFORT}
        return llm.chat_via_gateway(name, msgs, temperature=0.2, idle_timeout_s=min(60, remaining), absolute_timeout_s=remaining,
                                    queue_timeout_s=60, options=opts, response_format=response_format_for_turn())

    def studio(tool, args):
        if tool == 'knowledge_search':
            return search(args['query'])
        if tool == 'knowledge_read':
            return read(args['document_id'], args.get('offset', 0), args.get('focus'))
        if tool == 'hb_tasks' and not _guest_turn():   # Practice 253 (JD 23:38 from Telegram: 'now do your tasks Apex')
            from core.hb_agent_tools import hb_tasks_tool
            return hb_tasks_tool(args)
        if tool == 'alm_step_get' and not _guest_turn():   # Practice 253b: HB's step check asks for it; JD's phone turns have it
            from core.apex_alm import read_step
            return read_step(args['step_id'])
        if tool == 'gpu_profile' and not _guest_turn():   # Practice 271: JD's phone can have APEX apply his GPU profiles
            from core.hb_agent_tools import gpu_profile_tool
            return gpu_profile_tool(args)
        if tool == 'hb_restart' and not _guest_turn():
            from core.hb_agent_tools import hb_restart_tool
            return hb_restart_tool(args)
        if tool == 'hb_service' and not _guest_turn():
            from core.hb_agent_tools import hb_service_tool
            return hb_service_tool(args)
        if tool == 'hb_media_download' and not _guest_turn():
            from core.hb_agent_tools import hb_media_download_tool
            return hb_media_download_tool(args)
        if tool == 'hb_custom_tool' and not _guest_turn():
            from core.hb_agent_tools import hb_custom_tool_handler
            return hb_custom_tool_handler(args)
        if tool == 'studio_proposal' and not _guest_turn():   # Practice 269: JD granted it explicitly (22 Nov 00:4x)
            from core.hb_proposals import create as propose
            from utils.db._connection import get_connection as _gc2
            from contextlib import closing as _cl2
            with _cl2(_gc2()) as conn, conn:
                return propose(conn, 'apex', args, None)
        if tool == 'ask_instructor' and not _guest_turn():   # Practice 255 (JD 23:51 phone: 'Ask Claude to fix it')
            from core import peer_bridge
            from utils.db._connection import get_connection as _gc
            from contextlib import closing as _cl
            with _cl(_gc()) as conn, conn:
                return peer_bridge.request_help(conn, 2845, args.get('peer') or 'instructor', str(args.get('question') or ''), str(args.get('context') or ''))
        if tool in ('backlog_list', 'runtime_status') and not _guest_turn():   # 253b: read-only status for JD's phone turns
            from core.hb_workflow import call_control
            return call_control(tool, args)
        raise PermissionError(f'{tool} is not attached to a question from a phone')
    row = {**APEX_AGENT, 'model': route.model}
    trusted = [h['content'] for h in history if h.get('role') == 'system' and str(h.get('content', '')).startswith(PHONE_STATE_PREFIX)]
    system = apex_system_prompt(row, recovery=False, proposals=False, web=True)
    system += ('\nThis phone turn answers with its attached tools. Its read-only scope does not describe the execution rights '
               'of an authorised HB worker. Report recorded completion accurately; never call accepted work merely prepared. '
               'A transport receipt does not prove the human has read a message.')
    if trusted:
        system += '\n' + '\n'.join(trusted)
    if not _guest_turn():   # Practice 253: JD (or a partner) on the phone can have APEX run the task list
        system += ('\nFrom JD\'s phone you also have the hb_tasks tool: {"action":"list"} shows open tasks; '
                   '{"action":"continue"|"pause","task_id":"T-..."}; {"action":"cancel","task_id":"T-...","reason":"..."}. '
                   'When JD asks you to work through or clear the task list, call it - do not say it is unavailable. '
                   'You can also run_tests {"tests":["tests/test_x.py"]} and ask_instructor {"peer":"instructor","question":"...","context":"..."} '
                   '(Claude Code or Codex answers in main chat). When JD says test it or ask Claude, do it. '
                   'To change code from the phone, call studio_proposal with title, why, edits [{path, old, new}], new_files and tests - '
                   'HB proves it with the test and JD approves it. '
                   'To restart HB when JD asks, call hb_restart {"scope":"ui","reason":"..."} (or scope "all" for UI + APEX worker). '
                   'To check or restart any HB service (fridays, discord, housekeeping, ollama, swarm-terminal), call hb_service {"action":"list"|"status"|"start"|"stop"|"restart","service":"..."}. '
                   'To download a YouTube/media video or audio episode for JD, call hb_media_download {"query":"...","format":"video"|"audio"}.')
    try:   # Practice 213 (JD 21 Nov: "make it APEX opinion based on the notes without giving direct access to the notes")
        from core import hb_guest
        if hb_guest.GUEST_TURN.get():
            system += '\n' + hb_guest.ANSWER_RULE
    except Exception:
        pass
    note = 'HB note: a channel user asks from their phone. Answer plainly.'
    if research_question(question):
        note += ' ' + research_method()
    msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': note}]
    # Fresh research drops old chat. Trusted current records belong in system above,
    # so that deliberate history reset cannot discard the task's actual outcome.
    chat_history = [h for h in history if h.get('role') in ('user', 'assistant')]
    msgs += apex_request_history(chat_history, question)
    with use_model(route):
        from core.apex_test_runner import run_tests as _run_tests   # Practice 255: JD's phone turns run tests; guests never
        answer, _tokens, receipts = run_apex_tools(model, msgs, lambda: True, lambda r: None, studio_handler=studio,
                                                   test_handler=None if _guest_turn() else _run_tests,
                                                   web_handler=lambda a: search_provider(a['query'], a['provider']),
                                                   prepare_messages=lambda cur: prepare_context(cur),
                                                   prepare_receipts=lambda cur, b: budget_receipts(cur, b))
    return link_phone_receipts(ground_answer(answer, receipts), receipts)   # Practice 254


def _history(conn, before_id=None, limit=8, *, exclude_id=None):
    if exclude_id is not None:
        rows = conn.execute(
            "SELECT from_agent, content FROM messages WHERE conversation_id=? AND id<>? ORDER BY id DESC LIMIT ?",
            (_chat(conn), exclude_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT from_agent, content FROM messages WHERE conversation_id=? AND id<? ORDER BY id DESC LIMIT ?",
            (_chat(conn), before_id, limit),
        ).fetchall()
    return [{'role': 'user' if f in ('user', 'ghost') else 'assistant', 'content': str(c)[:1500]} for f, c in reversed(rows)]



PHONE_STATE_PREFIX = 'HB authoritative task snapshot (current records, not new permission): '
_TASK_REF = re.compile(r'\b[TS]-[0-9A-F]{10,12}\b', re.I)
_TASK_TOPIC = re.compile(r'\b(?:tasks?|queue|backlog|approval|approve|permission|authori[sz]ed|write access|prepared|completed?|finished|repair|fix|proceed|continue|status|progress)\b', re.I)


def _owner_task_state(conn, job):
    """Snapshot linked/cited work and current operational results before releasing DB.

    Only the verified owner receives this context; it never establishes authority.
    An unrelated fresh research question receives no operational records.
    """
    from core import hb_tasks, hb_change_sets
    question = str(job.get('question') or '')
    refs = list(dict.fromkeys(r.upper() for r in _TASK_REF.findall(question)))[:6]
    if not refs and not _TASK_TOPIC.search(question):
        return ''
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_tasks'").fetchone():
        return ''
    tids = []
    for ref in refs:
        if ref.startswith('T-'):
            row = conn.execute('SELECT task_id FROM hb_tasks WHERE task_id=? AND conversation_id=?', (ref, _chat(conn))).fetchone()
        else:
            row = conn.execute('SELECT task_id FROM hb_tasks WHERE step_id=? AND conversation_id=? ORDER BY updated_at DESC LIMIT 1', (ref, _chat(conn))).fetchone()
        if row:
            tids.append(row[0])
    if not refs:
        linked = hb_tasks.for_message(conn, job['message_id'])
        if linked:
            tids.append(linked['task_id'])
        tids += [r[0] for r in conn.execute("SELECT task_id FROM hb_tasks WHERE conversation_id=? AND step_id IS NOT NULL ORDER BY updated_at DESC LIMIT 5", (_chat(conn),))]
    records = []
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for tid in list(dict.fromkeys(tids))[:6]:
        task = hb_tasks.get(conn, tid)
        record = {k:task.get(k) for k in ('task_id', 'title', 'state', 'project_id', 'step_id')}
        if task.get('step_id') and 'project_steps' in tables:
            step = conn.execute('SELECT status FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()
            record['step_status'] = step[0] if step else 'missing'
        if task.get('step_id'):
            receipt = hb_change_sets.record(task['step_id'])
            record['change_set'] = ({k:receipt.get(k) for k in ('files','commit','reverted')}
                                    if receipt and receipt.get('commit') else receipt)
        latest = conn.execute("SELECT event_id,payload FROM hb_task_events WHERE task_id=? AND kind='test_result' ORDER BY event_id DESC LIMIT 1", (tid,)).fetchone()
        if latest:
            result = json.loads(latest[1])
            record['latest_test'] = {'event_id':latest[0], **{k:result.get(k) for k in ('alm_run_id','alm_run_status','summary','exit_code','tests')}}
        accepted = conn.execute("SELECT event_id,agent,kind FROM hb_task_events WHERE task_id=? AND kind IN ('accepted','owner_accepted') ORDER BY event_id DESC LIMIT 1", (tid,)).fetchone()
        if accepted:
            record['acceptance'] = dict(zip(('event_id','agent','kind'), accepted))
        records.append(record)
    return PHONE_STATE_PREFIX + json.dumps({'at':time.time(),'tasks':records}, ensure_ascii=True) if records else ''


def _work_task(job):
    """Practice 257: the owner's phone message HB bound to a real work task (not a chat thread), or None. That task's turns have
    the write and test tools; an answer-only phone turn does not, and used to reply 'I don't have permission' while the task ran."""
    try:
        from core import hb_tasks
        from core.hb_owner_intent import is_chat_task
        conn = _connect()
        try:
            task = hb_tasks.for_message(conn, job['message_id'])
        finally:
            conn.close()
        if task and task.get('state') not in ('completed', 'cancelled') and not is_chat_task(task):
            return task
    except Exception:
        pass
    return None


def work_one(job, connect=_connect, answer=answer_only, mail=None):
    """Answer one queued question: post it in main chat as APEX (the mirror sends it on); email it back when it came by email."""
    conn = connect()
    try:
        who = role(conn, job['key'])
        if who not in ('owner', 'user'):
            return ''  # enrollment was revoked while this answer waited in the queue
        history = _history(conn, exclude_id=job['message_id']) if who == 'owner' else []
        if who == 'owner':
            try:
                from core import hb_carry_forward as _cf
                cf_card = _cf.card(conn, _chat(conn))
                if cf_card:
                    history.append({'role': 'system', 'content': PHONE_STATE_PREFIX + cf_card})
            except Exception:
                pass
        state = _owner_task_state(conn, job) if who == 'owner' else ''
        if state:
            history.append({'role':'system', 'content':state})
    finally:
        conn.close()
    from core import hb_guest
    guest = hb_guest.GUEST_TURN.set(who != 'owner')   # Practice 213: a guest gets APEX's opinion, not the notes
    try:
        work = _work_task(job) if who == 'owner' else None   # Practice 257 (JD 23:57: 'Build it Apex' got 'I don't have permission')
        text = (f"▶ On it: {work['task_id']} runs as an HB task with APEX's full tools (read, write, tests). Progress posts here."
                if work else answer(job['question'], history))
    except Exception as exc:
        text = f'APEX could not answer this one ({type(exc).__name__}: {str(exc)[:160]}). It is in main chat; ask again or at the screen.'
    finally:
        hb_guest.GUEST_TURN.reset(guest)
    conn = connect()
    try:
        if role(conn, job['key']) != who:
            return ''  # do not deliver owner-derived context after a trust change
        mid = _post(conn, 'apex', text)
        direct = job['channel'] == 'telegram' and who != 'owner'
        _log(conn, job['channel'], 'out', 'apex', mid, text)
        if who == 'owner':
            try:
                from core import hb_carry_forward as _cf
                _cf.record(conn, _chat(conn), job['question'], text, [])
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
    if direct:                                         # enrolled users never get the owner's mirror - their answer goes to them
        for part in chunks(f'APEX: {plain(text)}'):
            telegram_send(job['key'].split(':', 1)[1], part)
    if job['channel'] == 'email' and job['reply'].get('to'):
        try:
            if mail is None:
                from lib.email.email_handler import send_reply as mail
            subject = job['reply'].get('subject') or 'your question'
            mail(job['reply']['to'], subject if subject.lower().startswith('re:') else 'Re: ' + subject, text,
                 original_message_id=job['reply'].get('message_id'), sender_name='Hummingbird')
        except Exception:
            pass
    return text


def _worker():
    while True:
        job = JOBS.get()
        try:
            work_one(job)
        except Exception:
            pass


# ------------------------------------------------------------------ outbound mirror
def plain(text):
    text = re.sub(r'\[([^\]]+)\]\((?:[^)]+)\)', r'\1', str(text or ''))       # markdown links -> their text
    text = re.sub(r'\*\*|__|`{1,3}', '', text)
    return text.strip()


def worth_mirroring(sender, content, kind):
    content = str(content or '').strip()
    if not content or kind in ('tool_result', 'system'):
        return False
    if content.startswith(('[tool:', '{', '[Backend', 'BACKEND ')):
        return False
    return True


def chunks(text, size=TELEGRAM_CHUNK, most=3):
    parts = [text[i:i + size] for i in range(0, len(text), size)] or ['']
    if len(parts) > most:
        parts = parts[:most]
        parts[-1] += '\n… (the rest is in main chat)'
    return parts


def _needs_entries(conn, seen):
    """New Needs-you items as one message each, with the reply commands that settle them."""
    try:
        from core.hb_commands import waiting_items
        items = waiting_items(conn)
    except Exception:
        return [], seen
    out, keys = [], set(seen)
    for i in items:
        if i.get('info') or i.get('key') in keys:
            continue
        keys.add(i.get('key'))
        replies = []
        if i.get('kind') == 'accept' and i.get('step_id'):
            replies += [f"/accept {i['step_id']}", f"/reject {i['step_id']} <reason>"]
        if i.get('task_id'):
            replies += [f"/continue {i['task_id']}", f"/cancel {i['task_id']}"]
        replies += [a['command'] for a in i.get('actions') or [] if a.get('command')]
        out.append((i.get('key'), f"⚑ Needs you: {i.get('label', '')}\n{str(i.get('why') or i.get('title') or '')[:300]}" +
                    (f"\nReply: {' · '.join(dict.fromkeys(replies))}" if replies else '')))
    return out, sorted(k for k in keys if k)


def needs_lines(conn, seen):
    entries, keys = _needs_entries(conn, seen)
    return [text for _, text in entries], keys


def mirror_once(conn, send):
    """Durable, ordered delivery. A failed chunk stays pending; no DB lock spans a send.

    A transport timeout after remote acceptance can still duplicate the unacknowledged
    chunk. Telegram supplies no idempotency key, so this is at-least-once delivery.
    """
    from core.hb_process_lock import ProcessLock
    lock = ProcessLock('channel-mirror')
    if not lock.acquire(0):
        return 0
    try:
        return _mirror_locked(conn, send)
    finally:
        lock.release()


def _mirror_locked(conn, send):
    ensure(conn)
    chat = _chat(conn)
    last = cursor(conn, 'mirror_last_id')
    if last is None:
        top = conn.execute('SELECT COALESCE(MAX(id),0) FROM messages WHERE conversation_id=?', (chat,)).fetchone()[0]
        set_cursor(conn, 'mirror_last_id', top)
        set_cursor(conn, 'needs_seen', json.dumps(needs_lines(conn, [])[1]))
        conn.commit()
        return 0
    pending = json.loads(cursor(conn, 'mirror_pending', '[]'))
    seen = set(json.loads(cursor(conn, 'needs_seen', '[]')))
    if not pending:
        echoes = {r[0] for r in conn.execute("SELECT message_id FROM hb_channel_log WHERE direction IN ('in','delivered') AND message_id IS NOT NULL")}
        rows = conn.execute('SELECT id, from_agent, content, message_type FROM messages WHERE conversation_id=? AND id>? '
                            'ORDER BY id LIMIT 30', (chat, int(last))).fetchall()
        for mid, sender, content, kind in rows:
            parts = (chunks(f'{SENDER_LABEL.get(sender, sender)}: {plain(content)}')
                     if mid not in echoes and worth_mirroring(sender, content, kind) else [])
            pending.append({'message_id': mid, 'parts': parts, 'next': 0})
        entries, _ = _needs_entries(conn, seen)
        pending += [{'needs_key': key, 'parts': chunks(text), 'next': 0} for key, text in entries]
        set_cursor(conn, 'mirror_pending', json.dumps(pending))
    # Practice 196 remains a hard boundary: release transactions BEFORE network I/O.
    conn.commit()
    sent = 0
    while pending:
        item = pending[0]
        while item['next'] < len(item['parts']):
            try:
                ok = send(item['parts'][item['next']])
            except Exception:
                ok = False
            if not ok:
                return sent
            sent += 1
            item['next'] += 1
            set_cursor(conn, 'mirror_pending', json.dumps(pending))
            conn.commit()
        if 'message_id' in item:
            set_cursor(conn, 'mirror_last_id', item['message_id'])
        if item.get('needs_key'):
            seen.add(item['needs_key'])
            set_cursor(conn, 'needs_seen', json.dumps(sorted(seen)))
        pending.pop(0)
        set_cursor(conn, 'mirror_pending', json.dumps(pending))
        conn.commit()
    return sent


# ------------------------------------------------------------------ Telegram
def _telegram(method, payload=None, timeout=35):
    from utils.config import TELEGRAM_TOKEN
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}'
    data = urllib.parse.urlencode(payload or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data), timeout=timeout) as r:
        return json.loads(r.read())


def telegram_buttons(text):
    """Build native Telegram inline keyboard buttons bound to exact step/task IDs found in text."""
    body = str(text or '')
    steps = list(dict.fromkeys(m.upper() for m in re.findall(r'/accept\s+(S-[0-9A-F]{10})\b', body, re.I)))
    pauses = list(dict.fromkeys(m.upper() for m in re.findall(r'/pause\s+(T-[0-9A-F]{12})\b', body, re.I)))
    rows = []
    for idx, sid in enumerate(steps[:3]):
        row = [{'text': f'🌺 Approve {sid}', 'callback_data': f'/accept {sid}'}]
        if idx < len(pauses):
            row.append({'text': '⏸ Hold', 'callback_data': f'/pause {pauses[idx]}'})
        rows.append(row)
    return {'inline_keyboard': rows} if rows else None


def telegram_send(chat_id, text, call=_telegram, buttons=None):
    try:
        payload = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': 'true'}
        markup = buttons if buttons is not None else telegram_buttons(text)
        if markup:
            payload['reply_markup'] = json.dumps(markup)
        return bool(call('sendMessage', payload, 20).get('ok'))
    except Exception:
        return False


def telegram_poll_once(conn, call=_telegram, handle=inbound):
    """One long-poll of Telegram: handles both text messages and native inline button callback_query taps."""
    offset = int(cursor(conn, 'telegram_offset', 0) or 0)
    got = call('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': json.dumps(['message', 'callback_query'])}, 35)
    for upd in got.get('result', []):
        set_cursor(conn, 'telegram_offset', upd['update_id'] + 1)
        cb = upd.get('callback_query') or {}
        if cb:
            cb_id = cb.get('id')
            msg = cb.get('message') or {}
            chat_id = (msg.get('chat') or {}).get('id')
            data = str(cb.get('data') or '').strip()
            frm = cb.get('from') or {}
            name = frm.get('username') or frm.get('first_name') or str(chat_id)
            if cb_id:
                try:
                    call('answerCallbackQuery', {'callback_query_id': cb_id, 'text': f'Running {data[:40]}...'}, 10)
                except Exception:
                    pass
            if chat_id is not None and data:
                said = handle(conn, 'telegram', f'telegram:{chat_id}', name, data)
                conn.commit()
                if said:
                    telegram_send(chat_id, said, call)
            continue
        msg = upd.get('message') or {}
        chat_id, text = (msg.get('chat') or {}).get('id'), msg.get('text') or msg.get('caption') or ''
        if chat_id is None:
            continue
        if not text:
            text = '(a file or photo - HB cannot read those from Telegram yet; send it by email or put it in ~/HB-Inbox)'
        frm = msg.get('from') or {}
        name = frm.get('username') or frm.get('first_name') or str(chat_id)
        said = handle(conn, 'telegram', f'telegram:{chat_id}', name, text)
        conn.commit()
        if said:
            telegram_send(chat_id, said, call)
    conn.commit()
    return len(got.get('result', []))


def _telegram_loop():
    import logging
    log = logging.getLogger('hb.channels')
    while True:
        try:
            conn = _connect()
            try:
                telegram_poll_once(conn)
            finally:
                conn.close()
        except Exception as exc:
            log.warning('Telegram poll failed: %s', exc)
            time.sleep(15)


def _mirror_loop(every=3):
    while True:
        try:
            conn = _connect()
            try:
                owners = [k.split(':', 1)[1] for k in owner_keys(conn, 'telegram')]
                if owners:
                    mirror_once(conn, lambda text: all(telegram_send(o, text) for o in owners))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        time.sleep(every)


# ------------------------------------------------------------------ email (called by core/hb_email_intake.ingest)
def verified(msg):
    """Gmail's Authentication-Results for this message show a DKIM or SPF pass (a forged From: fails both)."""
    results = ' '.join(str(v) for v in (msg.get_all('Authentication-Results') or []))
    return bool(re.search(r'\b(dkim|spf)=pass\b', results, re.I))


def request_text(subject, body):
    lines = []
    for line in str(body or '').splitlines():
        if re.match(r'^\s*On .+wrote:\s*$', line) or line.startswith('>') or line.strip() in ('--', '-- '):
            break
        lines.append(line)
    text = '\n'.join(lines).strip()
    subject = str(subject or '').strip()
    if subject.startswith('/'):
        return subject
    if subject and subject.lower() not in ('(no subject)', 're:', 'fw:') and subject.lower() not in text.lower():
        text = (subject + '\n' + text).strip()
    return text


def from_email(conn, msg, sender, subject, body, message_id, handle=inbound, has_files=False, mail=None):
    sender = str(sender or '').lower()
    who = role(conn, 'email:' + sender)
    via_trusted_only = False
    if who is None:
        try:
            if conn.execute('SELECT 1 FROM hb_email_trusted WHERE lower(address)=?', (sender,)).fetchone():
                who = 'owner'
                via_trusted_only = True
        except Exception:
            pass
    if any(own in sender for own in HB_OWN) or who is None:
        return None
    text = request_text(subject, body)
    if not text:
        return None
    if has_files and len(str(body or '').split()) < 5 and not (text.startswith('/') or '?' in text or re.match(r'^\s*hb\b', text, re.I)):
        return None                                    # a file with a brief cover note ('here you go') is data (kept in KC)
    if not verified(msg):
        if not via_trusted_only:
            _post(conn, 'hummingbird', f'📧 The email from {sender} ("{str(subject)[:80]}") did not pass Gmail\'s sender check (DKIM/SPF), so HB '
                                       'kept it as data only and ran nothing from it.')
        return 'unverified'
    kind = kind_of(text, who == 'owner')
    said = handle(conn, 'email', 'email:' + sender, sender, text, {'to': sender, 'subject': subject, 'message_id': message_id})
    if said and kind != 'question':                    # a question's answer is emailed when APEX has it
        try:
            if mail is None:
                from lib.email.email_handler import send_reply as mail
            subj = str(subject or 'HB')
            mail(sender, subj if subj.lower().startswith('re:') else 'Re: ' + subj, said, original_message_id=message_id, sender_name='Hummingbird')
        except Exception:
            pass
    return said


# ------------------------------------------------------------------ status / command / tick
def status(conn):
    ensure(conn)
    ids = conn.execute('SELECT role, COUNT(*) FROM hb_channel_identities GROUP BY role').fetchall()
    last_in = conn.execute("SELECT channel, MAX(at) FROM hb_channel_log WHERE direction='in' GROUP BY channel").fetchall()
    return {'telegram': cursor(conn, 'telegram_state', 'not started'), 'discord': cursor(conn, 'discord_state', 'not started'),
            'email': 'through the email intake (requests from verified owner mail)', 'identities': dict(ids),
            'last_in': {c: time.strftime('%d %b %H:%M', time.localtime(a)) for c, a in last_in}}


def command(conn, args, actor):
    """/channels | /channels trust <key> [owner] | /channels untrust <key>"""
    if not args:
        s = status(conn)
        return (f"Channels: Telegram {s['telegram']}; Discord {s['discord']}; email {s['email']}. Identities: {s['identities']}. "
                f"Last messages in: {s['last_in'] or 'none yet'}. /channels trust <telegram:id|discord:id|email:address> [owner] enrolls someone.")
    if args[0].lower() in ('trust', 'untrust') and len(args) >= 2:
        key = args[1].lower()
        if not re.fullmatch(r'(telegram|discord):\d+|email:[^@\s]+@[^@\s]+', key):
            return 'Use telegram:<chat id>, discord:<user id> or email:<address>.'
        ensure(conn)
        if args[0].lower() == 'untrust':
            conn.execute('DELETE FROM hb_channel_identities WHERE key=?', (key,))
            return f'{key} can no longer talk to HB.'
        who = 'owner' if len(args) > 2 and args[2].lower() == 'owner' else 'user'
        conn.execute('INSERT OR REPLACE INTO hb_channel_identities VALUES (?,?,?,?,?)', (key, who, key, actor, time.time()))
        import os
        if who == 'user' and key.startswith('telegram:') and (WELCOME_IN_TESTS or not os.environ.get('PYTEST_CURRENT_TEST')):   # Practice 212: guest welcome
            from core import hb_guest
            threading.Thread(target=telegram_send, args=(key.split(':', 1)[1], hb_guest.welcome()), name='hb-guest-welcome', daemon=True).start()
            return f'{key} is enrolled as user - a guest (questions only; he sees only his own questions and answers). HB sent him a welcome.'
        return f'{key} is enrolled as {who} ({"your rights" if who == "owner" else "questions only"}).'
    return 'Use /channels, /channels trust <key> [owner] or /channels untrust <key>.'


_CHECKED = {'at': 0}


def tick(conn, now=None, start=True):
    """From HB's coordinator: identities once, then the Telegram poller, the mirror and the answer worker (once per process)."""
    now = now or time.time()
    if not _STARTED.get('seeded'):
        seed(conn)
        _STARTED['seeded'] = True
    if _STARTED['threads'] or not start or now - _CHECKED['at'] < 300:
        return False
    _CHECKED['at'] = now
    try:
        ok = bool(_telegram('getMe', timeout=10).get('ok'))
    except Exception as exc:
        set_cursor(conn, 'telegram_state', f'not reachable ({type(exc).__name__})')
        return False
    set_cursor(conn, 'telegram_state', 'connected' if ok else 'token rejected')
    try:
        from utils.config import DISCORD_TOKEN
        req = urllib.request.Request('https://discord.com/api/v10/users/@me', headers={'Authorization': 'Bot ' + str(DISCORD_TOKEN),
                                                                                       'User-Agent': 'Hummingbird (local)'})
        urllib.request.urlopen(req, timeout=10)
        set_cursor(conn, 'discord_state', 'token works (Discord relay not built yet)')
    except Exception as exc:
        set_cursor(conn, 'discord_state', 'token rejected - JD resets it in the Discord Developer Portal' if '401' in str(exc) else f'not reachable ({type(exc).__name__})')
    if not ok:
        return False
    for target, name in ((_telegram_loop, 'hb-telegram'), (_mirror_loop, 'hb-channel-mirror'), (_worker, 'hb-channel-answers')):
        threading.Thread(target=target, name=name, daemon=True).start()
    _STARTED['threads'] = True
    return True
