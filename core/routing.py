"""core/routing.py — Deterministic routing brain for Seven's Swarm.

Phase 3 of the Apr 2026 rewire. Pure-rules classifier: given a message + its
sender + a snapshot of current agent state, decides who should receive it.
No LLM calls. No I/O inside the decision function itself — callers pass in
whatever state they have.

The seven Seven-roles are the routing categories:

    voice        — conversational, chat, explain, identity
    coder        — write code, refactor, debug, fix, patch
    researcher   — lookup, find, search, what is, summarise, latest
    orchestrator — schedule, queue, run, retry, stop, relay, assign
    memory       — remember, recall, history, what did I say, log
    auditor      — review, validate, test, check, verify, approve
    messenger    — notify, send, email, discord, telegram, remind

Callers:
    frontend.blueprints.chat — suggest default target / validate relay
    frontend.services.queue_wrappers — classify inbound tickets
    fridays.discord_bot / telegram_bot / email — route inbound messages
    agents.seven.seven_agent — self-classify its own replies for audit

Usage:
    from core.routing import route
    decision = route(message='@ten fix the regex', sender='user',
                     routable_agents=registry.get_routable_agents())
    decision.target      # 'ten'
    decision.category    # 'coder'
    decision.confidence  # 0.95 (explicit @mention)
    decision.rationale   # '@mention of ten; routable'
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

__all__ = ['route', 'RouteDecision', 'SEVEN_ROLES', 'ROLE_KEYWORDS']


# ── The seven roles (routing categories) ─────────────────────────────────────
SEVEN_ROLES = (
    'voice',
    'coder',
    'researcher',
    'orchestrator',
    'memory',
    'auditor',
    'messenger',
)

# Role keywords — ordered by specificity. First match wins, so narrower patterns
# come before broader ones. Lowercased, whole-word matching via _has_keyword().
ROLE_KEYWORDS = {
    'coder': (
        'refactor', 'debug', 'fix the', 'patch', 'implement', 'write code',
        'write a function', 'regex', 'syntax error', 'traceback', 'bug',
        'compile', 'runtime error', 'exception',
    ),
    'researcher': (
        'look up', 'search for', 'find out', 'what is', 'who is',
        'latest', 'news about', 'summarise', 'summarize', 'research',
        'paper', 'article',
    ),
    'orchestrator': (
        'schedule', 'queue', 'enqueue', 'retry', 'stop', 'cancel',
        'assign to', 'relay to', 'hand off', 'handoff', 'dispatch',
        'route to',
    ),
    'memory': (
        'remember when', 'recall', 'what did i say', 'what did you say',
        'history of', 'log of', 'last time we', 'previously',
    ),
    'auditor': (
        'review', 'validate', 'verify', 'audit', 'check that',
        'approve', 'reject', 'sign off', 'pre-flight',
    ),
    'messenger': (
        'notify', 'send to discord', 'send to telegram', 'email',
        'remind me', 'push notification', 'alert',
    ),
    'voice': (
        'hello', 'hi ', 'hey', 'thanks', 'thank you', 'who are you',
        'what are you', 'tell me about', 'explain',
    ),
}

# Default agents per role. These are *hints*, not hard bindings. Actual
# resolution consults the routable list so disabled/missing agents fall through
# to the next-best candidate.
ROLE_DEFAULT_AGENTS = {
    'coder':        ('ten', 'nine', 'ghost_coder', 'qwen'),
    'researcher':   ('gemma', 'llama', 'mistral'),  # routed through silent-api (scholar/seeker) internally
    'orchestrator': ('duck', 'seven'),
    'memory':       ('librarian', 'duck'),
    'auditor':      ('duck', 'eleven', 'nineteen'),
    'messenger':    ('duck',),
    'voice':        ('seven', 'duck', 'gemma'),
}

# @mention pattern — captures `@name`, `@Ten`, `@ghost_coder`. Case-insensitive.
_MENTION_RE = re.compile(r'@([A-Za-z][A-Za-z0-9_-]{1,30})\b')

# Direct "name:" or "name," prefix — `Ten: fix the ...`, `Duck, can you ...`
_ADDRESS_RE = re.compile(
    r'^\s*([A-Za-z][A-Za-z0-9_-]{1,30})\s*[:,]\s+', re.MULTILINE,
)


@dataclass(frozen=True)
class RouteDecision:
    """Deterministic routing result. Safe to log in full for audit."""
    target: Optional[str]            # canonical agent name, or None if no decision
    category: str                    # one of SEVEN_ROLES
    confidence: float                # 0.0-1.0; 1.0 = explicit @mention
    rationale: str                   # short human-readable reason
    candidates: tuple = field(default_factory=tuple)  # other routable options in descending preference


def _has_keyword(text: str, keywords: Iterable[str]) -> Optional[str]:
    """Return the first keyword substring found in text (lowercased), or None."""
    for kw in keywords:
        if kw in text:
            return kw
    return None


def _normalize(name: Optional[str]) -> str:
    if not name:
        return ''
    return str(name).strip().lower()


def _pick_first_routable(candidates: Iterable[str], routable_set: set) -> Optional[str]:
    for c in candidates:
        if _normalize(c) in routable_set:
            return _normalize(c)
    return None


def route(
    message: str,
    sender: str = 'user',
    routable_agents: Optional[List[dict]] = None,
    explicit_target: Optional[str] = None,
) -> RouteDecision:
    """Classify a message and return the preferred routing target.

    Parameters
    ----------
    message : str
        Raw message body. Trimmed, case-insensitive matching.
    sender : str, default 'user'
        Who sent the message. Used only to avoid self-loops (an agent's own
        message never routes back to itself).
    routable_agents : list[dict], optional
        Output of ``utils.db.registry.get_routable_agents()``. Passed in so
        callers control caching. Empty/None → decision falls back to 'voice'
        with no target.
    explicit_target : str, optional
        Caller-provided target (e.g. UI dropdown selection). Wins over all
        other signals IF the target is in the routable set.

    Returns
    -------
    RouteDecision
        Pure-data record; safe to serialise for audit log.
    """
    text = (message or '').strip()
    lower = text.lower()
    sender_norm = _normalize(sender)
    routable_set = {
        _normalize(a.get('name')) for a in (routable_agents or [])
    }

    # Step 1: honor explicit target if it's routable.
    if explicit_target:
        tgt = _normalize(explicit_target)
        if tgt in routable_set:
            return RouteDecision(
                target=tgt,
                category='voice',
                confidence=1.0,
                rationale=f'explicit target "{tgt}" from caller; routable',
            )

    # Step 2: @mention wins if the mentioned agent is routable.
    for m in _MENTION_RE.finditer(text):
        tgt = _normalize(m.group(1))
        if tgt == sender_norm:
            continue  # don't route back to self
        if tgt in routable_set:
            return RouteDecision(
                target=tgt,
                category=_classify_category(lower),
                confidence=0.95,
                rationale=f'@{tgt} mention; routable',
            )

    # Step 3: "Name:" / "Name," address form.
    addr = _ADDRESS_RE.match(text)
    if addr:
        tgt = _normalize(addr.group(1))
        if tgt != sender_norm and tgt in routable_set:
            return RouteDecision(
                target=tgt,
                category=_classify_category(lower),
                confidence=0.85,
                rationale=f'direct address "{addr.group(1)}:"; routable',
            )

    # Step 4: role-keyword classification.
    category = _classify_category(lower)
    defaults = ROLE_DEFAULT_AGENTS.get(category, ())
    tgt = _pick_first_routable(defaults, routable_set)
    if tgt and tgt != sender_norm:
        # Remaining candidates in preference order, minus the picked one + sender.
        remaining = tuple(
            _normalize(c) for c in defaults
            if _normalize(c) in routable_set
            and _normalize(c) != tgt
            and _normalize(c) != sender_norm
        )
        return RouteDecision(
            target=tgt,
            category=category,
            confidence=0.6,
            rationale=f'role-match "{category}" → {tgt}',
            candidates=remaining,
        )

    # Step 5: no preferred default available — pick any routable, or bail.
    if routable_set:
        any_target = next(
            (n for n in sorted(routable_set) if n != sender_norm),
            None,
        )
        if any_target:
            return RouteDecision(
                target=any_target,
                category=category,
                confidence=0.3,
                rationale=f'fallback: no preferred agent for "{category}"',
            )

    return RouteDecision(
        target=None,
        category=category,
        confidence=0.0,
        rationale='no routable agents available',
    )


def _classify_category(lower_text: str) -> str:
    """Keyword match against ROLE_KEYWORDS. Returns 'voice' if nothing matches."""
    # Order matters: more specific roles first so generic 'voice' is last.
    priority = ('coder', 'orchestrator', 'memory', 'auditor',
                'researcher', 'messenger', 'voice')
    for role in priority:
        if _has_keyword(lower_text, ROLE_KEYWORDS.get(role, ())):
            return role
    return 'voice'
