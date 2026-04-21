"""
services.queue_wrappers — Queue manager wrappers with compatibility fallbacks.

Extracted from services/__init__.py as part of Phase B.

These functions wrap `queue_manager` methods but include full fallback
implementations for older queue_manager modules in some worktrees where
the expected methods may not exist.
"""
import queue_manager as _queue_manager
from database import get_connection, log_activity


def intake_internal(agent, title, description, priority=5):
    fn = getattr(_queue_manager, 'intake_internal', None)
    if callable(fn):
        return fn(agent, title, description, priority=priority)

    # Compatibility fallback for older queue_manager modules in some worktrees.
    snapshot = 'system snapshot unavailable'
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO queue (from_addr, subject, question, tags, system_snapshot, status, priority, source_type, agent)
               VALUES (?, ?, ?, ?, ?, 'queued', ?, 'internal', ?)""",
            (f'agent:{agent}', title, description[:500], agent, snapshot, priority, agent)
        )
        queue_id = cursor.lastrowid
        proposal_id = f'INTERNAL-{agent.upper()}-{queue_id:04d}'
        conn.execute(
            """INSERT OR IGNORE INTO work_proposals (proposal_id, agent, title, description, status, queue_id)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (proposal_id, agent, title[:200], description[:500], queue_id)
        )
        conn.commit()
    finally:
        conn.close()

    # Late import to avoid circular dep at package load time
    from . import _safe_time_event
    _safe_time_event(
        agent=agent,
        action='proposal_created',
        event_type='proposal',
        target=proposal_id,
        details={'queue_id': queue_id, 'title': title[:200], 'priority': priority}
    )

    return queue_id, proposal_id


def update_proposal_status(proposal_id, status, ticket_number=''):
    fn = getattr(_queue_manager, 'update_proposal_status', None)
    if callable(fn):
        return fn(proposal_id, status, ticket_number=ticket_number)

    # Fallback: route through governance
    from utils.governance import transition_proposal, GovernanceError
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT agent FROM work_proposals WHERE proposal_id=?', (proposal_id,)
        ).fetchone()
        agent = (row['agent'] if row else 'unknown')

        try:
            transition_proposal(proposal_id, status, agent,
                                actor='services', note='services.update_proposal_status',
                                conn=conn)
        except GovernanceError as exc:
            log_activity('terminal', 'governance_blocked', f'{proposal_id}:{status} — {exc}')
            return

        if ticket_number:
            conn.execute(
                "UPDATE work_proposals SET ticket_number=? WHERE proposal_id=?",
                (ticket_number, proposal_id)
            )
        conn.commit()

        # ALM routing fix — ensure every status change is Vortex-logged for Studio visibility
        try:
            from . import _safe_time_event
            _safe_time_event('terminal_ui', 'proposal_status_updated_via_skill', 'proposal', f'{proposal_id}:{status}')
        except Exception:
            pass
    finally:
        conn.close()


def get_queue_entries(source_type=None, status=None, limit=50):
    fn = getattr(_queue_manager, 'get_queue_entries', None)
    if callable(fn):
        return fn(source_type=source_type, status=status, limit=limit)

    clauses, params = [], []
    if source_type:
        clauses.append('source_type=?')
        params.append(source_type)
    if status:
        clauses.append('status=?')
        params.append(status)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    conn = get_connection()
    try:
        rows = conn.execute(
            f'SELECT * FROM queue {where} ORDER BY created_at DESC LIMIT ?',
            tuple(params + [limit])
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
