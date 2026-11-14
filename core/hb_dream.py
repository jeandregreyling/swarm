"""Persistent DREAM inactivity primitives; authenticated observers are wired separately."""
import math
import time
import json
from datetime import datetime, timezone


def ensure_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_dream_activity(id INTEGER PRIMARY KEY CHECK(id=1), timestamp REAL NOT NULL, source_key TEXT NOT NULL)")


def _observe(conn, timestamp, source_key):
    ensure_schema(conn)
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("A finite UTC owner timestamp is required")
    return conn.execute("INSERT INTO hb_dream_activity VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET timestamp=excluded.timestamp,source_key=excluded.source_key WHERE excluded.timestamp>hb_dream_activity.timestamp", (timestamp, source_key)).rowcount > 0

def observe_native_event(conn, event_id):
    row = conn.execute(
        "SELECT payload FROM hb_task_events WHERE event_id=? AND agent=? AND kind=?",
        (event_id, "owner-host", "owner_input_observed"),
    ).fetchone()
    if row is None:
        return False
    try:
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            return False
        stamp = payload.get("timestamp")
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            stamp = stamp.timestamp()
        return _observe(conn, stamp, f"native:{event_id}")
    except (ValueError, TypeError, OverflowError):
        return False

def idle_seconds(conn, now=None):
    ensure_schema(conn)
    row = conn.execute("SELECT timestamp FROM hb_dream_activity WHERE id=1").fetchone()
    if row is None:
        return None
    return max(0.0, (time.time() if now is None else now) - row[0])
def observe_owner_message(conn, message_id):
    row = conn.execute(
        "SELECT created_at FROM messages WHERE id=? AND from_agent=? AND message_type=?",
        (message_id, "user", "chat"),
    ).fetchone()
    if row is None:
        return False
    try:
        stamp = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.timestamp()
        return _observe(conn, stamp, f"message_id:{message_id}")
    except (ValueError, TypeError, OverflowError):
        return False