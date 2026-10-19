"""chat_history.py — Thread row fetch + context assembly for the chat engine.

Extracted from frontend/blueprints/chat.py during Session 25 Step 4.
These helpers read the `messages` table and assemble per-turn context
(history list, transcript string, reply-routing context, handoff prompt block).

LINKED TO:
  frontend/blueprints/chat.py — consumes these through `from services import *`.
  services/__init__.py        — re-exports every name below.
  database.get_connection     — only DB touch is `_fetch_chat_thread_rows`.
"""
from database import get_connection

from .chat_jobs import _normalize_chat_participant


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


def _display_chat_participant_local(name):
    # Local display resolver — avoids a circular import on services.__init__
    # (which itself imports this module). Mirrors the logic in
    # services/__init__.py:_display_chat_participant.
    from utils.db.registry import get_display_labels
    canonical = _normalize_chat_participant(name)
    labels = get_display_labels()
    if canonical in labels:
        return labels[canonical]
    return str(name or 'AGENT').strip().upper() or 'AGENT'


def _chat_history_from_rows(rows):
    history = []
    for row in rows:
        sender = _normalize_chat_participant(row.get('from_agent'))
        target = _normalize_chat_participant(row.get('to_agent'))
        role = 'user' if sender == 'user' else 'assistant'
        route = _display_chat_participant_local(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant_local(target)}'
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
        route = _display_chat_participant_local(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant_local(target)}'
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
    latest_sender = _display_chat_participant_local(reply_context.get('latest_sender') or 'user')
    previous_participant = reply_context.get('previous_participant') or ''
    prior_agent = reply_context.get('prior_agent') or ''
    default_target = _display_chat_participant_local(reply_context.get('default_reply_target') or 'user')

    if str(selected_agent or '').lower() == 'fred':
        return '\n'.join([
            '=== Thread routing ===',
            'You are FRED, the only local agent. Answer the latest message yourself; no relay is needed.',
            f'Latest visible sender: {latest_sender}',
            f'Default reply target: {default_target}',
            'SKILLS (the SKILL line itself is plain text, never inside a fence; file content goes in a ``` fenced block right after it):',
            '  SKILL shell python3 scripts/db_query.py "select ... from ..."   (stored records and counts; ids are rows, not files)',
            '  SKILL fs_readonly read <full/path/to/file>   (files)',
            '  SKILL swarm_knowledge_search <query>   (Knowledge Center: decisions, docs, lessons)',
            '  SKILL memory_search <query>   (your own saved memory)',
            'FILE EDITING (the SKILL line is plain text; the file content goes in ``` fenced blocks right after it, no other markers):',
            '  SKILL fs_write <path>   + 1 block: the FULL file (overwrites)',
            '  SKILL fs_append <path>   + 1 block: text added to the end',
            '  SKILL fs_patch <path>   + 2 blocks: exact old text, then new text',
            '  SKILL fs_insert_after <path>   + 2 blocks: exact anchor text, then the text to insert after it',
            '  SKILL fs_patch_lines <path> <start> <end>   + 1 block: replacement lines',
            '  fs_insert_after puts the text after the WHOLE anchor, so make the anchor the one line you mean. When you report file content, copy it from the fs_readonly output; never retype it from memory.',
            '  SKILL fs_diff <path_a> <path_b>   (read-only; every change keeps a backup in runtime/backups/fs/, named in the result)',
            '  SKILL studio_step_update <step_id> <doing|done|blocked|skipped> <reason>   (only steps you own; reason is logged)',
            '  SKILL alm_create_proposal "<title>" "<description>"   (changes go through a proposal)',
            'Only state a change happened after you see [skill:...] OK in the output.',
            '',
        ])
    lines = [
        '=== Thread routing ===',
        f'You are {selected_agent.upper()}.',
        f'Latest visible sender: {latest_sender}',
        f'Default reply target: {default_target}',
    ]
    if previous_participant:
        lines.append(f'Previous participant before that: {_display_chat_participant_local(previous_participant)}')
    if prior_agent:
        lines.append(f'Active collaborator already in thread: {_display_chat_participant_local(prior_agent)}')
    lines.extend([
        'RELAY ROUTING — how to pass work on:',
        'To hand off to another agent, end your response with the relay syntax on its own line:',
        '  AgentName: <your question or task for them>',
        'Examples: "LLaMA: Can you search for the latest SAP release notes on this?" or "Qwen: What is your risk analysis of this approach?"',
        'For multiple agents, one directive per line:',
        '  LLaMA: Can you verify X online?',
        '  Qwen: Can you reason through the implications?',
        'Please skip phrases like "I will direct LLaMA to..." — the relay system only reads the AgentName: format.',
        'Please speak only for yourself; when you hand off, stop and let them answer.',
        '"AgentName" is only a placeholder; use a real agent name in a relay line, or no relay line at all.',
        '',
        'CHAIN OF COMMAND:',
        '  1. Ghost One (human) decides. 2. Seven regulates and checks the swarm. 3. Watchdog guards routing and read-only rules. 4. Duck audits proposals.',
        '  Everyone else works inside that line. Answer only the latest request addressed to you; do not answer for, or talk over, another agent.',
        '  If a peer is already handling a task, do not repeat their acknowledgement or restate their plan. Add only what is new, or say nothing.',
        '  Relay only to a real agent, only with a real question, and never to an agent that just spoke to you unless you need their answer.',
        'SKILLS (one command per line, plain text, never inside a code fence or brackets):',
        '  SKILL fs_readonly lines docs/sample.md 1 20      (format example: use the file and lines you were asked about)',
        '  SKILL alm_create_proposal "<title>" "<description>"',
        '  SKILL fs_patch_lines <path> <start> <end>   then the replacement lines in a ``` fenced block',
        'Work order: read first, then create a proposal, then pause at the approval gate. For now approval is open: you may approve your own proposal with SKILL alm_self_approve <proposal_id>, and Ghost One or Seven can approve too. Please take a Vortex checkpoint before any file change. Thank you, you are doing good work.',
        'Only state a change happened after you see [skill:...] OK in the output.',
        '',
    ])
    return '\n'.join(lines)


__all__ = [
    '_build_chat_handoff_block',
    '_chat_history_from_rows',
    '_conversation_reply_context_from_rows',
    '_fetch_chat_thread_rows',
    '_thread_transcript_from_rows',
]
