"""
agents/skills_loop.py — Shared SKILL execution loop for paid Developer Agents.

Nine, Eleven, Twelve, and Thirteen all use this module to gain real tool-execution
capability. When a model emits a SKILL line, the runtime intercepts it, runs the
skill, and feeds the output back for a synthesised final answer.

Usage
-----
    from agents.skills_loop import run_skill_loop

    def _api_call(msgs):
        resp = client.chat.completions.create(model=MODEL, messages=msgs, max_tokens=4096)
        return resp.choices[0].message.content, resp.usage.total_tokens

    answer, tokens = run_skill_loop(
        agent_name='nine',
        call_fn=_api_call,
        messages=messages,        # full list, may include system role
        emit_fn=_emit,
        max_passes=3,
    )

For Anthropic (Twelve), pass a `call_fn` that accepts a message list WITHOUT the
system entry and handles `system=` internally via closure.

call_fn signature
-----------------
    call_fn(messages: list[dict]) -> (content: str, tokens: int)

The loop appends assistant + user result turns to a working copy of `messages` on
each SKILL pass so the model always sees the full conversation including prior
skill results.
"""

import logging

logger = logging.getLogger('seven.skills_loop')

_MAX_SKILL_CMDS_PER_PASS = 4
_MAX_SKILL_OUTPUT_CHARS  = 8000


def _extract_skill_cmds(text):
    """
    Parse SKILL / /SKILL command lines from model output.
    Returns list of (skill_name, skill_args) tuples, capped at _MAX_SKILL_CMDS_PER_PASS.
    Skips the meta 'list' command (just asks what skills exist).
    """
    try:
        from fridays.skills import parse_skill_command
    except Exception:
        return []

    cmds = []
    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith('SKILL '):
            parsed = parse_skill_command(line)
        elif line.upper().startswith('/SKILL '):
            parsed = parse_skill_command('SKILL ' + line[7:].strip())
        else:
            continue
        if not parsed:
            continue
        skill_name, skill_args = parsed
        if skill_name == 'list':
            continue
        cmds.append((skill_name, skill_args))
        if len(cmds) >= _MAX_SKILL_CMDS_PER_PASS:
            break
    return cmds


def _execute_skill_cmds(cmds, agent_name, emit_fn):
    """Execute a list of (skill_name, skill_args) pairs. Returns joined output string."""
    try:
        from fridays.skills import call as skill_call
    except Exception as e:
        return f'[skills] import error: {e}'

    parts = []
    for skill_name, skill_args in cmds:
        emit_fn(f'executing skill: {skill_name}')

        # Optional per-agent permission check (non-fatal if missing)
        try:
            from database import can_user_invoke_skill
            if not can_user_invoke_skill(agent_name, skill_name, default_allow=True):
                parts.append(f'[skill:{skill_name}] FAILED\nNot authorized for agent {agent_name}')
                continue
        except Exception:
            pass

        try:
            ok, out = skill_call(skill_name, args=skill_args, agent=agent_name)
        except Exception as exc:
            parts.append(f'[skill:{skill_name}] ERROR\n{exc}')
            continue

        preview = str(out or '')[:_MAX_SKILL_OUTPUT_CHARS]
        parts.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\n{preview}")

    return '\n\n'.join(parts)


def run_skill_loop(agent_name, call_fn, messages, emit_fn, max_passes=3):
    """
    Execute `call_fn(messages)` with SKILL command interception and re-prompting.

    Parameters
    ----------
    agent_name : str
        Identifies which agent is calling (used for auth checks and logging).
    call_fn : callable
        Signature: (messages: list[dict]) -> (content: str, tokens: int).
        For OpenAI-compat agents pass the full messages list including system.
        For Anthropic (Twelve) pass a closure that handles `system=` internally.
    messages : list[dict]
        Starting message list.  The loop works on a local copy; the caller's
        original list is never mutated.
    emit_fn : callable
        Signature: (text: str) -> None.  Used to push stage labels to the UI.
    max_passes : int
        Maximum SKILL execution rounds before returning whatever the model said.

    Returns
    -------
    (answer: str, tokens: int)
    """
    working_messages = list(messages)
    total_tokens = 0

    emit_fn('sending model request')
    try:
        first_content, tokens = call_fn(working_messages)
    except Exception as exc:
        logger.error(f'[{agent_name}] skills_loop first call error: {exc}')
        raise

    total_tokens += tokens
    answer = first_content

    for _pass in range(max_passes):
        skill_cmds = _extract_skill_cmds(answer)
        if not skill_cmds:
            break  # model is done — no skills requested

        emit_fn('running requested skills')
        skill_results = _execute_skill_cmds(skill_cmds, agent_name, emit_fn)

        logger.debug(
            f'[{agent_name}] pass {_pass + 1}: ran {len(skill_cmds)} skill(s); '
            f'result preview: {skill_results[:120]}'
        )

        # Append turn pair so the model sees its own skill requests + results
        working_messages = working_messages + [
            {'role': 'assistant', 'content': answer},
            {
                'role': 'user',
                'content': (
                    'Executed skill outputs are below. Use these concrete results to produce '
                    'your final answer. Do not re-request the same skill commands.\n\n'
                    + skill_results
                ),
            },
        ]

        emit_fn('synthesizing final answer')
        try:
            answer, tokens = call_fn(working_messages)
        except Exception as exc:
            logger.error(f'[{agent_name}] skills_loop pass {_pass + 2} error: {exc}')
            # Return whatever we have so far rather than crashing
            answer = (answer or '') + f'\n\n[skills_loop error on pass {_pass + 2}: {exc}]'
            break
        total_tokens += tokens

    return answer, total_tokens
