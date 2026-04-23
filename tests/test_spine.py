"""
test_spine.py — Session 29 contract tests for core/spine.py.

Verifies the in-memory ring, fanout to subscribers, guardian routing,
and the durable DB mirror via utils.db.trace_log.
"""
from __future__ import annotations

import os
import queue
import sys
import tempfile
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ('', 'frontend', 'utils', 'core'):
    _p = os.path.join(_ROOT, _sub) if _sub else _ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(autouse=True)
def _clean_ring():
    from core import spine
    spine.clear_ring()
    yield
    spine.clear_ring()


# ── Ring + log() ────────────────────────────────────────────────────────────

def test_log_returns_event_and_populates_ring():
    from core import spine
    ev = spine.log(spine.EventKind.SYSTEM, 'hello', persist=False)
    assert ev.kind == 'system'
    assert ev.message == 'hello'
    assert ev.id
    recent = spine.get_recent(limit=5)
    assert len(recent) == 1
    assert recent[0].id == ev.id


def test_unknown_kind_coerces_to_system():
    from core import spine
    ev = spine.log('not-a-real-kind', 'x', persist=False)
    assert ev.kind == 'system'


def test_severity_filter():
    from core import spine
    spine.log(spine.EventKind.SYSTEM, 'a', severity='debug', persist=False)
    spine.log(spine.EventKind.SYSTEM, 'b', severity='warn', persist=False)
    spine.log(spine.EventKind.SYSTEM, 'c', severity='error', persist=False)
    warn_plus = spine.get_recent(min_severity='warn')
    assert {e.message for e in warn_plus} == {'b', 'c'}


def test_kind_filter():
    from core import spine
    spine.log(spine.EventKind.WATCHDOG, 'stall', persist=False)
    spine.log(spine.EventKind.TICKET, 'opened', persist=False)
    spine.log(spine.EventKind.CHECKPOINT, 'made', persist=False)
    tix = spine.get_recent(kinds=[spine.EventKind.TICKET])
    assert len(tix) == 1 and tix[0].message == 'opened'


def test_thread_and_change_filter():
    from core import spine
    spine.log(spine.EventKind.CHAT, 'x', thread_id='t1', persist=False)
    spine.log(spine.EventKind.CHAT, 'y', thread_id='t2', persist=False)
    spine.log(spine.EventKind.TESTLAB, 'z', change_id='1306', persist=False)
    assert len(spine.get_recent(thread_id='t1')) == 1
    assert len(spine.get_recent(change_id='1306')) == 1


def test_ring_is_bounded():
    from core import spine
    for i in range(spine.RING_MAX + 50):
        spine.log(spine.EventKind.SYSTEM, f'm{i}', persist=False)
    assert len(spine.get_recent(limit=10_000)) == spine.RING_MAX


def test_message_truncation():
    from core import spine
    big = 'x' * 5000
    ev = spine.log(spine.EventKind.SYSTEM, big, persist=False)
    assert len(ev.message) == 2000


# ── Subscribers ─────────────────────────────────────────────────────────────

def test_subscribe_receives_emit():
    from core import spine
    q = queue.Queue(maxsize=10)
    spine.subscribe(q)
    try:
        spine.log(spine.EventKind.SYSTEM, 'hi', persist=False)
        got = q.get(timeout=0.5)
        assert got['message'] == 'hi'
        assert got['kind'] == 'system'
    finally:
        spine.unsubscribe(q)


def test_full_subscriber_is_dropped():
    from core import spine
    q = queue.Queue(maxsize=1)
    q.put('occupied')  # fill it
    spine.subscribe(q)
    try:
        spine.log(spine.EventKind.SYSTEM, 'x', persist=False)
        # dead queue removed on next emit
        spine.log(spine.EventKind.SYSTEM, 'y', persist=False)
        # q never received events — still has only the original item
        assert q.qsize() == 1
    finally:
        spine.unsubscribe(q)


# ── Guardian routing ────────────────────────────────────────────────────────

def test_route_passes_through_confident_decision():
    from core import spine
    r = spine.route(
        'ten: please fix the regex',
        sender='user',
        routable_agents=['seven', 'ten', 'gemma'],
    )
    assert r.guardian is False
    assert r.target == 'ten'


def test_route_intercepts_low_confidence(monkeypatch):
    """Low-confidence non-Seven pick → Seven takes first refusal."""
    from core import spine, routing

    class FakeDecision:
        target = 'gemma'
        category = 'voice'
        confidence = 0.4
        rationale = 'fallback'

    monkeypatch.setattr(routing, 'route', lambda **kw: FakeDecision())
    r = spine.route(
        'hmm',
        sender='user',
        routable_agents=['seven', 'gemma'],
    )
    assert r.guardian is True
    assert r.target == 'seven'
    assert r.original_target == 'gemma'


def test_route_intercepts_unroutable_target(monkeypatch):
    """Confident pick but target isn't routable → Seven takes it."""
    from core import spine, routing

    class FakeDecision:
        target = 'gemma'
        category = 'voice'
        confidence = 0.9
        rationale = 'keyword match'

    monkeypatch.setattr(routing, 'route', lambda **kw: FakeDecision())
    r = spine.route(
        'anything',
        sender='user',
        routable_agents=['seven', 'ten'],   # gemma NOT in set
    )
    assert r.guardian is True
    assert r.target == 'seven'
    assert r.original_target == 'gemma'


def test_route_seven_default_is_passthrough():
    """When the classifier already picks Seven, no guardian intercept needed."""
    from core import spine
    r = spine.route(
        'hmm',
        sender='user',
        routable_agents=['seven', 'ten'],
    )
    assert r.guardian is False
    assert r.target == 'seven'


def test_route_seven_sender_never_rerouted():
    from core import spine
    r = spine.route('anything at all', sender='seven', routable_agents=['seven'])
    assert r.guardian is False


def test_guardian_intercept_logs_event(monkeypatch):
    from core import spine, routing

    class FakeDecision:
        target = 'gemma'
        category = 'voice'
        confidence = 0.3
        rationale = 'low-conf'

    monkeypatch.setattr(routing, 'route', lambda **kw: FakeDecision())
    spine.route('ambiguous', sender='user', routable_agents=['seven', 'gemma'])
    guardians = spine.get_recent(kinds=[spine.EventKind.GUARDIAN])
    assert len(guardians) >= 1
    assert guardians[0].agent == 'seven'


# ── Durable mirror (utils.db.trace_log) ─────────────────────────────────────

@pytest.fixture
def isolated_db(monkeypatch):
    """Point DB_PATH at a fresh temp file so we don't pollute swarm_memory.db."""
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setenv('SWARM_DB_PATH', tmp.name)
    # Force _connection module to pick up the new path
    from utils.db import _connection
    monkeypatch.setattr(_connection, 'DB_PATH', tmp.name)
    # Force trace_log to re-install schema in the new DB
    from utils.db import trace_log
    monkeypatch.setattr(trace_log, '_SCHEMA_READY', False)
    yield tmp.name
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_persist_and_list(isolated_db):
    from core import spine
    from utils.db import trace_log
    spine.log(spine.EventKind.TICKET, 'opened 1', source='listener')
    spine.log(spine.EventKind.CHECKPOINT, 'snap', source='time_machine')
    rows = trace_log.list_events(limit=10)
    kinds = {r['kind'] for r in rows}
    assert 'ticket' in kinds
    assert 'checkpoint' in kinds


def test_list_events_filter_by_kind(isolated_db):
    from core import spine
    from utils.db import trace_log
    spine.log(spine.EventKind.WATCHDOG, 'stall')
    spine.log(spine.EventKind.TICKET, 'open')
    rows = trace_log.list_events(kinds=['watchdog'], limit=10)
    assert len(rows) == 1
    assert rows[0]['kind'] == 'watchdog'


def test_vacuum_removes_old_rows(isolated_db):
    from core import spine
    from utils.db import trace_log
    from utils.db._connection import get_connection

    spine.log(spine.EventKind.SYSTEM, 'recent')
    # Hand-forge an ancient row
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO trace_events (id, ts, kind, severity, source, message, payload)
               VALUES ('old', ?, 'system', 'info', 't', 'old', '{}')""",
            (time.time() - 14 * 24 * 3600,),
        )
        conn.commit()
    finally:
        conn.close()

    deleted = trace_log.vacuum(max_age_seconds=7 * 24 * 3600)
    assert deleted >= 1
    remaining = {r['id'] for r in trace_log.list_events(limit=100)}
    assert 'old' not in remaining


def test_persist_survives_bad_payload(isolated_db):
    from core import spine
    from utils.db import trace_log

    class Weird:
        def __repr__(self):
            return 'weird'

    spine.log(spine.EventKind.SYSTEM, 'x', payload={'obj': Weird()})
    rows = trace_log.list_events(limit=5)
    assert any(r['message'] == 'x' for r in rows)


# ── Session 29.1 — activity_log mirror for warn+ events ─────────────────────

def test_warn_event_mirrors_to_activity_log(isolated_db):
    """spine.log() at warn+ severity should also write to activity_log so the
    Trace tile's System Log tab and /api/activity/stream surface it."""
    from core import spine
    from utils.db._connection import get_connection
    from utils.db.audit import get_activity_log

    # The isolated temp DB doesn't include activity_log — create it.
    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT, event TEXT, detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

    spine.log(spine.EventKind.WATCHDOG, 'gemma stalled after 1000s',
              severity='warn', source='chat_jobs', agent='gemma')
    rows = get_activity_log(limit=20)
    matched = [r for r in rows if r['event'] == 'watchdog' and 'gemma' in (r['detail'] or '')]
    assert matched, f'expected watchdog row in activity_log, got {rows!r}'


def test_info_event_does_not_mirror_to_activity_log(isolated_db):
    """Info-level spine events stay in the spine ring/DB only — they should NOT
    pollute activity_log. Activity log is for warn+ glitches."""
    from core import spine
    from utils.db._connection import get_connection
    from utils.db.audit import get_activity_log

    conn = get_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT, event TEXT, detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

    spine.log(spine.EventKind.RELAY_STEP, 'gemma → seven',
              severity='info', source='chat')
    rows = get_activity_log(limit=20)
    assert not any(r['event'] == 'relay_step' for r in rows), \
        f'info-level relay_step should not mirror to activity_log, got {rows!r}'
