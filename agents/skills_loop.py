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
        max_passes=5,
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

_MAX_SKILL_CMDS_PER_PASS  = 6
_MAX_SKILL_OUTPUT_CHARS   = 8000  # default; override via max_skill_chars arg
_SKILL_NUDGE = (
    'Your response did not contain any SKILL commands.\n'
    'If this request requires reading or modifying files, emit the SKILL commands now.\n'
    'Start with SKILL fs_readonly grep to find values by pattern — do NOT read files line by line from the top.\n'
    'Do NOT describe what you plan to do — emit the SKILL line directly.\n'
    'Key directories (in order of relevance for backend/config tasks):\n'
    '  frontend/blueprints/   ← backend Python: agent dispatch, timeouts, routes\n'
    '  agents/                ← agent implementations\n'
    '  utils/                 ← config and system prompts\n'
    '  frontend/static/js/views/ ← frontend JS\n'
    'Example workflow:\n'
    '  SKILL fs_readonly grep frontend/blueprints/chat.py 900        ← find 900 instantly\n'
    '  SKILL fs_readonly lines frontend/blueprints/chat.py 825 875   ← read context\n'
    'Never read a whole file from line 1 when you can grep for the value.\n'
    'Never guess paths that do not appear in ls output (backend/, config/, src/ do not exist).\n'
    'If this request needed no file access, respond with your final answer and ignore this message.'
)


def _extract_skill_cmds(text):
    """
    Parse SKILL / /SKILL commands from model output.
    Handles multi-line skill blocks so that fs_patch with multi-line
    <<<OLD>>>...<<<NEW>>>... delimiters is captured as a single command.
    Returns list of (skill_name, skill_args) tuples, capped at _MAX_SKILL_CMDS_PER_PASS.
    """
    try:
        from fridays.skills import parse_skill_command
    except Exception:
        return []

    lines = str(text or '').splitlines()
    cmds = []
    i = 0

    while i < len(lines) and len(cmds) < _MAX_SKILL_CMDS_PER_PASS:
        line = lines[i].strip()
        is_skill = line.upper().startswith('SKILL ') or line.upper().startswith('/SKILL ')
        if not is_skill:
            i += 1
            continue

        # Collect continuation lines for multi-line skills (e.g. fs_patch blocks).
        # Rules:
        # - Inside <<<OLD>>> content: blank lines are legitimate code and must NOT
        #   terminate collection.
        # - Inside <<<NEW>>> content: same for blank lines, BUT stop if we hit an
        #   unindented line that starts with an uppercase letter followed by a space
        #   — that pattern is prose commentary the model writes between skill calls,
        #   never valid code at column 0 (JS is always indented; CSS selectors start
        #   with '.', '#', '@', or lowercase).
        # - The next SKILL command always terminates unconditionally.
        collected = [line]
        i += 1
        in_patch_block = False  # True once we've seen <<<OLD>>> or <<<NEW>>>
        in_new_block = False    # True once we've seen <<<NEW>>> (enables prose guard)

        while i < len(lines):
            nxt = lines[i]
            nxt_stripped = nxt.strip()

            # Detect entry into patch block delimiters
            nxt_up = nxt_stripped.upper()
            if '<<<OLD>>>' in nxt_up:
                in_patch_block = True
            if '<<<NEW>>>' in nxt_up:
                in_patch_block = True
                in_new_block = True

            # A following SKILL command always ends the current block
            if nxt_up.startswith('SKILL ') or nxt_up.startswith('/SKILL '):
                break

            # After <<<NEW>>>: stop on unindented prose commentary.
            # Rules — break if the line at column 0 looks like prose, not code:
            #   • Uppercase letter + space  ("Now I'll update...")
            #   • Numbered list item        ("2. **Verifying the Patch**:")
            #   • Bold markdown             ("**Note:**")
            #   • Markdown header           ("### Summary")
            # Valid code is never unindented prose: Python/JS is always indented;
            # CSS selectors start with '.', '#', '@', or lowercase.
            if in_new_block and nxt and not nxt[0].isspace():
                c = nxt[0]
                # Uppercase start + space
                if c.isupper() and len(nxt) > 1 and nxt[1] == ' ':
                    break
                # Numbered list: "1. " / "2. " etc.
                if c.isdigit() and len(nxt) > 2 and nxt[1] == '.' and nxt[2] == ' ':
                    break
                # Bold / italic markdown: "**" or "*word"
                if nxt.startswith('**') or (c == '*' and len(nxt) > 1 and nxt[1] != ' '):
                    break
                # Markdown header: "# " / "## "
                if c == '#' and len(nxt) > 1 and nxt[1] in ('# ', ' '):
                    break

            # Blank lines end the block only when we're NOT inside a patch block
            if not in_patch_block and not nxt_stripped:
                break

            collected.append(nxt)
            i += 1

        full = '\n'.join(collected)
        if full.strip().upper().startswith('/SKILL '):
            full = 'SKILL ' + full.strip()[7:]

        parsed = parse_skill_command(full.strip())
        if not parsed:
            continue
        skill_name, skill_args = parsed
        if skill_name == 'list':
            continue
        cmds.append((skill_name, skill_args))

    return cmds


def _execute_skill_cmds(cmds, agent_name, emit_fn, max_chars=None, source_conv_id=None):
    """Execute a list of (skill_name, skill_args) pairs. Returns joined output string."""
    char_limit = max_chars or _MAX_SKILL_OUTPUT_CHARS
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
            # Pass source_conv_id for proposal skills so Duck can notify the chat thread
            _conv_id = source_conv_id if skill_name == 'alm_create_proposal' else None
            ok, out = skill_call(skill_name, args=skill_args, agent=agent_name, source_conv_id=_conv_id)
        except Exception as exc:
            parts.append(f'[skill:{skill_name}] ERROR\n{exc}')
            continue

        preview = str(out or '')[:char_limit]
        parts.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\n{preview}")

    return '\n\n'.join(parts)


def run_skill_loop(
    agent_name,
    call_fn,
    messages,
    emit_fn,
    max_passes=5,
    max_skill_chars=None,
    nudge_if_no_skills=False,
    source_conv_id=None,
):
    """
    Execute `call_fn(messages)` with SKILL command interception and re-prompting.

    Parameters
    ----------
    agent_name : str
        Identifies which agent is calling (used for auth checks and logging).
    call_fn : callable
        Signature: (messages: list[dict]) -> (content: str, tokens: int).
    messages : list[dict]
        Starting message list. The loop works on a local copy.
    emit_fn : callable
        Signature: (text: str) -> None. Pushes stage labels to the UI.
    max_passes : int
        Maximum SKILL execution rounds before returning.
    max_skill_chars : int or None
        Cap on skill output per result. Defaults to _MAX_SKILL_OUTPUT_CHARS.
        Set lower (e.g. 2500) for APIs with tight token limits (gpt-4.1).
    nudge_if_no_skills : bool
        If True and the first response contains no SKILL commands, send one
        follow-up nudge asking the model to emit them. Useful for models
        (e.g. Grok) that default to prose descriptions instead of commands.

    Returns
    -------
    (answer: str, tokens: int)
    """
    skill_char_limit = max_skill_chars or _MAX_SKILL_OUTPUT_CHARS
    # Track the baseline message count so we can trim accumulated turns later.
    baseline_len = len(messages)
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

    # Diagnostic: log whether the first response contains SKILL commands
    has_skill = 'SKILL ' in str(first_content or '').upper()
    logger.info(
        f'[{agent_name}] pass 0 response: has_skill={has_skill} '
        f'len={len(str(first_content or ""))} '
        f'preview={str(first_content or "")[:200].replace(chr(10), " ")}'
    )

    # Nudge pass — one extra call if no skills and the caller requested it.
    if nudge_if_no_skills and not has_skill:
        emit_fn('nudging for skill commands')
        nudge_messages = working_messages + [
            {'role': 'assistant', 'content': answer},
            {'role': 'user', 'content': _SKILL_NUDGE},
        ]
        try:
            nudge_content, nudge_tokens = call_fn(nudge_messages)
            total_tokens += nudge_tokens
            # Only use the nudge response if it actually produced skills.
            if 'SKILL ' in str(nudge_content or '').upper():
                answer = nudge_content
                working_messages = nudge_messages
                logger.info(f'[{agent_name}] nudge produced SKILL commands')
            else:
                logger.info(f'[{agent_name}] nudge produced no skills — keeping original')
        except Exception as exc:
            logger.warning(f'[{agent_name}] nudge call failed: {exc}')

    pass_num = 0
    _mid_loop_nudges_remaining = 2  # allow up to 2 mid-loop nudges per request

    for _pass in range(max_passes):
        skill_cmds = _extract_skill_cmds(answer)
        if not skill_cmds:
            # If we've already run skills and the model returned prose without a new
            # SKILL command, nudge it inline — it may be mid-exploration and forgot
            # to emit the next command rather than genuinely being done.
            # NOTE: do NOT use `continue` here — at max_passes-1 that would exhaust
            # the loop and the nudge's skills would never run. Instead, execute the
            # nudge-recovered skills directly and update `answer` in-place.
            if pass_num > 0 and _mid_loop_nudges_remaining > 0:
                _mid_loop_nudges_remaining -= 1
                emit_fn('nudging for next skill command')
                nudge_msgs = (
                    list(messages[:baseline_len])
                    + [
                        {'role': 'assistant', 'content': answer},
                        {'role': 'user',      'content': _SKILL_NUDGE},
                    ]
                )
                try:
                    nudge_content, nudge_tokens = call_fn(nudge_msgs)
                    total_tokens += nudge_tokens
                    nudge_cmds = _extract_skill_cmds(nudge_content)
                    if nudge_cmds:
                        logger.info(f'[{agent_name}] mid-loop nudge (pass {pass_num}) produced {len(nudge_cmds)} SKILL command(s) — executing inline')
                        emit_fn('running nudged skills')
                        nudge_results = _execute_skill_cmds(nudge_cmds, agent_name, emit_fn, skill_char_limit, source_conv_id=source_conv_id)
                        pass_num += 1
                        follow_up = (
                            'Skill outputs below.\n'
                            'If the original request was a code/file change and you now have enough information, '
                            'emit SKILL fs_patch_lines NOW. '
                            'Only produce a final text answer when all changes are done and verified.\n\n'
                            + nudge_results
                        )
                        working_messages = (
                            list(messages[:baseline_len])
                            + [
                                {'role': 'assistant', 'content': nudge_content},
                                {'role': 'user',      'content': follow_up},
                            ]
                        )
                        emit_fn('synthesizing final answer')
                        answer, tokens = call_fn(working_messages)
                        total_tokens += tokens
                        # Now loop back to check if the new answer has more SKILL commands
                        continue
                    else:
                        logger.info(f'[{agent_name}] mid-loop nudge (pass {pass_num}) produced no skills — done')
                except Exception as exc:
                    logger.warning(f'[{agent_name}] mid-loop nudge failed: {exc}')
            break  # model is done — no skills requested

        emit_fn('running requested skills')
        skill_results = _execute_skill_cmds(skill_cmds, agent_name, emit_fn, skill_char_limit, source_conv_id=source_conv_id)
        pass_num += 1

        logger.debug(
            f'[{agent_name}] pass {pass_num}: ran {len(skill_cmds)} skill(s); '
            f'result preview: {skill_results[:120]}'
        )

        is_final_pass = (_pass == max_passes - 1)

        if is_final_pass:
            follow_up = (
                'Final skill outputs below. Produce your final answer now.\n\n'
                + skill_results
            )
        else:
            follow_up = (
                'Skill outputs below.\n'
                'IMPORTANT: If the original request was a code/file change and you now have '
                'enough information, emit SKILL fs_patch NOW to apply it. '
                'The <<<OLD>>> text MUST be copied EXACTLY character-for-character from the '
                'skill output — every line in the block including background, border, etc. '
                'Do NOT abbreviate or reconstruct OLD text — copy it verbatim.\n'
                'If you just applied a patch, confirm with SKILL fs_readonly lines.\n'
                'Only produce a final text answer when all changes are done and verified.\n\n'
                + skill_results
            )

        # Keep context lean: baseline messages + last assistant turn + new follow_up.
        # This prevents unbounded growth that blows token limits on tight APIs.
        working_messages = (
            list(messages[:baseline_len])
            + [
                {'role': 'assistant', 'content': answer},
                {'role': 'user', 'content': follow_up},
            ]
        )

        emit_fn('synthesizing final answer')
        try:
            answer, tokens = call_fn(working_messages)
        except Exception as exc:
            logger.error(f'[{agent_name}] skills_loop pass {pass_num + 1} error: {exc}')
            answer = (answer or '') + f'\n\n[skills_loop error on pass {pass_num + 1}: {exc}]'
            break
        total_tokens += tokens

    return answer, total_tokens
