"""
services.duck_review — Duck (quality gate) helpers for proposal review.

Extracted from services/__init__.py as part of Phase B.
"""
from database import get_connection


def _duck_stats():
    conn = get_connection()
    try:
        total  = conn.execute("SELECT COUNT(*) FROM duck_log").fetchone()[0]
        passed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'").fetchone()[0]
    finally:
        conn.close()
    return {'total': total, 'passed': passed, 'failed': failed}


def _log_proposal_duck_review(proposal_id, title, review_text, result, reason):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO duck_log (ticket_number, question, answer, result, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (proposal_id, title[:100], review_text[:500], result, reason[:500])
        )
        conn.commit()
    finally:
        conn.close()


def _run_proposal_duck_review(row):
    title = (row['title'] or '').strip()
    description = (row['description'] or '').strip()
    agent = (row.get('agent') or '').strip().lower()
    review_text = f'{title}\n{description}'.strip()
    lowered = review_text.lower()

    # --- Hard rejects ---

    if len(title) < 8:
        return {'result': 'NO', 'reason': 'proposal title is too short for meaningful review'}

    if len(description) < 24:
        return {'result': 'NO', 'reason': 'proposal description is too short for queue-visible approval'}

    # Reject if the title is a raw SKILL command — agent pasted a command as the title
    _SKILL_TITLE_PREFIXES = ('[fs_patch', '[fs_write', '[fs_patch_lines', '[fs_readonly',
                              '[alm_', '[shell ', 'skill fs_', 'skill alm_', '<<<old>>>', '<<<new>>>')
    if any(title.lower().startswith(p) for p in _SKILL_TITLE_PREFIXES):
        return {'result': 'NO', 'reason': 'proposal title appears to be a raw SKILL command — write a human-readable title describing the goal'}

    # Reject if the title contains patch delimiters (agent dumped file content as title)
    if '<<<old>>>' in title.lower() or '<<<new>>>' in title.lower() or '<<<content>>>' in title.lower():
        return {'result': 'NO', 'reason': 'proposal title contains patch block content — title must be a plain description'}

    if any(marker in lowered for marker in ('tbd', 'todo', '[pending]', 'placeholder', 'fix later')):
        return {'result': 'NO', 'reason': 'proposal still contains placeholder or unresolved review language'}

    if '.history' in lowered and 'ghost-layer' not in lowered and 'ghost layer' not in lowered and 'rollback' not in lowered and 'vortex' not in lowered:
        return {'result': 'NO', 'reason': '.history references must be explicitly scoped — use ghost layer, rollback, or Vortex context'}

    # Reject if the agent already has 2+ proposals created within the last 5 minutes
    # (agent burning tokens on repeated proposals without completing any work)
    if agent:
        try:
            conn = get_connection()
            try:
                recent_count = conn.execute(
                    """SELECT COUNT(*) FROM work_proposals
                       WHERE agent=? AND status IN ('pending','approved')
                       AND created_at >= datetime('now', '-5 minutes')""",
                    (agent,)
                ).fetchone()[0]
            finally:
                conn.close()
            if recent_count >= 2:
                return {
                    'result': 'NO',
                    'reason': f'{agent} already has {recent_count} open proposals created in the last 5 minutes — complete or cancel existing work before creating more'
                }
        except Exception:
            pass

    return {'result': 'YES', 'reason': 'proposal passed Duck first-pass review'}


def _get_duck_flags_today():
    """Return count of Duck NO results today (used by attention panel)."""
    try:
        conn = get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM duck_log WHERE result='NO' AND DATE(created_at)=DATE('now')"
        ).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0
