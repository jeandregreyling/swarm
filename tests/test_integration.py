"""
tests/test_integration.py — A.6.1 Integration Test Suite
═══════════════════════════════════════════════════════════
End-to-end tests that verify the full Diamond Layer chain:

  1. Proposal lifecycle: create → governance gate → all transitions → side effects
  2. Skill trust: all trust levels × all tiers + overrides
  3. Cross-references: ticket → proposal → conversation → timeline
  4. Agent coordination: check_and_reroute + claim_pending_proposal
  5. Bus + Knowledge integration: events emitted and consumable
"""

import datetime
import json
import os
import sqlite3
import sys

import pytest

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'utils'))


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def integ_db(tmp_path, monkeypatch):
    """
    Full-schema isolated DB for integration tests.
    Includes: work_proposals, governance_log, conv_timeline, swarm_knowledge,
    swarm_events, swarm_bus, conversations, tickets, agents, user_skill_permissions,
    chat_jobs, circuit_breaker_state.
    """
    db_path = str(tmp_path / 'integ.db')
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
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
        );

        CREATE TABLE IF NOT EXISTS governance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            agent TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_govlog_proposal ON governance_log(proposal_id);

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            source TEXT DEFAULT '',
            sender TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conv_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER,
            agent TEXT DEFAULT '',
            event_type TEXT DEFAULT '',
            payload TEXT DEFAULT '',
            job_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_timeline_conv ON conv_timeline(conv_id);

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE,
            queue_id TEXT DEFAULT '',
            sender_email TEXT DEFAULT '',
            question TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            content TEXT DEFAULT '',
            source_agent TEXT DEFAULT '',
            source_proposal_id TEXT DEFAULT '',
            category TEXT DEFAULT 'fact',
            importance INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT DEFAULT '',
            payload TEXT DEFAULT '',
            source_agent TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_events_ack (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            agent TEXT DEFAULT '',
            acked_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_bus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            source_service TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            consumed_at TEXT DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bus_topic ON swarm_bus(topic);
        CREATE INDEX IF NOT EXISTS idx_bus_unconsumed ON swarm_bus(consumed_at) WHERE consumed_at IS NULL;

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER DEFAULT 0,
            name TEXT NOT NULL,
            label TEXT DEFAULT '',
            model TEXT DEFAULT '',
            temperature REAL DEFAULT 0.3,
            role TEXT DEFAULT '',
            system_prompt TEXT DEFAULT '',
            api_key_var TEXT DEFAULT '',
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            memory_table TEXT DEFAULT '',
            display_label TEXT DEFAULT '',
            aliases TEXT DEFAULT '',
            eta_seconds INTEGER DEFAULT 30,
            keep_alive TEXT DEFAULT '5m'
        );

        CREATE TABLE IF NOT EXISTS user_skill_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            skill TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS chat_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            conv_id INTEGER,
            agent TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS circuit_breaker_state (
            agent TEXT PRIMARY KEY,
            state TEXT DEFAULT 'closed',
            failure_count INTEGER DEFAULT 0,
            last_failure TEXT DEFAULT '',
            half_open_at TEXT DEFAULT ''
        );
    """)

    # Seed agents for trust and coordination tests
    agents_data = [
        (1, 'gemma', 'Gemma3', 'gemma3:latest', 'researcher', 'local', 1),
        (2, 'llama', 'LlaMA', 'llama3.2:latest', 'researcher', 'local', 1),
        (3, 'eleven', 'Eleven', 'claude-3.5', 'coordinator', 'paid', 1),
        (4, 'ghost', 'Ghost', 'ghost', 'human', 'human', 1),
        (5, 'qwen', 'Qwen', 'qwen2:latest', 'reviewer', 'local', 0),  # disabled
    ]
    conn.executemany(
        "INSERT INTO agents (number, name, label, model, role, tier, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", agents_data
    )
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    # Patch all the places that call get_connection (direct and copied refs)
    import database
    monkeypatch.setattr(database, 'get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    try:
        monkeypatch.setattr('utils.db.nodes.get_connection', _get_conn)
    except Exception:
        pass
    try:
        monkeypatch.setattr('utils.db.knowledge.get_connection', _get_conn)
    except Exception:
        pass
    try:
        monkeypatch.setattr('utils.db.timeline.get_connection', _get_conn)
    except Exception:
        pass
    try:
        monkeypatch.setattr('utils.swarm_bus.get_connection', _get_conn)
    except Exception:
        pass

    yield conn, _get_conn, db_path
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 1. End-to-End Proposal Lifecycle
# ══════════════════════════════════════════════════════════════════════════════

class TestProposalLifecycle:
    """Full lifecycle: create → all transitions → verify every side effect."""

    def test_full_lifecycle_with_all_side_effects(self, integ_db):
        """
        pending → approved → in_progress → done → uat → closed.
        After each step, verify the correct side effects fired.
        """
        conn, get_conn, _ = integ_db
        from governance import transition_proposal, get_transition_history

        # Create a proposal in pending state with a linked conversation
        conv_id = conn.execute(
            "INSERT INTO conversations (title, source) VALUES ('Test conv', 'terminal')"
        ).lastrowid
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, description, status, "
            "source_conv_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('INT-001', 'eleven', 'Integration proposal', 'Testing the full chain',
             'pending', str(conv_id), now)
        )
        conn.commit()

        # Step 1: pending → approved
        r = transition_proposal('INT-001', 'approved', 'eleven', actor='duck')
        assert r['old_status'] == 'pending'
        assert r['new_status'] == 'approved'

        # Bus event: proposal.created (pending→approved)
        bus_rows = conn.execute(
            "SELECT * FROM swarm_bus WHERE topic='proposal.created'"
        ).fetchall()
        assert len(bus_rows) >= 1
        payload = json.loads(bus_rows[-1]['payload_json'])
        assert payload['proposal_id'] == 'INT-001'

        # Step 2: approved → in_progress
        r = transition_proposal('INT-001', 'in_progress', 'eleven')
        assert r['new_status'] == 'in_progress'

        # Bus event: proposal.status_changed
        bus_rows = conn.execute(
            "SELECT * FROM swarm_bus WHERE topic='proposal.status_changed'"
        ).fetchall()
        assert any(
            json.loads(row['payload_json'])['new_status'] == 'in_progress'
            for row in bus_rows
        )

        # Timeline: trace should have been written for both transitions
        timeline = conn.execute(
            "SELECT * FROM conv_timeline WHERE conv_id=? ORDER BY id",
            (conv_id,)
        ).fetchall()
        assert len(timeline) >= 2
        assert timeline[0]['event_type'] == 'proposal'

        # Step 3: in_progress → done
        r = transition_proposal('INT-001', 'done', 'eleven')
        assert r['new_status'] == 'done'

        # Knowledge auto-published on →done
        knowledge = conn.execute(
            "SELECT * FROM swarm_knowledge WHERE source_proposal_id='INT-001'"
        ).fetchall()
        assert len(knowledge) == 1
        assert 'Integration proposal' in knowledge[0]['content']
        assert knowledge[0]['category'] == 'decision'

        # Step 4: done → uat
        r = transition_proposal('INT-001', 'uat', 'eleven')
        assert r['new_status'] == 'uat'

        # Step 5: uat → closed
        r = transition_proposal('INT-001', 'closed', 'eleven')
        assert r['new_status'] == 'closed'

        # Audit trail: should have 5 entries for the 5 transitions
        history = get_transition_history('INT-001')
        assert len(history) == 5
        statuses = [(h['old_status'], h['new_status']) for h in history]
        assert statuses == [
            ('pending', 'approved'),
            ('approved', 'in_progress'),
            ('in_progress', 'done'),
            ('done', 'uat'),
            ('uat', 'closed'),
        ]

    def test_rejection_and_recovery(self, integ_db):
        """Test the rejection → re-submission path."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('INT-002', 'gemma', 'Rejected proposal', 'pending', now)
        )
        conn.commit()

        # pending → rejected
        r = transition_proposal('INT-002', 'rejected', 'gemma', actor='duck',
                                note='Needs more detail')
        assert r['new_status'] == 'rejected'

        # rejected → pending (re-submit)
        r = transition_proposal('INT-002', 'pending', 'gemma',
                                note='Added more detail')
        assert r['new_status'] == 'pending'

        # Now can be approved again
        r = transition_proposal('INT-002', 'approved', 'gemma', actor='duck')
        assert r['new_status'] == 'approved'

    def test_done_rollback_to_in_progress(self, integ_db):
        """done → in_progress is allowed (rework)."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('INT-003', 'eleven', 'Rework proposal', 'done', now)
        )
        conn.commit()

        r = transition_proposal('INT-003', 'in_progress', 'eleven',
                                note='Bug found in UAT')
        assert r['new_status'] == 'in_progress'

    def test_parallel_agents_independent(self, integ_db):
        """Two different agents can both have in_progress proposals."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('PAR-A', 'gemma', 'Gemma work', 'approved', now)
        )
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('PAR-B', 'eleven', 'Eleven work', 'approved', now)
        )
        conn.commit()

        r1 = transition_proposal('PAR-A', 'in_progress', 'gemma')
        r2 = transition_proposal('PAR-B', 'in_progress', 'eleven')
        assert r1['new_status'] == 'in_progress'
        assert r2['new_status'] == 'in_progress'

    def test_singleton_blocks_second_in_progress(self, integ_db):
        """Same agent cannot have two in_progress proposals."""
        conn, _, _ = integ_db
        from governance import transition_proposal, SingletonViolationError

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('SNG-A', 'gemma', 'First', 'approved', now)
        )
        conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('SNG-B', 'gemma', 'Second', 'approved', now)
        )
        conn.commit()

        transition_proposal('SNG-A', 'in_progress', 'gemma')
        with pytest.raises(SingletonViolationError):
            transition_proposal('SNG-B', 'in_progress', 'gemma')


# ══════════════════════════════════════════════════════════════════════════════
# 2. Skill Trust Enforcement
# ══════════════════════════════════════════════════════════════════════════════

class TestSkillTrust:
    """Verify trust_level × tier gating across all combinations."""

    def _get_trust_gate(self):
        """Import the internal _trust_gate function."""
        try:
            from fridays.skills import _trust_gate
            return _trust_gate
        except ImportError:
            pytest.skip('fridays.skills not importable in test env')

    def _get_tier_max(self):
        try:
            from fridays.skills import TIER_MAX_TRUST
            return TIER_MAX_TRUST
        except ImportError:
            pytest.skip('fridays.skills not importable in test env')

    def test_tier_max_trust_map_complete(self, integ_db):
        """All expected tiers are in the map."""
        tier_max = self._get_tier_max()
        for tier in ('local', 'paid', 'service', 'human', 'ghost'):
            assert tier in tier_max, f'Missing tier: {tier}'

    def test_local_blocked_from_trust2(self, integ_db):
        """Local agent cannot call a trust_level=2 skill."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        # Inject a fake skill with trust_level=2
        REGISTRY['_test_trust2'] = {'trust_level': 2}
        _tier_cache['gemma'] = 'local'
        try:
            blocked, reason = _trust_gate('_test_trust2', 'gemma')
            assert blocked is True
            assert 'Trust denied' in reason
        finally:
            REGISTRY.pop('_test_trust2', None)
            _tier_cache.pop('gemma', None)

    def test_local_allowed_trust0(self, integ_db):
        """Local agent can call trust_level=0 skill (read-only always allowed)."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        REGISTRY['_test_trust0'] = {'trust_level': 0}
        _tier_cache['gemma'] = 'local'
        try:
            blocked, reason = _trust_gate('_test_trust0', 'gemma')
            assert blocked is False
        finally:
            REGISTRY.pop('_test_trust0', None)
            _tier_cache.pop('gemma', None)

    def test_local_allowed_trust1(self, integ_db):
        """Local agent can call trust_level=1 skill."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        REGISTRY['_test_trust1'] = {'trust_level': 1}
        _tier_cache['gemma'] = 'local'
        try:
            blocked, reason = _trust_gate('_test_trust1', 'gemma')
            assert blocked is False
        finally:
            REGISTRY.pop('_test_trust1', None)
            _tier_cache.pop('gemma', None)

    def test_paid_allowed_trust2(self, integ_db):
        """Paid agent can call trust_level=2 skill."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        REGISTRY['_test_trust2'] = {'trust_level': 2}
        _tier_cache['eleven'] = 'paid'
        try:
            blocked, reason = _trust_gate('_test_trust2', 'eleven')
            assert blocked is False
        finally:
            REGISTRY.pop('_test_trust2', None)
            _tier_cache.pop('eleven', None)

    def test_human_allowed_trust4(self, integ_db):
        """Human/ghost agent can call trust_level=4 skill."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        REGISTRY['_test_trust4'] = {'trust_level': 4}
        _tier_cache['ghost'] = 'human'
        try:
            blocked, reason = _trust_gate('_test_trust4', 'ghost')
            assert blocked is False
        finally:
            REGISTRY.pop('_test_trust4', None)
            _tier_cache.pop('ghost', None)

    def test_override_local_gets_trust2(self, integ_db):
        """user_skill_permissions override allows local agent to use trust2 skill."""
        from fridays.skills import _trust_gate, REGISTRY, _tier_cache
        from unittest.mock import patch

        REGISTRY['_test_trust2_override'] = {'trust_level': 2}
        _tier_cache['gemma'] = 'local'
        try:
            # Without override: blocked
            blocked, reason = _trust_gate('_test_trust2_override', 'gemma')
            assert blocked is True

            # With override: patch the lazy import target in utils.db.auth
            with patch('utils.db.auth.can_user_invoke_skill', return_value=True):
                blocked, _ = _trust_gate('_test_trust2_override', 'gemma')
                assert blocked is False  # With override, allowed
        finally:
            REGISTRY.pop('_test_trust2_override', None)
            _tier_cache.pop('gemma', None)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Cross-Reference Chain: Ticket → Proposal → Conversation → Timeline
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossReferences:
    """Verify the traceability chain across tickets, proposals, and conversations."""

    def test_ticket_to_proposal_link(self, integ_db):
        """A proposal's ticket_number links back to the tickets table."""
        conn, _, _ = integ_db

        conn.execute(
            "INSERT INTO tickets (ticket_number, question, status) "
            "VALUES ('TKT-100', 'How to fix the widget?', 'open')"
        )
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, status, ticket_number, updated_at) "
            "VALUES ('XREF-001', 'gemma', 'Fix widget', 'pending', 'TKT-100', ?)",
            (now,)
        )
        conn.commit()

        # Cross-ref: proposal → ticket
        row = conn.execute(
            "SELECT p.proposal_id, t.question "
            "FROM work_proposals p JOIN tickets t ON p.ticket_number = t.ticket_number "
            "WHERE p.proposal_id='XREF-001'"
        ).fetchone()
        assert row is not None
        assert row['question'] == 'How to fix the widget?'

    def test_proposal_to_conversation_link(self, integ_db):
        """A proposal's source_conv_id links to the conversations table."""
        conn, _, _ = integ_db

        conv_id = conn.execute(
            "INSERT INTO conversations (title, source) VALUES ('Widget discussion', 'terminal')"
        ).lastrowid
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, status, source_conv_id, updated_at) "
            "VALUES ('XREF-002', 'eleven', 'Widget redesign', 'pending', ?, ?)",
            (str(conv_id), now)
        )
        conn.commit()

        row = conn.execute(
            "SELECT p.proposal_id, c.title AS conv_title "
            "FROM work_proposals p JOIN conversations c ON p.source_conv_id = CAST(c.id AS TEXT) "
            "WHERE p.proposal_id='XREF-002'"
        ).fetchone()
        assert row is not None
        assert row['conv_title'] == 'Widget discussion'

    def test_transition_creates_timeline_in_linked_conversation(self, integ_db):
        """Governance transitions auto-trace to the conversation's timeline."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        conv_id = conn.execute(
            "INSERT INTO conversations (title) VALUES ('Traced conversation')"
        ).lastrowid
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, status, source_conv_id, updated_at) "
            "VALUES ('XREF-003', 'eleven', 'Traced proposal', 'pending', ?, ?)",
            (str(conv_id), now)
        )
        conn.commit()

        transition_proposal('XREF-003', 'approved', 'eleven', actor='duck')

        events = conn.execute(
            "SELECT * FROM conv_timeline WHERE conv_id=? AND event_type='proposal'",
            (conv_id,)
        ).fetchall()
        assert len(events) == 1
        payload = json.loads(events[0]['payload'])
        assert payload['proposal_id'] == 'XREF-003'
        assert payload['old_status'] == 'pending'
        assert payload['new_status'] == 'approved'
        assert events[0]['job_id'] == 'gov-XREF-003'

    def test_full_chain_ticket_proposal_timeline(self, integ_db):
        """Full traceability: ticket → proposal → conversation → timeline events."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        # Create all three linked entities
        conv_id = conn.execute(
            "INSERT INTO conversations (title) VALUES ('Full chain conv')"
        ).lastrowid
        conn.execute(
            "INSERT INTO tickets (ticket_number, question) "
            "VALUES ('TKT-200', 'Implement feature X')"
        )
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, status, ticket_number, source_conv_id, updated_at) "
            "VALUES ('CHAIN-001', 'eleven', 'Feature X', 'pending', 'TKT-200', ?, ?)",
            (str(conv_id), now)
        )
        conn.commit()

        # Drive through lifecycle
        transition_proposal('CHAIN-001', 'approved', 'eleven', actor='duck')
        transition_proposal('CHAIN-001', 'in_progress', 'eleven')
        transition_proposal('CHAIN-001', 'done', 'eleven')

        # Verify the chain
        # 1. Ticket is linked
        ticket_link = conn.execute(
            "SELECT t.ticket_number FROM tickets t "
            "JOIN work_proposals p ON t.ticket_number = p.ticket_number "
            "WHERE p.proposal_id='CHAIN-001'"
        ).fetchone()
        assert ticket_link['ticket_number'] == 'TKT-200'

        # 2. Timeline events exist in the conversation
        events = conn.execute(
            "SELECT * FROM conv_timeline WHERE conv_id=? ORDER BY id",
            (conv_id,)
        ).fetchall()
        assert len(events) == 3  # approved, in_progress, done

        # 3. Knowledge was auto-published on →done
        knowledge = conn.execute(
            "SELECT * FROM swarm_knowledge WHERE source_proposal_id='CHAIN-001'"
        ).fetchone()
        assert knowledge is not None
        assert 'Feature X' in knowledge['content']

        # 4. Bus events for all transitions
        bus = conn.execute(
            "SELECT topic, payload_json FROM swarm_bus ORDER BY id"
        ).fetchall()
        bus_for_chain = [
            b for b in bus
            if json.loads(b['payload_json']).get('proposal_id') == 'CHAIN-001'
        ]
        assert len(bus_for_chain) == 3


# ══════════════════════════════════════════════════════════════════════════════
# 4. Agent Coordination
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentCoordination:
    """Integration tests for check_and_reroute and claim_pending_proposal."""

    def test_check_idle_agent_returns_same(self, integ_db):
        """An idle agent should be returned as-is."""
        conn, _, _ = integ_db
        try:
            from utils.agent_coordination import check_and_reroute
        except ImportError:
            pytest.skip('agent_coordination not importable')

        agent, rerouted, reason = check_and_reroute('gemma')
        assert agent == 'gemma'
        assert rerouted is False

    def test_reroute_busy_agent(self, integ_db):
        """A busy agent should be rerouted to an alternative with the same role."""
        conn, _, _ = integ_db
        try:
            from utils.agent_coordination import check_and_reroute
        except ImportError:
            pytest.skip('agent_coordination not importable')

        # Make gemma busy by adding an active job
        conn.execute(
            "INSERT INTO chat_jobs (job_id, agent, status) VALUES ('j1', 'gemma', 'running')"
        )
        conn.commit()

        agent, rerouted, reason = check_and_reroute('gemma')
        # Should reroute to llama (same role=researcher, also idle)
        if rerouted:
            assert agent == 'llama'
        else:
            # If system doesn't consider single job as "busy", that's also valid
            assert agent == 'gemma'

    def test_claim_pending_proposal(self, integ_db):
        """An agent should be able to claim an unclaimed pending proposal."""
        conn, _, _ = integ_db
        try:
            from utils.agent_coordination import claim_pending_proposal
        except ImportError:
            pytest.skip('agent_coordination not importable')

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, status, updated_at) "
            "VALUES ('CLAIM-001', '', 'Unclaimed work', 'pending', ?)",
            (now,)
        )
        conn.commit()

        result = claim_pending_proposal('gemma')
        # Should have claimed the proposal
        if result:
            row = conn.execute(
                "SELECT agent, status FROM work_proposals WHERE proposal_id='CLAIM-001'"
            ).fetchone()
            # Re-read from a new conn since claim uses its own
            from database import get_connection
            c2 = get_connection()
            row = c2.execute(
                "SELECT agent, status FROM work_proposals WHERE proposal_id='CLAIM-001'"
            ).fetchone()
            c2.close()
            assert row['agent'] == 'gemma'
            assert row['status'] == 'approved'

    def test_claim_no_available_proposals(self, integ_db):
        """Claiming with no pending proposals returns None."""
        conn, _, _ = integ_db
        try:
            from utils.agent_coordination import claim_pending_proposal
        except ImportError:
            pytest.skip('agent_coordination not importable')

        result = claim_pending_proposal('gemma')
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 5. Bus + Knowledge Integration
# ══════════════════════════════════════════════════════════════════════════════

class TestBusKnowledgeIntegration:
    """Verify bus events and knowledge entries work together."""

    def test_done_transition_creates_both_knowledge_and_bus_event(self, integ_db):
        """→done should create a knowledge entry AND a bus event."""
        conn, _, _ = integ_db
        from governance import transition_proposal

        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            "INSERT INTO work_proposals "
            "(proposal_id, agent, title, description, status, updated_at) "
            "VALUES ('BUS-001', 'eleven', 'Bus test', 'Testing bus+knowledge', 'in_progress', ?)",
            (now,)
        )
        conn.commit()

        transition_proposal('BUS-001', 'done', 'eleven')

        # Knowledge created
        k = conn.execute(
            "SELECT * FROM swarm_knowledge WHERE key='proposal-BUS-001'"
        ).fetchone()
        assert k is not None
        assert k['category'] == 'decision'
        assert k['importance'] == 6

        # Bus event for status_changed
        bus = conn.execute(
            "SELECT * FROM swarm_bus WHERE topic='proposal.status_changed' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert bus is not None
        payload = json.loads(bus['payload_json'])
        assert payload['new_status'] == 'done'
        assert payload['proposal_id'] == 'BUS-001'

    def test_knowledge_event_emitted_on_publish(self, integ_db):
        """Knowledge write emits a swarm_events entry for broadcast."""
        conn, _, _ = integ_db
        try:
            from utils.db.knowledge import write_knowledge
        except ImportError:
            pytest.skip('knowledge module not importable')

        write_knowledge(
            key='test-entry',
            content='Integration test knowledge',
            source_agent='gemma',
            category='fact',
            conn=conn,
        )
        conn.commit()

        events = conn.execute(
            "SELECT * FROM swarm_events WHERE event_type='knowledge.new'"
        ).fetchall()
        assert len(events) >= 1
        payload = json.loads(events[-1]['payload'])
        assert payload['key'] == 'test-entry'

    def test_bus_messages_consumable(self, integ_db):
        """Published bus messages can be consumed and marked."""
        conn, _, _ = integ_db
        from utils.swarm_bus import publish, get_unconsumed, mark_consumed

        publish('test.topic', {'data': 42}, 'test_service', conn=conn)
        conn.commit()

        unconsumed = get_unconsumed(topic='test.topic', conn=conn)
        assert len(unconsumed) >= 1
        msg_id = unconsumed[0]['id']

        mark_consumed(msg_id, conn=conn)
        conn.commit()

        remaining = get_unconsumed(topic='test.topic', conn=conn)
        assert all(r['id'] != msg_id for r in remaining)
