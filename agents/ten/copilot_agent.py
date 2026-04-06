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
    lines.append('=== Developer Agent context ===')
    lines.append('You are a Developer Agent operating under Ghost One direction. Execute directly — no proposal queue for Ghost One-directed work.')
    lines.append('Worker Agent requests still require proposal approval.')
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

    _emit_stage('loading context')
    context = _build_context(message)
    system = TEN_SYSTEM_PROMPT + f'\n\n{context}'

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({'role': 'user', 'content': message})

    # ── Skill extraction ───────────────────────────────────────────────────────
    def _extract_skill_lines(text):
        """
        Parse SKILL / /SKILL commands from GPT output. Max 6.
        Handles multi-line skills: a SKILL line followed by continuation lines
        (before the next SKILL or blank line) is joined so fs_patch with
        multi-line <<<OLD>>>...<<<NEW>>>... blocks are captured whole.
        """
        from fridays.skills import parse_skill_command
        raw = str(text or '')
        lines = raw.splitlines()
        cmds = []

        i = 0
        while i < len(lines) and len(cmds) < 6:
            line = lines[i].strip()
            is_skill = line.upper().startswith('SKILL ') or line.upper().startswith('/SKILL ')
            if not is_skill:
                i += 1
                continue

            # Collect continuation lines (multi-line fs_patch blocks).
            # For fs_patch: <<<OLD>>>...content...<<<NEW>>>...new content...
            # Do NOT stop when <<<NEW>>> appears — new content follows it.
            # Let blank lines and next SKILL commands terminate the block.
            collected = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_stripped = nxt.strip()
                # Stop collecting if blank line or next SKILL command
                if not nxt_stripped:
                    break
                if nxt_stripped.upper().startswith('SKILL ') or nxt_stripped.upper().startswith('/SKILL '):
                    break
                collected.append(nxt)
                i += 1

            full_line = ' '.join(collected) if len(collected) == 1 else '\n'.join(collected)
            # Normalise /SKILL prefix
            if full_line.strip().upper().startswith('/SKILL '):
                full_line = 'SKILL ' + full_line.strip()[7:]

            parsed = parse_skill_command(full_line.strip())
            if not parsed:
                continue
            skill_name, skill_args = parsed
            if skill_name == 'list':
                continue
            cmds.append((skill_name, skill_args))

        return cmds

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
                        'Skill outputs below.\n'
                        'IMPORTANT: If the original request was a code/file change and you now have '
                        'enough information, emit SKILL fs_patch NOW to apply it. '
                        'The <<<OLD>>> text MUST be copied EXACTLY character-for-character from the '
                        'skill output above — including all lines in the block (whitespace, background, etc). '
                        'Do NOT reconstruct or abbreviate the OLD text — copy it verbatim from the output. '
                        'Only produce a text final answer if no file change is needed.\n\n'
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
            second_answer = second.choices[0].message.content
            tokens += second.usage.total_tokens if second.usage else 0

            # Passes 3-5: keep executing skill chains until no more skills or max passes
            all_results = skill_results
            current_messages = followup_messages
            current_answer = second_answer
            current_tokens = tokens

            for _pass in range(3):  # up to 3 more passes (total 5)
                next_cmds = _extract_skill_lines(current_answer)
                if not next_cmds:
                    break
                _emit_stage('running follow-up skills')
                next_results = _run_skill_lines(next_cmds)
                all_results += '\n\n' + next_results

                next_messages = current_messages + [
                    {'role': 'assistant', 'content': current_answer},
                    {
                        'role': 'user',
                        'content': (
                            'Skill outputs below.\n'
                            'IMPORTANT: If the original request was a code/file change and you now have '
                            'enough information, emit SKILL fs_patch NOW to apply it. '
                            'The <<<OLD>>> text MUST be copied EXACTLY from the skill output — every line, '
                            'including background, border, and any other properties in the block. '
                            'If you just applied a patch, confirm with SKILL fs_readonly lines. '
                            'Only produce a final text answer when all changes are done and verified.\n\n'
                            + next_results
                        ),
                    },
                ]
                _emit_stage('synthesizing final answer')
                next_resp = client.chat.completions.create(
                    model=model,
                    messages=next_messages,
                    max_tokens=4096,
                )
                current_answer = next_resp.choices[0].message.content
                current_tokens += next_resp.usage.total_tokens if next_resp.usage else 0
                current_messages = next_messages

            tokens = current_tokens
            answer = current_answer + '\n\n---\nSkill outputs:\n' + all_results

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
