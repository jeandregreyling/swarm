"""
utils/governance.py — Central proposal governance engine.

Phase A.1.1: Proposal Singleton Enforcement + State Machine.

ALL proposal status transitions MUST go through transition_proposal().
Direct UPDATE of work_proposals.status is forbidden outside this module.

State machine:
    pending → approved | rejected
    approved → in_progress | rejected
    in_progress → done | rejected
    done → uat | in_progress      (Duck QA pass → uat, fail → back to in_progress)
    uat → closed | in_progress    (Ghost ships → closed, rejects → in_progress)
    rejected → pending            (resubmit allowed)
    closed → (terminal)
"""

import logging
import datetime

from proposal_status import (
    STATUS_PENDING, STATUS_APPROVED, STATUS_IN_PROGRESS,
    STATUS_DONE, STATUS_UAT, STATUS_CLOSED, STATUS_REJECTED,
    normalize_proposal_status,
)

logger = logging.getLogger('seven.governance')

# ── Legal transitions ─────────────────────────────────────────────────────────
# Maps current_status → set of allowed next statuses.

LEGAL_TRANSITIONS = {
    STATUS_PENDING:     {STATUS_APPROVED, STATUS_REJECTED, STATUS_CLOSED},  # closed: legacy decision auto-execute
    STATUS_APPROVED:    {STATUS_IN_PROGRESS, STATUS_REJECTED, STATUS_CLOSED},
    STATUS_IN_PROGRESS: {STATUS_DONE, STATUS_REJECTED},
    STATUS_DONE:        {STATUS_UAT, STATUS_IN_PROGRESS, STATUS_CLOSED},
    STATUS_UAT:         {STATUS_CLOSED, STATUS_IN_PROGRESS},
    STATUS_REJECTED:    {STATUS_PENDING},
    STATUS_CLOSED:      set(),  # terminal — no transitions out
}

# Statuses where we enforce the singleton rule (max 1 per agent)
_SINGLETON_STATUSES = {STATUS_IN_PROGRESS}


class GovernanceError(Exception):
    """Raised when a governance rule is violated."""
    pass


class IllegalTransitionError(GovernanceError):
    """The requested status transition is not allowed."""
    pass


class SingletonViolationError(GovernanceError):
    """Agent already has an in_progress proposal."""
    pass


class ProposalNotFoundError(GovernanceError):
    """The proposal_id does not exist."""
    pass


class StaleProposalError(GovernanceError):
    """Optimistic lock failure — proposal was modified concurrently."""
    pass


# ── Core transition function ─────────────────────────────────────────────────

def transition_proposal(proposal_id, new_status, agent, *,
                        actor=None, note='', conn=None,
                        _skip_singleton=False):
    """
    Central state machine for all proposal status changes.

    Parameters
    ----------
    proposal_id : str   — the unique proposal ID
    new_status  : str   — target status (will be normalised)
    agent       : str   — agent that owns the proposal (used for singleton check)
    actor       : str   — who initiated the transition (default: agent)
    note        : str   — optional note for the transition audit trail
    conn        : sqlite3.Connection — optional; caller manages commit if provided
    _skip_singleton : bool — internal only; bypass singleton for restore operations

    Returns
    -------
    dict with keys: proposal_id, old_status, new_status, agent, actor, timestamp

    Raises
    ------
    ProposalNotFoundError   — proposal_id not found in DB
    IllegalTransitionError  — transition not in LEGAL_TRANSITIONS
    SingletonViolationError — agent already has an in_progress proposal
    StaleProposalError      — row was updated between read and write (optimistic lock)
    """
    from database import get_connection

    new_status = normalize_proposal_status(new_status)
    if not new_status:
        raise GovernanceError('new_status is required')

    actor = actor or agent
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        # ── Read current state with optimistic lock anchor ────────────────
        row = conn.execute(
            'SELECT proposal_id, status, agent, updated_at '
            'FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()

        if not row:
            raise ProposalNotFoundError(f'Proposal not found: {proposal_id}')

        old_status = normalize_proposal_status(row['status'])
        lock_ts = row['updated_at']  # optimistic lock anchor

        # ── Validate transition is legal ──────────────────────────────────
        allowed = LEGAL_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise IllegalTransitionError(
                f'Cannot transition {proposal_id} from {old_status!r} to {new_status!r}. '
                f'Allowed: {sorted(allowed) if allowed else "(terminal state)"}'
            )

        # ── Singleton enforcement ─────────────────────────────────────────
        if (not _skip_singleton
                and new_status in _SINGLETON_STATUSES):
            conflict = conn.execute(
                'SELECT proposal_id FROM work_proposals '
                'WHERE agent=? AND status=? AND proposal_id!=?',
                (row['agent'], new_status, proposal_id)
            ).fetchone()
            if conflict:
                raise SingletonViolationError(
                    f'Agent {row["agent"]!r} already has proposal '
                    f'{conflict["proposal_id"]!r} in {new_status!r}. '
                    f'Finish or reject it before starting another.'
                )

        # ── Optimistic lock: ensure row hasn't changed since our read ─────
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        cursor = conn.execute(
            """UPDATE work_proposals
               SET status=?, updated_at=?
               WHERE proposal_id=? AND updated_at=?""",
            (new_status, now, proposal_id, lock_ts)
        )
        if cursor.rowcount == 0:
            raise StaleProposalError(
                f'Proposal {proposal_id} was modified concurrently. '
                f'Re-read and retry.'
            )

        # ── Write audit to governance_log ─────────────────────────────────
        _write_audit(conn, proposal_id, old_status, new_status,
                     row['agent'], actor, note)

        # ── Auto-trace to conv_timeline (A.1.4) ──────────────────────────
        _auto_trace(conn, proposal_id, old_status, new_status,
                    row['agent'], actor)

        if own_conn:
            conn.commit()

        result = {
            'proposal_id': proposal_id,
            'old_status': old_status,
            'new_status': new_status,
            'agent': row['agent'],
            'actor': actor,
            'timestamp': now,
        }

        logger.info(
            f'[Governance] {proposal_id}: {old_status} → {new_status} '
            f'(agent={row["agent"]}, actor={actor})'
        )

        # ── Auto-checkpoint on key transitions (A.1.3) ───────────────────
        if new_status in (STATUS_IN_PROGRESS, STATUS_DONE):
            _auto_checkpoint(proposal_id, new_status, row['agent'])

        # ── Auto-publish knowledge on completion (A.3.2) ──────────────────
        if new_status == STATUS_DONE:
            _auto_publish_knowledge(proposal_id, row['agent'], conn)

        # ── Broadcast via swarm_bus (A.4.2) ──────────────────────────────
        _bus_broadcast(proposal_id, old_status, new_status, row['agent'], conn)

        return result

    except GovernanceError:
        raise
    except Exception as exc:
        logger.error(f'[Governance] transition failed: {exc}')
        raise GovernanceError(f'Transition failed: {exc}') from exc
    finally:
        if own_conn:
            conn.close()


# ── Auto-trace (A.1.4) ────────────────────────────────────────────────────────

def _auto_trace(conn, proposal_id, old_status, new_status, agent, actor):
    """Write proposal lifecycle events to conv_timeline for traceability."""
    try:
        # Look up the source conversation for this proposal
        row = conn.execute(
            'SELECT source_conv_id FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        conv_id = row['source_conv_id'] if row and row['source_conv_id'] else None

        if not conv_id:
            return  # no conversation to trace against

        from db.timeline import timeline_append
        payload = {
            'proposal_id': proposal_id,
            'old_status': old_status,
            'new_status': new_status,
            'actor': actor,
        }
        timeline_append(
            conv_id=int(conv_id),
            agent=agent or 'governance',
            event_type='proposal',
            payload=payload,
            _conn=conn,
            job_id=f'gov-{proposal_id}',
        )
    except Exception as exc:
        logger.debug(f'[Governance] auto-trace failed: {exc}')


# ── Auto-checkpoint (A.1.3) ───────────────────────────────────────────────────

def _auto_checkpoint(proposal_id, new_status, agent):
    """Create a Vortex checkpoint on key proposal transitions."""
    try:
        from core.time_machine import time_wizard
        label = f'{proposal_id}-{new_status}'
        description = f'Auto-checkpoint: {proposal_id} → {new_status} (agent={agent})'
        time_wizard.create_workflow_checkpoint(
            label=label, agent=agent, description=description,
        )
        logger.info(f'[Governance] auto-checkpoint created: {label}')
    except Exception as exc:
        logger.warning(f'[Governance] auto-checkpoint failed: {exc}')


# ── Auto-publish knowledge on completion (A.3.2) ─────────────────────────────

def _auto_publish_knowledge(proposal_id, agent, conn):
    """Extract key information from a completed proposal and write to swarm_knowledge."""
    try:
        row = conn.execute(
            'SELECT proposal_id, title, description, agent FROM work_proposals WHERE proposal_id=?',
            (proposal_id,)
        ).fetchone()
        if not row:
            return

        title = row['title'] or ''
        desc = row['description'] or ''
        summary = f'Completed: {title}. {desc}'.strip()[:2000]

        from utils.db.knowledge import write_knowledge
        write_knowledge(
            key=f'proposal-{proposal_id}',
            content=summary,
            source_agent=agent or 'governance',
            source_proposal_id=proposal_id,
            category='decision',
            importance=6,
            conn=conn,
        )
        logger.info(f'[Governance] auto-published knowledge for {proposal_id}')
    except Exception as exc:
        logger.warning(f'[Governance] auto-publish knowledge failed: {exc}')


# ── Bus broadcast (A.4.2) ────────────────────────────────────────────────────

def _bus_broadcast(proposal_id, old_status, new_status, agent, conn):
    """Publish proposal lifecycle events to swarm_bus for decoupled subscribers."""
    try:
        from utils.swarm_bus import publish
        topic = 'proposal.created' if old_status == STATUS_PENDING and new_status == STATUS_APPROVED else 'proposal.status_changed'
        publish(topic, {
            'proposal_id': proposal_id,
            'old_status': old_status,
            'new_status': new_status,
            'agent': agent,
        }, source_service='governance', conn=conn)
    except Exception as exc:
        logger.warning(f'[Governance] bus broadcast failed: {exc}')


# ── Audit log ─────────────────────────────────────────────────────────────────

def _ensure_governance_log(conn):
    """Create the governance_log table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS governance_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            old_status  TEXT NOT NULL,
            new_status  TEXT NOT NULL,
            agent       TEXT NOT NULL DEFAULT '',
            actor       TEXT NOT NULL DEFAULT '',
            note        TEXT NOT NULL DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gov_log_proposal
        ON governance_log (proposal_id)
    """)


def _write_audit(conn, proposal_id, old_status, new_status, agent, actor, note):
    """Write a row to the governance audit log."""
    try:
        _ensure_governance_log(conn)
        conn.execute(
            """INSERT INTO governance_log
               (proposal_id, old_status, new_status, agent, actor, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (proposal_id, old_status, new_status, agent, actor, note)
        )
    except Exception as exc:
        logger.warning(f'[Governance] audit write failed: {exc}')


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_agent_active_proposal(agent, conn=None):
    """Return the in_progress proposal for an agent, or None."""
    from database import get_connection
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            'SELECT proposal_id, title, status, updated_at '
            'FROM work_proposals WHERE agent=? AND status=?',
            (agent, STATUS_IN_PROGRESS)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def get_transition_history(proposal_id, limit=50, conn=None):
    """Return the governance audit trail for a proposal."""
    from database import get_connection
    own = conn is None
    if own:
        conn = get_connection()
    try:
        _ensure_governance_log(conn)
        rows = conn.execute(
            'SELECT * FROM governance_log WHERE proposal_id=? ORDER BY id ASC LIMIT ?',
            (proposal_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def is_transition_legal(current_status, new_status):
    """Check if a transition is allowed without hitting the DB."""
    current = normalize_proposal_status(current_status)
    new = normalize_proposal_status(new_status)
    return new in LEGAL_TRANSITIONS.get(current, set())
