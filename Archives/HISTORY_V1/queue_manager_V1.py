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

