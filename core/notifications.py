"""core/notifications.py — Shared notification formatter.

Phase 6 of the Apr 2026 rewire. Channel-agnostic helpers used by Discord,
Telegram, and Email (WhatsApp deferred). Pure functions, no I/O — callers
own transport. Tests live in ``tests/test_notifications.py``.

Design goals:
- Single source of truth for agent-reply formatting (prefix, truncation,
  code-fence safety).
- Deterministic output: same inputs → same string, forever. Safe to diff.
- Escape-free: returns plain text. Each transport re-escapes for its own
  markup rules (Discord markdown, Telegram HTML, Email plaintext/HTML).

Non-goals:
- HTML sanitisation. Use DOMPurify client-side; on the server, strip tags
  via bleach before calling these.
- Transport-specific formatting (embeds, buttons, inline keyboards).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    'format_agent_reply',
    'format_alert',
    'NotificationLevel',
    'AlertEnvelope',
]


# ── Constants ────────────────────────────────────────────────────────────────

# Discord hard limit is 2000 chars; Telegram is 4096. Use the smaller as the
# shared cap so any formatter output is safe to send anywhere.
DEFAULT_MAX_CHARS = 1800

# Visual markers for levels. ASCII-safe — transports can replace with emoji.
_LEVEL_PREFIX = {
    'info':    '[i]',
    'success': '[+]',
    'warn':    '[!]',
    'error':   '[x]',
    'critical': '[!!]',
}

# Ordered tuple for validation.
NotificationLevel = ('info', 'success', 'warn', 'error', 'critical')


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AlertEnvelope:
    """Structured alert. Safe to log, queue, or serialise as JSON."""
    level: str          # one of NotificationLevel
    subject: str        # short headline, 1 line
    body: str           # full text, may span many lines
    source: str = ''    # originating agent / subsystem, e.g. 'duck', 'vortex'


# ── Public API ──────────────────────────────────────────────────────────────

def format_agent_reply(
    agent: str,
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    include_prefix: bool = True,
) -> str:
    """Format an agent's reply for outbound channels.

    Parameters
    ----------
    agent : str
        Canonical agent name. Lowercased and wrapped in a short header.
    text : str
        Raw reply body. Leading/trailing whitespace is stripped.
    max_chars : int, optional
        Total output cap. Truncation happens at a word boundary where possible
        and appends ``… [truncated]`` inside the cap.
    include_prefix : bool, optional
        When True (default) a ``**agent**: `` prefix line is added. Callers
        for channels that render their own sender chrome can pass False.

    Returns
    -------
    str
        Plain text, ≤ max_chars. Never contains trailing whitespace.
    """
    agent_norm = str(agent or '').strip().lower() or 'agent'
    body = str(text or '').strip()
    prefix = f'**{agent_norm}**: ' if include_prefix else ''

    if not body:
        return (prefix + '(no content)').strip()

    # Keep code fences balanced across truncation. If the original has an odd
    # number of fences after truncation, append a closing fence inside the cap.
    candidate = prefix + body
    if len(candidate) <= max_chars:
        return candidate

    suffix = '… [truncated]'
    budget = max_chars - len(prefix) - len(suffix)
    if budget <= 0:
        # Pathological case: prefix alone exceeds cap. Return as-is trimmed.
        return candidate[:max_chars].rstrip()

    # Prefer word-boundary truncation within the last 80 chars of budget.
    slice_ = body[:budget]
    break_at = slice_.rfind(' ', max(0, budget - 80), budget)
    if break_at > 0:
        slice_ = slice_[:break_at]

    # Re-balance fences. Count on the trimmed slice; if odd, close it.
    if slice_.count('```') % 2 == 1:
        slice_ = slice_.rstrip() + '\n```'

    return (prefix + slice_.rstrip() + suffix).rstrip()


def format_alert(envelope: AlertEnvelope, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Format a structured alert for outbound channels.

    Output shape::

        [!] SUBJECT
        source: duck
        ---
        body text here, possibly multi-line
    """
    level = str(envelope.level or 'info').lower()
    if level not in NotificationLevel:
        level = 'info'
    marker = _LEVEL_PREFIX[level]
    subject = str(envelope.subject or '').strip().splitlines()[0] if envelope.subject else ''
    if not subject:
        subject = '(no subject)'

    header_lines = [f'{marker} {subject}']
    if envelope.source:
        header_lines.append(f'source: {str(envelope.source).strip().lower()}')
    header_lines.append('---')
    header = '\n'.join(header_lines)

    body = str(envelope.body or '').strip()
    if not body:
        return header[:max_chars]

    candidate = header + '\n' + body
    if len(candidate) <= max_chars:
        return candidate

    suffix = '\n… [truncated]'
    budget = max_chars - len(header) - 1 - len(suffix)
    if budget <= 0:
        return candidate[:max_chars].rstrip()
    return header + '\n' + body[:budget].rstrip() + suffix
