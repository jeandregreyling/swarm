"""core/vortex_health.py — Stale-state probe for the Vortex (TimeMachine).

Regression for STEP-VORTEX-UPDATING-HEALTH-20260430.

Pure helper — no I/O outside the SQLite connection passed in. Returns a dict:

    {
      "ok": bool,
      "status": "healthy" | "stale" | "empty" | "missing",
      "last_event_at": iso-string | None,
      "age_seconds": int | None,
      "stale_threshold_seconds": int,
      "recovery_actions": [str, ...],
      "checkpoint_count": int,
      "event_count": int,
    }

UI / endpoints can render `status` as a banner and `recovery_actions` as
clickable buttons. The probe NEVER raises — a missing schema is reported
as "missing", not an exception.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

# Anything older than this with no new events is "stale" by default.
DEFAULT_STALE_THRESHOLD_SECONDS = 60 * 60 * 6  # 6 hours

_RECOVERY_HINTS = {
    "missing": [
        "Run TimeMachine.init_schema() to create the time_events table",
        "Restart the swarm-terminal service to re-bootstrap the Vortex",
    ],
    "empty": [
        "Trigger a manual checkpoint via /api/time/checkpoints",
        "Confirm background workflow recorders are running",
    ],
    "stale": [
        "Check swarm-terminal.service status",
        "Inspect logs/swarm.log for TimeMachine errors",
        "Trigger a manual checkpoint to confirm writes succeed",
    ],
}


def _table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _last_event_row(conn) -> tuple[str | None, int]:
    """Return (last_event_at, total_event_count) or (None, 0) if unavailable."""
    if not _table_exists(conn, "time_events"):
        return None, 0
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM time_events").fetchone()
        count = int(cnt[0]) if cnt else 0
        if count == 0:
            return None, 0
        last = conn.execute(
            "SELECT MAX(timestamp) FROM time_events"
        ).fetchone()
        return (last[0] if last else None), count
    except Exception:
        return None, 0


def _checkpoint_count(conn) -> int:
    if not _table_exists(conn, "checkpoints"):
        return 0
    try:
        row = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _parse_iso(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        # Common formats: '2026-05-02T00:50:47' or '2026-05-02 00:50:47'
        cleaned = s.replace("T", " ").split(".")[0].rstrip("Z")
        return _dt.datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def probe(
    conn,
    *,
    now: _dt.datetime | None = None,
    stale_threshold_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Return a Vortex health snapshot. See module docstring for shape."""
    if now is None:
        now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)

    snapshot: dict[str, Any] = {
        "ok": False,
        "status": "missing",
        "last_event_at": None,
        "age_seconds": None,
        "stale_threshold_seconds": int(stale_threshold_seconds),
        "recovery_actions": [],
        "checkpoint_count": 0,
        "event_count": 0,
    }

    if conn is None:
        snapshot["recovery_actions"] = list(_RECOVERY_HINTS["missing"])
        return snapshot

    if not _table_exists(conn, "time_events"):
        snapshot["recovery_actions"] = list(_RECOVERY_HINTS["missing"])
        return snapshot

    last_at, event_count = _last_event_row(conn)
    snapshot["last_event_at"] = last_at
    snapshot["event_count"] = event_count
    snapshot["checkpoint_count"] = _checkpoint_count(conn)

    if event_count == 0 or last_at is None:
        snapshot["status"] = "empty"
        snapshot["recovery_actions"] = list(_RECOVERY_HINTS["empty"])
        return snapshot

    parsed = _parse_iso(last_at)
    if parsed is None:
        # Couldn't parse the timestamp — treat as stale rather than healthy.
        snapshot["status"] = "stale"
        snapshot["recovery_actions"] = list(_RECOVERY_HINTS["stale"])
        return snapshot

    age = max(0, int((now - parsed).total_seconds()))
    snapshot["age_seconds"] = age

    if age > stale_threshold_seconds:
        snapshot["status"] = "stale"
        snapshot["recovery_actions"] = list(_RECOVERY_HINTS["stale"])
        return snapshot

    snapshot["status"] = "healthy"
    snapshot["ok"] = True
    return snapshot


def banner_text(snapshot: dict[str, Any]) -> str | None:
    """Return a short user-facing banner string, or None when healthy."""
    status = snapshot.get("status")
    if status == "healthy":
        return None
    if status == "missing":
        return "Vortex schema not found — run init or restart the service."
    if status == "empty":
        return "Vortex is online but has no events recorded yet."
    if status == "stale":
        age = snapshot.get("age_seconds")
        if isinstance(age, int):
            hours = age // 3600
            if hours >= 1:
                return f"Vortex stopped updating ~{hours}h ago — check service health."
        return "Vortex stopped updating — check service health."
    return f"Vortex status unknown: {status}"


__all__ = [
    "DEFAULT_STALE_THRESHOLD_SECONDS",
    "banner_text",
    "probe",
]
