"""
utils.db.research — Research session & evidence CRUD (B.1.2)
═══════════════════════════════════════════════════════════════════════════════
Tables: research_sessions, research_evidence
Deduplication: (session_id, source_url, snippet_hash)
"""

import hashlib
import json
import datetime
from ._connection import get_connection


# ── Session CRUD ──────────────────────────────────────────────────────────

VALID_STATUSES = ('planning', 'searching', 'analysing', 'synthesising', 'done', 'paused')
VALID_DEPTHS = ('quick', 'standard', 'deep')


def create_session(topic, *, depth='standard', requesting_agent='user',
                   linked_proposal_id='', conn=None):
    """Create a new research session. Returns the new session id."""
    if depth not in VALID_DEPTHS:
        raise ValueError(f"Invalid depth {depth!r}, must be one of {VALID_DEPTHS}")
    own = conn is None
    if own:
        conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO research_sessions
               (topic, depth, status, phases_json, linked_proposal_id, requesting_agent)
               VALUES (?, ?, 'planning', '[]', ?, ?)""",
            (topic, depth, linked_proposal_id, requesting_agent),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


def get_session(session_id, *, conn=None):
    """Return a session dict or None."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM research_sessions LIMIT 0").description]
        return dict(zip(cols, row))
    finally:
        if own:
            conn.close()


def update_session(session_id, *, status=None, phases_json=None,
                   summary=None, conn=None):
    """Update mutable fields on a session."""
    sets, vals = [], []
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {status!r}")
        sets.append("status = ?")
        vals.append(status)
    if phases_json is not None:
        sets.append("phases_json = ?")
        vals.append(phases_json if isinstance(phases_json, str)
                    else json.dumps(phases_json))
    if summary is not None:
        sets.append("summary = ?")
        vals.append(summary)
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    vals.append(session_id)
    own = conn is None
    if own:
        conn = get_connection()
    try:
        conn.execute(
            f"UPDATE research_sessions SET {', '.join(sets)} WHERE id = ?",
            vals,
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def list_sessions(*, status=None, limit=50, conn=None):
    """Return recent sessions, optionally filtered by status."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM research_sessions WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM research_sessions LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        if own:
            conn.close()


# ── Evidence CRUD ─────────────────────────────────────────────────────────

def _snippet_hash(snippet):
    """Deterministic hash for deduplication."""
    return hashlib.sha256(snippet.encode('utf-8', errors='replace')).hexdigest()[:16]


def add_evidence(session_id, *, source_url='', source_type='web', title='',
                 snippet='', confidence=0.5, collecting_agent='', conn=None):
    """Add an evidence record. Returns id, or None if duplicate."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        shash = _snippet_hash(snippet)
        try:
            cur = conn.execute(
                """INSERT INTO research_evidence
                   (session_id, source_url, source_type, title, snippet,
                    confidence, collecting_agent, snippet_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, source_url, source_type, title,
                 snippet, confidence, collecting_agent, shash),
            )
            conn.commit()
            return cur.lastrowid
        except Exception:
            # unique constraint violation → duplicate
            conn.rollback()
            return None
    finally:
        if own:
            conn.close()


def get_evidence_for_session(session_id, *, limit=100, conn=None):
    """Return all evidence for a session."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM research_evidence WHERE session_id = ? "
            "ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM research_evidence LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        if own:
            conn.close()


def count_evidence(session_id, *, conn=None):
    """Count evidence records for a session."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM research_evidence WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        if own:
            conn.close()
