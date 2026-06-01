"""Advisory DEOS+ governor for Fridays runtime.

This module does not hard-block the runtime yet. It observes focus surface
events and state-mutating actions, emits violation notices for silent mutations
or padded language, and exposes a small composition helper for future agent
prompt injection.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any


_MUTATING_KINDS = {
    'sync',
    'sync_story',
    'checkpoint',
    'proposal_transition',
    'state_change',
    'write',
    'persist',
}

_PEOPLE_PLEASING_MARKERS = (
    'sorry',
    'i would be happy to help',
    "i'd be happy to help",
    "i'm afraid",
    'unfortunately',
)


class SovereignGovernor:
    """Enforces DEOS+ in advisory form.

    The current mode is intentionally advisory while legacy seams are still
    being instrumented. Violations are narrated and logged; they do not reject
    execution globally.
    """

    def __init__(self, node_identity: str, mode: str = 'advisory') -> None:
        self.node = str(node_identity or 'unknown-node')
        self.mode = str(mode or 'advisory')
        self.laws = {
            'VISIBLE_CAUSALITY': 'Every action must expose cause, actor, transition, and consequence.',
            'NO_STATE_WITHOUT_STORY': 'State mutation must be narratable before persistence.',
            'OPERATOR_TELEMETRY': 'Operator focus and cognition are first-class system signals.',
        }
        self._lock = threading.Lock()
        self._last_focus: dict[str, Any] = {}
        self._last_violation: dict[str, Any] = {}

    def state(self) -> dict[str, Any]:
        with self._lock:
            last_focus = dict(self._last_focus)
            last_violation = dict(self._last_violation)
        return {
            'node': self.node,
            'mode': self.mode,
            'laws': dict(self.laws),
            'last_focus': last_focus,
            'last_violation': last_violation,
        }

    def compose(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        context = dict(context or {})
        focus = context.get('focus_surface') or self.state().get('last_focus') or {}
        focus_label = focus.get('surface') or focus.get('title') or 'unknown-focus'
        preface = (
            f"[GOVERNANCE_PROTOCOL: FRIDAYS_SYSTEM]\n"
            f"Node: {self.node}\n"
            f"Mode: {self.mode}\n"
            f"Focus-Surface: {focus_label}\n"
            f"Rules:\n"
            f"1. Narrate origin, intent, transition, consequence, risk for mutating actions.\n"
            f"2. If causal link is missing, say so directly.\n"
            f"3. Do not add padding or false certainty.\n"
        )
        return f"{preface}\n{prompt}"

    def update_focus_surface(self, focus: dict[str, Any]) -> dict[str, Any]:
        event = {
            'node': self.node,
            'surface': str(focus.get('surface') or focus.get('window') or 'unknown-surface'),
            'title': str(focus.get('title') or ''),
            'source': str(focus.get('source') or 'ui'),
            'path': str(focus.get('path') or ''),
            'ts': int(time.time()),
        }
        with self._lock:
            self._last_focus = dict(event)
        self._emit_focus(event)
        return event

    def enforce(self, input_data: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(input_data or {})
        story_ok = self._validate_story(payload)
        if not story_ok and self._looks_mutating(payload):
            violation = self._violation(
                policy='NGAS',
                reason='Causal link missing for state mutation.',
                target=payload.get('target') or payload.get('kind') or payload.get('action') or 'unknown',
                detail='State your intent clearly before persisting.',
            )
            return violation

        text = self._extract_text(payload)
        if text and self._is_people_pleasing(text):
            violation = self._violation(
                policy='DGIF',
                reason='Linguistic padding detected.',
                target=payload.get('target') or payload.get('kind') or 'message',
                detail='Strip the fluff and state the root cause directly.',
            )
            return violation

        return {
            'status': 'APPROVED',
            'node': self.node,
            'mode': self.mode,
            'story_present': story_ok,
        }

    def _extract_text(self, payload: dict[str, Any]) -> str:
        for key in ('message', 'text', 'prompt', 'response'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ''

    def _looks_mutating(self, payload: dict[str, Any]) -> bool:
        kind = str(payload.get('kind') or payload.get('event_type') or payload.get('action') or '').strip().lower()
        if kind in _MUTATING_KINDS:
            return True
        return bool(payload.get('mutates_state'))

    def _validate_story(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        story = payload.get('story') if isinstance(payload.get('story'), dict) else payload
        return all(isinstance(story.get(key), dict) and story.get(key) for key in ('origin', 'intent', 'consequence'))

    def _is_people_pleasing(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _PEOPLE_PLEASING_MARKERS)

    def _violation(self, *, policy: str, reason: str, target: str, detail: str) -> dict[str, Any]:
        event = {
            'status': 'VIOLATION_NOTICE',
            'policy': policy,
            'node': self.node,
            'reason': reason,
            'target': str(target or ''),
            'detail': detail,
            'mode': self.mode,
            'ts': int(time.time()),
        }
        with self._lock:
            self._last_violation = dict(event)
        self._emit_violation(event)
        return event

    def _emit_focus(self, event: dict[str, Any]) -> None:
        try:
            from utils.swarm_bus import publish as bus_publish
            bus_publish('focus.surface', event, source_service='system_governor')
        except Exception:
            pass
        try:
            from core import spine
            spine.log(
                spine.EventKind.SYSTEM,
                f"focus_surface {event.get('surface')} @ {event.get('title') or event.get('path') or ''}".strip(),
                source='system_governor',
                payload={'kind': 'focus_surface', **event},
            )
        except Exception:
            pass

    def _emit_violation(self, event: dict[str, Any]) -> None:
        try:
            from utils.swarm_bus import publish as bus_publish
            bus_publish('governor.violation', event, source_service='system_governor')
        except Exception:
            pass
        try:
            from core import spine
            spine.log(
                spine.EventKind.SYSTEM,
                f"{event['policy']}: {event['reason']} target={event['target']}",
                severity=spine.Severity.WARN,
                source='system_governor',
                payload={'kind': 'governor_violation', **event},
            )
        except Exception:
            pass
        try:
            from utils.db.audit import log_activity, log_ghost_circle
            log_activity('governor', 'violation_notice', f"{event['policy']} | {event['target']} | {event['reason']}")
            log_ghost_circle('governor_violation', self.node, f"{event['policy']} | {event['target']} | {event['detail']}")
        except Exception:
            pass


_SINGLETON: SovereignGovernor | None = None
_SINGLETON_LOCK = threading.Lock()


def init_governor(*, node_identity: str | None = None, mode: str = 'advisory') -> SovereignGovernor:
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            mode = os.environ.get('SWARM_GOVERNOR_MODE', mode).strip() or mode
            if not node_identity:
                try:
                    from core.hive.local_node import get_local_node
                    node_identity = get_local_node().node_id
                except Exception:
                    node_identity = 'unknown-node'
            _SINGLETON = SovereignGovernor(node_identity=node_identity, mode=mode)
            try:
                from core import spine
                spine.log(
                    spine.EventKind.SYSTEM,
                    f"system governor online on {_SINGLETON.node} ({_SINGLETON.mode})",
                    source='system_governor',
                    payload={'kind': 'governor_boot', 'node': _SINGLETON.node, 'mode': _SINGLETON.mode},
                )
            except Exception:
                pass
        return _SINGLETON


def get_governor() -> SovereignGovernor:
    return init_governor()
