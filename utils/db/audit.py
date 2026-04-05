"""
db.audit — Ghost circle and activity log.
"""
from ._connection import get_connection, logger


def get_ghost_circle_entries(limit=50, severity_filter=None):
    conn = get_connection()
    if severity_filter:
        rows = conn.execute(
            "SELECT * FROM ghost_circle WHERE severity=? ORDER BY created_at DESC LIMIT ?",
            (severity_filter, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ghost_circle ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return rows


def log_activity(service, event, detail='', severity='info'):
    """
    Write a line to the activity_log. Called from listener, telegram, scheduler, skills.
    service: 'listener' | 'telegram' | 'scheduler' | 'terminal' | 'skills'
    event:   short label e.g. 'email_received', 'pipeline_start', 'stage1_done', etc.
    detail:  human-readable context string
    severity: 'info' | 'warning' | 'error' | 'critical' (accepted but not stored — for compat)
    """
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO activity_log (service, event, detail) VALUES (?, ?, ?)",
            (service, event, detail[:500])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Activity] log_activity failed: {e}')


def get_activity_log(limit=100, since_id=0):
    """Return recent activity entries, optionally after a given id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, service, event, detail, created_at FROM activity_log WHERE id > ? ORDER BY id DESC LIMIT ?",
        (since_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
