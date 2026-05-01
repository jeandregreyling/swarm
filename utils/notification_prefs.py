"""Notification channel preferences (S-859446F555).

Single source of truth for "where should a notification for X go?".

Keys are namespaced free-form strings — e.g. ``topic:sap-news``,
``agent:eight``, ``ticket:approval``. Callers fall back to ``default`` when
no key-specific row exists.
"""
from __future__ import annotations

import json
from typing import Iterable


VALID_CHANNELS = ('email', 'discord', 'telegram', 'terminal')


def _conn():
    from utils.db._connection import get_connection
    return get_connection()


def get_channels(key: str, *, default: Iterable[str] = ('email',)) -> list[str]:
    """Return the channels configured for ``key`` (falls back to ``default``)."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT channels_json, muted FROM notification_channel_prefs "
                "WHERE key=?", (key,)
            ).fetchone()
    except Exception:
        return list(default)
    if not row:
        return list(default)
    if row[1]:
        return []
    try:
        ch = json.loads(row[0]) if row[0] else list(default)
        return [c for c in ch if c in VALID_CHANNELS]
    except Exception:
        return list(default)


def set_channels(key: str, channels: Iterable[str], *, muted: bool = False) -> None:
    """Set the channels for ``key``. Invalid channels are silently dropped."""
    cleaned = [c for c in channels if c in VALID_CHANNELS]
    payload = json.dumps(cleaned)
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO notification_channel_prefs "
                "(key, channels_json, muted, updated_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET "
                "channels_json=excluded.channels_json, "
                "muted=excluded.muted, "
                "updated_at=datetime('now')",
                (key, payload, 1 if muted else 0),
            )
            conn.commit()
    except Exception:
        pass


def is_muted(key: str) -> bool:
    """Return True if ``key`` is explicitly muted."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT muted FROM notification_channel_prefs WHERE key=?",
                (key,),
            ).fetchone()
    except Exception:
        return False
    return bool(row and row[0])


def list_all() -> list[dict]:
    """Return every preference row, useful for the settings UI."""
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT key, channels_json, muted, updated_at "
                "FROM notification_channel_prefs ORDER BY key"
            ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            channels = json.loads(r[1]) if r[1] else []
        except Exception:
            channels = []
        out.append({
            'key': r[0], 'channels': channels,
            'muted': bool(r[2]), 'updated_at': r[3],
        })
    return out
