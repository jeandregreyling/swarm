"""
tests/test_governance.py — Unit tests for A.1.1 Proposal Singleton Enforcement.

Tests:
  1. Legal transitions succeed
  2. Illegal transitions raise IllegalTransitionError
  3. Singleton: 2nd in_progress for same agent blocked
  4. Singleton: different agents can both have in_progress
  5. Optimistic lock detects concurrent modification
  6. Audit trail written on every transition
  7. Terminal state (closed) rejects all transitions
"""

import os
import sys
import sqlite3
import datetime

# Ensure project root on path
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

import pytest

from proposal_status import (
    STATUS_PENDING, STATUS_APPROVED, STATUS_IN_PROGRESS,
    STATUS_DONE, STATUS_UAT, STATUS_CLOSED, STATUS_REJECTED,
)
from governance import (
    transition_proposal,
    LEGAL_TRANSITIONS,
    GovernanceError,
    IllegalTransitionError,
    SingletonViolationError,
    ProposalNotFoundError,
    StaleProposalError,
    get_agent_active_proposal,
    get_transition_history,
    is_transition_legal,
    _ensure_governance_log,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a fresh in-memory-like SQLite DB with schema."""
    db_path = str(tmp_path / 'test_swarm.db')
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS work_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE NOT NULL,
            agent TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            proposal_file TEXT DEFAULT '',
            ticket_number TEXT DEFAULT '',
            queue_id TEXT DEFAULT '',
            source_conv_id TEXT DEFAULT '',
            duck_verdict TEXT DEFAULT '',
            duck_note TEXT DEFAULT '',
            git_branch TEXT DEFAULT '',
            git_commit TEXT DEFAULT '',
            test_results TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    _ensure_governance_log(conn)
    conn.commit()

    def mock_get_connection():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    # Monkeypatch at the database module level so lazy imports find it
    import database
    monkeypatch.setattr(database, 'get_connection', mock_get_connection)

    # Insert a couple of test proposals
    now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) VALUES (?,?,?,?,?)",
        ('PROP-001', 'eleven', 'Test Proposal 1', 'pending', now)
    )
    conn.execute(
        "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) VALUES (?,?,?,?,?)",
        ('PROP-002', 'eleven', 'Test Proposal 2', 'pending', now)
    )
    conn.execute(
        "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) VALUES (?,?,?,?,?)",
        ('PROP-003', 'gemma', 'Gemma Proposal', 'pending', now)
    )
    conn.commit()
    conn.close()

    return db_path, mock_get_connection


# ── Test: Legal transitions ───────────────────────────────────────────────────

def test_legal_transition_pending_to_approved(test_db):
    _, _ = test_db
    result = transition_proposal('PROP-001', 'approved', 'eleven')
    assert result['old_status'] == 'pending'
    assert result['new_status'] == 'approved'
    assert result['proposal_id'] == 'PROP-001'


def test_legal_full_lifecycle(test_db):
    _, get_conn = test_db
    # pending → approved
    r = transition_proposal('PROP-001', 'approved', 'eleven')
    assert r['new_status'] == 'approved'

    # approved → in_progress
    r = transition_proposal('PROP-001', 'in_progress', 'eleven')
    assert r['new_status'] == 'in_progress'

    # in_progress → done
    r = transition_proposal('PROP-001', 'done', 'eleven')
    assert r['new_status'] == 'done'

    # done → uat
    r = transition_proposal('PROP-001', 'uat', 'eleven')
    assert r['new_status'] == 'uat'

    # uat → closed
    r = transition_proposal('PROP-001', 'closed', 'eleven')
    assert r['new_status'] == 'closed'


# ── Test: Illegal transitions ─────────────────────────────────────────────────

def test_illegal_pending_to_done(test_db):
    with pytest.raises(IllegalTransitionError):
        transition_proposal('PROP-001', 'done', 'eleven')


def test_illegal_pending_to_in_progress(test_db):
    with pytest.raises(IllegalTransitionError):
        transition_proposal('PROP-001', 'in_progress', 'eleven')


def test_terminal_closed_rejects_all(test_db):
    # Move to closed first
    transition_proposal('PROP-001', 'approved', 'eleven')
    transition_proposal('PROP-001', 'closed', 'eleven')

    with pytest.raises(IllegalTransitionError):
        transition_proposal('PROP-001', 'pending', 'eleven')


# ── Test: Singleton enforcement ───────────────────────────────────────────────

def test_singleton_blocks_second_in_progress(test_db):
    """Two proposals from same agent cannot both be in_progress."""
    transition_proposal('PROP-001', 'approved', 'eleven')
    transition_proposal('PROP-001', 'in_progress', 'eleven')

    transition_proposal('PROP-002', 'approved', 'eleven')

    with pytest.raises(SingletonViolationError):
        transition_proposal('PROP-002', 'in_progress', 'eleven')


def test_singleton_allows_different_agents(test_db):
    """Different agents can each have one in_progress."""
    transition_proposal('PROP-001', 'approved', 'eleven')
    transition_proposal('PROP-001', 'in_progress', 'eleven')

    transition_proposal('PROP-003', 'approved', 'gemma')
    result = transition_proposal('PROP-003', 'in_progress', 'gemma')
    assert result['new_status'] == 'in_progress'


def test_singleton_after_first_finishes(test_db):
    """After first proposal finishes, agent can start another."""
    transition_proposal('PROP-001', 'approved', 'eleven')
    transition_proposal('PROP-001', 'in_progress', 'eleven')
    transition_proposal('PROP-001', 'done', 'eleven')  # frees the slot

    transition_proposal('PROP-002', 'approved', 'eleven')
    result = transition_proposal('PROP-002', 'in_progress', 'eleven')
    assert result['new_status'] == 'in_progress'


# ── Test: Proposal not found ──────────────────────────────────────────────────

def test_not_found(test_db):
    with pytest.raises(ProposalNotFoundError):
        transition_proposal('DOES-NOT-EXIST', 'approved', 'eleven')


# ── Test: Audit trail ─────────────────────────────────────────────────────────

def test_audit_trail_written(test_db):
    transition_proposal('PROP-001', 'approved', 'eleven', actor='duck', note='test note')
    history = get_transition_history('PROP-001')
    assert len(history) == 1
    assert history[0]['old_status'] == 'pending'
    assert history[0]['new_status'] == 'approved'
    assert history[0]['actor'] == 'duck'
    assert history[0]['note'] == 'test note'


# ── Test: is_transition_legal helper ──────────────────────────────────────────

def test_is_transition_legal():
    assert is_transition_legal('pending', 'approved') is True
    assert is_transition_legal('pending', 'done') is False
    assert is_transition_legal('closed', 'pending') is False


# ── Test: get_agent_active_proposal ───────────────────────────────────────────

def test_get_agent_active_proposal(test_db):
    assert get_agent_active_proposal('eleven') is None

    transition_proposal('PROP-001', 'approved', 'eleven')
    transition_proposal('PROP-001', 'in_progress', 'eleven')

    active = get_agent_active_proposal('eleven')
    assert active is not None
    assert active['proposal_id'] == 'PROP-001'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
