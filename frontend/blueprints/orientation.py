"""orientation.py — First-run orientation flag (Y.49 / STEP-DOCS-UX-BC3D33C260).

User feedback: "The Help tile is hard to find on first launch" + "confused about
the search bar". Surfaces a tiny orientation card on the home tile until the
user dismisses it. The actual content is served by the existing single-source
manual (`manual_content.MANUAL['orientation']`); this module only tracks
whether the user has seen / dismissed the card.

State table::

    orientation_seen(
        username TEXT PRIMARY KEY,
        seen_at  REAL NOT NULL,
        version  TEXT NOT NULL DEFAULT 'v1'
    )

Endpoints:
* GET  /api/orientation/seen        → { ok, seen, seen_at?, version? }
* POST /api/orientation/dismiss     → { ok, seen: true, seen_at, version }
* POST /api/orientation/reset       → { ok, reset: true }   (re-show the card)

Bumping `_VERSION` here causes the card to re-appear for everyone after a
release that changes orientation messaging — consistent UX contract for
"new things on home tile" announcements.
"""
from __future__ import annotations

import sqlite3
import time

from flask import Blueprint, jsonify, request

from services import get_connection

orientation_bp = Blueprint('orientation', __name__)

_VERSION = 'v1'


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS orientation_seen (
            username TEXT PRIMARY KEY,
            seen_at  REAL NOT NULL,
            version  TEXT NOT NULL DEFAULT 'v1'
        )"""
    )


def _username() -> str:
    # Single-user default; respects an explicit ?user= override for tests.
    return (request.args.get('user') or 'seven').strip()[:60] or 'seven'


@orientation_bp.route('/api/orientation/seen', methods=['GET'])
def seen():
    user = _username()
    conn = get_connection()
    try:
        _ensure_schema(conn)
        row = conn.execute(
            'SELECT seen_at, version FROM orientation_seen WHERE username=?',
            (user,),
        ).fetchone()
        if not row:
            return jsonify({'ok': True, 'seen': False, 'version': _VERSION})
        seen_at = row[0] if not hasattr(row, 'keys') else row['seen_at']
        ver = row[1] if not hasattr(row, 'keys') else row['version']
        # If the active orientation version moves ahead, treat as not-seen.
        if ver != _VERSION:
            return jsonify({'ok': True, 'seen': False, 'version': _VERSION,
                            'previous_version': ver})
        return jsonify({'ok': True, 'seen': True, 'seen_at': seen_at, 'version': ver})
    finally:
        conn.close()


@orientation_bp.route('/api/orientation/dismiss', methods=['POST'])
def dismiss():
    user = _username()
    now = time.time()
    conn = get_connection()
    try:
        _ensure_schema(conn)
        conn.execute(
            'INSERT INTO orientation_seen (username, seen_at, version) VALUES (?,?,?) '
            'ON CONFLICT(username) DO UPDATE SET seen_at=excluded.seen_at, version=excluded.version',
            (user, now, _VERSION),
        )
        conn.commit()
        return jsonify({'ok': True, 'seen': True, 'seen_at': now, 'version': _VERSION})
    finally:
        conn.close()


@orientation_bp.route('/api/orientation/reset', methods=['POST'])
def reset():
    user = _username()
    conn = get_connection()
    try:
        _ensure_schema(conn)
        conn.execute('DELETE FROM orientation_seen WHERE username=?', (user,))
        conn.commit()
        return jsonify({'ok': True, 'reset': True})
    finally:
        conn.close()
