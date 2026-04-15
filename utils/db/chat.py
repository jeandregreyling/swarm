"""
db.chat — Conversations, messages, and chat job tracking.
"""
from ._connection import get_connection


def new_conversation(title, source='email', sender=''):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO conversations (title,source,sender) VALUES (?,?,?)",
        (title[:100], source, sender)
    )
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conv_id


def log_message(conv_id, from_agent, content, to_agent='', message_type='chat', tokens_used=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,?,?,?,?,?)",
        (conv_id, from_agent, to_agent, content, message_type, int(tokens_used or 0))
    )
    conn.commit()
    conn.close()


def get_ghost_history(limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT m.content, m.created_at, c.title
        FROM messages m JOIN conversations c ON m.conversation_id=c.id
        WHERE m.from_agent='Ghost'
        ORDER BY m.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return list(reversed(rows))


def persist_chat_job(job_id, conversation_id, agent, runtime_class, eta_seconds, started_at):
    """Record a new chat job. Best-effort — never raises."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO chat_jobs
                   (job_id, conversation_id, agent, status, runtime_class,
                    eta_seconds, started_at, updated_at)
                   VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
                (str(job_id), int(conversation_id or 0), str(agent or ''),
                 str(runtime_class or ''), int(eta_seconds or 60),
                 str(started_at or ''), str(started_at or ''))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def update_chat_job_db(job_id, status, stage='', error='', elapsed_ms=0, tokens=0, stage_trace_json=None):
    """Update a chat job record. Best-effort — never raises."""
    try:
        conn = get_connection()
        try:
            if stage_trace_json is not None:
                conn.execute(
                    """UPDATE chat_jobs
                       SET status=?, stage=?, error=?, elapsed_ms=?, tokens=?,
                           stage_trace_json=?, updated_at=datetime('now')
                       WHERE job_id=?""",
                    (str(status), str(stage or ''), str(error or '')[:500],
                     int(elapsed_ms or 0), int(tokens or 0),
                     str(stage_trace_json), str(job_id))
                )
            else:
                conn.execute(
                    """UPDATE chat_jobs
                       SET status=?, stage=?, error=?, elapsed_ms=?, tokens=?,
                           updated_at=datetime('now')
                       WHERE job_id=?""",
                    (str(status), str(stage or ''), str(error or '')[:500],
                     int(elapsed_ms or 0), int(tokens or 0), str(job_id))
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_chat_jobs_by_ids(job_ids):
    """Fetch chat_jobs rows for a set of job IDs. Returns list of dicts."""
    job_ids = [str(j) for j in (job_ids or []) if j]
    if not job_ids:
        return []
    try:
        conn = get_connection()
        try:
            placeholders = ','.join('?' for _ in job_ids)
            rows = conn.execute(
                f'SELECT * FROM chat_jobs WHERE job_id IN ({placeholders})',
                job_ids
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def mark_orphaned_chat_jobs():
    """Mark any 'running' chat_jobs rows as failed. Call once on server startup."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE chat_jobs
                   SET status='failed', stage='failed',
                       error='server restarted — job lost',
                       updated_at=datetime('now')
                   WHERE status='running'"""
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def sweep_stuck_jobs(max_age_minutes=120):
    """Fail jobs stuck in running/dispatched/processing state beyond max_age_minutes.

    Designed to be called periodically (e.g. every 10 minutes) from a
    background thread. Returns the number of jobs swept.
    """
    try:
        conn = get_connection()
        try:
            cutoff = f'-{max_age_minutes} minutes'
            cur = conn.execute(
                """UPDATE chat_jobs
                   SET status='failed', stage='failed',
                       error=printf('stuck job swept (>%d min in state: %s)',
                                    ?, status),
                       updated_at=datetime('now')
                   WHERE status IN ('running', 'dispatched', 'processing')
                     AND started_at < datetime('now', ?)
                   RETURNING job_id, agent, status""",
                (max_age_minutes, cutoff),
            )
            swept = cur.fetchall()
            if swept:
                conn.commit()
            conn.close()
            return len(swept)
        except Exception:
            conn.close()
            return 0
    except Exception:
        return 0
