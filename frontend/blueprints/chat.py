"""chat.py — Chat Engine routes

LINKED TO:
  frontend/services.py      — imports everything via `from services import *`.
                              _AGENT_ROSTER, _CHAT_AGENT_ETA_SECONDS, and
                              _alm_gate_or_response all live there.
  utils/config.py           — agent system prompts loaded dynamically in
                              _run_ghost_layer_chat() via <NAME>_SYSTEM_PROMPT.
  utils/db/_schema.py       — _get_ghost_agent_names() queries agents table
                              for tier IN ('paid','free'). If an agent's tier
                              is wrong in the DB the ALM gate will mis-fire.
  frontend/blueprints/proposals.py — ALM gate creates/checks work_proposals;
                              developer_agents set here must match that file.
"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

chat_bp = Blueprint('chat', __name__)

def _fetch_chat_thread_rows(conv_id, limit=20):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT from_agent, to_agent, content
               FROM messages
               WHERE conversation_id=?
                 AND LOWER(from_agent) != 'fridays'
               ORDER BY id DESC
               LIMIT ?""",
            (conv_id, limit)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in reversed(rows)]



def _chat_history_from_rows(rows):
    history = []
    for row in rows:
        sender = _normalize_chat_participant(row.get('from_agent'))
        target = _normalize_chat_participant(row.get('to_agent'))
        role = 'user' if sender == 'user' else 'assistant'
        route = _display_chat_participant(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant(target)}'
        content = str(row.get('content') or '').strip()
        history.append({'role': role, 'content': f'{route}: {content}'})
    return history



def _thread_transcript_from_rows(rows):
    if not rows:
        return ''
    lines = []
    for row in rows:
        sender = _normalize_chat_participant(row.get('from_agent'))
        target = _normalize_chat_participant(row.get('to_agent'))
        route = _display_chat_participant(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant(target)}'
        text = str(row.get('content') or '').strip()
        lines.append(f'{route}: {text[:500]}')
    return '\n'.join(lines)



def _conversation_reply_context_from_rows(rows, selected_agent):
    selected = _normalize_chat_participant(selected_agent)
    latest_sender = 'user'
    previous_participant = ''
    prior_agent = ''

    if rows:
        latest_sender = _normalize_chat_participant(rows[-1].get('from_agent')) or 'user'
        for row in reversed(rows[:-1]):
            sender = _normalize_chat_participant(row.get('from_agent'))
            if sender and sender != selected:
                previous_participant = sender
                break
        for row in reversed(rows[:-1]):
            sender = _normalize_chat_participant(row.get('from_agent'))
            if sender and sender not in {'user', selected}:
                prior_agent = sender
                break

    default_reply_target = latest_sender or 'user'
    if default_reply_target == selected:
        default_reply_target = previous_participant or 'user'

    return {
        'latest_sender': latest_sender or 'user',
        'previous_participant': previous_participant,
        'prior_agent': prior_agent,
        'default_reply_target': default_reply_target or 'user',
    }



def _build_chat_handoff_block(selected_agent, reply_context):
    latest_sender = _display_chat_participant(reply_context.get('latest_sender') or 'user')
    previous_participant = reply_context.get('previous_participant') or ''
    prior_agent = reply_context.get('prior_agent') or ''
    default_target = _display_chat_participant(reply_context.get('default_reply_target') or 'user')

    lines = [
        '=== Thread routing ===',
        f'You are {selected_agent.upper()}.',
        f'Latest visible sender: {latest_sender}',
        f'Default reply target: {default_target}',
    ]
    if previous_participant:
        lines.append(f'Previous participant before that: {_display_chat_participant(previous_participant)}')
    if prior_agent:
        lines.append(f'Active collaborator already in thread: {_display_chat_participant(prior_agent)}')
    lines.extend([
        'RELAY ROUTING — CRITICAL:',
        'To hand off to another agent, end your response with the relay syntax on its own line:',
        '  AgentName: <your question or task for them>',
        'Examples: "LLaMA: Can you search for the latest SAP release notes on this?" or "Qwen: What is your risk analysis of this approach?"',
        'For multiple agents, one directive per line:',
        '  LLaMA: Can you verify X online?',
        '  Qwen: Can you reason through the implications?',
        'Do NOT write "I will direct LLaMA to..." or "Asking Qwen to..." — the relay system reads only the AgentName: format.',
        'Do NOT simulate other agents. Route and stop.',
        '',
    ])
    return '\n'.join(lines)



def _infer_reply_target_from_text(response_text):
    text = str(response_text or '').strip()
    if not text:
        return ''
    first_line = text.splitlines()[0].strip()
    match = re.match(r'^(?:@)?([A-Za-z][A-Za-z0-9_ /-]{0,30})\s*[:,]\s+', first_line)
    if not match:
        return ''
    return _normalize_chat_participant(match.group(1))



def _resolve_chat_reply_target(selected_agent, response_text, reply_context):
    explicit = _infer_reply_target_from_text(response_text)
    selected = _normalize_chat_participant(selected_agent)
    if explicit and explicit != selected and explicit != 'fridays':
        return explicit

    fallback = _normalize_chat_participant(reply_context.get('default_reply_target')) or 'user'
    if fallback == selected:
        fallback = _normalize_chat_participant(reply_context.get('previous_participant')) or 'user'
    if fallback == 'ghost':
        return 'user'
    return fallback or 'user'



def _parse_chat_skill_command(text):
    raw = (text or '').strip()
    upper = raw.upper()
    if not raw:
        return None

    if upper in {'/SKILLS', 'SKILLS', '/SKILL', 'SKILL'}:
        return 'list', ''

    if upper.startswith('/SKILL '):
        payload = raw[7:].strip()
    elif upper.startswith('SKILL '):
        payload = raw[6:].strip()
    else:
        return None

    if not payload:
        return 'list', ''

    parts = payload.split(None, 1)
    skill_name = parts[0].strip().lower()
    skill_args = parts[1].strip() if len(parts) > 1 else ''
    return skill_name, skill_args

def _is_execution_confirmation(text):
    raw = str(text or '').strip().lower()
    if not raw:
        return False
    confirmations = {
        'go ahead', 'yes', 'y', 'yep', 'yeah', 'continue', 'proceed', 'do it',
        'go for it', 'execute', 'run it', 'ship it'
    }
    if raw in confirmations:
        return True
    return bool(re.search(r'\b(go\s+ahead|continue|proceed|do\s+it|execute|run\s+it|ship\s+it|yes)\b', raw))

def _derive_proposal_from_text(selected_agent, text, user_prompt):
    body = str(text or '').strip()
    if not body:
        return None

    # Require at least one structured field label in colon form.
    # Bare mentions of words like "title" or "description" in a conversational
    # response must not auto-trigger proposal creation.
    if not re.search(r'(?:title|description|scope|goal|objective)\s*:', body, re.IGNORECASE):
        return None

    title = ''
    desc = ''

    m_title = re.search(r'(?:\*\*\s*)?title(?:\s*\*\*)?\s*:\s*(.+)', body, re.IGNORECASE)
    if m_title:
        title = m_title.group(1).strip().strip('*').strip()

    m_desc = re.search(r'(?:\*\*\s*)?description(?:\s*\*\*)?\s*:\s*([\s\S]{20,1200})', body, re.IGNORECASE)
    if m_desc:
        desc = m_desc.group(1).strip()
        desc = re.split(r'\n\s*(?:---|##+\s+|\*\*\w)', desc, maxsplit=1)[0].strip()

    if not title:
        title = f'{selected_agent} proposal from chat confirmation'
    if not desc:
        desc = str(user_prompt or '').strip()[:600] or body[:600]

    if not title or not desc:
        return None

    return title[:180], desc[:1500]

def _extract_skill_lines_from_text(text):
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

def _load_local_agent_memories(selected_agent, latest_message, topic_limit=4, recent_limit=2):
    query = str(latest_message or '').strip()[:160]
    collected = []
    seen_ids = set()

    for search_query, limit in ((query, topic_limit), ('', recent_limit)):
        try:
            rows = get_agent_memory(selected_agent, query=search_query, limit=limit) or []
        except Exception:
            rows = []
        for row in rows:
            row_id = row['id'] if 'id' in row.keys() else id(row)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            collected.append(row)
    return collected

def _build_local_memory_block(selected_agent, latest_message):
    memories = _load_local_agent_memories(selected_agent, latest_message)
    if not memories:
        return ''

    lines = []
    for row in memories:
        tags = str(row['tags'] or '').strip()
        subject = str(row['subject'] or '').strip()[:120]
        content = str(row['content'] or '').strip().replace('\n', ' ')[:420]
        prefix = f'[{tags}] ' if tags else ''
        lines.append(f'- {prefix}{subject}: {content}')

    return (
        '\n\n=== Your recent memory ===\n'
        + '\n'.join(lines)
        + '\n=== End memory ===\n'
        + 'Use this for continuity and hand-off. Do not quote it verbatim unless asked.'
    )

def _build_local_agent_prompt(selected_agent, threaded_prompt, latest_message, reply_context):
    memory_block = _build_local_memory_block(selected_agent, latest_message)
    handoff_block = _build_chat_handoff_block(selected_agent, reply_context)
    base_prompt = handoff_block + threaded_prompt + memory_block
    if selected_agent in {'duck', 'sniffles'}:
        return (
            '=== Audit mode ===\n'
            'Review the thread and latest user message. Focus on factual consistency, risk,'
            ' contradictions, and missing assumptions. Return concise findings only.\n\n'
            + base_prompt
        )
    return base_prompt

def _get_ghost_agent_names():
    """Return names of all enabled non-local agents (tier paid/free) from DB."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name FROM agents WHERE tier IN ('paid','free') AND enabled=1"
        ).fetchall()
        conn.close()
        return {r['name'] for r in rows}
    except Exception:
        return {'nine', 'ten', 'eleven', 'twelve', 'thirteen'}


def _get_agent_labels():
    """Return {name: label} for all agents from DB, with fallback to name."""
    try:
        conn = get_connection()
        rows = conn.execute("SELECT name, label FROM agents WHERE enabled=1").fetchall()
        conn.close()
        return {r['name']: (r['label'] or r['name'].capitalize()) for r in rows}
    except Exception:
        return {}


def _should_attach_ticket_snapshot(latest_message, thread_rows):
    text = str(latest_message or '').strip().lower()
    if not text and thread_rows:
        text = str(thread_rows[-1].get('message') or '').strip().lower()
    if not text:
        return False
    triggers = (
        'ticket', 'tickets', 'queue', 'triage', 'open',
        'proposal', 'proposals', 'backlog', 'pending',
        'work item', 'work items', 'action plan', 'status'
    )
    return any(term in text for term in triggers)

def _build_ticket_snapshot_block(limit=8):
    conn = get_connection()
    try:
        queue_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM queue GROUP BY status"
        ).fetchall()
        queue_counts = {str(r['status'] or 'unknown').lower(): int(r['c'] or 0) for r in queue_rows}
        queue_total = sum(queue_counts.values())

        proposal_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM work_proposals GROUP BY status"
        ).fetchall()
        proposal_counts = {str(r['status'] or 'unknown').lower(): int(r['c'] or 0) for r in proposal_rows}

        pending_rows = conn.execute(
            """
            SELECT wp.proposal_id, wp.agent, wp.title, wp.status, wp.queue_id,
                   q.status AS queue_status, q.created_at
            FROM work_proposals wp
            LEFT JOIN queue q ON q.id = wp.queue_id
            WHERE lower(coalesce(wp.status, '')) IN ('pending', 'approved', 'in_progress')
            ORDER BY coalesce(q.created_at, wp.created_at) DESC
            LIMIT ?
            """,
            (int(max(1, min(20, limit))),)
        ).fetchall()

        lines = []
        for row in pending_rows:
            pid = str(row['proposal_id'] or '').strip() or '(no-id)'
            agent_name = str(row['agent'] or 'unknown').strip()
            title = str(row['title'] or '').strip().replace('\n', ' ')
            title = title[:140] if len(title) > 140 else title
            p_status = str(row['status'] or 'unknown').strip().lower()
            q_status = str(row['queue_status'] or 'unknown').strip().lower()
            lines.append(f"- {pid} | {agent_name} | {p_status}/{q_status} | {title}")

        queue_open = int(queue_counts.get('queued', 0) + queue_counts.get('processing', 0))
        queue_done = int(queue_counts.get('completed', 0) + queue_counts.get('done', 0))
        queue_failed = int(queue_counts.get('failed', 0))

        prop_pending = int(proposal_counts.get('pending', 0))
        prop_approved = int(proposal_counts.get('approved', 0))
        prop_in_progress = int(proposal_counts.get('in_progress', 0))
        prop_executed = int(proposal_counts.get('executed', 0) + proposal_counts.get('done', 0))

        return (
            "\n\n=== Live Ticket Snapshot ===\n"
            f"Queue: total={queue_total}, open={queue_open}, done={queue_done}, failed={queue_failed}\n"
            f"Proposals: pending={prop_pending}, approved={prop_approved}, in_progress={prop_in_progress}, executed={prop_executed}\n"
            "Open proposal samples (newest first):\n"
            + ("\n".join(lines) if lines else "- none")
            + "\nUse this snapshot directly as ground truth for this turn."
            + " If the user asks about open tickets/triage/action plan, answer from these counts and samples first"
            + " and do NOT ask the user to provide the same ticket list again unless snapshot shows none."
        )
    except Exception as exc:
        log_activity('terminal', 'chat_ticket_snapshot_warning', str(exc)[:180])
        return ''
    finally:
        conn.close()

def _persist_local_agent_memory(selected_agent, latest_message, response_text):
    answer = str(response_text or '').strip()
    if not answer:
        return

    lowered = answer.lower()
    if lowered.startswith(f'[{selected_agent}] acknowledged.'):
        return
    if 'taking longer than expected' in lowered:
        return
    if lowered.endswith('no response'):
        return

    content = (
        f'User asked: {str(latest_message or '').strip()[:400]}\n'
        f'You answered: {answer[:1600]}'
    )
    try:
        save_agent_memory(
            agent_name=selected_agent,
            subject=str(latest_message or '').strip()[:100] or f'{selected_agent} terminal chat',
            content=content,
            tags='chat,terminal-ui,shared-thread',
            importance=7,
            source='terminal_chat',
        )
    except Exception as exc:
        log_activity('terminal', 'chat_memory_persist_warning', f'{selected_agent}: {exc}')


def _friendly_api_error(exc) -> str:
    """Return a concise, human-readable description of an API exception."""
    import re as _re
    # SDK-style structured errors (Anthropic, OpenAI) expose .body or .message
    body = getattr(exc, 'body', None)
    if isinstance(body, dict):
        inner = body.get('error') or {}
        msg = inner.get('message') if isinstance(inner, dict) else None
        if msg:
            return str(msg)
    sdk_msg = getattr(exc, 'message', None)
    if sdk_msg and sdk_msg != str(exc):
        return str(sdk_msg)
    # Try to pull 'message': '...' out of the string representation
    raw = str(exc)
    m = _re.search(r"'message':\s*'([^']+)'", raw) or _re.search(r'"message":\s*"([^"]+)"', raw)
    if m:
        return m.group(1)
    # Known substrings → friendly labels
    if 'credit balance' in raw.lower() or 'billing' in raw.lower():
        return 'API credit balance too low — please top up billing'
    if 'rate limit' in raw.lower() or '429' in raw:
        return 'Rate limit reached — please retry shortly'
    if 'invalid api key' in raw.lower() or '401' in raw:
        return 'Invalid or missing API key'
    if 'context length' in raw.lower() or 'token' in raw.lower() and 'exceed' in raw.lower():
        return 'Context length exceeded'
    # Fallback: first 120 chars stripped of dict noise
    return raw[:120]



@chat_bp.route('/api/chat', methods=['POST'])
def api_chat():
    """Send a chat message to one or more agents on a shared conversation thread."""
    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    agent = (data.get('agent') or 'gemma').strip().lower()
    requested_agents = data.get('agents')
    requested_conv_id = data.get('conversation_id')
    force_new_thread = bool(data.get('new_thread'))
    relay_from = str(data.get('relay_from') or '').strip().lower() or None
    auto_relay = bool(data.get('auto_relay', True))
    history_mode = str(data.get('history_mode') or 'full').strip().lower()
    history_limit_raw = data.get('history_limit')

    if not message:
        return jsonify({'ok': False, 'response': 'Empty message'}), 400

    if history_mode not in {'full', 'recent', 'none'}:
        history_mode = 'full'

    try:
        history_limit = int(history_limit_raw) if history_limit_raw is not None else 8
    except Exception:
        history_limit = 8
    history_limit = max(1, min(30, history_limit))

    allowed_agents = {a['name'].lower() for a in _AGENT_ROSTER if a['name'].lower() != 'ghost'}

    if isinstance(requested_agents, list) and requested_agents:
        normalized_agents = []
        for item in requested_agents:
            name = str(item or '').strip().lower()
            if name and name not in normalized_agents:
                normalized_agents.append(name)
        if not normalized_agents:
            return jsonify({'ok': False, 'response': 'No agents selected'}), 400
    else:
        normalized_agents = [agent]

    bad_agents = [name for name in normalized_agents if name not in allowed_agents]
    if bad_agents:
        return jsonify({'ok': False, 'response': f"Unsupported agent(s): {', '.join(bad_agents)}"}), 400

    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    def _execute_agent_skill_lines(selected_agent, response_text, request_data):
        from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY

        # Developer Agents (Nine, Ten, Eleven, Twelve, Thirteen) execute Ghost One-directed
        # requests immediately — no proposal gate, no ALM confirmation loop.
        # Worker Agents (Gemma, LLaMA, Qwen, Mistral, Eight, Duck, Sniffles, Librarian)
        # must route through proposals and wait for approval.
        _developer_agents = _get_ghost_agent_names()
        is_developer_agent = selected_agent in _developer_agents

        allowed_auto_skills = {'alm_create_proposal', 'ticket_create'}
        if is_developer_agent:
            allowed_auto_skills = allowed_auto_skills | {'fs_write', 'fs_patch', 'fs_readonly'}

        cmds = _extract_skill_lines_from_text(response_text)
        if not cmds:
            # Developer agents: do NOT auto-create proposals from structured text.
            # Their responses are execution narration, not proposal drafts.
            if is_developer_agent:
                return ''
            derived = _derive_proposal_from_text(selected_agent, response_text, message)
            if not derived:
                return ''
            title, desc = derived
            safe_title = str(title).replace('"', "'")
            safe_desc = str(desc).replace('"', "'")
            synthetic_args = f'"{safe_title}" "{safe_desc}"'
            ok, out = skill_call('alm_create_proposal', args=synthetic_args, agent=selected_agent)
            preview = str(out or '')[:3000]
            return f"[skill:alm_create_proposal] {'OK' if ok else 'FAILED'}\\n{preview}"

        lines = []
        for skill_name, skill_args in cmds:
            if skill_name not in allowed_auto_skills:
                lines.append(f'[skill:{skill_name}] SKIPPED\\nAuto-execution only allows proposal skills.')
                continue

            meta = SKILL_REGISTRY.get(skill_name)
            if not meta:
                lines.append(f'[skill:{skill_name}] FAILED\\nUnknown skill')
                continue

            if not can_user_invoke_skill(selected_agent, skill_name, default_allow=True):
                lines.append(f'[skill:{skill_name}] FAILED\\nNot authorized for user {selected_agent}')
                continue

            trust_level = int(meta.get('trust_level', 0) or 0)
            # Developer agents bypass the ALM gate for Ghost One-directed chat requests.
            # Worker agents and self-initiated background work still go through the gate.
            if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'} and not is_developer_agent:
                gate = _alm_gate_or_response(request_data, f'chat_skill_{skill_name}')
                if gate:
                    lines.append(f'[skill:{skill_name}] FAILED\\nALM gate blocked execution (approval required).')
                    continue

            ok, out = skill_call(skill_name, args=skill_args, agent=selected_agent)
            preview = str(out or '')[:3000]
            lines.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\\n{preview}")

        return '\\n\\n'.join(lines)

    def _run_ghost_layer_chat(selected_agent, prompt, history, stage_cb=None):
        from claude_api import _load_api_key, CLAUDE_MODEL
        import anthropic
        import config as _config_mod
        from fridays.skills import call as skill_call

        def _emit_stage(text):
            if callable(stage_cb):
                try:
                    stage_cb(text, None)
                except Exception:
                    pass

        api_key = _load_api_key()
        if not api_key:
            return None, 0, 'ANTHROPIC_API_KEY not configured'

        # Dynamic system prompt lookup: try <NAME>_SYSTEM_PROMPT in config, fall back to DB
        _prompt_const = f'{selected_agent.upper()}_SYSTEM_PROMPT'
        base_system = getattr(_config_mod, _prompt_const, None)
        if not base_system:
            try:
                _db_conn = get_connection()
                _db_row = _db_conn.execute(
                    "SELECT system_prompt FROM agents WHERE name=?", (selected_agent,)
                ).fetchone()
                _db_conn.close()
                base_system = (_db_row['system_prompt'] or '') if _db_row else ''
            except Exception:
                base_system = ''
        if not base_system:
            base_system = getattr(_config_mod, 'TEN_SYSTEM_PROMPT', '')
        _emit_stage('loading ghost-layer memory')

        try:
            recent_memories = get_agent_memory(selected_agent, query='', limit=6)
            if recent_memories:
                mem_lines = []
                for row in recent_memories:
                    subj = str(row['subject'] or '').strip()[:120]
                    body = str(row['content'] or '').strip()[:400]
                    mem_lines.append(f'- [{subj}] {body}')
                memory_block = (
                    '\n\n=== Your recent memory (most important first) ===\n'
                    + '\n'.join(mem_lines)
                    + '\n=== End memory ===\n'
                    + 'Use this for continuity but do not narrate or repeat it verbatim.'
                )
                system_prompt = base_system.rstrip() + memory_block
            else:
                system_prompt = base_system
        except Exception:
            system_prompt = base_system

        client = anthropic.Anthropic(api_key=api_key)

        def _run_skill_lines(cmds):
            def _route_shell_to_fs_readonly(shell_args):
                cmd = (shell_args or '').strip()
                if not cmd:
                    return None

                match = re.match(r'^ls(?:\s+-[a-zA-Z]+)?\s+(.+)$', cmd)
                if match:
                    return f'ls {match.group(1).strip()}'

                match = re.match(r'^cat\s+(.+)$', cmd)
                if match:
                    return f'read {match.group(1).strip()} 5000'

                match = re.match(r'^head\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'head {match.group(2).strip()} {match.group(1)}'

                match = re.match(r'^tail\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'tail {match.group(2).strip()} {match.group(1)}'

                return None

            lines = []
            for skill_name, skill_args in cmds:
                _emit_stage(f'executing skill: {skill_name}')
                effective_name = skill_name
                effective_args = skill_args
                if skill_name == 'shell':
                    mapped = _route_shell_to_fs_readonly(skill_args)
                    if mapped:
                        effective_name = 'fs_readonly'
                        effective_args = mapped

                if not can_user_invoke_skill(selected_agent, effective_name, default_allow=True):
                    lines.append(f'[skill:{effective_name}] FAILED\\nNot authorized for user {selected_agent}')
                    continue
                ok, out = skill_call(effective_name, args=effective_args, agent=selected_agent)
                preview = str(out or '')[:3000]
                lines.append(f"[skill:{effective_name}] {'OK' if ok else 'FAILED'}\\n{preview}")
            return '\\n\\n'.join(lines)

        _emit_stage('sending model request')
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=(history[-10:] if history else []) + [{'role': 'user', 'content': prompt}],
        )
        first_answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        answer = first_answer
        skill_cmds = _extract_skill_lines_from_text(first_answer)
        if skill_cmds:
            _emit_stage('running requested skills')
            skill_results = _run_skill_lines(skill_cmds)
            followup_messages = (history[-10:] if history else []) + [
                {'role': 'user', 'content': prompt},
                {'role': 'assistant', 'content': first_answer},
                {
                    'role': 'user',
                    'content': (
                        'Executed skill outputs are below. Use these concrete results to produce your final answer. '
                        'Do not ask to run the same commands again in this response.\\n\\n'
                        + skill_results
                    ),
                },
            ]
            _emit_stage('synthesizing final answer')
            second = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=followup_messages,
            )
            answer = second.content[0].text + '\\n\\n---\\nExecuted skill output:\\n' + skill_results
            tokens += second.usage.input_tokens + second.usage.output_tokens

        _emit_stage('persisting response memory')
        save_agent_memory(
            agent_name=selected_agent,
            subject=message[:100],
            content=answer,
            tags='chat,shared-thread',
            importance=7,
            source='terminal_chat'
        )
        log_activity('terminal', f'{selected_agent}_chat', f'tokens={tokens} | {message[:80]}')
        return answer, tokens, None

    def _run_single_agent(selected_agent, prompt, history, reply_context, persistent_mode=False, stage_cb=None):
        def _duck_fast_check(text):
            t = (text or '').strip()
            if not t:
                return 'Sanity check: no claim provided.'
            cues = []
            if '?' in t:
                cues.append('contains a question; verify assumptions before acting')
            if any(k in t.lower() for k in ['always', 'never', 'guaranteed', 'impossible']):
                cues.append('absolute wording detected; high risk of overclaim')
            if any(k in t.lower() for k in ['maybe', 'probably', 'i think']):
                cues.append('uncertainty markers found; ask for evidence')
            if not cues:
                cues.append('no obvious red flags; still verify with one independent source')
            return 'Duck quick sanity: ' + '; '.join(cues) + '.'

        def _stage(text, eta_seconds=None):
            if callable(stage_cb):
                try:
                    stage_cb(text, eta_seconds)
                except Exception:
                    pass

        response_text = None
        tokens_used = 0
        started_at = time.time()
        executor = _CHAT_WORKER_EXECUTOR
        est_eta = _chat_eta_seconds(selected_agent)
        effective_prompt = _build_local_agent_prompt(selected_agent, prompt, message, reply_context)
        effective_prompt = f'[Auto Relay: {"ENABLED" if auto_relay else "DISABLED"}]\n' + effective_prompt
        if _is_execution_confirmation(message):
            effective_prompt = (
                effective_prompt
                + '\n\n=== EXECUTION CONFIRMATION ===\n'
                + 'User explicitly approved execution. If your next step is to create a work proposal, '
                + 'output exactly one executable command line in this format and then brief context:\n'
                + 'SKILL alm_create_proposal "<title>" "<description>"\n'
                + 'Do not ask for reconfirmation.'
            )
        _stage('queued', est_eta)
        local_timeout = 12
        if selected_agent == 'sniffles':
            local_timeout = 35
        elif selected_agent == 'duck':
            local_timeout = 18
        if persistent_mode:
            if selected_agent in {'gemma', 'llama', 'mistral', 'qwen', 'eight', 'librarian', 'duck', 'sniffles'}:
                local_timeout = 900
            else:
                local_timeout = 240

        # Tavily web research for Mistral (same service Qwen used) — injected before model call
        if selected_agent == 'mistral' and _TAVILY_OK and _tavily_search:
            try:
                _stage('searching web · Tavily', est_eta)
                _web = _tavily_search(message)
                if _web and not _web.startswith('[Tavily search unavailable'):
                    effective_prompt = '[Mistral / Tavily]\n' + _web + '\n\n' + effective_prompt
            except Exception:
                pass

        try:
            if selected_agent in {'gemma', 'llama', 'qwen', 'eight', 'librarian', 'duck', 'sniffles'}:
                _model_name = orchestrator.AGENTS.get(selected_agent, selected_agent)
                _stage(f'reading memory · {_model_name}', est_eta)
                if selected_agent in {'duck', 'sniffles'}:
                    _stage(f'building audit context · {_model_name}', est_eta)
                else:
                    _stage(f'preparing prompt · {_model_name}', est_eta)
                future = executor.submit(orchestrator.ask_agent, selected_agent, effective_prompt)
                _stage(f'generating · {_model_name}', est_eta)
                response_text = future.result(timeout=local_timeout)
                tokens_used = orchestrator._LAST_EVAL_COUNT.get(selected_agent, 0)
                _stage('writing to memory', 0)
                _persist_local_agent_memory(selected_agent, message, response_text)
            elif selected_agent == 'mistral':
                _stage('dispatching to local ollama · mistral', est_eta)
                from agents.mistral import mistral_agent
                future = executor.submit(mistral_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=900 if persistent_mode else 120)
                response_text = answer or '[mistral] No response — check server logs.'
                tokens_used = tokens or 0
            elif selected_agent == 'nine':
                _stage('dispatching to Groq', est_eta)
                from agents.nine import nine_agent
                future = executor.submit(nine_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[nine unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'ten':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.ten import copilot_agent
                future = executor.submit(copilot_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[ten] No response — check server logs.'
                tokens_used = tokens or 0
            elif selected_agent == 'eleven':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.eleven import grok_agent
                future = executor.submit(grok_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[eleven unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'twelve':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.twelve import twelve_agent
                future = executor.submit(twelve_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[twelve unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'scholar':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.scholar import scholar_agent
                future = executor.submit(scholar_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[scholar unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'seeker':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.seeker import seeker_agent
                future = executor.submit(seeker_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[seeker unavailable]'
                tokens_used = tokens or 0
            else:
                # Dynamic dispatch — any agent with agents/<name>/<name>_agent.py auto-routes here
                import importlib
                try:
                    mod = importlib.import_module(f'agents.{selected_agent}.{selected_agent}_agent')
                    _stage(f'dispatching to {selected_agent}', est_eta)
                    future = executor.submit(mod.chat, effective_prompt, history, stage_cb)
                    answer, tokens = future.result(timeout=120 if persistent_mode else 60)
                    response_text = answer or f'[{selected_agent} unavailable]'
                    tokens_used = tokens or 0
                except ModuleNotFoundError:
                    response_text = f'[{selected_agent}] agent module not found — bootstrap may be incomplete'
                except Exception as _dyn_err:
                    response_text = f'[{selected_agent}] error: {_dyn_err}'
            _stage('finalizing answer', 0)
        except FuturesTimeoutError:
            _stage('timed out waiting for completion', 0)
            if persistent_mode:
                raise RuntimeError(f'{selected_agent} timed out after {local_timeout}s')
            if selected_agent == 'duck':
                response_text = _duck_fast_check(message)
            elif selected_agent in {'gemma', 'llama', 'qwen', 'librarian'}:
                raise
            else:
                response_text = (
                    f'[{selected_agent}] is taking longer than expected. '
                    'Try again in a moment or switch to another agent.'
                )
        if response_text is None:
            response_text = f'[{selected_agent}] no response'

        elapsed_ms = int((time.time() - started_at) * 1000)
        return response_text, tokens_used, elapsed_ms

    try:
        conv_id = None
        if requested_conv_id is not None:
            try:
                parsed = int(requested_conv_id)
                conn = get_connection()
                try:
                    exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (parsed,)).fetchone()
                finally:
                    conn.close()
                if exists:
                    conv_id = parsed
            except Exception:
                conv_id = None

        if conv_id is None and not force_new_thread:
            conn = get_connection()
            try:
                latest = conn.execute(
                    "SELECT id FROM conversations WHERE source='terminal-ui' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if latest:
                conv_id = int(latest['id'])

        if conv_id is None:
            title_agents = ','.join(normalized_agents[:2])
            conv_id = new_conversation(f'{title_agents}: {message[:90]}', source='terminal-ui')

        to_agent = normalized_agents[0] if len(normalized_agents) == 1 else ','.join(normalized_agents)
        msg_sender = relay_from if relay_from else 'user'
        log_message(conv_id, msg_sender, message, to_agent=to_agent, message_type='relay' if relay_from else 'chat')

        parsed_skill = _parse_chat_skill_command(message)
        if parsed_skill:
            from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY

            skill_name, skill_args = parsed_skill
            meta = SKILL_REGISTRY.get(skill_name)

            if not meta:
                known = ', '.join(sorted(SKILL_REGISTRY.keys()))
                skill_ok = False
                skill_output = f"Unknown skill: {skill_name!r}. Known skills: {known}"
            else:
                effective_user = identity['effective_user']
                if not can_user_invoke_skill(effective_user, skill_name, default_allow=True):
                    return jsonify({
                        'ok': False,
                        'error': f'user {effective_user} is not authorized for skill {skill_name}'
                    }), 403
                trust_level = int(meta.get('trust_level', 0) or 0)
                if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'}:
                    gate = _alm_gate_or_response(data, f'chat_skill_{skill_name}')
                    if gate:
                        return gate
                caller_agent = effective_user
                skill_ok, skill_output = skill_call(skill_name, args=skill_args, agent=caller_agent)

            skill_response = (
                f"[skill:{skill_name}] {'OK' if skill_ok else 'FAILED'}\n"
                f'{skill_output}'
            )
            log_message(conv_id, 'fridays', skill_response, to_agent='user', message_type='response')

            return jsonify({
                'ok': True,
                'mode': 'skill',
                'skill': {
                    'name': skill_name,
                    'args': skill_args,
                    'ok': skill_ok,
                },
                'identity': {
                    'acting_user': identity['acting_user'],
                    'proxy_as': identity['proxy_as'],
                    'effective_user': identity['effective_user'],
                },
                'agent': 'fridays',
                'response': skill_response,
                'tokens': 0,
                'responses': [{
                    'agent': 'fridays',
                    'response': skill_response,
                    'tokens': 0,
                    'elapsed_ms': 0,
                }],
                'agents': normalized_agents,
                'conversation_id': conv_id,
            })

        if history_mode == 'none':
            thread_rows = []
        elif history_mode == 'recent':
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=history_limit)
        else:
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=60)
        history = _chat_history_from_rows(thread_rows)
        transcript = _thread_transcript_from_rows(thread_rows[-12:])
        reply_contexts = {
            selected_agent: _conversation_reply_context_from_rows(thread_rows, selected_agent)
            for selected_agent in normalized_agents
        }
        threaded_prompt = (
            '=== Shared conversation thread (latest) ===\n'
            f"{transcript or 'No previous messages.'}\n\n"
            '=== New user message ===\n'
            f'{message}'
        )
        if _should_attach_ticket_snapshot(message, thread_rows):
            threaded_prompt += _build_ticket_snapshot_block(limit=10)

        responses_map = {}
        pending_jobs = []
        deferred_agents = set()
        runnable_agents = list(normalized_agents)
        if 'sniffles' in runnable_agents and len(runnable_agents) > 1:
            runnable_agents = [a for a in runnable_agents if a != 'sniffles']
            deferred_agents.add('sniffles')

        def _register_persistent_job(selected_agent, future, reply_context, job_ref=None):
            job_id = f'chatjob-{uuid.uuid4().hex[:12]}'
            started_ts = time.time()
            now_iso = _chat_now_iso()
            eta_seconds = _chat_eta_seconds(selected_agent)
            with _CHAT_JOB_LOCK:
                _cleanup_chat_jobs_locked()
                _CHAT_JOBS[job_id] = {
                    'job_id': job_id,
                    'conversation_id': conv_id,
                    'agent': selected_agent,
                    'status': 'running',
                    'runtime_class': _chat_runtime_class(selected_agent),
                    'stage': _chat_stage_for(selected_agent, 0),
                    'eta_seconds': eta_seconds,
                    'started_ts': started_ts,
                    'updated_ts': started_ts,
                    'started_at': now_iso,
                    'updated_at': now_iso,
                    'future': future,
                    'cancel_requested': False,
                    'stage_trace': [],
                }
            # Persist to DB so the frontend can learn job outcome after a restart.
            persist_chat_job(
                job_id=job_id,
                conversation_id=conv_id,
                agent=selected_agent,
                runtime_class=_chat_runtime_class(selected_agent),
                eta_seconds=eta_seconds,
                started_at=now_iso,
            )
            if isinstance(job_ref, dict):
                job_ref['job_id'] = job_id

            def _finish_job(done_future):
                updated_ts = time.time()
                updated_iso = _chat_now_iso()
                try:
                    response_text, tokens_used, elapsed_ms = done_future.result()
                    if selected_agent in _get_ghost_agent_names() and _is_execution_confirmation(message):
                        try:
                            skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                            if skill_output:
                                response_text = f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                        except Exception as skill_exc:
                            response_text = (
                                f"{response_text}\n\n---\n"
                                f"Auto-executed skill output:\n[skill:auto] FAILED\\n{skill_exc}"
                            )
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        cancelled = bool(existing and existing.get('status') == 'cancelled')
                    if cancelled:
                        return
                    response_target = _resolve_chat_reply_target(selected_agent, response_text, reply_context)
                    log_message(
                        conv_id,
                        selected_agent,
                        response_text,
                        to_agent=response_target,
                        message_type='response',
                        tokens_used=int(tokens_used or 0),
                    )
                    _trace_json = None
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') != 'cancelled':
                            job.update({
                                'status': 'completed',
                                'stage': 'completed',
                                'eta_seconds': 0,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                                'elapsed_ms': int(elapsed_ms or 0),
                                'tokens': int(tokens_used or 0),
                            })
                            _trace_json = json.dumps(job.get('stage_trace') or [])
                    update_chat_job_db(
                        job_id, status='completed', stage='completed',
                        elapsed_ms=int(elapsed_ms or 0), tokens=int(tokens_used or 0),
                        stage_trace_json=_trace_json,
                    )
                except Exception as exc:
                    err_text = str(exc or '').strip() or exc.__class__.__name__
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        cancelled = bool(existing and existing.get('status') == 'cancelled')
                    if cancelled:
                        return
                    fail_msg = f'[{selected_agent}] background run failed: {err_text}'
                    try:
                        response_target = _resolve_chat_reply_target(selected_agent, fail_msg, reply_context)
                        log_message(
                            conv_id,
                            selected_agent,
                            fail_msg,
                            to_agent=response_target,
                            message_type='response',
                            tokens_used=0,
                        )
                    except Exception:
                        pass
                    _trace_json_f = None
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') != 'cancelled':
                            job.update({
                                'status': 'failed',
                                'stage': 'failed',
                                'eta_seconds': 0,
                                'error': err_text,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                            })
                            _trace_json_f = json.dumps(job.get('stage_trace') or [])
                    update_chat_job_db(job_id, status='failed', stage='failed', error=err_text,
                                       stage_trace_json=_trace_json_f)

            future.add_done_callback(_finish_job)
            return job_id

        debate_turn = []

        def _agent_label(agent_key):
            key = str(agent_key or '').strip().lower()
            return _get_agent_labels().get(key, key.capitalize() or 'Agent')

        def _build_debate_prompt(selected_agent):
            if len(runnable_agents) <= 1:
                return threaded_prompt

            active_labels = [_agent_label(a) for a in runnable_agents]
            if debate_turn:
                turn_lines = '\n'.join(
                    f"{_agent_label(item['agent'])}: {str(item['response'])[:800]}"
                    for item in debate_turn
                )
            else:
                turn_lines = 'No peer responses yet in this turn.'

            return (
                threaded_prompt
                + '\n\n=== Multi-Agent Debate Mode (Current Turn) ===\n'
                + f"You are {_agent_label(selected_agent)}.\n"
                + f"ACTIVE AGENTS IN THIS CHAT: {', '.join(active_labels)}.\n"
                + 'RULES: Only address agents from the list above. Do NOT mention, ask, or direct questions to '
                + 'any agent, person, or entity not in ACTIVE AGENTS. Do NOT ask Ghost to respond — '
                + 'Ghost has already sent their message above.\n'
                + 'Read the peer responses below and reply to them where useful. '
                + 'When another active agent already covered a point, extend or challenge it instead of restating it. '
                + 'If you agree or disagree, name the agent and explain in 1-2 lines. '
                + 'Then give your own answer.\n\n'
                + 'Peer responses so far this turn:\n'
                + turn_lines
            )

        for selected_agent in runnable_agents:
            selected_agent_key = str(selected_agent or '').strip().lower()
            if selected_agent_key in _CHAT_SINGLE_TASK_LOCAL_AGENTS:
                with _CHAT_JOB_LOCK:
                    _cleanup_chat_jobs_locked()
                    running_job = _chat_find_running_job_for_agent_locked(selected_agent_key)
                if running_job:
                    busy_conv = int(running_job.get('conversation_id') or 0)
                    busy_job_id = str(running_job.get('job_id') or '').strip()
                    busy_stage = str(running_job.get('stage') or 'running').strip()
                    responses_map[selected_agent] = {
                        'agent': selected_agent,
                        'response': (
                            f'[{selected_agent}] is already assigned to one active task '
                            f'(thread #{busy_conv}, job {busy_job_id or "unknown"}, stage: {busy_stage}). '
                            'Each local worker can run one task at a time. Cancel that run to move this agent to another thread now.'
                        ),
                        'tokens': 0,
                        'elapsed_ms': 0,
                        'runtime_class': _chat_runtime_class(selected_agent),
                        'eta_seconds': 0,
                        'pending': False,
                        'job_id': None,
                    }
                    continue

            job_ref = {'job_id': None}
            _agent_stage_trace = []

            def _stage_cb(stage_text, eta_seconds=None, _job_ref=job_ref, _trace=_agent_stage_trace):
                _trace.append({'text': str(stage_text), 'ts': time.time()})
                job_id = _job_ref.get('job_id')
                if not job_id:
                    return
                _chat_update_job(job_id, stage=stage_text, eta_seconds=eta_seconds)

            agent_prompt = _build_debate_prompt(selected_agent)
            future = _CHAT_DISPATCH_EXECUTOR.submit(
                _run_single_agent,
                selected_agent,
                agent_prompt,
                history,
                reply_contexts[selected_agent],
                True,
                _stage_cb,
            )
            try:
                wait_timeout = 20 if selected_agent == 'sniffles' else 10
                response_text, tokens_used, elapsed_ms = future.result(timeout=wait_timeout)
                pending = False
                pending_job_id = None
            except FuturesTimeoutError:
                pending_job_id = _register_persistent_job(selected_agent, future, reply_contexts[selected_agent], job_ref)
                pending_jobs.append(pending_job_id)
                # Sync stages that fired before job_id was set into the job record.
                if _agent_stage_trace and pending_job_id:
                    with _CHAT_JOB_LOCK:
                        _pj = _CHAT_JOBS.get(pending_job_id)
                        if _pj is not None:
                            existing = _pj.get('stage_trace') or []
                            # Merge pre-timeout trace entries at the front.
                            _pj['stage_trace'] = [e for e in _agent_stage_trace if e not in existing] + existing
                pending = True
                eta_seconds = _chat_eta_seconds(selected_agent)
                response_text, tokens_used = (
                    f'[{selected_agent}] acknowledged. Running now. ETA ~{eta_seconds}s; monitor shows live stage.',
                    0,
                )
                elapsed_ms = int(wait_timeout * 1000)
            except Exception as exc:
                response_text, tokens_used = (f'[{selected_agent}] Unavailable: {_friendly_api_error(exc)}', 0)
                elapsed_ms = 0
                pending = False
                pending_job_id = None

            responses_map[selected_agent] = {
                'agent': selected_agent,
                'response': response_text,
                'tokens': tokens_used,
                'elapsed_ms': elapsed_ms,
                'runtime_class': _chat_runtime_class(selected_agent),
                'eta_seconds': _chat_eta_seconds(selected_agent) if pending else 0,
                'pending': pending,
                'job_id': pending_job_id,
                'stage_trace': [] if pending else _agent_stage_trace,
            }

            if (not pending) and selected_agent in _get_ghost_agent_names() and _is_execution_confirmation(message):
                skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                if skill_output:
                    responses_map[selected_agent]['response'] = (
                        f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                    )

            debate_turn.append({'agent': selected_agent, 'response': response_text})

        for agent_name in deferred_agents:
            responses_map[agent_name] = {
                'agent': agent_name,
                'response': (
                    '[sniffles] deferred: heavyweight auditor runs on-demand. '
                    'Send to sniffles alone for a full audit.'
                ),
                'tokens': 0,
                'elapsed_ms': 0,
                'runtime_class': _chat_runtime_class(agent_name),
                'eta_seconds': 0,
                'pending': False,
                'job_id': None,
            }

        responses = [responses_map[a] for a in normalized_agents if a in responses_map]
        total_tokens = sum(int(r.get('tokens') or 0) for r in responses)
        for entry in responses:
            if entry.get('pending'):
                continue
            response_target = _resolve_chat_reply_target(entry['agent'], entry['response'], reply_contexts[entry['agent']])
            log_message(
                conv_id,
                entry['agent'],
                entry['response'],
                to_agent=response_target,
                message_type='response',
                tokens_used=int(entry.get('tokens') or 0),
            )

        primary = responses[0] if responses else {'agent': normalized_agents[0], 'response': '', 'tokens': 0}

        return jsonify({
            'ok': True,
            'agent': primary['agent'],
            'response': primary['response'],
            'tokens': total_tokens,
            'responses': responses,
            'pending_jobs': pending_jobs,
            'agents': normalized_agents,
            'history_mode': history_mode,
            'history_limit': history_limit if history_mode == 'recent' else None,
            'conversation_id': conv_id,
        })
    except Exception as exc:
        return jsonify({'ok': False, 'response': f'Error: {str(exc)}'}), 500



@chat_bp.route('/api/chat/jobs/status')
def api_chat_jobs_status():
    """Poll status for long-running chat jobs.

    Query params:
    - conversation_id (optional)
    - job_ids (optional comma-separated list)
    """
    conv_id = request.args.get('conversation_id')
    raw_job_ids = (request.args.get('job_ids') or '').strip()
    want_ids = {x.strip() for x in raw_job_ids.split(',') if x.strip()} if raw_job_ids else set()

    conv_id_int = None
    if conv_id:
        try:
            conv_id_int = int(conv_id)
        except Exception:
            conv_id_int = None

    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        jobs = []
        for job in _CHAT_JOBS.values():
            if conv_id_int is not None and int(job.get('conversation_id') or -1) != conv_id_int:
                continue
            if want_ids and job.get('job_id') not in want_ids:
                continue
            jobs.append(_chat_job_public(job))

    # For any explicitly requested IDs not found in memory, fall back to DB.
    # This surfaces outcomes for jobs that finished after a server restart.
    if want_ids:
        found_in_memory = {j['job_id'] for j in jobs}
        missing_ids = want_ids - found_in_memory
        if missing_ids:
            for row in get_chat_jobs_by_ids(missing_ids):
                elapsed = int(row.get('elapsed_ms') or 0)
                _db_trace = []
                try:
                    _db_trace = json.loads(row.get('stage_trace_json') or '[]')
                except Exception:
                    pass
                jobs.append({
                    'job_id': row.get('job_id'),
                    'conversation_id': row.get('conversation_id'),
                    'agent': row.get('agent'),
                    'status': row.get('status') or 'failed',
                    'runtime_class': row.get('runtime_class') or _chat_runtime_class(row.get('agent')),
                    'stage': row.get('stage') or 'unknown',
                    'eta_seconds': int(row.get('eta_seconds') or 0),
                    'eta_remaining_seconds': 0,
                    'started_at': row.get('started_at'),
                    'updated_at': row.get('updated_at'),
                    'elapsed_ms': elapsed,
                    'error': row.get('error') or '',
                    'stage_trace': _db_trace,
                })

    jobs.sort(key=lambda j: (j.get('status') != 'running', j.get('agent') or ''))
    return jsonify({'ok': True, 'jobs': jobs})



@chat_bp.route('/api/chat/jobs/cancel', methods=['POST'])
def api_chat_jobs_cancel():
    """Best-effort cancellation for long-running chat jobs.

    Body:
    - job_ids: array of job IDs or comma-separated string (optional)
    - conversation_id: optional, cancel all running jobs in conversation when job_ids omitted
    """
    data = request.get_json() or {}
    raw_ids = data.get('job_ids') or []
    hard_kill = bool(data.get('hard_kill', True))
    if isinstance(raw_ids, str):
        raw_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
    want_ids = {str(x).strip() for x in raw_ids if str(x).strip()}

    conv_id = data.get('conversation_id')
    conv_id_int = None
    if conv_id is not None and str(conv_id).strip() != '':
        try:
            conv_id_int = int(conv_id)
        except Exception:
            return jsonify({'ok': False, 'error': 'conversation_id must be int'}), 400

    cancelled = []
    skipped = []
    local_agents_to_kill = set()
    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        for job_id, job in list(_CHAT_JOBS.items()):
            if want_ids and job_id not in want_ids:
                continue
            if conv_id_int is not None and int(job.get('conversation_id') or -1) != conv_id_int:
                continue

            status = str(job.get('status') or 'running')
            if status in {'completed', 'failed', 'cancelled'}:
                skipped.append({'job_id': job_id, 'reason': f'already {status}'})
                continue

            fut = job.get('future')
            cancel_signal_sent = False
            if fut is not None:
                try:
                    cancel_signal_sent = bool(fut.cancel())
                except Exception:
                    cancel_signal_sent = False

            now_ts = time.time()
            now_iso = _chat_now_iso()
            job.update({
                'status': 'cancelled',
                'stage': 'cancelled by user',
                'eta_seconds': 0,
                'error': 'cancelled by user',
                'cancel_requested': True,
                'updated_ts': now_ts,
                'updated_at': now_iso,
            })
            update_chat_job_db(job_id, status='cancelled', stage='cancelled by user',
                               error='cancelled by user')
            if hard_kill and _chat_runtime_class(job.get('agent')) == 'local':
                local_agents_to_kill.add(str(job.get('agent') or '').strip().lower())
            cancelled.append({'job_id': job_id, 'agent': job.get('agent'), 'cancel_signal_sent': cancel_signal_sent})

    hard_kill_results = []
    if hard_kill and local_agents_to_kill:
        for agent_name in sorted(a for a in local_agents_to_kill if a):
            result = _chat_try_hard_kill_local_agent(agent_name)
            hard_kill_results.append(result)
            log_activity('terminal', 'chat_job_hard_kill', f"agent={agent_name} ok={result.get('ok')} detail={result.get('detail', '')[:120]}")

    for item in cancelled:
        log_activity('terminal', 'chat_job_cancelled', f"job_id={item['job_id']} agent={item.get('agent')}")

    return jsonify({
        'ok': True,
        'cancelled': cancelled,
        'skipped': skipped,
        'hard_kill': hard_kill,
        'hard_kill_results': hard_kill_results,
        'count': len(cancelled),
    })



@chat_bp.route('/api/chat/librarian/review', methods=['POST'])
def api_chat_librarian_review():
    """
    Ask Librarian to detect implicit relay candidates that the regex relay missed.
    The call runs synchronously but with a hard timeout — the frontend should call
    this async/debounced and not block the chat UI on the result.

    Body:
    - text: the agent response text to review (required, max 1200 chars trimmed)
    - from_agent: who sent the message (required)
    - conversation_id: for logging (optional)
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get('text') or '').strip()
    from_agent = str(data.get('from_agent') or 'agent').strip().lower()
    conversation_id = data.get('conversation_id')

    if not text or len(text) < 20:
        return jsonify({'ok': True, 'candidates': []})
    if len(text) > 2000:
        text = text[:2000]

    try:
        candidates = orchestrator.librarian_relay_review(text, from_agent, timeout_s=18)
        log_activity('terminal', 'librarian_relay_review',
                     f'from={from_agent} conv={conversation_id} found={len(candidates)}')
        return jsonify({'ok': True, 'candidates': candidates})
    except Exception as e:
        log_activity('terminal', 'librarian_relay_review_error', str(e)[:200])
        return jsonify({'ok': True, 'candidates': [], 'error': str(e)[:120]})



