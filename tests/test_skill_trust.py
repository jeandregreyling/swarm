"""
tests/test_skill_trust.py — A.2 unit + integration tests
═══════════════════════════════════════════════════════════════
Tests trust level enforcement, agent status API, self-coordination.
"""
import sqlite3
import sys
import types
import pytest

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')


# ── Shared DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
def mock_db(monkeypatch, tmp_path):
    """In-memory SQLite with agents, chat_jobs, work_proposals, user_skill_permissions tables."""
    db_path = str(tmp_path / 'test.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE agents (
        id INTEGER PRIMARY KEY, number INTEGER, name TEXT UNIQUE, label TEXT,
        model TEXT, role TEXT, temperature REAL, tier TEXT DEFAULT 'local',
        enabled INTEGER DEFAULT 1, system_prompt TEXT DEFAULT '', api_key_var TEXT DEFAULT '',
        roles TEXT DEFAULT '[]'
    )""")
    conn.execute("""CREATE TABLE chat_jobs (
        job_id TEXT PRIMARY KEY, conversation_id INTEGER, agent TEXT,
        status TEXT, runtime_class TEXT, stage TEXT,
        eta_seconds INTEGER, elapsed_ms INTEGER, tokens INTEGER,
        error TEXT, started_at TEXT, updated_at TEXT,
        stage_trace_json TEXT
    )""")
    conn.execute("""CREATE TABLE work_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT,
        agent TEXT, status TEXT DEFAULT 'pending', priority INTEGER DEFAULT 5,
        tags TEXT, created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE user_skill_permissions (
        username TEXT, skill_name TEXT, allowed INTEGER DEFAULT 1,
        created_by TEXT, created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(username, skill_name)
    )""")
    conn.execute("""CREATE TABLE ghost_circle (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entry_type TEXT, source TEXT,
        content TEXT, severity TEXT, created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE user_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
        display_name TEXT, user_type TEXT DEFAULT 'human',
        linked_agent TEXT, is_active INTEGER DEFAULT 1,
        can_proxy INTEGER DEFAULT 0, created_by TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    # Seed agents
    agents = [
        (0, 'gemma', 'GEMMA', 'gemma:latest', 'developer', 'local', 1),
        (1, 'llama', 'LLAMA', 'llama:latest', 'developer', 'local', 1),
        (2, 'nine', 'NINE', 'groq', 'developer', 'paid', 1),
        (3, 'ten', 'TEN', 'gpt-4', 'developer', 'paid', 1),
        (4, 'ghost', 'GHOST', '', '', 'human', 1),
        (5, 'duck', 'DUCK', 'qwen:latest', 'auditor', 'local', 1),
        (6, 'scholar', 'SCHOLAR', 'gemini', 'researcher', 'service', 1),
        (7, 'eight', 'EIGHT', 'eight:latest', 'developer', 'local', 0),  # disabled
    ]
    for num, name, label, model, role, tier, enabled in agents:
        conn.execute(
            "INSERT INTO agents (number, name, label, model, role, tier, enabled) VALUES (?,?,?,?,?,?,?)",
            (num, name, label, model, role, tier, enabled)
        )
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    import database
    monkeypatch.setattr(database, 'get_connection', _get_conn)

    # Also patch utils.db._connection + auth which auth.py imports at module level
    import utils.db._connection as _db_conn
    monkeypatch.setattr(_db_conn, 'get_connection', _get_conn)
    import utils.db.auth as _db_auth
    monkeypatch.setattr(_db_auth, 'get_connection', _get_conn)

    # Clear the tier cache in skills module
    from fridays.skills import _tier_cache
    _tier_cache.clear()

    return _get_conn


# ── A.2.1: Trust Level Enforcement ────────────────────────────────────────

class TestTrustEnforcement:
    def test_local_agent_blocked_from_trust2_skill(self, mock_db):
        """Local tier (max_trust=1) cannot invoke trust_level=2 skill."""
        from fridays.skills import _trust_gate
        blocked, reason = _trust_gate('fs_write', 'gemma')
        assert blocked is True
        assert 'Trust denied' in reason
        assert 'tier=local' in reason
        assert 'SKILL user_skill_permissions' not in reason
        assert 'Do not emit a user_skill_permissions skill' in reason

    def test_local_agent_allowed_trust0_skill(self, mock_db):
        """Local tier can invoke trust_level=0 (read-only) skills."""
        from fridays.skills import _trust_gate
        blocked, reason = _trust_gate('search', 'gemma')
        assert blocked is False

    def test_local_agent_allowed_trust1_skill(self, mock_db):
        """Local tier (max_trust=1) can invoke trust_level=1 skills."""
        from fridays.skills import _trust_gate
        blocked, reason = _trust_gate('file_write', 'gemma')
        assert blocked is False

    def test_paid_agent_allowed_trust2_skill(self, mock_db):
        """Paid tier (max_trust=2) can invoke trust_level=2 skills."""
        from fridays.skills import _trust_gate
        blocked, reason = _trust_gate('fs_write', 'nine')
        assert blocked is False

    def test_ghost_can_call_any_skill(self, mock_db):
        """Ghost/human tier (max_trust=4) can invoke any skill."""
        from fridays.skills import _trust_gate
        # fs_write is trust_level=2
        blocked, reason = _trust_gate('fs_write', 'ghost')
        assert blocked is False
        # Even trust_level=0
        blocked2, _ = _trust_gate('search', 'ghost')
        assert blocked2 is False

    def test_user_skill_permission_override(self, mock_db):
        """user_skill_permissions override grants access to blocked skill."""
        from fridays.skills import _trust_gate
        # Gemma (local, max_trust=1) should be blocked from fs_write (trust=2)
        blocked, _ = _trust_gate('fs_write', 'gemma')
        assert blocked is True

        # Grant override: need a user profile (is_active) + permission row
        conn = mock_db()
        conn.execute(
            "INSERT INTO user_profiles (username, display_name, is_active) VALUES (?,?,?)",
            ('gemma', 'Gemma', 1)
        )
        conn.execute(
            "INSERT INTO user_skill_permissions (username, skill_name, allowed, created_by) VALUES (?,?,?,?)",
            ('gemma', 'fs_write', 1, 'ghost')
        )
        conn.commit()
        conn.close()

        # Now should be allowed
        blocked2, _ = _trust_gate('fs_write', 'gemma')
        assert blocked2 is False

    def test_tier_hierarchy(self, mock_db):
        """Verify tier → max_trust mapping."""
        from fridays.skills import TIER_MAX_TRUST
        assert TIER_MAX_TRUST['local'] == 1
        assert TIER_MAX_TRUST['paid'] == 2
        assert TIER_MAX_TRUST['service'] == 2
        assert TIER_MAX_TRUST['human'] == 4
        assert TIER_MAX_TRUST['ghost'] == 4


# ── A.2.2: Agent Status ──────────────────────────────────────────────────

class TestAgentStatus:
    def test_status_idle_agent(self, mock_db):
        """Agent with no running jobs should be idle."""
        from utils.agent_coordination import get_agent_status_map
        status_map = get_agent_status_map()
        assert status_map['gemma']['status'] == 'idle'

    def test_status_busy_agent(self, mock_db):
        """Agent with a running chat_job should be busy."""
        conn = mock_db()
        conn.execute(
            "INSERT INTO chat_jobs (job_id, agent, status, started_at, updated_at) VALUES (?,?,?,?,?)",
            ('job-1', 'gemma', 'running', '2026-01-01', '2026-01-01')
        )
        conn.commit()
        conn.close()
        from utils.agent_coordination import get_agent_status_map
        status_map = get_agent_status_map()
        assert status_map['gemma']['status'] == 'busy'
        assert status_map['gemma']['active_jobs'] == 1

    def test_status_disabled_agent(self, mock_db):
        """Agent with enabled=0 should be disabled."""
        from utils.agent_coordination import get_agent_status_map
        status_map = get_agent_status_map()
        assert status_map['eight']['status'] == 'disabled'

    def test_skill_agent_status_all(self, mock_db):
        """SKILL agent_status with no args returns all agents."""
        from fridays.skills import _skill_agent_status
        ok, output = _skill_agent_status('', 'ghost')
        assert ok is True
        assert 'gemma' in output
        assert 'nine' in output

    def test_skill_agent_status_single(self, mock_db):
        """SKILL agent_status with agent name returns single agent."""
        from fridays.skills import _skill_agent_status
        ok, output = _skill_agent_status('gemma', 'ghost')
        assert ok is True
        assert 'gemma' in output
        assert 'nine' not in output

    def test_skill_agent_status_unknown(self, mock_db):
        """SKILL agent_status with unknown agent returns error."""
        from fridays.skills import _skill_agent_status
        ok, output = _skill_agent_status('nonexistent', 'ghost')
        assert ok is False
        assert 'not found' in output


# ── A.2.3: Self-Coordination ─────────────────────────────────────────────

class TestSelfCoordination:
    def test_check_available_idle(self, mock_db):
        """Idle agent should be available."""
        from utils.agent_coordination import check_agent_available
        ok, info = check_agent_available('gemma')
        assert ok is True
        assert info['status'] == 'idle'

    def test_check_unavailable_busy(self, mock_db):
        """Busy agent should not be available."""
        conn = mock_db()
        conn.execute(
            "INSERT INTO chat_jobs (job_id, agent, status, started_at, updated_at) VALUES (?,?,?,?,?)",
            ('job-1', 'gemma', 'running', '2026-01-01', '2026-01-01')
        )
        conn.commit()
        conn.close()
        from utils.agent_coordination import check_agent_available
        ok, info = check_agent_available('gemma')
        assert ok is False
        assert 'active job' in info.get('reason', '')

    def test_find_alternative_same_role(self, mock_db):
        """Should find another idle agent with the same role."""
        conn = mock_db()
        # Make gemma busy so it needs rerouting
        conn.execute(
            "INSERT INTO chat_jobs (job_id, agent, status, started_at, updated_at) VALUES (?,?,?,?,?)",
            ('job-1', 'gemma', 'running', '2026-01-01', '2026-01-01')
        )
        conn.commit()
        conn.close()
        from utils.agent_coordination import find_alternative
        alt = find_alternative('gemma')
        assert alt is not None
        # Should find another developer: llama, nine, or ten (all have role=developer)
        assert alt in ('llama', 'nine', 'ten')

    def test_check_and_reroute(self, mock_db):
        """check_and_reroute returns alternative when target is busy."""
        conn = mock_db()
        conn.execute(
            "INSERT INTO chat_jobs (job_id, agent, status, started_at, updated_at) VALUES (?,?,?,?,?)",
            ('job-1', 'gemma', 'running', '2026-01-01', '2026-01-01')
        )
        conn.commit()
        conn.close()
        from utils.agent_coordination import check_and_reroute
        agent, rerouted, reason = check_and_reroute('gemma')
        assert rerouted is True
        assert agent != 'gemma'
        assert 'rerouted' in reason

    def test_check_and_reroute_available(self, mock_db):
        """check_and_reroute returns original agent when available."""
        from utils.agent_coordination import check_and_reroute
        agent, rerouted, reason = check_and_reroute('gemma')
        assert rerouted is False
        assert agent == 'gemma'

    def test_claim_pending_proposal(self, mock_db):
        """Idle agent can claim oldest pending proposal."""
        conn = mock_db()
        conn.execute(
            "INSERT INTO work_proposals (title, description, status, priority) VALUES (?,?,?,?)",
            ('Fix bug', 'Fix the bug', 'pending', 5)
        )
        conn.execute(
            "INSERT INTO work_proposals (title, description, status, priority) VALUES (?,?,?,?)",
            ('Add feature', 'Add the feature', 'pending', 3)
        )
        conn.commit()
        conn.close()
        from utils.agent_coordination import claim_pending_proposal
        pid = claim_pending_proposal('gemma')
        assert pid is not None
        # Should claim the higher-priority (lower number) one first
        conn2 = mock_db()
        row = conn2.execute("SELECT * FROM work_proposals WHERE id=?", (pid,)).fetchone()
        conn2.close()
        assert row['agent'] == 'gemma'
        assert row['status'] == 'approved'
        assert row['title'] == 'Add feature'  # priority 3 < 5

    def test_claim_no_proposals(self, mock_db):
        """Claim returns None when no pending proposals."""
        from utils.agent_coordination import claim_pending_proposal
        pid = claim_pending_proposal('gemma')
        assert pid is None
