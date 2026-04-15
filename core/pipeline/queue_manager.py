"""
queue_manager.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Librarian intake layer. Owns the queue table.

Every trusted email enters here before any model loads.
Every closed ticket exits here after Duck and Librarian are done.

The Librarian tags, queues, and manages position.
It does not read the question. It does not interpret content.
It stamps and files. That is all.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
import logging

logger = logging.getLogger('seven.queue_manager')


def _get_queue_position():
    """How many emails are actively queued or processing ahead of this one."""
    from database import get_connection
    conn = get_connection()
    result = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status IN ('queued', 'processing')"
    ).fetchone()
    conn.close()
    return result[0] if result else 0


def _system_snapshot():
    """Lightweight RAM snapshot stored with the queue entry for context."""
    try:
        import psutil
        ram = psutil.virtual_memory()
        return (
            f"RAM: {ram.available / (1024**3):.1f}GB free / "
            f"{ram.total / (1024**3):.1f}GB total | "
            f"CPU: {psutil.cpu_percent(interval=0.5):.0f}%"
        )
    except Exception:
        return 'system snapshot unavailable'


def _librarian_tag(question):
    """
    Ask the Librarian to generate 3-5 tags from the question.
    The Librarian sees only what it needs to see — a brief peek, nothing more.
    """
    try:
        from orchestrator import tag_content
        tags = tag_content(question[:300])
        logger.info(f'[Librarian] Tagged: {tags}')
        return tags
    except Exception as e:
        logger.warning(f'[Librarian] Tagging failed: {e}')
        return ''


def intake(from_addr, subject, question, priority=5):
    """
    Librarian intakes an email from a trusted sender.

    Tags the question, records system state, creates queue entry.
    Returns (queue_id, position, tags).

    Position 1 means the queue is empty and this email is next.
    Position N means N-1 emails are ahead.
    priority=1 means URGENT — jumps to front regardless of queue depth.
    """
    from database import get_connection

    tags     = _librarian_tag(question)
    snapshot = _system_snapshot()
    position = 1 if priority == 1 else _get_queue_position() + 1

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO queue (from_addr, subject, question, tags, system_snapshot, status, priority)
               VALUES (?, ?, ?, ?, ?, 'queued', ?)""",
            (from_addr, subject, question[:500], tags, snapshot, priority)
        )
        queue_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    logger.info(f'[Queue] #{queue_id} from {from_addr} — position {position} priority {priority}')
    return queue_id, position, tags


def mark_processing(queue_id):
    """Called when the swarm begins working on a ticket."""
    from database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE queue SET status='processing', processed_at=datetime('now') WHERE id=?",
        (queue_id,)
    )
    conn.commit()
    conn.close()


def mark_completed(queue_id):
    """Called by Librarian close — ticket is fully resolved."""
    from database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE queue SET status='completed', completed_at=datetime('now') WHERE id=?",
        (queue_id,)
    )
    conn.commit()
    conn.close()
    logger.info(f'[Queue] #{queue_id} marked completed.')


def mark_failed(queue_id, reason=''):
    """Called when processing crashes so entries do not stay stuck in processing."""
    from database import get_connection
    conn = get_connection()
    conn.execute(
        "UPDATE queue SET status='queued', completed_at=NULL WHERE id=?",
        (queue_id,)
    )
    conn.commit()
    conn.close()
    if reason:
        logger.warning(f'[Queue] #{queue_id} reset to queued after failure: {reason}')
    else:
        logger.warning(f'[Queue] #{queue_id} reset to queued after failure.')


def get_queue_depth():
    """How many emails are currently waiting or processing."""
    from database import get_connection
    conn = get_connection()
    result = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status IN ('queued', 'processing')"
    ).fetchone()
    conn.close()
    return result[0] if result else 0


def estimate_wait_minutes(position):
    """Rough estimate: ~3 minutes per email in queue."""
    return position * 3


def intake_internal(agent, title, description, priority=5):
    """
    Create an internal queue entry for an agent-initiated action or proposal.

    Unlike intake(), this does not tag via Ollama and skips the email path entirely.
    Also creates a work_proposals record so the action is visible to all agents.

    Returns (queue_id, proposal_id).
    proposal_id format: INTERNAL-{agent.upper()}-{queue_id:04d}
    """
    from database import get_connection
    import re

    snapshot = _system_snapshot()
    position = 1 if priority == 1 else _get_queue_position() + 1

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO queue (from_addr, subject, question, tags, system_snapshot, status, priority, source_type, agent)
               VALUES (?, ?, ?, ?, ?, 'queued', ?, 'internal', ?)""",
            (f'agent:{agent}', title, description[:500], agent, snapshot, priority, agent)
        )
        queue_id = cursor.lastrowid
        conn.commit()

        proposal_id = f'INTERNAL-{agent.upper()}-{queue_id:04d}'
        conn.execute(
            """INSERT OR IGNORE INTO work_proposals (proposal_id, agent, title, description, status, queue_id)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (proposal_id, agent, title[:200], description[:500], queue_id)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f'[Queue/Internal] #{queue_id} from {agent} — position {position} | {proposal_id}')
    return queue_id, proposal_id


def update_proposal_status(proposal_id, status, ticket_number=''):
    """Update a work_proposal status via governance state machine."""
    from database import get_connection
    import sys
    sys.path.insert(0, '/home/seven/swarm')
    sys.path.insert(0, '/home/seven/swarm/utils')
    from governance import transition_proposal, GovernanceError

    # Look up owning agent
    conn = get_connection()
    row = conn.execute(
        'SELECT agent FROM work_proposals WHERE proposal_id=?', (proposal_id,)
    ).fetchone()
    agent = (row['agent'] if row else 'unknown')
    conn.close()

    try:
        transition_proposal(proposal_id, status, agent,
                            actor='queue_manager', note='queue_manager.update_proposal_status')
    except GovernanceError as exc:
        logger.warning(f'[Queue] governance blocked status update for {proposal_id}: {exc}')
        return

    # Update ticket_number separately if provided
    if ticket_number:
        conn = get_connection()
        conn.execute(
            "UPDATE work_proposals SET ticket_number=? WHERE proposal_id=?",
            (ticket_number, proposal_id)
        )
        conn.commit()
        conn.close()


def get_queue_entries(source_type=None, status=None, limit=50):
    """Return queue entries, optionally filtered by source_type and/or status."""
    from database import get_connection
    conn = get_connection()
    clauses, params = [], []
    if source_type:
        clauses.append('source_type=?')
        params.append(source_type)
    if status:
        clauses.append('status=?')
        params.append(status)
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(
        f'SELECT * FROM queue {where} ORDER BY created_at DESC LIMIT ?',
        params + [limit]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_queue_quiet():
    """
    True if no email has completed in the last hour.
    Used by Sniffles to decide if it's safe to run a deep audit.
    """
    from database import get_connection
    from datetime import datetime, timedelta
    conn = get_connection()
    result = conn.execute(
        "SELECT MAX(completed_at) FROM queue WHERE status='completed'"
    ).fetchone()
    conn.close()
    last = result[0] if result else None
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now() - last_dt > timedelta(hours=1)
    except Exception:
        return True
