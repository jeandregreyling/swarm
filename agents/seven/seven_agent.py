"""
agents/seven/seven_agent.py — Qwen3.6 (Agent 18)
Personal companion agent. Powered by Qwen3.6.
Served via Ollama as 'qwen3:latest'.
"""
import logging, sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
logger = logging.getLogger('seven.seven')
AGENT_NAME = 'seven'
MODEL      = 'qwen3:latest'


def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = []
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp     = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append(f'Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp}')
    except Exception:
        pass
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5) or []
    if mems:
        lines.append(f"\n=== Seven's memory ===")
        for m in mems:
            m = dict(m)
            lines.append(f"[{str(m.get('created_at',''))[:16]}] {m.get('subject','')}: {str(m.get('content',''))[:200]}")
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    try:
        import ollama as _ollama
    except ImportError:
        return '[seven] ollama package not installed', 0

    from config import SEVEN_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system  = SEVEN_SYSTEM_PROMPT + f'\n\n{context}' if context else SEVEN_SYSTEM_PROMPT

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        # Strip routing prefixes ("User -> Seven: ...", "Seven -> User: ...")
        # that confuse the merged model into hallucinating multi-agent routing.
        import re
        _route_re = re.compile(r'^[\w]+(?:\s*->\s*[\w]+)?:\s*', re.IGNORECASE)
        for entry in conversation_history[-8:]:
            cleaned = dict(entry)
            cleaned['content'] = _route_re.sub('', str(cleaned.get('content', '')), count=1)
            if cleaned['content'].strip():
                messages.append(cleaned)
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        chunks, token_count, tokens = [], 0, 0
        try:
            stream = _ollama.chat(
                model=MODEL, messages=msgs,
                options={'temperature': 0.6}, keep_alive=-1, stream=True,
            )
            for chunk in stream:
                part = (chunk.get('message') or {}).get('content') or ''
                if part:
                    chunks.append(part)
                    token_count += 1
                    if token_count % 15 == 0:
                        _emit(f'generating · {("".join(chunks))[-300:]}')
                if chunk.get('done'):
                    tokens = int(chunk.get('eval_count') or 0)
        except Exception as exc:
            logger.warning(f'[Seven] stream fallback: {exc}')
            resp = _ollama.chat(model=MODEL, messages=msgs, options={'temperature': 0.6}, keep_alive=-1)
            """
            agents/seven/seven_agent.py — Seven (local-algorithm)
            The nervous system of the Swarm. Observes, deliberates, and speaks without an LLM.
            Reads DB state directly and synthesises a deterministic, structured response.
            """
            import logging, sys, re as _re, random
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
                                    'what\'s happening', 'how is', 'health']):
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
