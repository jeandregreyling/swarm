"""
utils/db/trace_log.py — Session 29 durable mirror for core.spine events.

Lazy schema install on first persist. Best-effort everywhere — callers in
the spine swallow exceptions so ring-emit cannot be broken by DB trouble.

Retention: rolling 7 days OR 20k rows (whichever trims first). `vacuum()`
is called opportunistically from list_events when the table grows past
the row cap; no background thread.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from ._connection import get_connection

logger = logging.getLogger('seven.trace_log')

_SCHEMA_READY = False
_ROW_CAP = 20_000
_MAX_AGE_SECONDS = 7 * 24 * 3600


_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_events (
    id          TEXT PRIMARY KEY,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    source      TEXT NOT NULL,
    agent       TEXT,
    thread_id   TEXT,
    change_id   TEXT,
    message     TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trace_events_ts ON trace_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_kind_ts ON trace_events(kind, ts DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_thread ON trace_events(thread_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_trace_events_change ON trace_events(change_id, ts DESC);
"""


def _ensure_schema(conn) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    conn.executescript(_SCHEMA)
    conn.commit()
    _SCHEMA_READY = True


def persist_event(ev) -> None:
    """Persist a TraceEvent. `ev` may be a dataclass or a dict-like object."""
    try:
        get = (lambda k: getattr(ev, k)) if hasattr(ev, 'id') else ev.get
        row = (
            get('id'),
            float(get('ts')),
            get('kind'),
            get('severity'),
            get('source'),
            get('agent'),
            get('thread_id'),
            get('change_id'),
            get('message'),
            json.dumps(get('payload') or {}, default=str),
        )
    except Exception as exc:
        logger.debug('persist_event: coerce failed: %s', exc)
        return

    try:
        conn = get_connection()
        try:
            _ensure_schema(conn)
            conn.execute(
                """INSERT OR REPLACE INTO trace_events
                   (id, ts, kind, severity, source, agent, thread_id,
                    change_id, message, payload)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                row,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.debug('persist_event: insert failed: %s', exc)


def list_events(
    *,
    limit: int = 200,
    kinds: Optional[Iterable[str]] = None,
    min_severity: Optional[str] = None,
    thread_id: Optional[str] = None,
    change_id: Optional[str] = None,
    since_ts: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Newest-first page of durable events."""
    try:
        conn = get_connection()
    except Exception as exc:
        logger.debug('list_events: connect failed: %s', exc)
        return []
    try:
        _ensure_schema(conn)

        clauses: List[str] = []
        params: List[Any] = []

        if kinds:
            k = list(kinds)
            clauses.append(f"kind IN ({','.join('?' for _ in k)})")
            params.extend(k)
        if thread_id:
            clauses.append('thread_id = ?')
            params.append(thread_id)
        if change_id:
            clauses.append('change_id = ?')
            params.append(change_id)
        if since_ts is not None:
            clauses.append('ts >= ?')
            params.append(float(since_ts))
        if min_severity:
            order = {'debug': 0, 'info': 1, 'warn': 2, 'error': 3, 'critical': 4}
            want = order.get(min_severity, 1)
            wanted = [s for s, v in order.items() if v >= want]
            clauses.append(f"severity IN ({','.join('?' for _ in wanted)})")
            params.extend(wanted)

        where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
        sql = f"""SELECT id, ts, kind, severity, source, agent, thread_id,
                          change_id, message, payload
                   FROM trace_events {where}
                   ORDER BY ts DESC LIMIT ?"""
        params.append(max(1, min(int(limit), 1000)))

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.debug('list_events: query failed: %s', exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _row_to_dict(r) -> Dict[str, Any]:
    try:
        payload = json.loads(r['payload']) if r['payload'] else {}
    except Exception:
        payload = {}
    return {
        'id': r['id'],
        'ts': r['ts'],
        'kind': r['kind'],
        'severity': r['severity'],
        'source': r['source'],
        'agent': r['agent'],
        'thread_id': r['thread_id'],
        'change_id': r['change_id'],
        'message': r['message'],
        'payload': payload,
    }


def vacuum(*, max_age_seconds: int = _MAX_AGE_SECONDS, row_cap: int = _ROW_CAP) -> int:
    """Delete events older than `max_age_seconds` and trim to `row_cap`.

    Returns the number of rows deleted. Safe to call from tests.
    """
    deleted = 0
    try:
        conn = get_connection()
    except Exception:
        return 0
    try:
        _ensure_schema(conn)
        cutoff = time.time() - max_age_seconds
        cur = conn.execute('DELETE FROM trace_events WHERE ts < ?', (cutoff,))
        deleted += cur.rowcount or 0

        total = conn.execute('SELECT COUNT(*) FROM trace_events').fetchone()[0]
        if total > row_cap:
            to_drop = total - row_cap
            cur = conn.execute(
                """DELETE FROM trace_events WHERE id IN (
                     SELECT id FROM trace_events ORDER BY ts ASC LIMIT ?)""",
                (to_drop,),
            )
            deleted += cur.rowcount or 0
        conn.commit()
    except Exception as exc:
        logger.debug('vacuum: failed: %s', exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return deleted


def count() -> int:
    """Row count, for smoke and tests."""
    try:
        conn = get_connection()
    except Exception:
        return 0
    try:
        _ensure_schema(conn)
        return int(conn.execute('SELECT COUNT(*) FROM trace_events').fetchone()[0])
    except Exception:
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass
