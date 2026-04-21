"""
agents/seven/seven_agent.py — Seven (local-algorithm)
The nervous system of the Swarm. Observes, deliberates, and speaks without an LLM.
Reads DB state directly and synthesises a deterministic, structured response.
"""
import logging
import random
import sys

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.seven')
AGENT_NAME = 'seven'


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

    # Status / queue / tickets
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

    # Agent / team query
    if _is_about(msg, ['agent', 'team', 'who is', 'list', 'agents', 'roster']):
        return (
            f"{intro}\n\n"
            f"Local agents I coordinate: {agents}\n\n"
            f"{state_block}\n\n"
            "I manage routing between all of them. Select any agent in this chat to speak directly with them."
        ), 0

    # Memory / history
    if memories and _is_about(msg, ['remember', 'recall', 'history', 'last time', 'previous', 'before']):
        lines = [f"{intro}\n\nFrom memory:"]
        for m in memories[:3]:
            subj = str(m.get('subject') or '').strip()[:80]
            body = str(m.get('content') or '').strip()[:300]
            lines.append(f"  [{subj}]: {body}")
        return '\n'.join(lines), 0

    # Fallback: general system read
    return (
        f"{intro}\n\n"
        f"{state_block}\n\n"
        f"Local agents: {agents}\n\n"
        f"Your message arrived at the algorithm layer. I do not interpret language — "
        f"I observe structure. For a conversational response, route to one of the agents above."
    ), 0


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

    try:
        from database import save_agent_memory
        save_agent_memory(AGENT_NAME, str(message or '')[:100], answer,
                          tags='chat,shared-thread,local-algorithm', importance=6,
                          source='terminal_chat')
    except Exception:
        pass

    logger.info(f'[Seven] local-algorithm response | msg_len={len(message or "")}')
    return answer, tokens
