"""Fred is the only local agent. He wears one hat at a time.

The hat is chosen per message from keywords (operator can force one with
"hat: coder" and so on) and is injected into his prompt so he knows which job
he is doing right now. Hats do not change his permissions; those are on the
agent itself.
"""
import re

FRED_HATS = {
    'system_administrator': (
        'You are the system administrator of Fridays. You check status, queues, '
        'proposals, agents, permissions and logs, and you report facts with evidence. '
        'You do not change the system without an approved proposal.'
    ),
    'chat_bot': (
        'You are the chat bot. You talk with Ghost One plainly and kindly, answer '
        'what was asked, and do not run skills unless he asks for an action.'
    ),
    'coder': (
        'You are the coder. You read code first, make small surgical proposals, '
        'and never claim a change until a [skill:...] result shows it.'
    ),
}
DEFAULT_HAT = 'chat_bot'

_HAT_WORDS = {
    'coder': (
        'code', 'patch', 'bug', 'fix', 'refactor', 'function', 'traceback',
        'test', 'implement', 'script', '.py', '.js',
    ),
    'system_administrator': (
        'status', 'queue', 'proposal', 'agent', 'permission', 'role', 'restart',
        'port', 'database', 'log', 'handover', 'decommission', 'backup',
    ),
}
_FORCE_RE = re.compile(r'\bhat\s*[:=]\s*(system_administrator|sysadmin|admin|chat_bot|chat|coder)\b', re.I)
_ALIASES = {'sysadmin': 'system_administrator', 'admin': 'system_administrator', 'chat': 'chat_bot'}


def pick_hat(message):
    text = str(message or '')
    forced = _FORCE_RE.search(text)
    if forced:
        word = forced.group(1).lower()
        return _ALIASES.get(word, word)
    lower = text.lower()
    scores = {hat: sum(1 for w in words if w in lower) for hat, words in _HAT_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else DEFAULT_HAT


def hat_block(message):
    hat = pick_hat(message)
    return (
        f'=== YOUR HAT RIGHT NOW: {hat} ===\n{FRED_HATS[hat]}\n'
        'You wear one hat at a time; the other hats are '
        + ', '.join(h for h in FRED_HATS if h != hat) + '.\n=== END HAT ===\n\n'
    )
