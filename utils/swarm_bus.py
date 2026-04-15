"""
utils/swarm_bus.py — Lightweight internal message bus (A.4.2)
═══════════════════════════════════════════════════════════════
SQLite-backed publish/subscribe. Same interface can later be
swapped to Redis/NATS by changing the transport functions.

Topics:
  proposal.created, proposal.status_changed,
  knowledge.new, agent.status_changed
"""

import json
import logging
import datetime
import threading
from collections import defaultdict

from utils.db._connection import get_connection

logger = logging.getLogger(__name__)

# ── In-process subscriber registry ────────────────────────────────────────────
# topic → list of callables: fn(topic, payload_dict, source_service)
_subscribers = defaultdict(list)
_lock = threading.Lock()


def subscribe(topic, handler):
    """Register an in-process handler for *topic*.

    handler signature: handler(topic: str, payload: dict, source: str) -> None
    """
    with _lock:
        _subscribers[topic].append(handler)


def unsubscribe(topic, handler):
    """Remove a previously registered handler."""
    with _lock:
        try:
            _subscribers[topic].remove(handler)
        except ValueError:
            pass


# ── Publish ───────────────────────────────────────────────────────────────────

def publish(topic, payload, source_service='local', *, conn=None):
    """Persist a message to swarm_bus and notify in-process subscribers.

    Returns the new message id.
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
        cur = conn.execute(
            """INSERT INTO swarm_bus
               (topic, payload_json, source_service, created_at)
               VALUES (?, ?, ?, ?)""",
            (topic, payload_str, source_service, now)
        )
        msg_id = cur.lastrowid
        if own:
            conn.commit()
        # Fire in-process subscribers (best-effort, never block publish)
        _dispatch(topic, payload if isinstance(payload, dict) else {'raw': payload_str}, source_service)
        return msg_id
    finally:
        if own:
            conn.close()


def _dispatch(topic, payload, source):
    """Fire registered handlers. Exceptions are logged, never propagated."""
    with _lock:
        handlers = list(_subscribers.get(topic, []))
    for fn in handlers:
        try:
            fn(topic, payload, source)
        except Exception:
            logger.exception('swarm_bus handler %s failed for topic %s', fn.__name__, topic)


# ── Consume / poll ────────────────────────────────────────────────────────────

def get_unconsumed(*, topic=None, limit=50, conn=None):
    """Fetch messages not yet marked consumed. Newest first."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        sql = "SELECT * FROM swarm_bus WHERE consumed_at IS NULL"
        params = []
        if topic:
            sql += " AND topic = ?"
            params.append(topic)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def mark_consumed(msg_id, *, conn=None):
    """Mark a single message as consumed."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "UPDATE swarm_bus SET consumed_at = ? WHERE id = ?",
            (now, msg_id)
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def mark_consumed_batch(msg_ids, *, conn=None):
    """Bulk-mark messages as consumed."""
    if not msg_ids:
        return
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
        placeholders = ','.join('?' for _ in msg_ids)
        conn.execute(
            f"UPDATE swarm_bus SET consumed_at = ? WHERE id IN ({placeholders})",
            [now] + list(msg_ids)
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_recent(*, topic=None, limit=20, conn=None):
    """Get recent messages regardless of consumed state."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        sql = "SELECT * FROM swarm_bus"
        params = []
        if topic:
            sql += " WHERE topic = ?"
            params.append(topic)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()
