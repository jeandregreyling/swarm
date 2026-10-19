"""
agents/skills_loop.py — Shared SKILL execution loop for tool-enabled agents.

Developer agents and the tool-enabled local trio use this module for controlled
tool execution. When a model emits a SKILL line, the runtime intercepts it, runs
the skill, and feeds the output back for a synthesised final answer.

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

import json
import logging
import re

logger = logging.getLogger('seven.skills_loop')


def _tl(conv_id, agent, event_type, payload):
    """Write a timeline event — silent on failure."""
    if not conv_id:
        return
    try:
        from database import timeline_append
        timeline_append(conv_id, agent, event_type, payload)
    except Exception:
        pass

_MAX_SKILL_CMDS_PER_PASS  = 6
_MAX_SKILL_OUTPUT_CHARS   = 8000  # default; override via max_skill_chars arg
_READ_ONLY_SKILL_COMMAND_RE = re.compile(
    r'^\s*/?SKILL\s+([a-z0-9_-]+)\b(.*)$',
    re.IGNORECASE,
)
_READ_ONLY_TASK_RE = re.compile(
    r'\b(?:do not|don\'t|never)\s+'
    r'(?:edit|modify|change|write|patch|create|delete|remove|use|run)\b',
    re.IGNORECASE,
)
_READ_ONLY_TASK_SKILLS = {'fs_readonly'}
# Pure lookups that never change anything, so read-only turns may still use them.
_READ_ONLY_LOOKUP_SKILLS = {'memory_search', 'swarm_knowledge_search', 'swarm_knowledge_read', 'knowledge_search'}
_SKILL_NUDGE = (
    'Your response did not contain any SKILL commands.\n'
    'Only emit a SKILL command if the operator explicitly requested an action that needs it.\n'
    'For inspection-only requests, use only the exact read-only operation needed and then report its output.\n'
    'Never infer a request to edit, patch, write, schedule, or create a proposal from a read or diagnostic task.\n'
    'For a requested mutation, stop at any required human or ALM approval gate; never self-approve.\n'
    'Start repository searches with SKILL fs_readonly grep, and use workspace-relative paths returned by the backend.\n'
    'For stored records and counts (proposals, tickets, steps, projects, queue) use SKILL shell python3 scripts/db_query.py "select ..."; an id is a database row, not a file.\n'
    'Do NOT describe what you plan to do — emit the SKILL line directly.\n'
    'Key directories (in order of relevance for backend/config tasks):\n'
    '  frontend/blueprints/   ← backend Python: agent dispatch, timeouts, routes\n'
    '  agents/                ← agent implementations\n'
    '  utils/                 ← config and system prompts\n'
    '  frontend/static/js/views/ ← frontend JS\n'
    'Example workflow:\n'
    '  SKILL fs_readonly lines docs/sample.md 1 20              ← read a line range\n'
    '  SKILL fs_readonly grep docs/sample.md install         ← find text in a file\n'
    'These two lines only show the format. Replace the file, range and text with what the request asks for.\n'
    'Never read a whole file from line 1 when you can grep for the value.\n'
    'Never guess paths that do not appear in ls output (backend/, config/, src/ do not exist).\n'
    'If this request needed no file access, respond with your final answer and ignore this message.'
)


# Models imitate the echoed result format ("[skill:name] OK"), so accept
# "[skill:name args]" and "[skill:name] args" as commands, but never an echoed result.
_BRACKET_SKILL_INSIDE_RE = re.compile(r'^\s*\[skill:([a-z0-9_-]+)\s+(.+)\]\s*$', re.IGNORECASE)
_BRACKET_SKILL_AFTER_RE = re.compile(
    r'^\s*\[skill:([a-z0-9_-]+)\]\s+(?!(?:OK|FAILED|SKIPPED|ERROR)\b)(\S.*)$',
    re.IGNORECASE,
)


_BARE_DB_QUERY_RE = re.compile(r'^\s*(?:\$\s*)?(python3 scripts/db_query\.py\s+".+")\s*$')


def _normalize_bracket_skill_line(line):
    bare = _BARE_DB_QUERY_RE.match(line)
    if bare:
        return f'SKILL shell {bare.group(1)}'
    for pattern in (_BRACKET_SKILL_INSIDE_RE, _BRACKET_SKILL_AFTER_RE):
        match = pattern.match(line)
        if match:
            return f'SKILL {match.group(1).lower()} {match.group(2).strip()}'
    return line


def _extract_read_only_skill_cmds(text):
    """Parse simple one-line commands for the read-only profile's safe hook."""
    commands = []
    for line in str(text or '').splitlines():
        match = _READ_ONLY_SKILL_COMMAND_RE.match(line)
        if match:
            commands.append((match.group(1).lower(), match.group(2).strip()))
    return commands


def _extract_skill_cmds(text):
    """
    Parse SKILL / /SKILL commands from model output.

    A skill is one line. File skills (fs_write, fs_append, fs_patch, fs_insert_after, fs_patch_lines) are followed by
    ``` fenced blocks holding the content; the args handed to the skill are the head line
    plus those fenced lines, which the skill itself parses.
    Returns list of (skill_name, skill_args) tuples, capped at _MAX_SKILL_CMDS_PER_PASS.
    """
    try:
        from fridays.skills import parse_skill_command, read_fenced_blocks, FENCED_BODY_SKILLS
    except Exception:
        return []

    lines = [_normalize_bracket_skill_line(ln) for ln in str(text or '').splitlines()]
    cmds = []
    i = 0

    while i < len(lines) and len(cmds) < _MAX_SKILL_CMDS_PER_PASS:
        line = lines[i].strip()
        if not (line.upper().startswith('SKILL ') or line.upper().startswith('/SKILL ')):
            i += 1
            continue
        i += 1
        full = 'SKILL ' + line[7:].strip() if line.upper().startswith('/SKILL ') else line
        parsed = parse_skill_command(full)
        if not parsed or parsed[0] == 'list':
            continue
        skill_name, skill_args = parsed
        if _PLACEHOLDER_ARG_RE.search(skill_args.split('\n', 1)[0]):
            logger.warning(f'[skills] ignoring {skill_name}: arguments are a template placeholder')
            continue
        if skill_name in FENCED_BODY_SKILLS:
            blocks, nxt = read_fenced_blocks(lines, i, max_blocks=FENCED_BODY_SKILLS[skill_name])
            if blocks:
                skill_args = skill_args.strip() + '\n' + '\n'.join(lines[i:nxt]).strip('\n')
                i = nxt
            else:
                logger.warning(f'[skills] {skill_name}: no fenced block found; next lines: {lines[i:i + 4]!r}')
        cmds.append((skill_name, skill_args))

    return cmds


# Template slots copied from a skill list (<query>, <full/path/to/file>) are never real arguments.
_PLACEHOLDER_ARG_RE = re.compile(r'<[a-z_]+(?:[-/][a-z_]+)*>')
_FENCED_SKILL_RE = re.compile(r'(?m)^\s*`{3,}\s*/?SKILL\s+[a-z_]+', re.IGNORECASE)
_FENCED_SKILL_NUDGE = (
    'Your reply put SKILL lines inside backticks (```SKILL ...```). Text inside backticks is not run, '
    'so no skill ran and any results shown in your reply were not real.\n'
    'Send the SKILL line again as plain text on its own line. For file skills, the file text goes in a '
    'fenced block on the NEXT line:\n'
    'SKILL fs_write sandpits/fred/example.md\n'
    '```\n'
    'file text\n'
    '```\n'
    'Send only the first step now. The real result will come back to you.'
)


def _fenced_skill_in_text(text):
    return bool(_FENCED_SKILL_RE.search(str(text or '')))


_INJECTED_BLOCK_RE = re.compile(r'=== [A-Z][A-Z \-]+ ===.*?(?:=== END [A-Z \-]+ ===|\n={10,}\n)', re.DOTALL)


def _operator_text(content):
    # The chat layer prepends policy blocks (relay rules etc.) to the user turn;
    # their "do not write ..." wording is not the operator asking for read-only.
    return _INJECTED_BLOCK_RE.sub('', str(content or ''))


_ACTION_WORDS_RE = re.compile(
    r'(?i)\b(patch|edit|change|modify|write|fix|update|implement|create|add|apply|refactor|'
    r'delete|remove|rename|proposal|approve|complete|commit|push|deploy|install|restart)\b'
)


def _latest_operator_text(messages):
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        text = _operator_text(message.get('content'))
        marker = '=== New user message ==='
        if marker in text:
            text = text.rsplit(marker, 1)[1]
        return text.strip()
    return ''


def _all_asks_reminder(messages):
    """Reminder carrying the operator's own words so no part of a multi-part ask is dropped."""
    text = _latest_operator_text(messages)
    if not text:
        return ''
    return (
        f'The operator wrote: "{text[:600]}"\n'
        'Answer EVERY part of that message in your reply, in order. Skill output covers only some '
        'parts; the rest you answer from your own knowledge of who and where you are.\n\n'
    )


def _asks_only_to_look(messages):
    """True when the operator's newest message asks for no change, only to look and explain."""
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        text = _operator_text(message.get('content'))
        marker = '=== New user message ==='
        if marker in text:
            text = text.rsplit(marker, 1)[1]
        return not _ACTION_WORDS_RE.search(text)
    return False


def _is_explicitly_read_only_task(messages):
    # Only the latest user turn counts: earlier turns, and prose like "No write
    # occurs without a Vortex ID" in relayed peer messages, must not strip write skills.
    return bool(_READ_ONLY_TASK_RE.search(_latest_operator_text(messages)))


def _is_explicitly_no_tools_task(messages):
    from utils.local_runtime_policy import is_explicitly_no_tools_request

    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get('role') != 'user':
            continue
        if is_explicitly_no_tools_request(_operator_text(message.get('content'))):
            return True
    return False


_RECENT_PROPOSALS = {}


def _is_duplicate_proposal(agent_name, source_conv_id, skill_args):
    # Small models re-emit the same proposal on every pass; one per thread and title is enough.
    if not source_conv_id:
        return False
    import time
    title = str(skill_args or '').strip().split('" "')[0].strip('" ').lower()
    key = (agent_name, str(source_conv_id), title)
    now = time.time()
    for k in [k for k, t in _RECENT_PROPOSALS.items() if now - t > 600]:
        _RECENT_PROPOSALS.pop(k, None)
    if key in _RECENT_PROPOSALS:
        return True
    _RECENT_PROPOSALS[key] = now
    return False


def _is_level0_shell(skill_name, skill_args, allowed_skill_names):
    """Read-only turns may still run whitelisted level-0 shell commands (not when tools are off)."""
    if not allowed_skill_names:
        return False
    if skill_name in _READ_ONLY_LOOKUP_SKILLS:
        return True
    if skill_name != 'shell':
        return False
    try:
        from fridays.shell_agent import _match_whitelist
        match = _match_whitelist(str(skill_args or '').strip())
        return bool(match) and match[0] == 0
    except Exception:
        return False


def _execute_skill_cmds(cmds, agent_name, emit_fn, max_chars=None, source_conv_id=None, allowed_skill_names=None):
    """Execute a list of (skill_name, skill_args) pairs. Returns joined output string."""
    char_limit = max_chars or _MAX_SKILL_OUTPUT_CHARS
    try:
        from fridays.skills import call as skill_call
    except Exception as e:
        return f'[skills] import error: {e}'

    parts = []
    for skill_name, skill_args in cmds:
        emit_fn(f'executing skill: {skill_name}')

        from utils.local_runtime_policy import is_read_only_agent
        if is_read_only_agent(agent_name):
            parts.append(
                f'[skill:{skill_name}] SKIPPED\n'
                'Read-only agent profile: tool execution is disabled.'
            )
            _tl(source_conv_id, agent_name, 'skill_result', f'[{skill_name}] SKIPPED — read-only profile')
            continue

        # Log the skill invocation to the timeline
        args_preview = str(skill_args or '')[:300]
        _tl(source_conv_id, agent_name, 'skill_call', f'{skill_name} {args_preview}'.strip())

        if (
            allowed_skill_names is not None
            and skill_name not in allowed_skill_names
            and not _is_level0_shell(skill_name, skill_args, allowed_skill_names)
        ):
            parts.append(
                f'[skill:{skill_name}] SKIPPED\n'
                'Turn policy denied skill execution.'
            )
            _tl(source_conv_id, agent_name, 'skill_result', f'[{skill_name}] SKIPPED — turn policy')
            continue

        # Optional per-agent permission check (non-fatal if missing)
        try:
            from database import can_user_invoke_skill
            if not can_user_invoke_skill(agent_name, skill_name, default_allow=True):
                parts.append(f'[skill:{skill_name}] FAILED\nNot authorized for agent {agent_name}')
                _tl(source_conv_id, agent_name, 'skill_result', f'[{skill_name}] FAILED — not authorized')
                continue
        except Exception:
            pass

        try:
            if skill_name == 'alm_create_proposal' and _is_duplicate_proposal(agent_name, source_conv_id, skill_args):
                parts.append(f'[skill:{skill_name}] OK\nAlready created in this thread; not creating a duplicate.')
                continue
            # Pass source_conv_id for proposal skills so Duck can notify the chat thread
            _conv_id = source_conv_id if skill_name == 'alm_create_proposal' else None
            ok, out = skill_call(skill_name, args=skill_args, agent=agent_name, source_conv_id=_conv_id)
        except Exception as exc:
            parts.append(f'[skill:{skill_name}] ERROR\n{exc}')
            _tl(source_conv_id, agent_name, 'skill_result', f'[{skill_name}] ERROR: {exc}')
            continue

        try:
            from utils.thread_memory import record_fact
            record_fact(source_conv_id, agent_name, skill_name, skill_args, ok, out)
        except Exception:
            pass
        preview = str(out or '')[:char_limit]
        status = 'OK' if ok else 'FAILED'
        parts.append(f"[skill:{skill_name}] {status}\n{preview}")
        # Log first 800 chars of result to keep timeline readable
        _tl(source_conv_id, agent_name, 'skill_result',
            f'[{skill_name}] {status}\n{str(out or "")[:800]}')

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
    allowed_skill_names=None,
    mid_loop_nudges=2,
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
    no_tools_requested = _is_explicitly_no_tools_task(messages)
    if no_tools_requested:
        allowed_skill_names = set()
        logger.info(f'[{agent_name}] turn policy: no-tools request, skills disabled')
    elif allowed_skill_names is None:
        latest_user = next(
            (str(m.get('content', '')) for m in reversed(messages)
             if isinstance(m, dict) and m.get('role') == 'user'),
            '',
        )
        if 'WATCHDOG READ-ONLY ROUTING GUARD' in latest_user:
            allowed_skill_names = set(_READ_ONLY_TASK_SKILLS)
            logger.info(f'[{agent_name}] turn policy: read-only routing guard present')
        elif _is_explicitly_read_only_task(messages):
            allowed_skill_names = set(_READ_ONLY_TASK_SKILLS)
            m = _READ_ONLY_TASK_RE.search(_latest_operator_text(messages))
            logger.info(f'[{agent_name}] turn policy: read-only phrase {m.group(0)!r}' if m else f'[{agent_name}] turn policy: read-only')
    elif not isinstance(allowed_skill_names, set):
        allowed_skill_names = set(allowed_skill_names)
    # Track the baseline message count so we can trim accumulated turns later.
    baseline_len = len(messages)
    working_messages = list(messages)
    total_tokens = 0

    # Wrap emit_fn so every stage label is also written to the conversation timeline.
    _raw_emit = emit_fn
    def emit_fn(text):  # noqa: F811
        _raw_emit(text)
        _tl(source_conv_id, agent_name, 'stage', text)

    emit_fn('sending model request')
    try:
        first_content, tokens = call_fn(working_messages)
    except Exception as exc:
        logger.error(f'[{agent_name}] skills_loop first call error: {exc}')
        raise

    total_tokens += tokens

    from utils.local_runtime_policy import (
        MEMORY_WRITE_AGENT_PROFILES,
        is_read_only_agent,
        normalize_read_only_response,
    )
    is_read_only = is_read_only_agent(agent_name)
    if is_read_only or str(agent_name or '').strip().lower() in MEMORY_WRITE_AGENT_PROFILES:
        commands = _extract_read_only_skill_cmds(first_content)
        can_write_shared_note = (
            len(commands) == 1
            and commands[0][0] == 'shared_memory_write'
            and (
                allowed_skill_names is None
                or 'shared_memory_write' in allowed_skill_names
            )
        )
        if can_write_shared_note:
            from utils.local_runtime_policy import (
                agent_capability_allowed,
                persist_explicit_shared_memory_note,
            )

            if not agent_capability_allowed(agent_name, 'shared_memory_write'):
                answer = normalize_read_only_response(agent_name, first_content)
                _tl(source_conv_id, agent_name, 'response', answer[:1200])
                _tl(source_conv_id, agent_name, 'final', answer[:1200])
                return answer, total_tokens

            emit_fn('saving explicitly shared note')
            shared_note_saved = False
            write_error = ''
            try:
                shared_note_saved = persist_explicit_shared_memory_note(
                    agent_name, commands[0][1]
                )
                if shared_note_saved:
                    write_result = 'Shared-memory write succeeded.'
                    emit_fn('shared note saved')
                else:
                    write_error = 'backend declined the shared-memory write'
                    write_result = f'Shared-memory write failed: {write_error}'
            except Exception as exc:
                logger.exception('[%s] shared-memory write failed', agent_name)
                write_error = str(exc)
                write_result = f'Shared-memory write failed: {write_error}'
                emit_fn('shared-memory write failed')

            final_messages = list(working_messages[:baseline_len]) + [
                {'role': 'assistant', 'content': first_content},
                {
                    'role': 'user',
                    'content': (
                        f'{write_result} Return the final answer as one valid JSON '
                        'object using the required read-only response schema. '
                        'Do not issue another tool request.'
                    ),
                },
            ]
            try:
                final_content, final_tokens = call_fn(final_messages)
                total_tokens += final_tokens
                normalized = normalize_read_only_response(agent_name, final_content)
                if shared_note_saved:
                    final_payload = json.loads(normalized)
                    evidence = final_payload.get('evidence', [])
                    evidence.append({
                        'source': 'shared-memory backend',
                        'finding': 'The note was appended to trio_shared_notes.',
                    })
                    final_payload['evidence'] = evidence[:20]
                    answer = json.dumps(
                        final_payload, ensure_ascii=True, separators=(',', ':')
                    )
                else:
                    answer = normalize_read_only_response(
                        agent_name,
                        json.dumps({
                            'kind': 'error',
                            'summary': f'Shared-memory write failed: {write_error}',
                            'evidence': [],
                            'proposed_changes': [],
                            'human_review_required': True,
                        }),
                    )
            except Exception as exc:
                logger.exception('[%s] shared-memory result synthesis failed', agent_name)
                answer = normalize_read_only_response(
                    agent_name,
                    json.dumps({
                        'kind': 'error',
                        'summary': (
                            'Shared-memory write completed, but final response '
                            f'generation failed: {exc}'
                        ),
                        'evidence': [],
                        'proposed_changes': [],
                        'human_review_required': True,
                    }),
                )
        elif is_read_only:
            answer = normalize_read_only_response(agent_name, first_content)
        if can_write_shared_note or is_read_only:
            _tl(source_conv_id, agent_name, 'response', answer[:1200])
            _tl(source_conv_id, agent_name, 'final', answer[:1200])
            return answer, total_tokens

    answer = first_content

    # Log the first model response to the timeline
    _tl(source_conv_id, agent_name, 'response', str(first_content or '')[:1200])

    # Diagnostic: log whether the first response contains SKILL commands
    # A SKILL line inside backticks is text, not a command, so it must not count here.
    has_skill = bool(_extract_skill_cmds(first_content)) or (
        'SKILL ' in str(first_content or '').upper() and not _fenced_skill_in_text(first_content)
    )
    logger.info(
        f'[{agent_name}] pass 0 response: has_skill={has_skill} '
        f'len={len(str(first_content or ""))} '
        f'preview={str(first_content or "")[:200].replace(chr(10), " ")}'
    )

    # Nudge pass — one extra call if no skills and the caller requested it.
    if (
        nudge_if_no_skills
        and not no_tools_requested
        and not has_skill
        and str(first_content or '').strip()
    ):
        emit_fn('nudging for skill commands')
        nudge_messages = working_messages + [
            {'role': 'assistant', 'content': answer},
            {'role': 'user', 'content': _FENCED_SKILL_NUDGE if _fenced_skill_in_text(answer) else _SKILL_NUDGE},
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
    _all_results = []
    _look_only = _asks_only_to_look(messages)
    # Agents that finish in prose after reading (Fred) pass 0: the nudge leaves out skill results and invites stray greps.
    _mid_loop_nudges_remaining = 0 if _look_only else max(0, int(mid_loop_nudges))

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
                        nudge_results = _execute_skill_cmds(
                            nudge_cmds,
                            agent_name,
                            emit_fn,
                            skill_char_limit,
                            source_conv_id=source_conv_id,
                            allowed_skill_names=allowed_skill_names,
                        )
                        pass_num += 1
                        _all_results.append(nudge_results)
                        follow_up = (
                            'Skill outputs below.\n'
                            "Only continue with another skill if it is necessary for the operator's explicit request. "
                            'A read, search, or diagnostic request does not authorize a change. '
                            'If the operator explicitly requested a mutation, follow its required approval workflow '
                            'and never self-approve. '
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
        skill_results = _execute_skill_cmds(
            skill_cmds,
            agent_name,
            emit_fn,
            skill_char_limit,
            source_conv_id=source_conv_id,
            allowed_skill_names=allowed_skill_names,
        )
        pass_num += 1
        _all_results.append(skill_results)

        logger.debug(
            f'[{agent_name}] pass {pass_num}: ran {len(skill_cmds)} skill(s); '
            f'result preview: {skill_results[:120]}'
        )

        is_final_pass = (_pass == max_passes - 1)
        _asks_reminder = _all_asks_reminder(messages)

        if is_final_pass:
            follow_up = (
                'Final skill outputs below. Produce your final answer now.\n\n'
                + skill_results
            )
        elif _look_only:
            follow_up = (
                'Skill outputs below. The operator only asked you to look and explain, so answer '
                'them now in plain words, using only what these outputs show. Run another skill only '
                'if you truly cannot answer without it. If the output has odd or unrelated lines, '
                'mention them briefly rather than chasing them. If you cannot answer, say what is '
                'missing instead of writing "I do not know".\n\n'
                + skill_results
            )
        else:
            follow_up = (
                'Skill outputs below.\n'
                'IMPORTANT: If the original request was a code/file change and you now have '
                'enough information, emit SKILL fs_patch NOW to apply it. '
                'The old-text block MUST be copied EXACTLY character-for-character from the '
                'skill output. Do NOT abbreviate or reconstruct it — copy it verbatim.\n'
                'If you just applied a patch, confirm with SKILL fs_readonly lines.\n'
                'Only produce a final text answer when all changes are done and verified.\n\n'
                + skill_results
            )

        follow_up = _asks_reminder + follow_up

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

    # A reply that still ends in SKILL lines never got to run them; run them now.
    trailing = _extract_skill_cmds(answer) if answer else []
    if trailing:
        try:
            _all_results.append(_execute_skill_cmds(
                trailing, agent_name, emit_fn, skill_char_limit,
                source_conv_id=source_conv_id,
                allowed_skill_names=allowed_skill_names,
            ))
            raw_results = _all_results[-1]
            answer = 'Ran the final skill lines:\n' + raw_results
            # Let the model see those results and write its own closing message.
            try:
                summary, tokens = call_fn(
                    list(messages[:baseline_len])
                    + [
                        {'role': 'assistant', 'content': 'Running the last skill lines.'},
                        {'role': 'user', 'content': (
                            'Those skill lines ran. Outputs below. Write your final message now: plain words, '
                            'no SKILL lines. Give what was done, the paths, and anything that failed.\n\n' + raw_results
                        )},
                    ]
                )
                total_tokens += tokens
                if summary and not _extract_skill_cmds(summary):
                    answer = summary
            except Exception as exc:
                logger.warning(f'[{agent_name}] closing summary failed: {exc}')
        except Exception as exc:
            logger.warning(f'[{agent_name}] trailing skill run failed: {exc}')

    # Small models sometimes claim a proposal exists without ever creating one.
    joined = '\n'.join(_all_results)
    claims = re.search(
        r'(?i)\b(i|we|have|has)\s+(?:\w+\s+)?(created|submitted|raised|filed)\b[^\n]{0,40}\bproposal\b'
        r'|\bproposal\b[^\n]{0,40}\b(was|has been|is now)\s+(created|submitted|raised|filed)\b',
        str(answer or ''),
    )
    # An ID the model read from a skill result this turn is not an invented one.
    # Nor is one the operator named in their own message.
    operator_ids = _latest_operator_text(messages)
    if not claims:
        claims = any(
            pid not in joined and pid not in operator_ids
            for pid in re.findall(r'\bINTERNAL-[A-Z]+-\d+\b', str(answer or ''))
        )
    if claims and '[skill:alm_create_proposal] OK' not in joined:
        answer = (
            "[verification] No proposal was actually created: alm_create_proposal did not "
            "return OK in this turn, so any proposal ID mentioned below is not real.\n\n"
            + str(answer or '')
        )

    _tl(source_conv_id, agent_name, 'final', str(answer or '')[:1200])
    return answer, total_tokens
