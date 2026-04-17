"""
agents/ghost_coder/ghost_coder_agent.py — Ghost Coder (Agent #17)
═══════════════════════════════════════════════════════════════════════
Code-aware AI agent for Fridays. Bridges the gap between VS Code Copilot
and the Swarm — reads files, writes patches, runs shell commands, searches
memory, and holds persistent context across conversations.

Powered by Claude Sonnet via Anthropic API. Uses the existing skills_loop
for tool execution (fs_readonly, fs_patch_lines, shell, memory_search, etc).

LINKED TO: utils/config.py — imports GHOST_CODER_SYSTEM_PROMPT
"""

import logging
import os
import sys
import subprocess

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

logger = logging.getLogger('seven.ghost_coder')

AGENT_NAME = 'ghost_coder'

# Circuit breaker: skip Anthropic for 5 minutes after a billing failure
_anthropic_backoff_until = 0.0
# Circuit breaker: skip OpenAI for 5 minutes after a rate-limit failure
_openai_backoff_until = 0.0

# ── Project context builder ─────────────────────────────────────────────────

def _build_context(message):
    """Build rich project-aware context for the coder agent."""
    from database import get_connection, get_agent_memory

    lines = ['=== Ghost Coder — Project Context ===']

    # Current environment
    env = os.environ.get('SWARM_ENV', 'prod').upper()
    lines.append(f'Environment: {env}')
    lines.append(f'Working directory: /home/seven/swarm')

    # Git status snapshot
    try:
        branch = subprocess.check_output(
            ['git', 'branch', '--show-current'],
            cwd='/home/seven/swarm', timeout=5, text=True
        ).strip()
        lines.append(f'Git branch: {branch}')
    except Exception:
        lines.append('Git branch: (unknown)')

    try:
        status = subprocess.check_output(
            ['git', 'status', '--short'],
            cwd='/home/seven/swarm', timeout=5, text=True
        ).strip()
        if status:
            # Limit to 20 lines to save tokens
            status_lines = status.splitlines()[:20]
            lines.append(f'Git status ({len(status.splitlines())} files):')
            for sl in status_lines:
                lines.append(f'  {sl}')
            if len(status.splitlines()) > 20:
                lines.append(f'  ... and {len(status.splitlines()) - 20} more')
        else:
            lines.append('Git status: clean')
    except Exception:
        pass

    conn = get_connection()
    try:
        # Recent work proposals (what's been changed lately)
        proposals = conn.execute(
            "SELECT proposal_id, agent, title, status, created_at FROM work_proposals "
            "ORDER BY id DESC LIMIT 8"
        ).fetchall()
        if proposals:
            lines.append('\n=== Recent work proposals ===')
            for p in proposals:
                lines.append(
                    f"  [{p['proposal_id']}] {p['agent']}: {p['title'][:60]} | {p['status']}"
                )

        # Recent decisions
        decisions = conn.execute(
            "SELECT decision_id, agent, decision, test_status, created_at "
            "FROM decisions ORDER BY decision_id DESC LIMIT 5"
        ).fetchall()
        if decisions:
            lines.append('\n=== Recent decisions ===')
            for d in decisions:
                lines.append(
                    f"  [{d['decision_id']}] {d['agent']} | {d['test_status']} | "
                    f"{d['decision'][:80]}"
                )

        # Active agents summary
        agents = conn.execute(
            "SELECT name, model, tier, enabled FROM agents WHERE enabled=1 ORDER BY number"
        ).fetchall()
        if agents:
            lines.append(f'\n=== Active agents ({len(agents)}) ===')
            for a in agents:
                lines.append(f"  {a['name']:15s} model={a['model']:30s} tier={a['tier']}")

    finally:
        conn.close()

    # Agent memory — relevant to this query
    relevant = get_agent_memory(AGENT_NAME, query=message[:160], limit=6)
    if relevant:
        lines.append('\n=== Ghost Coder memory (relevant) ===')
        for m in relevant:
            m = dict(m)
            lines.append(
                f"[{str(m.get('created_at', ''))[:16]}] "
                f"{m.get('subject', '')}: {str(m.get('content', ''))[:300]}"
            )

    return '\n'.join(lines)


# ── Chat entry point ────────────────────────────────────────────────────────

def chat(message, conversation_history=None, stage_cb=None, conv_id=None):
    """
    Send a message to Ghost Coder (Claude Sonnet). Returns (answer, tokens_used).

    This agent has full code-awareness: it can read files, write patches,
    run shell commands, search memory, and create proposals — all through
    the standard SKILL framework.
    """
    def _emit(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        import anthropic
    except ImportError:
        return '[ghost_coder] anthropic package not installed', 0

    from claude_api import _load_api_key
    from config import GHOST_CODER_SYSTEM_PROMPT

    api_key = _load_api_key()

    _emit('building project context')
    context = _build_context(message)
    system = GHOST_CODER_SYSTEM_PROMPT + f'\n\n{context}'

    messages = []
    if conversation_history:
        messages.extend(conversation_history[-12:])
    messages.append({'role': 'user', 'content': message})

    # Try Anthropic first, fall back to OpenAI if credits are depleted
    backend_used = 'anthropic'

    def _try_anthropic():
        if not api_key:
            return None
        try:
            client = anthropic.Anthropic(api_key=api_key)

            def _api_call(msgs):
                resp = client.messages.create(
                    model='claude-sonnet-4-20250514',
                    max_tokens=8192,
                    system=system,
                    messages=msgs,
                )
                return resp.content[0].text, resp.usage.input_tokens + resp.usage.output_tokens

            return _api_call
        except Exception:
            return None

    def _try_openai():
        try:
            from openai import OpenAI
            from config import GITHUB_TOKEN
            if not GITHUB_TOKEN:
                return None
            client = OpenAI(
                api_key=GITHUB_TOKEN,
                base_url='https://models.inference.ai.azure.com',
            )

            def _api_call(msgs):
                full_msgs = [{'role': 'system', 'content': system}] + msgs
                resp = client.chat.completions.create(
                    model='gpt-4.1',
                    max_tokens=8192,
                    messages=full_msgs,
                )
                return resp.choices[0].message.content, resp.usage.total_tokens

            return _api_call
        except Exception:
            return None

    def _try_xai():
        try:
            from openai import OpenAI
            from config import XAI_API_KEY
            if not XAI_API_KEY:
                return None
            client = OpenAI(
                api_key=XAI_API_KEY,
                base_url='https://api.x.ai/v1',
            )

            def _api_call(msgs):
                full_msgs = [{'role': 'system', 'content': system}] + msgs
                resp = client.chat.completions.create(
                    model='grok-3',
                    max_tokens=8192,
                    messages=full_msgs,
                )
                return resp.choices[0].message.content, resp.usage.total_tokens

            return _api_call
        except Exception:
            return None

    # Attempt Anthropic first (unless circuit breaker is active)
    import time as _time
    global _anthropic_backoff_until
    _api_call = None
    if _time.time() >= _anthropic_backoff_until:
        _api_call = _try_anthropic()
    else:
        logger.info('[Ghost Coder] Anthropic circuit breaker active — skipping to OpenAI')

    if _api_call:
        _emit('reasoning · Claude Sonnet')
        try:
            # Test with a quick call to detect credit issues early
            from agents.skills_loop import run_skill_loop
            answer, tokens = run_skill_loop(
                agent_name=AGENT_NAME,
                call_fn=_api_call,
                messages=messages,
                emit_fn=_emit,
                max_passes=5,
                source_conv_id=conv_id,
            )
            # Check if the answer indicates a billing failure
            if 'credit balance' not in answer.lower():
                _emit('persisting memory')
                _persist_memory(message, answer)
                logger.info(f'[Ghost Coder] anthropic tokens={tokens} | {message[:60]}')
                return answer, tokens
            # Fall through to OpenAI
            logger.warning('[Ghost Coder] Anthropic credits depleted, trying OpenAI')
            _anthropic_backoff_until = _time.time() + 300  # 5 min
        except Exception as e:
            err = str(e).lower()
            if 'credit' in err or 'billing' in err or '402' in err:
                logger.warning('[Ghost Coder] Anthropic credits depleted, trying OpenAI')
                _anthropic_backoff_until = _time.time() + 300
            else:
                return f'[ghost_coder] Anthropic error: {e}', 0

    # Fallback to OpenAI
    global _openai_backoff_until
    if _time.time() >= _openai_backoff_until:
        _api_call = _try_openai()
    else:
        _api_call = None
        logger.info('[Ghost Coder] OpenAI circuit breaker active — skipping to Grok')

    if _api_call:
        backend_used = 'openai'
        _emit('reasoning · GPT-4.1 (fallback)')
        try:
            from agents.skills_loop import run_skill_loop
            answer, tokens = run_skill_loop(
                agent_name=AGENT_NAME,
                call_fn=_api_call,
                messages=messages,
                emit_fn=_emit,
                max_passes=5,
                source_conv_id=conv_id,
            )
            _emit('persisting memory')
            _persist_memory(message, answer)
            logger.info(f'[Ghost Coder] openai tokens={tokens} | {message[:60]}')
            return answer, tokens
        except Exception as e:
            err_msg = str(e)
            if '429' in err_msg or 'RateLimitReached' in err_msg:
                logger.warning('[Ghost Coder] OpenAI rate limited, trying Grok')
                _openai_backoff_until = _time.time() + 300  # 5 min
            else:
                return f'[ghost_coder] OpenAI error: {e}', 0

    # Fallback to Grok-3 (XAI)
    _api_call = _try_xai()
    if _api_call:
        backend_used = 'xai'
        _emit('reasoning · Grok-3 (fallback)')
        try:
            from agents.skills_loop import run_skill_loop
            answer, tokens = run_skill_loop(
                agent_name=AGENT_NAME,
                call_fn=_api_call,
                messages=messages,
                emit_fn=_emit,
                max_passes=5,
                source_conv_id=conv_id,
            )
            _emit('persisting memory')
            _persist_memory(message, answer)
            logger.info(f'[Ghost Coder] xai tokens={tokens} | {message[:60]}')
            return answer, tokens
        except Exception as e:
            return f'[ghost_coder] Grok error: {e}', 0

    return '[ghost_coder] No API backend available (all backends exhausted)', 0


def _persist_memory(message, answer):
    """Save response to agent memory."""
    try:
        from database import save_agent_memory
        save_agent_memory(
            agent_name=AGENT_NAME,
            subject=str(message or '')[:100],
            content=answer,
            tags='chat,code,shared-thread',
            importance=7,
            source='terminal_chat',
        )
    except Exception:
        pass
