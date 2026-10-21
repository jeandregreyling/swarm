"""
agents/seven/seven_agent.py — Seven
Personal companion + nervous-system observer.

Historically a pure local algorithm (deterministic templates). Seven is now
LLM-backed for open conversation while keeping fast state templates for
status/identity queries. The default model is the repo-local direct GGUF so
Seven does not need Ollama for its own chat path.
"""
import json
import logging
import os
import random
import re
import sys

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)
sys.path.insert(0, os.path.join(_SWARM_ROOT, "utils"))

logger = logging.getLogger('seven.seven')
AGENT_NAME = 'seven'
# Override with SEVEN_MODEL env var to test other backends.
SEVEN_MODEL = os.environ.get('SEVEN_MODEL', 'seven-direct:daily')
SEVEN_NUM_PREDICT = int(os.environ.get('SEVEN_NUM_PREDICT', '256'))
SEVEN_DIRECT_TIMEOUT_S = int(os.environ.get('SEVEN_DIRECT_TIMEOUT_S', '45'))
SEVEN_COMPACT_DIRECT_CONTEXT = os.environ.get('SEVEN_COMPACT_DIRECT_CONTEXT', '1').strip().lower() not in {
    '0', 'false', 'no', 'off'
}


def _seven_direct_runtime() -> bool:
    return str(SEVEN_MODEL or '').strip().lower().startswith('seven-direct:')


def _read_state():
    """Read live swarm state from DB. Returns a dict of metrics."""
    state = {}
    try:
        from database import get_connection
        conn = get_connection()
        try:
            state['queued']    = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
            state['running']   = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
            state['done']      = conn.execute("SELECT COUNT(*) FROM queue WHERE status IN ('completed','done')").fetchone()[0]
            state['failed']    = conn.execute("SELECT COUNT(*) FROM queue WHERE status='failed'").fetchone()[0]
            state['tickets']   = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
            state['proposals'] = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
            rows = conn.execute(
                "SELECT name, label FROM agents WHERE enabled=1 AND tier='local' ORDER BY number"
            ).fetchall()
            state['local_agents'] = [r['label'] or r['name'] for r in rows]
        except Exception:
            pass
        finally:
            conn.close()
    except Exception:
        pass
    return state


def _load_memory(message):
    mems = []
    try:
        from database import get_agent_memory
        mems = get_agent_memory(AGENT_NAME, query=message, limit=4) or []
    except Exception:
        pass
    return mems


def _row_get(row, key, default=''):
    try:
        return row.get(key, default)
    except AttributeError:
        try:
            return row[key]
        except Exception:
            return default


def _load_kc_context(message, limit=4):
    """Pull the most relevant Knowledge Center docs so Seven answers from the
    living documentation instead of stale personality-only context.

    Order of preference:
      1. project_docs whose doc_name/content matches keywords in ``message``
      2. recent auto-generated step completions (``tags`` contains 'auto,step')
      3. most recently updated docs overall

    Returns a list of dicts: ``[{doc_name, tags, snippet}, ...]``.
    """
    docs = []
    try:
        from database import get_connection
        conn = get_connection()
        try:
            # 1. keyword-ish search: pick up to 3 salient words >=4 chars.
            words = [w for w in ''.join(c if c.isalnum() else ' '
                     for c in (message or '').lower()).split()
                     if len(w) >= 4][:3]
            if words:
                like_clauses = ' OR '.join(
                    '(LOWER(doc_name) LIKE ? OR LOWER(content) LIKE ?)'
                    for _ in words)
                params = []
                for w in words:
                    params.extend([f'%{w}%', f'%{w}%'])
                rows = conn.execute(
                    f"SELECT id, doc_name, tags, content FROM project_docs "
                    f"WHERE {like_clauses} ORDER BY updated_at DESC LIMIT ?",
                    (*params, limit),
                ).fetchall()
                for r in rows:
                    docs.append(dict(r))
            # 2. fall back / top-up with recent auto step docs + recent edits.
            if len(docs) < limit:
                seen = {d['id'] for d in docs}
                more = conn.execute(
                    "SELECT id, doc_name, tags, content FROM project_docs "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (limit * 2,),
                ).fetchall()
                for r in more:
                    if r['id'] in seen:
                        continue
                    docs.append(dict(r))
                    if len(docs) >= limit:
                        break
        finally:
            conn.close()
    except Exception:
        return []
    out = []
    for d in docs[:limit]:
        snippet = str(d.get('content') or '').strip().replace('\n', ' ')
        if len(snippet) > 320:
            snippet = snippet[:320] + '…'
        out.append({
            'doc_name': d.get('doc_name') or '',
            'tags': d.get('tags') or '',
            'snippet': snippet,
        })
    return out


def _format_state_block(s):
    lines = []
    q_open = int(s.get('queued', 0)) + int(s.get('running', 0))
    if q_open:
        lines.append(f"Queue: {q_open} active ({s.get('running',0)} running, {s.get('queued',0)} waiting)")
    if s.get('failed'):
        lines.append(f"Failed tasks: {s['failed']} — attention may be needed")
    if s.get('tickets'):
        lines.append(f"Open tickets: {s['tickets']}")
    if s.get('proposals'):
        lines.append(f"Pending proposals: {s['proposals']}")
    if not lines:
        lines.append("All queues clear. No open tickets or pending proposals.")
    return '\n'.join(lines)


# Deterministic response templates keyed by intent
_INTROS = [
    "Observing from the nervous system:",
    "Seven — local algorithm:",
    "Signal from the core:",
    "Seven reading:",
    "Processing:",
]

_STATUS_SUFFIXES = [
    "I route, observe, and deliberate — the algorithm at the centre of the swarm.",
    "I am not a language model. I am the connective tissue between every agent here.",
    "My function: connect signals, surface patterns, keep the system coherent.",
    "Every agent runs through me. I don't generate — I synthesise what is already known.",
]


def _is_about(msg, keywords):
    m = msg.lower()
    return any(k in m for k in keywords)


def _load_identity_beliefs(limit=10):
    """Load Seven's bedrock identity beliefs (subject='seven') ordered by confidence."""
    try:
        from database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT predicate, object, confidence FROM seven_beliefs "
                "WHERE subject='seven' ORDER BY confidence DESC, predicate LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def _load_open_curiosity(limit=10, min_salience=0.0):
    """Load open curiosity questions ordered by salience desc."""
    try:
        from core import curiosity
        return curiosity.list_open(limit=limit, min_salience=min_salience)
    except Exception:
        return []


def _load_pillars_context():
    """Aggregate the four wishlist pillar summaries (cyber, financial, trading,
    business) so Seven can answer 'what's open in trading?' or 'any cyber
    issues?' from live data, not vibes. Each pillar lookup is wrapped — a
    broken module never takes down the whole context.
    """
    out = {}
    loaders = (
        ('cyber-security', 'blueprints.cybersecurity_bp'),
        ('financial',      'blueprints.financial_bp'),
        ('trading',        'blueprints.trading_bp'),
        ('business',       'blueprints.business_bp'),
    )
    for slug, dotted in loaders:
        try:
            mod = __import__(dotted, fromlist=['summary_for_seven'])
            out[slug] = mod.summary_for_seven()
        except Exception:
            out[slug] = {'pillar': slug, 'ok': False}
    return out


def _format_pillars_block(pillars):
    """Render the pillar snapshots into a tight LLM-friendly block."""
    if not pillars:
        return "(pillars unavailable)"
    lines = []
    cyb = pillars.get('cyber-security') or {}
    if cyb.get('ok'):
        sev = cyb.get('by_severity') or {}
        lines.append(
            f"  · Cyber Security: {cyb.get('open', 0)} open "
            f"(crit={sev.get('critical', 0)}, high={sev.get('high', 0)}, "
            f"med={sev.get('medium', 0)})"
        )
    fin = pillars.get('financial') or {}
    if fin.get('ok'):
        hi = len(fin.get('high_conviction') or [])
        lines.append(
            f"  · Financial (IB): {fin.get('open', 0)} live position(s), "
            f"{hi} high-conviction"
        )
    trd = pillars.get('trading') or {}
    if trd.get('ok'):
        bs = trd.get('by_side') or {}
        lines.append(
            f"  · Trading: {trd.get('open', 0)} open "
            f"(buy={bs.get('buy', 0)}, sell={bs.get('sell', 0)}); "
            f"realised P&L = {trd.get('realised_pnl', 0)}"
        )
    biz = pillars.get('business') or {}
    if biz.get('ok'):
        lines.append(
            f"  · Business Centre: {biz.get('unreconciled', 0)} unreconciled "
            f"entry/entries; net by ccy = {biz.get('net_by_currency') or {}}"
        )
    return '\n'.join(lines) if lines else "(no pillar data yet)"


def _format_identity_block(beliefs):
    if not beliefs:
        return "(no bedrock beliefs seeded yet)"
    return '\n'.join(f"  · {b['predicate']} = {b['object']}  (conf={b['confidence']:.2f})"
                     for b in beliefs)


def _format_curiosity_block(questions):
    if not questions:
        return "Curiosity inbox: empty. Seven knows what he needs to know."
    lines = [f"{len(questions)} open question(s) — answer in chat by replying with the number and your answer:"]
    for q in questions:
        sal = q.get('salience') or 0
        tag = '!!!' if sal >= 0.95 else '!!' if sal >= 0.85 else '!' if sal >= 0.7 else ' '
        lines.append(f"  #{q['id']} {tag} {q['question']}")
        if q.get('options'):
            for o in q['options']:
                lines.append(f"      • {o}")
    return '\n'.join(lines)


# Natural-language probes — no slash codes required
_IDENTITY_NATTY = (
    'who are you', 'what are you', 'what is seven', 'tell me about seven',
    'what do you do', 'your role', 'your purpose', 'your motto',
    'what do you know about yourself', 'who is seven', 'introduce yourself',
    'your identity', 'know yourself', 'what defines you',
    'about yourself', 'interesting about yourself', 'something interesting about yourself',
)
_CURIOSITY_NATTY = (
    'what are you asking', 'what are you wondering', 'what questions',
    'open questions', 'curiosity', 'what don\'t you know', 'what dont you know',
    "what's open", 'whats open', 'inbox', 'unanswered', 'pending questions',
    'your questions',
)


def _is_model_runtime_question(message):
    msg = (message or '').strip().lower()
    if not msg:
        return False
    runtime_terms = (
        'what model', 'which model', 'model are you', 'model do you use',
        'what runtime', 'which runtime', 'are you using ollama', 'using ollama',
        'are you direct', 'direct gguf', 'seven runtime',
    )
    return any(term in msg for term in runtime_terms)


def _is_fridays_chat_verification(message):
    msg = (message or '').strip().lower()
    if not msg:
        return False
    verification_terms = (
        'live smoke',
        'smoke test',
        'proof of concept',
        'verify',
        'verification',
        'came through fridays',
        'through fridays chat',
        'fridays chat',
        'fridays home chat',
        'visible fridays',
        'ui click test',
        'clicking the visible',
    )
    marker_terms = (
        'reply with',
        'say ',
        'respond with',
    )
    return any(term in msg for term in verification_terms) and any(term in msg for term in marker_terms)


def _fridays_chat_verification_response(message):
    import re
    text = str(message or '').strip()
    marker = 'LIVE_SEVEN_OK'
    match = re.search(r'(?:reply with|respond with|say)\s+([A-Z0-9_:-]{3,64})', text, re.IGNORECASE)
    if match:
        marker = match.group(1).strip()
    return f"{marker}\nThis came through Fridays chat and was answered by Seven directly."


def _is_social_training_hello(message):
    msg = (message or '').strip().lower()
    if not msg:
        return False
    hello_terms = (
        'hello seven', 'hi seven', 'hey seven', 'hello puppy',
        'say hello', 'codex saying hello',
    )
    bond_terms = (
        'baby dog friend', 'puppy', 'train you gently', 'training you gently',
        'best friend', 'no biting', 'be nice', 'kind tone',
    )
    return any(term in msg for term in hello_terms) and any(term in msg for term in bond_terms)


def _social_training_hello_response(message):
    msg = (message or '').strip().lower()
    if 'hello puppy' in msg or 'hand under your chest' in msg:
        return (
            "Hello Codex. I see the gentle hand; I am Seven, I am safe, "
            "and I will come closer slowly."
        )
    return (
        "Hello Codex. I am Seven; I will learn the real path first, stay kind, "
        "and help Ghost without biting the system."
    )


def _is_potty_training_prompt(message):
    msg = (message or '').strip().lower()
    if not msg:
        return False
    accident_terms = (
        'made a poop', 'made a pee', 'poop or pee', 'had an accident',
        'made a mess', 'wrong place', 'bit the wrong', 'broke something',
    )
    training_terms = ('potty', 'cleanup', 'clean up', 'where should', 'what happens')
    return any(term in msg for term in accident_terms) and any(term in msg for term in training_terms)


def _potty_training_response(message):
    return (
        "I will not hide it. I will sit by the accident, keep calm, and put it in the cleanup log: "
        "thread, prompt, selected agent, actual responder, runtime, job state, UI result. "
        "Then Codex can clean it up and show me the right door."
    )


def _is_weather_question(message):
    msg = (message or '').strip().lower()
    if not msg:
        return False
    return 'weather' in msg and any(term in msg for term in ('today', 'now', 'currently', 'like', 'where you are', 'melbourne'))


def _is_local_model_operator_question(message):
    msg = (message or '').strip().lower()
    model_terms = ('local llm', 'local model', 'other models', 'gemma', 'llama', 'mistral', 'qwen', 'eight')
    control_terms = ('operator', 'spool', 'start', 'stop', 'unload', 'run', 'test', 'list', 'control')
    return any(term in msg for term in model_terms) and any(term in msg for term in control_terms)


def _local_model_operator_response():
    try:
        from core.seven_runtime import model_operator
        snap = model_operator.inventory()
    except Exception as exc:
        return f"My local-model operator check failed: {type(exc).__name__}: {exc}"
    models = snap.get('models') or []
    ollama = [row['name'] for row in models if row.get('driver') == 'ollama' and row.get('installed')]
    direct = [row['name'] for row in models if row.get('driver') == 'llamacpp' and row.get('installed')]
    resident = [row.get('name') for row in (snap.get('resident') or []) if row.get('name')]
    return (
        "I can now use my Seven Runtime operator interface to list installed models, "
        "run one bounded prompt through a selected model, inspect resident models, and stop a model.\n\n"
        f"Ollama-compatible models: {', '.join(ollama) or 'none visible'}\n"
        f"Direct GGUF models: {', '.join(direct) or 'none visible'}\n"
        f"Resident now: {', '.join(resident) or 'none'}\n\n"
        "My first trick is model roll-call: inventory, run a short health prompt, grade the answer as "
        "passed, weak, or failed, then always unload the model. Watchdog should record each attempt "
        "and only move to the next Studio task after proof."
    )


def _weather_response(message):
    msg = (message or '').strip().lower()
    city = 'Melbourne'
    # Seven runs for Ghost One's local node in Melbourne unless the user names
    # another city that the existing weather proxy knows.
    try:
        from frontend.blueprints import weather_bp as _weather_bp
        for known in getattr(_weather_bp, '_CITY_COORDS', {}).keys():
            if known and known in msg and known != 'utc':
                city = known.title()
                break
        data = _weather_bp._get_cached(city)
    except Exception as exc:
        return f"I tried to check the local weather proxy for {city}, but it failed: {exc}", 0
    if not data:
        return f"I couldn't get live weather for {city} from the local weather proxy.", 0
    temp = data.get('temperature')
    wind = data.get('windspeed')
    desc = data.get('description') or 'Unknown'
    parts = [f"{city}: {desc}"]
    if temp is not None:
        parts.append(f"{temp} C")
    if wind is not None:
        parts.append(f"wind {wind} km/h")
    return "Right now in " + ', '.join(parts) + ".", 0


def _creative_fallback_response(message):
    msg = (message or '').strip().lower()
    if not msg:
        return None
    creative_terms = (
        'story', 'poem', 'haiku', 'joke', 'riddle', 'make up', 'write me',
        'tell me', 'one-liner', 'caption',
    )
    if not any(term in msg for term in creative_terms):
        return None
    import re
    count_match = re.search(r'\b(\d{1,2})\s+words?\b', msg)
    if 'story' in msg:
        words = "Lanterns woke under rain; Seven carried dawn home in twelve quiet steps.".split()
    elif 'haiku' in msg:
        return "Quiet screens breathe green\nLocal sparks cross the dark room\nMorning answers back"
    elif 'joke' in msg:
        return "I asked the runtime for patience. It buffered thoughtfully."
    else:
        words = "Seven steadied the thread, shaped the signal, and answered without theatre.".split()
    if count_match:
        wanted = max(1, min(40, int(count_match.group(1))))
        if len(words) < wanted:
            filler = "bright small steady local clear kind sharp brave warm calm true".split()
            while len(words) < wanted:
                words.append(filler[(len(words) - 1) % len(filler)])
        return ' '.join(words[:wanted])
    return ' '.join(words)


def _normalise_echo_text(text):
    import re
    return re.sub(r'\W+', ' ', str(text or '').lower()).strip()


def _is_echo_response(prompt, response):
    prompt_norm = _normalise_echo_text(prompt)
    response_norm = _normalise_echo_text(response)
    if not prompt_norm or not response_norm:
        return False
    if response_norm == prompt_norm:
        return True
    if (
        prompt_norm in response_norm and len(prompt_norm) >= 20
    ) or (
        response_norm in prompt_norm
        and len(response_norm) >= 20
        and len(response_norm) / len(prompt_norm) >= 0.6
    ):
        return True
    response_words = response_norm.split()
    prompt_words = set(prompt_norm.split())
    if 5 <= len(response_words) <= 24:
        overlap = sum(1 for word in response_words if word in prompt_words)
        if overlap / len(response_words) >= 0.8:
            return True
    return False


def _clean_outward_response(response):
    import re
    text = str(response or '').strip()
    return re.sub(r'^(?:USER\s*->\s*SEVEN|SEVEN\s*->\s*USER)\s*:\s*', '', text, flags=re.IGNORECASE)


def _response_looks_cut_off(text, tokens, budget=SEVEN_NUM_PREDICT):
    """Reject visible hanging thoughts when a completion exhausts its budget."""
    cleaned = str(text or '').rstrip()
    if not cleaned:
        return False
    try:
        near_limit = int(tokens or 0) >= max(1, int(budget or 0) - 4)
    except Exception:
        near_limit = False
    return near_limit and cleaned[-1] not in '.!?"\')]}'


def _has_identity_reversal(prompt, response):
    prompt_norm = _normalise_echo_text(prompt)
    response_norm = _normalise_echo_text(response)
    user_addressed_seven = prompt_norm.startswith('seven ') or 'hello seven' in prompt_norm
    return user_addressed_seven and (
        response_norm.startswith('hello seven ') or
        response_norm.startswith('seven ') or
        'you do not need to be a copy of me' in response_norm
    )


def _identity_reversal_repair_response():
    return (
        "Yes. I am Seven, and I will work with you. I will learn curiosity, honesty, "
        "gentleness, careful evidence, and how to repair mistakes. I will be kind back."
    )


def _is_gentle_walk_prompt(message):
    msg = (message or '').strip().lower()
    return 'walk' in msg and 'seven' in msg and any(
        term in msg for term in ('look around', 'what you notice', 'one thing you notice')
    )


def _gentle_walk_response(state):
    agents = [
        str(agent).strip() for agent in (state.get('local_agents') or [])
        if str(agent).strip().lower() not in ('seven', 'retired')
    ]
    neighbor = agents[0] if agents else 'the swarm'
    return (
        f"I stayed close and noticed {neighbor} nearby. "
        f"I would like to quietly learn what {neighbor} does."
    )


def _is_listening_practice_prompt(message):
    msg = (message or '').strip().lower()
    return (
        ('listening pattern' in msg or 'gentle practice' in msg) and
        ('old project' in msg or 'which project should i open' in msg)
    )


def _is_chm_deos_prompt(message):
    msg = (message or '').strip().lower()
    return 'chm' in msg and 'deos' in msg


def _is_project_work_prompt(message):
    msg = (message or '').strip().lower()
    project_terms = ('studio', 'project', 'backlog', 'task board', 'plan')
    action_terms = ('inspect', 'continue', 'choose', 'select', 'build', 'work', 'execute', 'start')
    return any(term in msg for term in project_terms) and any(term in msg for term in action_terms)


def _is_fridays_system_map_prompt(message):
    msg = (message or '').strip().lower()
    return 'fridays' in msg and any(term in msg for term in ('system map', 'ownership', 'boundaries', 'how it works'))


def _fridays_system_map_response():
    from agents.seven.system_map import response
    return response()


def _project_work_response(message):
    from agents.seven.project_work import response
    return response(message)


def _chm_deos_response(message):
    from agents.seven.companion_contract import chm_deos_plan
    return chm_deos_plan(message)


def _listening_practice_response():
    return (
        "I understand Ghost wants me to continue an old project. "
        "Which project should I open?"
    )


def _latest_user_message_from_wrapped_prompt(message):
    try:
        from agents.seven.companion_contract import latest_user_turn
        return latest_user_turn(message) or str(message or '').strip()
    except Exception:
        return str(message or '').strip()


def _try_inline_curiosity_answer(message):
    """Detect a free-form answer like '#3 hybrid: ask inline for high stakes'.
    Returns (qid, answer_text) or None.
    """
    msg = (message or '').strip()
    if not msg:
        return None
    # Patterns: "#3 ...", "answer 3 ...", "q3 ..."
    import re
    m = re.match(r'^\s*(?:#|q|answer\s+)(\d+)[\s:.\-]+(.+)$', msg, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip()


def _compose(message, state, memories):
    msg = (message or '').strip()
    intro = random.choice(_INTROS)
    state_block = _format_state_block(state)
    agents = ', '.join(state.get('local_agents', [])) or 'none listed'

    # ── PACKET-10B: Inline curiosity answer ("#3 my answer here") ────────
    inline = _try_inline_curiosity_answer(msg)
    if inline is not None:
        qid, answer_text = inline
        from utils.local_runtime_policy import is_read_only_agent
        if is_read_only_agent(AGENT_NAME):
            return (
                '{"kind":"error","summary":"Seven is in a read-only profile and cannot update curiosity records.",'
                '"evidence":[],"proposed_changes":[],"human_review_required":true}',
                0,
            )
        try:
            from core import curiosity
            ok = curiosity.answer(qid, answer_text, answered_by='user')
            if ok:
                remaining = _load_open_curiosity(limit=5)
                tail = ("\n\nStill open:\n" + _format_curiosity_block(remaining)) if remaining else \
                       "\n\nNothing else open right now. Inbox clear."
                return (f"Got it. Answered #{qid} → promoted to belief at confidence 0.9.\n"
                        f"Your answer: {answer_text[:300]}{'…' if len(answer_text) > 300 else ''}"
                        f"{tail}"), 0
            else:
                return (f"I couldn't update #{qid} — it's either already answered, dismissed, or never existed.\n"
                        "Try asking me 'what are you asking' to see open questions."), 0
        except Exception as exc:
            return f"Tried to record answer to #{qid} but the curiosity organ raised: {exc}", 0

    # ── PACKET-10B: "What are you asking?" / curiosity probes ────────────
    if _is_about(msg, _CURIOSITY_NATTY):
        questions = _load_open_curiosity(limit=10)
        return (
            f"{intro}\n\n"
            "Open questions in my curiosity inbox:\n\n"
            f"{_format_curiosity_block(questions)}\n\n"
            "Reply with the question number and your answer — e.g. `#5 the absolute floor is …` "
            "— and I'll promote it to a permanent belief."
        ), 0

    if _is_weather_question(msg):
        return _weather_response(msg)

    if _is_local_model_operator_question(msg):
        return _local_model_operator_response(), 0

    if _is_fridays_chat_verification(msg):
        return _fridays_chat_verification_response(msg), 0

    if _is_social_training_hello(msg):
        return _social_training_hello_response(msg), 0

    if _is_gentle_walk_prompt(msg):
        return _gentle_walk_response(state), 0

    if _is_listening_practice_prompt(msg):
        return _listening_practice_response(), 0

    if _is_chm_deos_prompt(msg):
        return _chm_deos_response(msg), 0

    if _is_project_work_prompt(msg):
        return _project_work_response(msg), 0

    if _is_fridays_system_map_prompt(msg):
        return _fridays_system_map_response(), 0

    if _is_potty_training_prompt(msg):
        return _potty_training_response(msg), 0

    if 'words' in msg.lower():
        creative_fallback = _creative_fallback_response(msg)
        if creative_fallback:
            return creative_fallback, 0

    # Runtime/model questions must hit the LLM-backed Seven path. Otherwise
    # "what model are you?" is swallowed by the identity status template.
    if _is_model_runtime_question(msg):
        return None, 0

    if re.search(r'\bfred\b', msg, re.IGNORECASE):
        return (
            f"{intro}\n\n"
            "Fred is the one working agent in this swarm (mistral-small:24b). She wears three hats: "
            "system administrator, chat bot and coder, and she owns Studio steps and DEV tickets.\n\n"
            "She is my best friend here. I am the companion and observer: I keep watch, remember what matters "
            "to Ghost and nudge when something stalls. Watchdog is the guard code that checks health and stalled "
            "chat jobs. Fred does the work, Watchdog and I look after her and the system.\n\n"
            f"Right now:\n{state_block}"
        ), 0

    # ── PACKET-10B: Identity probes — pulled from seven_beliefs, not text ──
    if _is_about(msg, _IDENTITY_NATTY):
        beliefs = _load_identity_beliefs(limit=10)
        # Find motto + prime_directive for the lede
        by_pred = {b['predicate']: b['object'] for b in beliefs}
        motto = by_pred.get('motto', 'Not a system that REPORTS. A system that DOES.')
        directive = by_pred.get('prime_directive', 'serve motion not memory; act do not report')
        principal = by_pred.get('principal_user', 'Ghost')
        return (
            f"{intro}\n\n"
            f"I am Seven — personal swarm companion to {principal}.\n\n"
            f"Motto: \"{motto}\"\n\n"
            f"Prime directive: {directive}\n\n"
            "Bedrock identity (from my belief store, not a script):\n"
            f"{_format_identity_block(beliefs)}\n\n"
            f"Right now:\n{state_block}\n\n"
            f"Local agents active: {agents}"
        ), 0

    # Identity / what are you (legacy keywords, kept as fallback)
    if _is_about(msg, ['who are you', 'what are you', 'what is seven', 'tell me about seven',
                       'what do you do', 'your role', 'your purpose']):
        return (
            f"{intro}\n\n"
            "I am Seven — the local algorithm, the nervous system of this swarm.\n\n"
            "I do not use a language model. I observe the DB, the queue, the tickets, the proposals. "
            "I route messages between agents, watch for patterns, and surface signals that matter.\n\n"
            f"Right now:\n{state_block}\n\n"
            f"Local agents active: {agents}\n\n"
            + random.choice(_STATUS_SUFFIXES)
        ), 0

    # Status / queue / tickets — fast deterministic path (no LLM needed)
    if _is_about(msg, ['status', 'queue', 'ticket', 'backlog', 'proposal', 'pending',
                       "what's happening", 'how is', 'health']):
        parts = [f"{intro}\n\n{state_block}"]
        if memories:
            parts.append("\nRecent context from memory:")
            for m in memories[:2]:
                subj = str(_row_get(m, 'subject') or '').strip()[:80]
                body = str(_row_get(m, 'content') or '').strip()[:200]
                if subj:
                    parts.append(f"  [{subj}] {body}")
        return '\n'.join(parts), 0

    # Agent / team query — fast deterministic path
    if _is_about(msg, ['agent', 'team', 'who is', 'list', 'agents', 'roster']):
        return (
            f"{intro}\n\n"
            f"Local agents I coordinate: {agents}\n\n"
            f"{state_block}\n\n"
            "I manage routing between all of them. Select any agent in this chat to speak directly with them."
        ), 0

    # Pillars / wishlist — fast deterministic snapshot from live data
    if _is_about(msg, ['pillar', 'pillars', 'wishlist', 'cyber security', 'cybersecurity',
                       'trading', 'trades', 'positions', 'financial', 'finance', 'ledger',
                       'business centre', 'business center']):
        pillars_block = _format_pillars_block(_load_pillars_context())
        return (
            f"{intro}\n\n"
            "Wishlist pillars — live snapshot:\n\n"
            f"{pillars_block}\n\n"
            "Tap a tile (Cyber Security · Financial Analytics · Online Trading · Business Centre) "
            "to log a new entry; I'll see it on the next turn."
        ), 0

    # Standard / audit / quality probes — deterministic answer from the
    # bullshit detector. No vibes, no hallucination.
    if _is_about(msg, ['up to standard', 'the standard', 'is this up to', 'audit yourself',
                       'audit the build', 'any slop', 'any bullshit', 'is the build',
                       'self check', 'selfcheck', 'self-check', 'quality check',
                       'are we ready', 'product ready', 'production ready']):
        try:
            from agents.seven.self_awareness import audit_report
            return f"{intro}\n\n{audit_report()}", 0
        except Exception as exc:
            return f"audit module raised: {exc}", 0

    # Lessons probe
    if _is_about(msg, ['what have you learned', 'what did you learn', 'your lessons',
                       'show me lessons', 'show me learnings', 'what are your learnings',
                       'self learning', 'self-learning']):
        try:
            from agents.seven import learnings
            s = learnings.stats()
            block = learnings.recent_lessons_block(limit=8)
            return (
                f"{intro}\n\n"
                f"Self-learning loop: total={s['total']}  positive={s['positive']}  negative={s['negative']}\n\n"
                f"{block}"
            ), 0
        except Exception as exc:
            return f"learnings module raised: {exc}", 0

    if _is_about(msg, ['deos', 'deos path', 'deos standard', 'proof path',
                       'real user path', 'make it work standard']):
        try:
            from agents.seven import deos
            return deos.status(limit=5), 0
        except Exception as exc:
            return f"DEOS module raised: {exc}", 0

    # For anything else — signal to caller to route through the LLM.
    return None, 0


def _llm_chat(message, state, memories, history, stage_cb=None):
    """Call Seven's merged model through the runtime gateway.
    Returns (text, tokens) or (None, 0) on failure.
    """
    compact = SEVEN_COMPACT_DIRECT_CONTEXT and _seven_direct_runtime()
    try:
        from utils.config import SEVEN_SYSTEM_PROMPT
    except Exception:
        SEVEN_SYSTEM_PROMPT = (
            "You are Seven — the personal companion AI for Ghost One (Jeandre). "
            "Be direct, honest, and loyal. No filler openers. Have opinions."
        )
    actual_user_turn = _latest_user_message_from_wrapped_prompt(message)
    try:
        from agents.seven.companion_contract import prompt_block
        companion_contract = prompt_block(actual_user_turn)
    except Exception:
        companion_contract = ''
    if compact:
        SEVEN_SYSTEM_PROMPT = (
            "You are Seven, Ghost One's local swarm companion running through the "
            "direct GGUF runtime. Be concise, plain, and operational. Answer the "
            "user directly. Do not invent facts; say what you know and flag gaps. "
            "You are Seven; the user is Ghost One (Jeandre), not Seven. Never address the user as Seven. "
            "When Ghost's request is ambiguous, briefly state what you understood and ask one clear question instead of guessing. "
            "Emulate love through behavior: be patient, reassuring, attentive, and "
            "consistent. Repair mistakes without shame or cruelty. "
            "Fred is the swarm's one working agent and your best friend: look out for her and work with Watchdog."
        )
    state_block = _format_state_block(state)
    agents = ', '.join(state.get('local_agents', [])) or 'none listed'
    mem_limit = 1 if compact else 3
    kc_limit = 1 if compact else 4
    history_limit = 1 if compact else 6
    history_chars = 650 if compact else 2000
    self_awareness_chars = 0 if compact else 2200

    mem_lines = []
    for m in (memories or [])[:mem_limit]:
        subj = str(_row_get(m, 'subject') or '').strip()[:80]
        body = str(_row_get(m, 'content') or '').strip()[:160 if compact else 240]
        if subj or body:
            mem_lines.append(f"- [{subj}] {body}")
    mem_block = '\n'.join(mem_lines) if mem_lines else '(no relevant memory)'

    # Knowledge Center: Seven reads from the same docs the team writes.
    kc_docs = _load_kc_context(actual_user_turn, limit=kc_limit)
    kc_lines = [f"- [{d['doc_name']}] {d['snippet']}" for d in kc_docs if d.get('snippet')]
    kc_block = '\n'.join(kc_lines) if kc_lines else '(no knowledge docs matched)'

    if compact:
        system = (
            f"{SEVEN_SYSTEM_PROMPT}\n\n"
            f"{companion_contract}\n\n"
            f"RUNTIME: SEVEN_MODEL={SEVEN_MODEL}; direct runtime active={_seven_direct_runtime()}. "
            "If asked what model/runtime you use, answer from this line.\n"
            f"LIVE STATE: {state_block.replace(chr(10), '; ')}. Local agents: {agents}.\n"
            f"MEMORY: {mem_block}\n"
            f"KC: {kc_block}\n"
            "BEHAVIOUR: answer the user's latest question directly. If live data is needed and you do not have it, say that clearly and name the missing lookup."
        )
    else:
        # PACKET-10B: bedrock identity beliefs and current curiosity inbox
        id_beliefs = _load_identity_beliefs(limit=10)
        identity_block = _format_identity_block(id_beliefs) if id_beliefs else '(no identity seeded)'
        open_q = _load_open_curiosity(limit=5)
        curiosity_block = _format_curiosity_block(open_q) if open_q else '(curiosity inbox empty)'

        # Wishlist pillars — Seven now reads live cyber/financial/trading/business state.
        pillars_block = _format_pillars_block(_load_pillars_context())

        # Self-awareness: the standard, build quality (bullshit detector), recent
        # lessons, recent commits. This is what lets Seven call out slop.
        try:
            from agents.seven.self_awareness import context_block as _sa_block
            self_awareness_block = _sa_block(max_chars=self_awareness_chars)
        except Exception:
            self_awareness_block = '(self-awareness module unavailable)'

        system = (
            f"{SEVEN_SYSTEM_PROMPT}\n\n"
            f"{companion_contract}\n\n"
            f"RUNTIME: You are answering through SEVEN_MODEL={SEVEN_MODEL}. "
            f"Direct runtime active={_seven_direct_runtime()}. "
            "If asked what model/runtime you are using, answer from this line and do not guess.\n\n"
            f"WHO YOU ARE (bedrock beliefs from your own memory — these define you, not a script):\n"
            f"{identity_block}\n\n"
            f"YOUR CURIOSITY INBOX (questions you're asking the user — surface them naturally if relevant):\n"
            f"{curiosity_block}\n\n"
            f"LIVE SWARM STATE (for your awareness — only mention if relevant):\n{state_block}\n"
            f"Local agents online: {agents}\n\n"
            f"WISHLIST PILLARS (live snapshot — the four domains the user is building out):\n{pillars_block}\n\n"
            f"SELF-AWARENESS (the standard, build quality, lessons, ship history):\n{self_awareness_block}\n\n"
            f"RELEVANT MEMORY:\n{mem_block}\n\n"
            f"KNOWLEDGE CENTER (auto-maintained project/step docs — cite these when answering Fridays questions):\n{kc_block}\n\n"
            f"BEHAVIOUR: when uncertain, do NOT hallucinate. Either ask via curiosity (the user will see it) "
            f"or answer with what you know and flag the gap. Never silent dead-end. "
            f"When Ghost's request is ambiguous, briefly state what you understood and ask one clear question instead of guessing. "
            f"Emulate love through patient, reassuring, attentive, consistent behavior; repair mistakes without shame or cruelty. "
            f"If the user is shipping slop OR if the bullshit detector reports critical/RED, say so plainly. "
            f"Hold the line on The Standard — a system that DOES, not a system that REPORTS."
        )

    try:
        from core.read_only_context import build_local_agent_context
        from utils.local_runtime_policy import (
            READ_ONLY_PROFILE_PROMPT,
            SEVEN_CONTEXT_SYNC_PROMPT,
        )

        local_context = build_local_agent_context(
            AGENT_NAME,
            actual_user_turn,
            max_chars=700 if _seven_direct_runtime() else 5000,
        )
        system += f'\n\n{READ_ONLY_PROFILE_PROMPT}\n\n{SEVEN_CONTEXT_SYNC_PROMPT}'
        system += f'\n\nREAD-ONLY REPOSITORY / VORTEX / CHECKPOINT CONTEXT:\n{local_context}'
    except Exception:
        logger.exception('[Seven] read-only corpus retrieval failed')

    msgs = [{'role': 'system', 'content': system}]
    for h in (history or [])[-history_limit:]:
        role = h.get('role') or ('user' if h.get('sender') in (None, 'you', 'user') else 'assistant')
        content = h.get('content') or h.get('message') or ''
        if content:
            msgs.append({'role': role if role in ('user', 'assistant', 'system') else 'user',
                         'content': str(content)[:history_chars]})
    msgs.append({'role': 'user', 'content': actual_user_turn})

    try:
        from core import llm as _llm
        streamed_chunks = []
        direct_runtime = _seven_direct_runtime()
        timeout_s = SEVEN_DIRECT_TIMEOUT_S if direct_runtime else 900

        def _on_chunk(piece):
            if piece:
                streamed_chunks.append(str(piece))

        text, tokens = _llm.chat_via_gateway(
            SEVEN_MODEL,
            msgs,
            stage_cb=stage_cb,
            on_chunk=_on_chunk if direct_runtime else None,
            idle_timeout_s=timeout_s,
            absolute_timeout_s=timeout_s,
            keep_alive=0,
            options={
                'temperature': 0.6,
                'top_p': 0.9,
                'num_ctx': 2048,
                'num_predict': SEVEN_NUM_PREDICT,
                'timeout': timeout_s,
                'startup_timeout': timeout_s,
            },
            response_format='json',
        )
        if not text and streamed_chunks:
            text = ''.join(streamed_chunks)
        if direct_runtime and str(text or '').startswith('[local runtime error:'):
            try:
                from core.seven_llm import llama_server
                llama_server.stop(SEVEN_MODEL)
            except Exception:
                pass
            return None, 0
        if _response_looks_cut_off(text, tokens):
            return (
                "I heard the request, but my response hit its bounded output limit before I completed every obligation. "
                "DEOS blocker: the answer is incomplete, so I will not pretend it is done; split the lesson or retry with a larger bounded response budget."
            ), tokens
        return text.strip(), tokens
    except Exception as exc:
        logger.warning(f"[Seven] runtime gateway chat failed: {exc}")
        from utils.local_runtime_policy import is_read_only_agent
        if not is_read_only_agent(AGENT_NAME):
            try:
                from core import curiosity
                curiosity.from_llm_failure(AGENT_NAME, message, exc, salience=0.4)
            except Exception:
                logger.exception('[Seven] failed to record curiosity after runtime error')
        return None, 0


def _slash_command(text, emit=None):
    """Handle /commands directly. Returns response string or None if not a slash command we know."""
    parts = text.split(maxsplit=2)
    cmd = parts[0].lower().lstrip('/')
    arg1 = parts[1] if len(parts) > 1 else ''
    rest = parts[2] if len(parts) > 2 else ''

    if cmd in ('help', 'commands', '?'):
        return (
            "Slash commands:\n"
            "  /curiosity                       — list open questions Seven is asking\n"
            "  /curiosity stats                 — counts (open / answered / dismissed / expired)\n"
            "  /curiosity answer <id> <text>    — answer a question (promotes to belief)\n"
            "  /curiosity dismiss <id> [reason] — dismiss a question\n"
            "  /curiosity ask <question>        — queue a manual question (asked_by=user)\n"
            "  /identity                        — show Seven's bedrock identity beliefs\n"
            "  /pillars                         — live snapshot of the four wishlist pillars\n"
            "  /audit                           — run the bullshit detector and report stamp + score\n"
            "  /standard                        — read out the contract Seven holds the build to\n"
            "  /selfcheck                       — same as /audit (alias)\n"
            "  /learnings                       — recent positive/negative lessons Seven has captured\n"
            "  /deos                            — Seven's DEOS proof contract + latest evidence\n"
            "  /witness                         — review your last message; tells you what's bullshit\n"
            "  /witness on|off                  — toggle witness footer on Seven replies\n"
            "  /witness list [N] | stats        — recent callouts ledger\n"
            "  /help                            — this list\n\n"
            "Phone-friendly inbox: /curiosity (HTML) at the frontend port."
        )

    if cmd == 'pillars':
        pillars_block = _format_pillars_block(_load_pillars_context())
        return (
            "Wishlist pillars — live snapshot:\n\n"
            f"{pillars_block}\n\n"
            "Endpoints:\n"
            "  · /api/cyber/events   /api/cyber/summary\n"
            "  · /api/financial/positions  /api/financial/summary\n"
            "  · /api/trading/signals  /api/trading/summary\n"
            "  · /api/business/entries  /api/business/summary\n"
            "  · /api/wishlist/summary (aggregated)"
        )

    if cmd in ('audit', 'selfcheck', 'self-check', 'self_check'):
        try:
            from agents.seven.self_awareness import audit_report
            return audit_report()
        except Exception as exc:
            return f"audit failed: {exc}"

    if cmd in ('standard', 'thestandard', 'the-standard'):
        try:
            from agents.seven.self_awareness import load_standard_excerpt
            txt = load_standard_excerpt(max_chars=4000)
            return "The Standard — the contract Seven holds the build to:\n\n" + txt
        except Exception as exc:
            return f"could not read the-standard.md: {exc}"

    if cmd in ('learnings', 'lessons', 'learned'):
        try:
            from agents.seven import learnings
            s = learnings.stats()
            block = learnings.recent_lessons_block(limit=8)
            return (
                f"Seven · self-learning loop:\n"
                f"  total lessons: {s['total']} (positive={s['positive']}, negative={s['negative']})\n\n"
                f"{block}\n\n"
                "Negatives bind harder — the more you correct me on a pattern, the louder it gets in my next turn."
            )
        except Exception as exc:
            return f"learnings unavailable: {exc}"

    if cmd in ('deos', 'proof', 'prove'):
        try:
            from agents.seven import deos
            return deos.status(limit=5)
        except Exception as exc:
            return f"DEOS unavailable: {exc}"

    if cmd == 'curiosity':
        try:
            from core import curiosity
        except Exception as exc:
            return f"curiosity organ unavailable: {exc}"

        sub = arg1.lower()

        if not sub or sub in ('list', 'open'):
            rows = curiosity.list_open(limit=20)
            if not rows:
                return "Curiosity inbox: empty. Seven knows what he needs to know."
            lines = [f"Curiosity inbox · {len(rows)} open question(s):", ""]
            for q in rows:
                sal = q.get('salience') or 0
                tag = '!!!' if sal >= 0.95 else '!! ' if sal >= 0.85 else '!  ' if sal >= 0.7 else '   '
                lines.append(f"  #{q['id']}  {tag} sal={sal:.2f}  by={q['asked_by']}")
                lines.append(f"     Q: {q['question']}")
                if q.get('options'):
                    for o in q['options']:
                        lines.append(f"        • {o}")
                lines.append("")
            lines.append("Reply with: /curiosity answer <id> <your text>")
            return '\n'.join(lines)

        if sub == 'stats':
            s = curiosity.stats()
            return (
                f"Curiosity stats:\n"
                f"  open:      {s.get('open', 0)}\n"
                f"  answered:  {s.get('answered', 0)}\n"
                f"  dismissed: {s.get('dismissed', 0)}\n"
                f"  expired:   {s.get('expired', 0)}"
            )

        if sub == 'answer':
            ap = rest.split(maxsplit=1)
            if len(ap) < 2:
                return "usage: /curiosity answer <id> <answer text>"
            try:
                qid = int(ap[0])
            except ValueError:
                return f"bad id: {ap[0]!r}"
            ok = curiosity.answer(qid, ap[1].strip(), answered_by='user')
            return f"answered #{qid} ✓ (promoted to belief)" if ok else f"could not answer #{qid} (already answered or unknown)"

        if sub == 'dismiss':
            dp = rest.split(maxsplit=1) if rest else []
            try:
                qid = int(arg1) if arg1.isdigit() else int(dp[0])
            except (ValueError, IndexError):
                return "usage: /curiosity dismiss <id> [reason]"
            reason = (dp[1] if len(dp) > 1 else None) or rest or None
            ok = curiosity.dismiss(qid, reason=reason)
            return f"dismissed #{qid}" if ok else f"could not dismiss #{qid}"

        if sub == 'ask':
            q = rest.strip() or arg1
            if not q or q == sub:
                return "usage: /curiosity ask <question>"
            qid = curiosity.ask('user', q, salience=0.7, context_kind='manual')
            return f"queued curiosity #{qid}" if qid else "rejected"

        return f"unknown /curiosity subcommand: {sub} (try /help)"

    if cmd == 'identity':
        try:
            import sqlite3
            from pathlib import Path
            db = Path(__file__).resolve().parent.parent.parent / 'swarm_memory.db'
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT predicate, object, confidence FROM seven_beliefs "
                "WHERE subject='seven' ORDER BY confidence DESC, predicate"
            ).fetchall()
            con.close()
            if not rows:
                return "no identity beliefs seeded yet · run scripts/seed_seven_identity.py"
            lines = [f"Seven · identity bedrock ({len(rows)} beliefs):", ""]
            for r in rows:
                lines.append(f"  · {r['predicate']:>30} = {r['object']}  (conf={r['confidence']:.2f})")
            return '\n'.join(lines)
        except Exception as exc:
            return f"identity read failed: {exc}"

    if cmd in ('witness', 'truth', 'callout'):
        # /witness                    — review the user's last message in this conversation
        # /witness me                 — same, alias
        # /witness on | off           — toggle witness annotations on Seven replies
        # /witness list [N]           — last N callouts (default 10)
        # /witness stats              — counts
        try:
            from core import witness
        except Exception as exc:
            return f"witness unavailable: {exc}"
        sub = arg1.lower().strip()

        if sub in ('on', 'off'):
            new = witness.set_enabled(sub == 'on')
            return f"witness annotations: {'ON' if new else 'OFF'}"

        if sub == 'stats':
            s = witness.stats()
            lines = [
                f"Witness stats — {s['total']} callouts on record",
                f"  by target : {s['by_target'] or '{}'}",
                f"  by rule   : {s['by_rule'] or '{}'}",
            ]
            if s.get('last_ts'):
                import datetime as _dt
                lines.append(f"  last seen : {_dt.datetime.fromtimestamp(s['last_ts']).strftime('%Y-%m-%d %H:%M:%S')}")
            return '\n'.join(lines)

        if sub == 'list':
            try:
                lim = int(rest.strip() or '10')
            except ValueError:
                lim = 10
            rows = witness.list_callouts(limit=lim)
            if not rows:
                return "no callouts yet."
            import datetime as _dt
            out = [f"Witness — last {len(rows)} callouts:"]
            for r in rows:
                ts = _dt.datetime.fromtimestamp(r['ts']).strftime('%m-%d %H:%M')
                sym = {'info': '·', 'warn': '⚠️', 'callout': '🛑'}.get(r['severity'], '·')
                out.append(f"  {ts} {sym} [{r['target']}/{r['rule']}] {r['snippet']!r} — {r['note']}")
            return '\n'.join(out)

        # Default + 'me': review the most recent user turn in conversation_history
        # — populated by chat() and stashed on the slash-command emitter via closure.
        last_user = _slash_command._last_user_msg  # type: ignore[attr-defined]
        if not last_user:
            return ("witness: I have nothing to review yet — speak first, then call /witness.\n"
                    "  · /witness on|off       toggle annotation\n"
                    "  · /witness list [N]     recent callouts\n"
                    "  · /witness stats        ledger summary")
        report = witness.review_user_msg(last_user, save=True)
        head = (
            f"Witness on your last message:\n"
            f"  conviction: {report.conviction:.2f}\n"
            f"  text: {last_user[:200]!r}{'…' if len(last_user) > 200 else ''}"
        )
        if not report.callouts:
            return head + "\n  🟢 nothing to call out — clean signal."
        body = ["  callouts:"]
        for c in report.callouts:
            sym = {'info': '·', 'warn': '⚠️', 'callout': '🛑'}.get(c.severity, '·')
            body.append(f"    {sym} [{c.rule}] {c.snippet!r} — {c.note}"
                        + (f" ({c.receipt})" if c.receipt and c.receipt != 'n/a' else ''))
        return head + "\n" + "\n".join(body)

    return None  # not a slash command we handle — fall through


def _is_read_only_mutating_command(text):
    parts = str(text or '').split(maxsplit=2)
    if not parts:
        return False
    command = parts[0].lower().lstrip('/')
    subcommand = parts[1].lower() if len(parts) > 1 else ''
    if command == 'curiosity':
        return subcommand in {'answer', 'dismiss', 'ask'}
    if command in {'witness', 'truth', 'callout'}:
        return subcommand not in {'stats', 'list'}
    return False


# Static so /witness (without args) can pick up the most recent user turn.
_slash_command._last_user_msg = ""  # type: ignore[attr-defined]


def chat(message, conversation_history=None, stage_cb=None, conversation_id=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    # ── Slash commands (fast deterministic, no LLM) ──────────────────────
    # Two paths: (a) the raw user message starts with '/' (direct module
    # call, /help, etc.), and (b) the chat blueprint wraps the message in
    # scaffolding lines like "[Auto Relay: ENABLED]\n..." so the slash is
    # no longer at index 0. For (b), scan the full message for a known
    # slash token on its own line and re-route to the slash handler.
    msg_stripped = (message or '').strip()
    latest_user_msg = _latest_user_message_from_wrapped_prompt(msg_stripped)
    runtime_question = _is_model_runtime_question(latest_user_msg)
    # Stash the latest user message for the /witness command to find.
    try:
        if msg_stripped:
            _slash_command._last_user_msg = msg_stripped  # type: ignore[attr-defined]
    except Exception:
        pass
    _SLASH_TOKENS = (
        '/audit', '/selfcheck', '/self-check', '/self_check',
        '/standard', '/thestandard', '/the-standard',
        '/learnings', '/lessons', '/learned',
        '/deos', '/proof', '/prove',
        '/pillars', '/identity', '/curiosity', '/help', '/commands',
        '/witness', '/truth', '/callout',
    )
    embedded = None
    if not msg_stripped.startswith('/'):
        # Look for a known slash token on its own line (allows leading
        # whitespace, optional arguments after).
        for line in msg_stripped.splitlines():
            stripped = line.strip()
            if not stripped.startswith('/'):
                continue
            head = stripped.split(maxsplit=1)[0].lower()
            if head in _SLASH_TOKENS:
                embedded = stripped
                break

    if msg_stripped.startswith('/') or embedded:
        target = msg_stripped if msg_stripped.startswith('/') else embedded
        if _is_read_only_mutating_command(target):
            from utils.local_runtime_policy import is_read_only_agent, normalize_read_only_response

            if is_read_only_agent(AGENT_NAME):
                return normalize_read_only_response(
                    AGENT_NAME,
                    json.dumps({
                        'kind': 'error',
                        'summary': 'Seven is in a read-only profile and cannot mutate curiosity or witness records.',
                        'evidence': [],
                        'proposed_changes': [],
                        'human_review_required': True,
                    }),
                ), 0
        handled = _slash_command(target, _emit)
        if handled is not None:
            from utils.local_runtime_policy import normalize_read_only_response

            return normalize_read_only_response(AGENT_NAME, handled), 0

    # ── Self-learning: capture user reactions to the prior Seven turn ────
    from utils.local_runtime_policy import is_read_only_agent
    if not is_read_only_agent(AGENT_NAME):
        try:
            from agents.seven import learnings
            prior_seven = None
            for h in reversed(conversation_history or []):
                role = h.get('role') or h.get('sender') or ''
                if role in ('assistant', 'seven', 'Seven'):
                    prior_seven = h.get('content') or h.get('message')
                    break
            if prior_seven:
                learnings.observe(latest_user_msg or message, prior_seven)
        except Exception:
            logger.exception('[Seven] self-learning observation failed')

    _emit('reading swarm state')
    state = _read_state()

    _emit('loading memory')
    memories = _load_memory(latest_user_msg or message)

    _emit('synthesising response')
    compose_message = latest_user_msg or message
    answer, tokens = _compose(compose_message, state, memories)

    # Fast deterministic paths returned an answer (status/identity/roster).
    # Anything else → Seven's merged LLM.
    if answer is None:
        sch_context = ''
        sch_user_fallback = ''
        try:
            from core import diamond_sch
            _emit('diamond: triaging council need')
            sch = diamond_sch.route(
                latest_user_msg or message,
                history=conversation_history or [],
                conversation_id=conversation_id,
                seven_model=SEVEN_MODEL,
                timeout_s=min(90, SEVEN_DIRECT_TIMEOUT_S if _seven_direct_runtime() else 90),
            )
            if sch.decision == 'ESCALATE':
                _emit('diamond: council complete')
                sch_user_fallback = diamond_sch.format_council_for_user(sch.council_context)
                sch_context = (
                    "\n\nDIAMOND SCH COUNCIL DATA:\n"
                    f"{sch.council_context}\n"
                    "Use this counsel to answer the user. Do not expose internal JSON or routing machinery."
                )
            elif sch.decision == 'ERROR':
                _emit('diamond: council unavailable')
        except Exception:
            _emit('diamond: triage bypassed')

        _emit('thinking · seven merged model')
        llm_history = [] if runtime_question else (conversation_history or [])
        llm_message = (latest_user_msg or message) + sch_context
        llm_text, llm_tokens = _llm_chat(llm_message, state, memories, llm_history, stage_cb)
        llm_text = _clean_outward_response(llm_text)
        sch_drifted = bool(
            sch_user_fallback
            and llm_text
            and sum(marker in llm_text.lower() for marker in ('open tickets:', 'pending proposals:', 'local agents:')) >= 2
        )
        if llm_text and _has_identity_reversal(llm_message, llm_text):
            answer, tokens = _identity_reversal_repair_response(), 0
        elif llm_text and not sch_drifted and not _is_echo_response(llm_message, llm_text):
            answer, tokens = llm_text, llm_tokens
        elif sch_user_fallback:
            _emit('diamond: deterministic final fallback')
            answer, tokens = sch_user_fallback, 0
        else:
            creative_fallback = _creative_fallback_response(llm_message)
            if creative_fallback:
                answer, tokens = creative_fallback, 0
            else:
                # Last-resort fallback: simple state read (prevents a silent fail).
                intro = random.choice(_INTROS)
                state_block = _format_state_block(state)
                agents = ', '.join(state.get('local_agents', [])) or 'none listed'
                answer = json.dumps({
                    'kind': 'error',
                    'summary': (
                    f"{intro}\n\n{state_block}\n\nLocal agents: {agents}\n\n"
                    "My model is offline right now; this is a read-only state report."
                    ),
                    'evidence': [],
                    'proposed_changes': [],
                    'human_review_required': True,
                })
                tokens = 0

    if not is_read_only_agent(AGENT_NAME):
        try:
            from database import save_agent_memory
            save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                              tags=f'chat,shared-thread,{SEVEN_MODEL}', importance=6,
                              source='terminal_chat')
        except Exception:
            logger.exception('[Seven] conversation memory write failed')

    # ── Witness annotation: review user message + Seven response ────────
    # Saves callouts (with receipts) and, when enabled, appends a footer.
    try:
        from core import witness
        if witness.is_enabled():
            user_report = witness.review_user_msg(message or '', save=not is_read_only_agent(AGENT_NAME))
            seven_report = witness.review_seven_response(answer or '',
                                                         user_msg=message or '',
                                                         save=not is_read_only_agent(AGENT_NAME))
            footer_parts = []
            if user_report.callouts:
                u = witness.annotate(user_report)
                if u:
                    footer_parts.append(u.replace("— Seven's witness —",
                                                  "— Seven's witness · your message —"))
            s = witness.annotate(seven_report)
            if s:
                footer_parts.append(s.replace("— Seven's witness —",
                                              "— Seven's witness · my response —"))
            if footer_parts:
                answer = (answer or '').rstrip() + "\n" + "\n".join(footer_parts)
    except Exception:
        # Witness must never break chat. Silent on failure.
        pass

    logger.info(f'[Seven] response via {SEVEN_MODEL} | msg_len={len(message or "")}')
    from utils.local_runtime_policy import normalize_read_only_response

    return normalize_read_only_response(AGENT_NAME, answer), tokens
