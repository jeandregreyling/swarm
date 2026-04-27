"""core/chat_actions.py — Pure-rules chat action detector ("Siri-but-better").

Phase 3, Workstream I. Given a free-text chat message, returns an optional
structured action that the UI can execute client-side (e.g. open a window,
run a spotlight search, capture a Vortex checkpoint).

Everything here is deterministic and side-effect-free — safe to call in any
request path. Actual execution is always driven by the frontend, which already
owns UI state. This module only *suggests* an action; the user clicks to
confirm.

Action schema (returned as a dict so it serialises cleanly):

    {
        'id':     'open_window',            # stable token for client dispatch
        'label':  'Open Vortex',            # human-readable pill text
        'args':   {'view': 'time-wizard'},  # action-specific payload
        'confidence': 0.9,                  # 0.0-1.0
        'rationale': 'matched "open vortex"',
    }

No action → returns ``None``. The bar is intentionally high: we only want to
surface an action pill when the user clearly asked for one, otherwise the chat
feels noisy.
"""
from __future__ import annotations

import re
from typing import Optional


# (view-id, template-id, title, synonyms) — synonyms are substring matches
# against the lowercased message. Keep them tight; noise here = false positives.
_WINDOW_ACTIONS = (
    ('time-wizard', 'view-time-wizard', 'Vortex',
     ('vortex', 'time wizard', 'timewizard', 'decision timeline')),
    ('tickets', 'view-tickets', 'Tickets',
     ('tickets', 'ticket queue', 'open tickets')),
    ('studio', 'view-studio', 'Studio',
     ('studio', 'proposals panel', 'work proposals', 'projects section',
      'project tracker', 'studio projects', 'projects tab')),
    ('media-center', 'view-media-center', 'Media Center',
     ('media center', 'music editor', 'video editor', 'media workspace',
      'music project', 'video project', 'media handoff', 'handoff manifest',
      'project handoff')),
    ('knowledge', 'view-knowledge', 'Knowledge',
     ('knowledge center', 'knowledge base', 'kb window')),
    ('chat', 'view-chat', 'Chat',
     ('open chat', 'chat window')),
    ('terminal', 'view-terminal', 'Terminal',
     ('terminal', 'shell window', 'open shell')),
    ('files', 'view-files', 'Files',
     ('files window', 'file browser', 'open files')),
    ('monitor', 'view-monitor', 'Monitor',
     ('monitor', 'agent monitor', 'system monitor')),
    ('email', 'view-email', 'Email',
     ('email window', 'inbox')),
    ('library', 'view-library', 'Library',
     ('library window',)),
    ('memory', 'view-memory', 'Memory',
     ('memory window', 'memory browser')),
    ('guide', 'view-guide', 'User Guide',
     ('user guide', 'help guide', 'documentation window')),
    ('skills', 'view-skills', 'Skills',
     ('skills window', 'skills panel')),
    ('docs', 'view-docs', 'Documents',
     ('documents window', 'docs window')),
)

# Strong verbs that mean "navigate me there". Used with a window synonym
# to form an open-window intent.
_OPEN_VERBS = (
    'open ', 'show ', 'show me ', 'bring up ', 'take me to ',
    'go to ', 'navigate to ', 'launch ',
)

# Search verbs → spotlight query. Captures the tail as the query.
_SEARCH_RE = re.compile(
    r'^\s*(?:search|find|look\s+up|lookup)\s+(?:for\s+)?["\']?(.+?)["\']?\s*[.?!]?\s*$',
    re.IGNORECASE,
)

# Explicit discrete commands. Keyed phrases → action dict.
_DISCRETE = (
    (('capture checkpoint', 'take a checkpoint', 'snapshot vortex', 'new checkpoint'),
     {'id': 'vortex_capture', 'label': 'Capture Vortex Checkpoint', 'args': {}}),
    (('go home', 'take me home', 'back to home', 'home screen'),
     {'id': 'go_home', 'label': 'Go to Home', 'args': {}}),
    (('keyboard shortcuts', 'show shortcuts', 'list shortcuts'),
     {'id': 'show_shortcuts', 'label': 'Show Keyboard Shortcuts', 'args': {}}),
)


def detect_action(message: str) -> Optional[dict]:
    """Return an action dict for a message, or None if nothing matches.

    Deterministic and cheap; callers may invoke on every inbound message.
    """
    text = (message or '').strip()
    if not text:
        return None
    lower = text.lower()

    # 1. Discrete named commands — highest precedence, no args needed.
    for phrases, payload in _DISCRETE:
        for ph in phrases:
            if ph in lower:
                return {
                    'id': payload['id'],
                    'label': payload['label'],
                    'args': dict(payload.get('args') or {}),
                    'confidence': 0.95,
                    'rationale': f'matched "{ph}"',
                }

    # 2. "search for X" / "find X" → spotlight query.
    m = _SEARCH_RE.match(text)
    if m:
        q = m.group(1).strip()
        # Reject trivially short or pure-pronoun queries.
        if len(q) >= 2 and q.lower() not in {'it', 'this', 'that', 'me', 'us'}:
            return {
                'id': 'spotlight_search',
                'label': f'Search for "{q[:48]}"' + ('…' if len(q) > 48 else ''),
                'args': {'q': q},
                'confidence': 0.9,
                'rationale': 'matched search verb',
            }

    # 3. "open/show <window>" → open_window.
    for view_id, template_id, title, synonyms in _WINDOW_ACTIONS:
        for syn in synonyms:
            if syn not in lower:
                continue
            # Require an open-verb nearby OR the synonym at the start of the
            # message (e.g. "vortex please"). Bare mentions mid-sentence do
            # not trigger an action — those are conversation, not commands.
            idx = lower.find(syn)
            prefix = lower[:idx]
            starts_message = idx <= 3
            has_verb = any(v in prefix[-24:] for v in _OPEN_VERBS)
            if not (starts_message or has_verb):
                continue
            return {
                'id': 'open_window',
                'label': f'Open {title}',
                'args': {'view': view_id, 'template': template_id, 'title': title},
                'confidence': 0.85 if has_verb else 0.7,
                'rationale': f'matched "{syn}"' + (' with open-verb' if has_verb else ''),
            }

    return None
