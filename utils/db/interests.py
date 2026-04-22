"""
utils/db/interests.py — Phase 5: agent-facing interests CRUD with provenance.

Lets Librarian (memory sweeps), Scholar (research digests) and Seeker
(web-finds) record suggested interests on behalf of a user, distinct from the
'user'-source rows that come from onboarding.

Schema (see utils/db/_schema.py):
    user_interests(
        id, username, topic, category,
        source,        -- 'user' | 'agent' | ...
        source_agent,  -- e.g. 'librarian', 'scholar', 'seeker', ''
        score, active, created_at, updated_at
    )

Reconciliation design (caller's responsibility for now):
    - Human 'user' rows are authoritative; agent rows are hints.
    - A nightly job can down-weight stale agent rows (score * 0.9 per week
      idle) and deactivate ones below a threshold. This module exposes
      `decay_agent_interests()` so that job can be a single-line cron.
"""

from ._connection import get_connection

# Agents whitelisted for interest-authoring. Kept narrow on purpose.
INTEREST_AUTHOR_AGENTS = frozenset({'librarian', 'scholar', 'seeker'})


def record_agent_interest(username, topic, *,
                          source_agent,
                          category='general',
                          score=5.0,
                          conn=None):
    """Record (or refresh) an agent-sourced interest for a user.

    Returns True if a row was inserted or updated, False if rejected.

    Rules:
      - `source_agent` must be in INTEREST_AUTHOR_AGENTS (case-insensitive).
      - Human-authored rows (source='user') are NEVER overwritten by agents;
        we touch `updated_at` but keep their score and source.
      - New rows get source='agent'. Repeated authoring from the same agent
        nudges the score up (capped at 9.0 so user-entered 10.0 stays on top).
    """
    if not username or not topic:
        return False
    sa = (source_agent or '').strip().lower()
    if sa not in INTEREST_AUTHOR_AGENTS:
        return False

    topic = str(topic).strip()[:100]
    if not topic:
        return False

    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, source, score FROM user_interests "
            "WHERE username = ? AND topic = ?",
            (username, topic),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO user_interests "
                "(username, topic, category, source, source_agent, score) "
                "VALUES (?, ?, ?, 'agent', ?, ?)",
                (username, topic, category, sa, float(score)),
            )
            if own:
                conn.commit()
            return True

        existing_source = (row[1] if not hasattr(row, 'keys') else row['source']) or ''
        existing_score = row[2] if not hasattr(row, 'keys') else row['score']

        if existing_source == 'user':
            # Never downgrade or relabel user-authored rows; just freshen.
            conn.execute(
                "UPDATE user_interests "
                "SET active = 1, updated_at = datetime('now') "
                "WHERE username = ? AND topic = ?",
                (username, topic),
            )
            if own:
                conn.commit()
            return True

        new_score = min(9.0, float(existing_score or 0) + 0.5)
        conn.execute(
            "UPDATE user_interests "
            "SET active = 1, score = ?, source_agent = ?, "
            "    updated_at = datetime('now') "
            "WHERE username = ? AND topic = ?",
            (new_score, sa, username, topic),
        )
        if own:
            conn.commit()
        return True
    finally:
        if own:
            conn.close()


def decay_agent_interests(*, factor=0.9, deactivate_below=1.0, conn=None):
    """Nightly reconciliation hook: decay agent-sourced scores and deactivate
    rows that have fallen below threshold. User-sourced rows untouched.

    Returns (decayed_count, deactivated_count).
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE user_interests "
            "SET score = score * ? "
            "WHERE source = 'agent' AND active = 1",
            (float(factor),),
        )
        decayed = cur.rowcount or 0
        cur2 = conn.execute(
            "UPDATE user_interests "
            "SET active = 0, updated_at = datetime('now') "
            "WHERE source = 'agent' AND active = 1 AND score < ?",
            (float(deactivate_below),),
        )
        deactivated = cur2.rowcount or 0
        if own:
            conn.commit()
        return (decayed, deactivated)
    finally:
        if own:
            conn.close()


def list_agent_interests(username, *, agent=None, conn=None):
    """Return active agent-authored interests for a user, optionally filtered
    by which agent authored them. Useful for the UI to show provenance.
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        if agent:
            rows = conn.execute(
                "SELECT topic, category, score, source_agent, updated_at "
                "FROM user_interests "
                "WHERE username = ? AND active = 1 "
                "  AND source = 'agent' AND source_agent = ? "
                "ORDER BY score DESC, updated_at DESC",
                (username, str(agent).lower()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT topic, category, score, source_agent, updated_at "
                "FROM user_interests "
                "WHERE username = ? AND active = 1 AND source = 'agent' "
                "ORDER BY score DESC, updated_at DESC",
                (username,),
            ).fetchall()
        out = []
        for r in rows:
            out.append({
                'topic': r[0],
                'category': r[1],
                'score': r[2],
                'source_agent': r[3],
                'updated_at': r[4],
            })
        return out
    finally:
        if own:
            conn.close()
