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


__all__ = [
    '_build_chat_handoff_block',
    '_chat_history_from_rows',
    '_conversation_reply_context_from_rows',
    '_fetch_chat_thread_rows',
    '_thread_transcript_from_rows',
]
