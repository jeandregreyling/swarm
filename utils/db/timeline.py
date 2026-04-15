"""
utils/db/timeline.py — Conversation timeline writer.

Every agent action during a chat conversation is appended here so Ghost
can see the full sequence of what happened: stages, skill calls, results,
reasoning text, and proposal events.

Usage:
    from database import timeline_append
    timeline_append(conv_id=123, agent='eleven', event_type='stage', payload='running skills')
"""

import json
import logging

logger = logging.getLogger('seven.timeline')

_MAX_PAYLOAD = 4000   # chars stored per event — keeps the table lean


def timeline_append(conv_id, agent, event_type, payload, _conn=None, job_id=None):
    """
    Write one timeline event. Safe to call from any thread — errors are logged,
    never raised, so they never interrupt the agent's work.

    Parameters
    ----------
    conv_id    : int or str — the chat conversation ID
    agent      : str — agent name (e.g. 'eleven', 'duck')
    event_type : str — one of: stage, skill_call, skill_result, response, final,
                        proposal, health, dispatch, route, error, relay, gate
    payload    : str or dict — text or JSON-serialisable dict
    job_id     : str or None — chat_jobs.job_id for per-message tracing
    """
    if not conv_id:
        return
    try:
        from ._connection import get_connection
        conn = _conn or get_connection()
        own  = _conn is None

        if isinstance(payload, dict):
            text = json.dumps(payload, ensure_ascii=False)
        else:
            text = str(payload or '')
        if len(text) > _MAX_PAYLOAD:
            text = text[:_MAX_PAYLOAD] + ' …[truncated]'

        conn.execute(
            """INSERT INTO conv_timeline (conv_id, agent, event_type, payload, job_id)
               VALUES (?, ?, ?, ?, ?)""",
            (int(conv_id), str(agent), str(event_type), text, str(job_id or '')),
        )
        if own:
            conn.commit()
            conn.close()
    except Exception as e:
        logger.debug(f'[timeline] write failed conv={conv_id} type={event_type}: {e}')


def timeline_get(conv_id, limit=200):
    """Return timeline rows for a conversation, oldest first."""
    try:
        from ._connection import get_connection
        conn = get_connection()
        rows = conn.execute(
            """SELECT id, agent, event_type, payload, created_at, job_id
               FROM conv_timeline WHERE conv_id=?
               ORDER BY id ASC LIMIT ?""",
            (int(conv_id), limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f'[timeline] read failed conv={conv_id}: {e}')
        return []


def timeline_get_job(job_id, limit=200):
    """Return timeline rows for a specific chat job, oldest first."""
    if not job_id:
        return []
    try:
        from ._connection import get_connection
        conn = get_connection()
        rows = conn.execute(
            """SELECT id, conv_id, agent, event_type, payload, created_at
               FROM conv_timeline WHERE job_id=?
               ORDER BY id ASC LIMIT ?""",
            (str(job_id), limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f'[timeline] read failed job={job_id}: {e}')
        return []
