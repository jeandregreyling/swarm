"""
agents/seven/seven_agent.py — Seven
Personal companion + nervous-system observer.

Historically a pure local algorithm (deterministic templates). 2026-04-23 —
now LLM-backed for open conversation while keeping fast state templates for
status/identity queries. The model is the custom merge (seven:latest =
Qwen 2.5 7B + DeepSeek-R1-Distill-Qwen-7B) registered in Ollama.
"""
import logging
import os
import random
import sys

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.seven')
AGENT_NAME = 'seven'
# 2026-04-23 — Seven scoped as the in-house "paperclip": tiny, always-hot,
# lives in the system to nudge orbs, flip the "?" glyph, and answer quick
# status/identity probes. Switched from qwen2.5:0.5b (~400 MB, too small to
# reason) to phi3:mini (~2.3 GB) per Ghost's feedback — still cheap but able
# to hold a conversation. The earlier custom merged GGUF (seven:latest = Qwen
# 2.5 7B + DeepSeek-R1-Distill-Qwen-7B) is shelved pending a rebuild.
# Override with SEVEN_MODEL env var to test other backends.
SEVEN_MODEL = os.environ.get('SEVEN_MODEL', 'phi3:mini')


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
)
_CURIOSITY_NATTY = (
    'what are you asking', 'what are you wondering', 'what questions',
    'open questions', 'curiosity', 'what don\'t you know', 'what dont you know',
    "what's open", 'whats open', 'inbox', 'unanswered', 'pending questions',
    'your questions',
)


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
                subj = str(m.get('subject') or '').strip()[:80]
                body = str(m.get('content') or '').strip()[:200]
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

    # For anything else — signal to caller to route through the LLM.
    return None, 0


def _llm_chat(message, state, memories, history):
    """Call Seven's merged Ollama model with system prompt + live context.
    Returns (text, tokens) or (None, 0) on failure.
    """
    try:
        from utils.config import SEVEN_SYSTEM_PROMPT
    except Exception:
        SEVEN_SYSTEM_PROMPT = (
            "You are Seven — the personal companion AI for Ghost One (Jeandre). "
            "Be direct, honest, and loyal. No filler openers. Have opinions."
        )
    try:
        import ollama
    except Exception as exc:
        logger.warning(f"[Seven] ollama import failed: {exc}")
        return None, 0

    state_block = _format_state_block(state)
    agents = ', '.join(state.get('local_agents', [])) or 'none listed'
    mem_lines = []
    for m in (memories or [])[:3]:
        subj = str(m.get('subject') or '').strip()[:80]
        body = str(m.get('content') or '').strip()[:240]
        if subj or body:
            mem_lines.append(f"- [{subj}] {body}")
    mem_block = '\n'.join(mem_lines) if mem_lines else '(no relevant memory)'

    # Knowledge Center: Seven reads from the same docs the team writes.
    kc_docs = _load_kc_context(message, limit=4)
    kc_lines = [f"- [{d['doc_name']}] {d['snippet']}" for d in kc_docs if d.get('snippet')]
    kc_block = '\n'.join(kc_lines) if kc_lines else '(no knowledge docs matched)'

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
        self_awareness_block = _sa_block(max_chars=2200)
    except Exception:
        self_awareness_block = '(self-awareness module unavailable)'

    system = (
        f"{SEVEN_SYSTEM_PROMPT}\n\n"
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
        f"If the user is shipping slop OR if the bullshit detector reports critical/RED, say so plainly. "
        f"Hold the line on The Standard — a system that DOES, not a system that REPORTS."
    )

    msgs = [{'role': 'system', 'content': system}]
    for h in (history or [])[-6:]:
        role = h.get('role') or ('user' if h.get('sender') in (None, 'you', 'user') else 'assistant')
        content = h.get('content') or h.get('message') or ''
        if content:
            msgs.append({'role': role if role in ('user', 'assistant', 'system') else 'user',
                         'content': str(content)[:2000]})
    msgs.append({'role': 'user', 'content': str(message or '')})

    try:
        resp = ollama.chat(
            model=SEVEN_MODEL,
            messages=msgs,
            options={'temperature': 0.8, 'top_p': 0.9, 'num_ctx': 4096, 'num_predict': 640},
        )
        text = (resp or {}).get('message', {}).get('content', '') or ''
        tokens = int((resp or {}).get('eval_count') or 0)
        return text.strip(), tokens
    except Exception as exc:
        logger.warning(f"[Seven] ollama chat failed: {exc}")
        # PACKET-10B Curiosity: rather than fail silently, ask a question.
        # Dedup is built into curiosity.ask() so repeated outages don't spam.
        try:
            from core import curiosity
            curiosity.from_llm_failure(AGENT_NAME, message, exc, salience=0.4)
        except Exception:
            pass
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


# Static so /witness (without args) can pick up the most recent user turn.
_slash_command._last_user_msg = ""  # type: ignore[attr-defined]


def chat(message, conversation_history=None, stage_cb=None):
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
        handled = _slash_command(target, _emit)
        if handled is not None:
            return handled, 0

    # ── Self-learning: capture user reactions to the prior Seven turn ────
    try:
        from agents.seven import learnings
        prior_seven = None
        for h in reversed(conversation_history or []):
            role = h.get('role') or h.get('sender') or ''
            if role in ('assistant', 'seven', 'Seven'):
                prior_seven = h.get('content') or h.get('message')
                break
        if prior_seven:
            learnings.observe(message, prior_seven)
    except Exception:
        pass

    _emit('reading swarm state')
    state = _read_state()

    _emit('loading memory')
    memories = _load_memory(message)

    _emit('synthesising response')
    answer, tokens = _compose(message, state, memories)

    # Fast deterministic paths returned an answer (status/identity/roster).
    # Anything else → Seven's merged LLM.
    if answer is None:
        _emit('thinking · seven merged model')
        llm_text, llm_tokens = _llm_chat(message, state, memories, conversation_history or [])
        if llm_text:
            answer, tokens = llm_text, llm_tokens
        else:
            # Last-resort fallback: simple state read (prevents a silent fail).
            intro = random.choice(_INTROS)
            state_block = _format_state_block(state)
            agents = ', '.join(state.get('local_agents', [])) or 'none listed'
            answer = (
                f"{intro}\n\n{state_block}\n\nLocal agents: {agents}\n\n"
                "My model is offline right now — state read only."
            )
            tokens = 0

    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread,local-algorithm', importance=6,
                          source='terminal_chat')
    except Exception:
        pass

    # ── Witness annotation: review user message + Seven response ────────
    # Saves callouts (with receipts) and, when enabled, appends a footer.
    try:
        from core import witness
        if witness.is_enabled():
            user_report = witness.review_user_msg(message or '', save=True)
            seven_report = witness.review_seven_response(answer or '',
                                                         user_msg=message or '',
                                                         save=True)
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

    logger.info(f'[Seven] local-algorithm response | msg_len={len(message or "")}')
    return answer, tokens
