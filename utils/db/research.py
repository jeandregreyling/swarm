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

VALID_STATUSES = ('planning', 'searching', 'analysing', 'synthesising',
                  'done', 'paused', 'cancelled')
VALID_DEPTHS = ('quick', 'standard', 'deep')


def create_session(topic, *, depth='standard', requesting_agent='user',
                   linked_proposal_id='', idempotency_key='',
                   project_id='', conn=None):
    """Create a new research session. Returns the new session id.

    2026-05-02 (S-12E202F189) — when ``idempotency_key`` is non-empty and a
    session already exists with that key, return its id instead of creating a
    duplicate. The unique index `idx_research_sessions_idem` enforces this at
    the DB layer; the lookup here just gives a clean response.

    2026-05-02 (S-BFEE738F64) — ``project_id`` optionally links this run to a
    Studio project so evidence shows up in project closeouts.
    """
    if depth not in VALID_DEPTHS:
        raise ValueError(f"Invalid depth {depth!r}, must be one of {VALID_DEPTHS}")
    own = conn is None
    if own:
        conn = get_connection()
    try:
        if idempotency_key:
            row = conn.execute(
                "SELECT id FROM research_sessions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                return row[0]
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(research_sessions)").fetchall()}
        if 'project_id' in cols:
            cur = conn.execute(
                """INSERT INTO research_sessions
                   (topic, depth, status, phases_json, linked_proposal_id,
                    requesting_agent, idempotency_key, project_id)
                   VALUES (?, ?, 'planning', '[]', ?, ?, ?, ?)""",
                (topic, depth, linked_proposal_id, requesting_agent,
                 idempotency_key, project_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO research_sessions
                   (topic, depth, status, phases_json, linked_proposal_id,
                    requesting_agent, idempotency_key)
                   VALUES (?, ?, 'planning', '[]', ?, ?, ?)""",
                (topic, depth, linked_proposal_id, requesting_agent,
                 idempotency_key),
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
                   summary=None, last_error=None, conn=None):
    """Update mutable fields on a session.

    2026-05-02 (S-A43BF83EB7) — ``last_error`` makes background failures
    visible instead of silently swallowing them.
    """
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
    if last_error is not None:
        sets.append("last_error = ?")
        vals.append(str(last_error)[:2000])
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


def cancel_session(session_id, *, reason='', conn=None):
    """Cancel a running research session.

    2026-05-02 (S-6F23DD5914) — gives the user a clean way to stop runaway
    research without leaving the row in 'searching' forever."""
    update_session(session_id, status='cancelled',
                   last_error=(reason or 'cancelled by user'), conn=conn)


def pause_session(session_id, *, conn=None):
    """Pause a research session; resume by setting status back to its phase."""
    update_session(session_id, status='paused', conn=conn)


# ── Source quality scoring (S-8306533874) ─────────────────────────────────
# Deliberately small + offline so it can be unit-tested without network.
# Returns a 0..1 score that callers blend with novelty + confidence.

_OFFICIAL_BONUS = 0.4   # official SAP/community/help domains
_REPUTABLE_BONUS = 0.2  # well-known engineering / docs domains
_PENALTY_THIN = 0.15    # very short snippets

_REPUTABLE_DOMAINS = (
    'github.com', 'stackoverflow.com', 'docs.microsoft.com',
    'learn.microsoft.com', 'developer.mozilla.org',
    'kubernetes.io', 'python.org', 'docs.python.org',
    'cloud.google.com', 'aws.amazon.com', 'docs.aws.amazon.com',
    'redhat.com', 'docs.oracle.com', 'ibm.com',
)


def score_source_quality(*, url='', snippet='', title=''):
    """Heuristic 0..1 quality score for a research source."""
    score = 0.4  # neutral baseline
    try:
        from lib.search.internet_tavily import is_official_sap_source
        if url and is_official_sap_source(url):
            score += _OFFICIAL_BONUS
    except Exception:
        pass
    u = (url or '').lower()
    host = u.split('://', 1)[-1].split('/', 1)[0] if '://' in u else u.split('/', 1)[0]
    if any(host == d or host.endswith('.' + d) for d in _REPUTABLE_DOMAINS):
        score += _REPUTABLE_BONUS
    text = f'{title or ""} {snippet or ""}'.strip()
    if len(text) < 60:
        score -= _PENALTY_THIN
    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0
    return round(score, 3)


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
    """Return all evidence for a session.

    2026-05-02 (S-6E6CD8BA76) — each row is annotated with ``is_novel``:
    True when this is the only session whose evidence carries this
    ``snippet_hash``; False when an earlier session already saw it.
    """
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
        result = []
        for r in rows:
            d = dict(zip(cols, r))
            shash = d.get('snippet_hash') or ''
            if shash:
                # Earlier rows (id < this one) with same snippet_hash → not novel.
                prior = conn.execute(
                    "SELECT 1 FROM research_evidence "
                    "WHERE snippet_hash = ? AND id < ? LIMIT 1",
                    (shash, d['id']),
                ).fetchone()
                d['is_novel'] = prior is None
            else:
                d['is_novel'] = True
            result.append(d)
        return result
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
