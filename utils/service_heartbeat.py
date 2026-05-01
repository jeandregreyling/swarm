"""Service heartbeat helpers (S-E056DBAD19, S-B1279A66EB).

Long-running daemons (listener, scheduler, terminal) call ``record_heartbeat``
on startup and once per loop. Health endpoints can read the table and warn
when a service hasn't beaten in N minutes or its ``restart_count`` is climbing.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Optional


def _conn():
    from utils.db._connection import get_connection
    return get_connection()


def _git_short_sha() -> str:
    """Return the current git short SHA, or ``''`` on failure."""
    try:
        out = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ''


def record_startup(service_name: str, *, code_version: Optional[str] = None) -> None:
    """Write a startup beat — increments ``restart_count``."""
    version = code_version if code_version is not None else _git_short_sha()
    pid = os.getpid()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT restart_count FROM service_heartbeat WHERE service_name=?",
                (service_name,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE service_heartbeat SET code_version=?, started_at=?, "
                    "last_beat_at=?, pid=?, restart_count=restart_count+1, "
                    "last_restart_at=? WHERE service_name=?",
                    (version, now, now, pid, now, service_name),
                )
            else:
                conn.execute(
                    "INSERT INTO service_heartbeat (service_name, code_version, "
                    "started_at, last_beat_at, pid, restart_count, last_restart_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, '')",
                    (service_name, version, now, now, pid),
                )
            conn.commit()
    except Exception:
        pass


def record_beat(service_name: str) -> None:
    """Update ``last_beat_at`` for an already-registered service. No-op on error."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with _conn() as conn:
            conn.execute(
                "UPDATE service_heartbeat SET last_beat_at=? WHERE service_name=?",
                (now, service_name),
            )
            conn.commit()
    except Exception:
        pass


def warnings(stale_minutes: int = 5, restart_threshold: int = 3) -> list[dict]:
    """Return a list of warnings for services that look unhealthy."""
    out: list[dict] = []
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT service_name, code_version, started_at, last_beat_at, "
                "pid, restart_count, last_restart_at FROM service_heartbeat"
            ).fetchall()
    except Exception:
        return out
    now = datetime.now()
    for r in rows:
        name, version, started_at, last_beat_at, pid, restart_count, last_restart_at = r
        try:
            last = datetime.strptime(last_beat_at, '%Y-%m-%d %H:%M:%S')
            stale = (now - last).total_seconds() / 60.0
        except Exception:
            stale = 0
        if stale > stale_minutes:
            out.append({
                'service': name,
                'kind': 'stale_heartbeat',
                'minutes_since_beat': round(stale, 1),
                'last_beat_at': last_beat_at,
            })
        if (restart_count or 0) >= restart_threshold:
            out.append({
                'service': name,
                'kind': 'frequent_restarts',
                'restart_count': restart_count,
                'last_restart_at': last_restart_at,
                'code_version': version,
            })
    return out
