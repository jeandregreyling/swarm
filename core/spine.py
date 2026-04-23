"""
core/spine.py — Session 29: Seven-as-spine.

One event ring, one router gate. Every significant thing that happens in the
swarm — relay steps, watchdog stalls, checkpoint creates, ticket filings,
test-lab runs, classifier decisions — emits through `log(event)` here.
Trace (ticker), Traced (history), and Vortex (timeline) all read from this.

Design contract:
    * Pure functions where possible. No I/O inside hot paths.
    * In-memory deque ring (default 500) is the fast path.
    * Optional durable mirror via `utils.db.trace_log.persist_event()`.
      The mirror is best-effort; failure to persist must NEVER break emit.
    * Subscribers are `queue.Queue` instances registered at SSE open; they
      receive `TraceEvent` dicts. Dead queues are dropped on next emit.
    * `route()` is the Seven-as-guardian wrapper around `core.routing.route`.
      Low-confidence decisions (< GUARDIAN_THRESHOLD) are rerouted to Seven.

Not in scope here:
    * Rendering — consumers format events themselves.
    * Retention — DB mirror owns retention/cleanup, not this module.
    * Auth — SSE endpoint enforces session auth, not this module.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    'log', 'get_recent', 'subscribe', 'unsubscribe', 'clear_ring',
    'route', 'TraceEvent', 'EventKind', 'Severity',
    'GUARDIAN_THRESHOLD', 'RING_MAX',
]


# ── Constants ───────────────────────────────────────────────────────────────

RING_MAX = 500
GUARDIAN_THRESHOLD = 0.6  # below → Seven takes first refusal


class EventKind:
    """Canonical event kinds. Strings, not an Enum, so tests/JS can use raw."""
    RELAY_STEP = 'relay_step'
    WATCHDOG = 'watchdog'
    CHECKPOINT = 'checkpoint'
    TICKET = 'ticket'
    TESTLAB = 'testlab'
    ROUTE = 'route'
    CHAT = 'chat'
    SYSTEM = 'system'
    GUARDIAN = 'guardian'

    ALL = frozenset({
        RELAY_STEP, WATCHDOG, CHECKPOINT, TICKET,
        TESTLAB, ROUTE, CHAT, SYSTEM, GUARDIAN,
    })


class Severity:
    DEBUG = 'debug'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'
    CRITICAL = 'critical'

    ORDER = {'debug': 0, 'info': 1, 'warn': 2, 'error': 3, 'critical': 4}

    @classmethod
    def at_least(cls, ev_sev: str, min_sev: str) -> bool:
        return cls.ORDER.get(ev_sev, 1) >= cls.ORDER.get(min_sev, 1)


@dataclass(frozen=True)
class TraceEvent:
    id: str
    ts: float                  # unix seconds, float
    kind: str
    severity: str
    source: str                # subsystem, e.g. 'chat_jobs', 'time_machine'
    agent: Optional[str]       # canonical agent name, if any
    thread_id: Optional[str]
    change_id: Optional[str]
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── State ───────────────────────────────────────────────────────────────────

_RING: "deque[TraceEvent]" = deque(maxlen=RING_MAX)
_RING_LOCK = Lock()
_SUBSCRIBERS: "list" = []       # list of queue.Queue
_SUB_LOCK = Lock()


# ── Public API ──────────────────────────────────────────────────────────────

def log(
    kind: str,
    message: str,
    *,
    severity: str = Severity.INFO,
    source: str = 'spine',
    agent: Optional[str] = None,
    thread_id: Optional[str] = None,
    change_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    persist: bool = True,
) -> TraceEvent:
    """Emit a single event. Returns the stored TraceEvent.

    Best-effort: never raises on subscriber/mirror failure.
    """
    if kind not in EventKind.ALL:
        # Accept unknown kinds but coerce so ring stays predictable
        kind = EventKind.SYSTEM
    if severity not in Severity.ORDER:
        severity = Severity.INFO

    ev = TraceEvent(
        id=uuid.uuid4().hex[:16],
        ts=time.time(),
        kind=kind,
        severity=severity,
        source=str(source or 'spine')[:64],
        agent=(agent or None),
        thread_id=(thread_id or None),
        change_id=(change_id or None),
        message=str(message or '')[:2000],
        payload=dict(payload or {}),
    )

    with _RING_LOCK:
        _RING.append(ev)

    # Best-effort durable mirror.
    if persist:
        try:
            from utils.db import trace_log as _tl  # lazy to avoid import cycle
            _tl.persist_event(ev)
        except Exception:
            pass

    # Session 29.1 — also mirror warn+ events into the legacy activity_log so
    # the existing Trace tile "System Log" tab and `/api/activity/stream` SSE
    # surface spine glitches alongside listener/scheduler entries. Keeps Trace,
    # Traced, ticker and System Log visually coherent without any UI plumbing.
    if persist and Severity.at_least(ev.severity, Severity.WARN):
        try:
            from utils.db.audit import log_activity as _log_activity
            _detail = ev.message
            if ev.agent:
                _detail = f"{ev.agent} · {_detail}"
            _log_activity(
                service=str(ev.source or 'spine')[:64],
                event=str(ev.kind),
                detail=_detail,
                severity=ev.severity,
            )
        except Exception:
            pass

    # Fanout to SSE subscribers. Drop full/broken queues silently.
    _fanout(ev)

    return ev


def get_recent(
    *,
    limit: int = 100,
    kinds: Optional[Iterable[str]] = None,
    min_severity: Optional[str] = None,
    thread_id: Optional[str] = None,
    change_id: Optional[str] = None,
) -> List[TraceEvent]:
    """Return most-recent-first events from the in-memory ring."""
    kind_set = set(kinds) if kinds else None
    with _RING_LOCK:
        snapshot = list(_RING)
    snapshot.reverse()
    out: List[TraceEvent] = []
    for ev in snapshot:
        if kind_set and ev.kind not in kind_set:
            continue
        if min_severity and not Severity.at_least(ev.severity, min_severity):
            continue
        if thread_id and ev.thread_id != thread_id:
            continue
        if change_id and ev.change_id != change_id:
            continue
        out.append(ev)
        if len(out) >= limit:
            break
    return out


def subscribe(q) -> None:
    """Register an SSE queue. Caller owns lifecycle; call `unsubscribe` on close."""
    with _SUB_LOCK:
        if q not in _SUBSCRIBERS:
            _SUBSCRIBERS.append(q)


def unsubscribe(q) -> None:
    with _SUB_LOCK:
        try:
            _SUBSCRIBERS.remove(q)
        except ValueError:
            pass


def clear_ring() -> None:
    """Test helper — wipe the in-memory ring only."""
    with _RING_LOCK:
        _RING.clear()


def _fanout(ev: TraceEvent) -> None:
    with _SUB_LOCK:
        subs = list(_SUBSCRIBERS)
    dead = []
    for q in subs:
        try:
            q.put_nowait(ev.to_dict())
        except Exception:
            dead.append(q)
    if dead:
        with _SUB_LOCK:
            for q in dead:
                try:
                    _SUBSCRIBERS.remove(q)
                except ValueError:
                    pass


# ── Seven-as-guardian routing ───────────────────────────────────────────────

@dataclass(frozen=True)
class SpineRoute:
    target: str
    category: str
    confidence: float
    rationale: str
    guardian: bool                 # True if Seven intercepted
    original_target: Optional[str]  # what the classifier would have picked


def route(
    message: str,
    *,
    sender: str = 'user',
    routable_agents: Optional[Iterable[Any]] = None,
    explicit_target: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> SpineRoute:
    """Seven-guarded wrapper around core.routing.route.

    Rules:
      * If the underlying decision is confident (>= GUARDIAN_THRESHOLD) and
        the target is a real, routable agent — pass through unchanged.
      * If confidence is low, OR the chosen target isn't in routable_agents,
        OR an explicit target resolves to a disabled agent — Seven takes first mic.
      * Explicit sender='seven' is never rerouted (avoid loops).

    routable_agents accepts either a list of dicts (as returned by
    ``utils.db.registry.get_routable_agents()``) or a list of plain names.
    """
    from core.routing import route as _underlying_route

    # Normalise routable_agents to the shape core.routing expects (list of dicts).
    raw = list(routable_agents or [])
    agent_dicts: List[Dict[str, Any]] = []
    name_set: set = set()
    for a in raw:
        if isinstance(a, dict):
            n = a.get('name')
            if n:
                agent_dicts.append(a)
                name_set.add(str(n).lower())
        elif isinstance(a, str):
            agent_dicts.append({'name': a})
            name_set.add(a.lower())

    decision = _underlying_route(
        message=message,
        sender=sender,
        routable_agents=agent_dicts,
        explicit_target=explicit_target,
    )

    target = getattr(decision, 'target', None) or 'seven'
    category = getattr(decision, 'category', 'voice')
    confidence = float(getattr(decision, 'confidence', 0.0) or 0.0)
    rationale = getattr(decision, 'rationale', '') or ''

    if sender == 'seven':
        return SpineRoute(target=target, category=category,
                          confidence=confidence, rationale=rationale,
                          guardian=False, original_target=target)

    target_ok = bool(target) and (not name_set or target.lower() in name_set or target == 'seven')
    confident = confidence >= GUARDIAN_THRESHOLD

    # Pass-through when target is Seven (he's already on the mic) or when the
    # classifier is both confident and routable. Guardian only intercepts
    # non-Seven picks that are uncertain or unroutable — this is the #2106 fix.
    if target == 'seven' or (confident and target_ok):
        return SpineRoute(target=target, category=category,
                          confidence=confidence, rationale=rationale,
                          guardian=False, original_target=target)

    # Guardian intercept — Seven takes first refusal.
    reason_bits = []
    if not confident:
        reason_bits.append(f'confidence {confidence:.2f} < {GUARDIAN_THRESHOLD}')
    if not target_ok:
        reason_bits.append(f'target {target!r} not routable')
    reason = '; '.join(reason_bits) or 'ambiguous'

    try:
        log(
            EventKind.GUARDIAN,
            f'Seven intercepted: {reason}',
            severity=Severity.INFO,
            source='spine.route',
            agent='seven',
            thread_id=thread_id,
            payload={
                'original_target': target,
                'category': category,
                'confidence': confidence,
                'message_preview': str(message or '')[:200],
            },
        )
    except Exception:
        pass

    return SpineRoute(
        target='seven',
        category=category,
        confidence=confidence,
        rationale=f'guardian: {reason}',
        guardian=True,
        original_target=target,
    )
