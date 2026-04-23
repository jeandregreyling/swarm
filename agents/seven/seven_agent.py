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
# status/identity probes. qwen2.5:0.5b (~400 MB) keeps him resident without
# touching the CPU budget that Duck/Librarian/Gemma need. The earlier custom
# merged GGUF (seven:latest = Qwen 2.5 7B + DeepSeek-R1-Distill-Qwen-7B) is
# shelved pending a rebuild — output was incoherent (repetition, token leakage).
# Override with SEVEN_MODEL env var to test other backends.
SEVEN_MODEL = os.environ.get('SEVEN_MODEL', 'qwen2.5:0.5b')


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


def _compose(message, state, memories):
    msg = (message or '').strip()
    intro = random.choice(_INTROS)
    state_block = _format_state_block(state)
    agents = ', '.join(state.get('local_agents', [])) or 'none listed'

    # Identity / what are you
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

    system = (
        f"{SEVEN_SYSTEM_PROMPT}\n\n"
        f"LIVE SWARM STATE (for your awareness — only mention if relevant):\n{state_block}\n"
        f"Local agents online: {agents}\n\n"
        f"RELEVANT MEMORY:\n{mem_block}\n\n"
        f"KNOWLEDGE CENTER (auto-maintained project/step docs — cite these when answering Fridays questions):\n{kc_block}"
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
        return None, 0


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
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

    logger.info(f'[Seven] local-algorithm response | msg_len={len(message or "")}')
    return answer, tokens
