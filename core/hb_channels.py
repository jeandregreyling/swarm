"""HB channels (plan 20 Nov 3/8; owner: "Telegram and Discord need to be wired back in so I can use either email, Discord or Telegram to
talk to the system if I'm away from the screen ... duplicating the main chat into those apps and show me what is needed from me to continue
working on open tasks ... listening and executing when I send a request, or any other user registered and enrolled in the system").

The old bots (fridays/telegram_bot.py, fridays/discord_bot.py, core/pipeline/listener.py) still ran the pre-HB "Fridays" debate pipeline
and their services pointed at the retired /home/seven/swarm; they have not run since April. This module puts the channels into HB:

  inbound(conn, channel, key, name, text, reply)  one message from Telegram / email / Discord, from a known identity:
      /command    the safe list (SAFE_COMMANDS) runs through hb_commands like a main-chat command, as "JD via Telegram";
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
                 'consult', 'choose', 'pick', 'note', 'notes', 'email', 'channels'}
USER_COMMANDS = {'help'}
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
    if not is_owner or QUESTION.search(text):
        return 'question'
    return 'request'


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
        if verb not in allowed:
            said = (f'/{verb} needs the screen (it changes the machine, runs as admin or spends money) - use main chat.'
                    if who == 'owner' else 'Enrolled users can ask questions; commands are for the owner.')
        else:
            after = []
            from core import hb_commands
            said = str((commands or hb_commands.run)(conn, _chat(conn), verb, args, f'JD via {title}', after))
            for job in after:
                try:
                    job()
                except Exception:
                    pass
        _log(conn, channel, 'delivered', 'hummingbird', _post(conn, 'hummingbird', said), said)
        return said
    if kind == 'request':
        from core import peer_bridge
        ids = (enqueue or peer_bridge.enqueue)(conn, _chat(conn), mid, text, ['apex'], sender='user')
        said = f'📌 APEX takes this as a task (request {ids[0] if ids else "?"}); progress and questions come here and in main chat.'
        _log(conn, channel, 'out', 'hummingbird', None, said)
        return said
    JOBS.put({'channel': channel, 'key': key, 'question': text, 'message_id': mid, 'reply': reply or {}})
    return '🔎 APEX is on it - the answer comes here and in main chat (research questions take a few minutes).'


# ------------------------------------------------------------------ answers (answer-only APEX turn with the research tools)
def answer_only(question, history=()):
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
        raise PermissionError(f'{tool} is not attached to a question from a phone')
    row = {**APEX_AGENT, 'model': route.model}
    msgs = [{'role': 'system', 'content': apex_system_prompt(row, recovery=False, proposals=False, web=True)},
            {'role': 'user', 'content': 'HB note: JD asks this from his phone (away from the screen). Answer plainly; ' + research_method()}]
    msgs += apex_request_history(list(history), question)
    with use_model(route):
        answer, _tokens, receipts = run_apex_tools(model, msgs, lambda: True, lambda r: None, studio_handler=studio,
                                                   web_handler=lambda a: search_provider(a['query'], a['provider']),
                                                   prepare_messages=lambda cur: prepare_context(cur),
                                                   prepare_receipts=lambda cur, b: budget_receipts(cur, b))
    return ground_answer(answer, receipts)


def _history(conn, before_id, limit=8):
    rows = conn.execute("SELECT from_agent, content FROM messages WHERE conversation_id=? AND id<? ORDER BY id DESC LIMIT ?",
                        (_chat(conn), before_id, limit)).fetchall()
    return [{'role': 'user' if f in ('user', 'ghost') else 'assistant', 'content': str(c)[:1500]} for f, c in reversed(rows)]


def work_one(job, connect=_connect, answer=answer_only, mail=None):
    """Answer one queued question: post it in main chat as APEX (the mirror sends it on); email it back when it came by email."""
    conn = connect()
    try:
        history = _history(conn, job['message_id'])
    finally:
        conn.close()
    try:
        text = answer(job['question'], history)
    except Exception as exc:
        text = f'APEX could not answer this one ({type(exc).__name__}: {str(exc)[:160]}). It is in main chat; ask again or at the screen.'
    conn = connect()
    try:
        mid = _post(conn, 'apex', text)
        direct = job['channel'] == 'telegram' and role(conn, job['key']) != 'owner'
        _log(conn, job['channel'], 'out', 'apex', mid, text)
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


def needs_lines(conn, seen):
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
        out.append(f"⚑ Needs you: {i.get('label', '')}\n{str(i.get('why') or i.get('title') or '')[:300]}" +
                   (f"\nReply: {' · '.join(dict.fromkeys(replies))}" if replies else ''))
    return out, sorted(k for k in keys if k)


def mirror_once(conn, send):
    """Send new main-chat posts and Needs-you items to the owner's Telegram. Returns how many messages were sent."""
    ensure(conn)
    chat = _chat(conn)
    top = conn.execute('SELECT COALESCE(MAX(id),0) FROM messages WHERE conversation_id=?', (chat,)).fetchone()[0]
    last = cursor(conn, 'mirror_last_id')
    if last is None:                                    # first start: from now on, not the whole history
        set_cursor(conn, 'mirror_last_id', top)
        set_cursor(conn, 'needs_seen', json.dumps(needs_lines(conn, [])[1]))
        return 0
    echoes = {r[0] for r in conn.execute("SELECT message_id FROM hb_channel_log WHERE direction IN ('in','delivered') AND message_id IS NOT NULL")}
    sent = 0
    for mid, sender, content, kind in conn.execute('SELECT id, from_agent, content, message_type FROM messages WHERE conversation_id=? AND id>? '
                                                   'ORDER BY id LIMIT 30', (chat, int(last))).fetchall():
        set_cursor(conn, 'mirror_last_id', mid)
        if mid in echoes or not worth_mirroring(sender, content, kind):
            continue
        label = SENDER_LABEL.get(sender, sender)
        for part in chunks(f'{label}: {plain(content)}'):
            if send(part):
                sent += 1
    lines, keys = needs_lines(conn, json.loads(cursor(conn, 'needs_seen', '[]')))
    set_cursor(conn, 'needs_seen', json.dumps(keys))
    for line in lines:
        if send(line):
            sent += 1
    return sent


# ------------------------------------------------------------------ Telegram
def _telegram(method, payload=None, timeout=35):
    from utils.config import TELEGRAM_TOKEN
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}'
    data = urllib.parse.urlencode(payload or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data), timeout=timeout) as r:
        return json.loads(r.read())


def telegram_send(chat_id, text, call=_telegram):
    try:
        return bool(call('sendMessage', {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': 'true'}, 20).get('ok'))
    except Exception:
        return False


def telegram_poll_once(conn, call=_telegram, handle=inbound):
    """One long-poll of Telegram: each text message goes through inbound; the immediate answer goes back to that chat."""
    offset = int(cursor(conn, 'telegram_offset', 0) or 0)
    got = call('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': json.dumps(['message'])}, 35)
    for upd in got.get('result', []):
        set_cursor(conn, 'telegram_offset', upd['update_id'] + 1)
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
    if any(own in sender for own in HB_OWN) or who is None:
        return None
    text = request_text(subject, body)
    if not text:
        return None
    if has_files and not (text.startswith('/') or '?' in text or re.match(r'^\s*hb\b', text, re.I)):
        return None                                    # a file with a short note is data (the intake keeps it in the KC)
    if not verified(msg):
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
