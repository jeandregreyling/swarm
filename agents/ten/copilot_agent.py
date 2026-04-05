"""
# LINKED TO: utils/config.py — imports TEN_SYSTEM_PROMPT (edit prompts there, not here)
agents/ten/copilot_agent.py — Ten (GPT)
Developer Agent — software engineer. Powered by GPT via GitHub Models API.
Uses a GitHub PAT with models:read scope via https://models.inference.ai.azure.com

Supports the same SKILL execution loop as Nine: GPT emits SKILL commands,
the runtime executes them and feeds results back for a final synthesised answer.
Stage callbacks stream progress to the Fridays chat UI in real time.
"""

import logging
import re
import sys
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.ten')

AGENT_NAME = 'ten'
_DEFAULT_MODEL = 'gpt-4.1'


def _build_context(message):
    """Build swarm context snapshot for Ten."""
    from database import get_connection, get_agent_memory
    lines = []
    lines.append('=== Governance rules (ALM) ===')
    lines.append('Mutating changes require approved work proposals (approved/executed).')
    lines.append('Use proposal-first guidance and include proposal IDs for execution paths.')
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        wp_pending = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
        lines.append('=== Swarm state ===')
        lines.append(f"Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp_pending}")
    except Exception:
        pass
    finally:
        conn.close()

    try:
        recent = get_agent_memory('ten', query='', limit=5) or []
        if recent:
            lines.append('=== Your recent memory (most important first) ===')
            for row in recent:
                subj = str(row.get('subject') or '').strip()[:120]
                body = str(row.get('content') or '').strip()[:400]
                lines.append(f'- [{subj}] {body}')
            lines.append('=== End memory ===')
            lines.append('Use this for continuity but do not narrate or repeat it verbatim.')
    except Exception:
        pass

    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    """
    Send a message to Ten (GPT via GitHub Models API).

    Supports a two-pass SKILL execution loop:
      Pass 1 — GPT responds; if it emits SKILL lines, they are executed.
      Pass 2 — skill outputs are fed back; GPT synthesises a final answer.

    stage_cb(text, eta_seconds) — called throughout to push progress to the UI.

    Returns (answer, tokens_used).
    """
    def _emit_stage(text):
        if callable(stage_cb):
            try:
                stage_cb(text, None)
            except Exception:
                pass

    try:
        from openai import OpenAI
    except ImportError:
        logger.error('[Ten] openai package not installed')
        return None, 0

    from config import GITHUB_TOKEN, TEN_SYSTEM_PROMPT, TEN_MODEL
    if not GITHUB_TOKEN:
        logger.error('[Ten] GITHUB_TOKEN not configured — add to .env.agents')
        return None, 0

    _emit_stage('loading ghost-layer memory')
    context = _build_context(message)
    system = TEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    # ── Skill extraction ───────────────────────────────────────────────────────
    def _extract_skill_lines(text):
        """Parse SKILL / /SKILL command lines from GPT output. Max 4."""
        from fridays.skills import parse_skill_command
        cmds = []
        for raw_line in str(text or '').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed = None
            if line.upper().startswith('SKILL '):
                parsed = parse_skill_command(line)
            elif line.upper().startswith('/SKILL '):
                parsed = parse_skill_command('SKILL ' + line[7:].strip())
            if not parsed:
                continue
            skill_name, skill_args = parsed
            if skill_name == 'list':
                continue
            cmds.append((skill_name, skill_args))
        return cmds[:4]

    def _run_skill_lines(cmds):
        """Execute a list of (skill_name, skill_args) pairs. Returns joined output string."""
        from fridays.skills import call as skill_call

        lines = []
        for skill_name, skill_args in cmds:
            _emit_stage(f'executing skill: {skill_name}')

            try:
                from database import can_user_invoke_skill
                if not can_user_invoke_skill('ten', skill_name, default_allow=True):
                    lines.append(f'[skill:{skill_name}] FAILED\nNot authorized for agent ten')
                    continue
            except Exception:
                pass

            ok, out = skill_call(skill_name, args=skill_args, agent='ten')
            preview = str(out or '')[:8000]
            lines.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\n{preview}")

        return '\n\n'.join(lines)

    # ── API calls ──────────────────────────────────────────────────────────────
    try:
        client = OpenAI(
            api_key=GITHUB_TOKEN,
            base_url='https://models.inference.ai.azure.com',
        )
        model = TEN_MODEL or _DEFAULT_MODEL

        _emit_stage('sending model request')
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
        )
        first_answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0

        answer = first_answer
        skill_cmds = _extract_skill_lines(first_answer)

        if skill_cmds:
            _emit_stage('running requested skills')
            skill_results = _run_skill_lines(skill_cmds)

            followup_messages = messages + [
                {'role': 'assistant', 'content': first_answer},
                {
                    'role': 'user',
                    'content': (
                        'Executed skill outputs are below. Use these concrete results to produce '
                        'your final answer. Do not ask to run the same commands again.\n\n'
                        + skill_results
                    ),
                },
            ]
            _emit_stage('synthesizing final answer')
            second = client.chat.completions.create(
                model=model,
                messages=followup_messages,
                max_tokens=4096,
            )
            answer = second.choices[0].message.content + '\n\n---\nExecuted skill output:\n' + skill_results
            tokens += second.usage.total_tokens if second.usage else 0

        _emit_stage('persisting response memory')
        try:
            from database import save_agent_memory
            save_agent_memory(
                agent_name='ten',
                subject=str(message or '')[:100],
                content=answer,
                tags='chat,shared-thread',
                importance=7,
                source='terminal_chat',
            )
        except Exception:
            pass

        logger.info(f'[Ten] model={model} tokens={tokens} | {str(message or "")[:60]}')
        return answer, tokens

    except Exception as e:
        msg = str(e)
        logger.error(f'[Ten] API error: {msg}')
        if 'RateLimitReached' in msg or '429' in msg or 'rate limit' in msg.lower():
            return f'[Ten] GitHub Models rate limit reached (50 req/day free tier). Resets in ~24h. Error: {msg}', 0
        if '401' in msg or 'Unauthorized' in msg or 'authentication' in msg.lower():
            return '[Ten] GitHub token rejected (401). Regenerate PAT with Models scope at github.com/settings/tokens.', 0
        return f'[Ten] API error: {msg}', 0
