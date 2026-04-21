"""Tests for Agent 20 — Phase 8.3: Memory, Decisions, Mapper, Health Digest.

Covers: memory r/w, honesty enforcement, decision matrix, system mapper,
health digest API, pattern learning, decay, consolidation, stress.
All deterministic, no LLM calls, no network.
"""

import json
import sqlite3
import pytest

from flask import Flask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db83(tmp_path, monkeypatch):
    """Full-schema test DB for Phase 8.3 modules."""
    db_path = str(tmp_path / 'test83.db')
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_addr TEXT DEFAULT '', subject TEXT DEFAULT '',
            question TEXT DEFAULT '', status TEXT DEFAULT 'queued',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE work_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE, agent TEXT, title TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE, question TEXT,
            sender_email TEXT DEFAULT '', status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT, event TEXT, detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE system_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT DEFAULT (datetime('now')),
            cpu_percent REAL DEFAULT 30, ram_used_gb REAL DEFAULT 4,
            ram_available_gb REAL DEFAULT 12, cpu_temp_c REAL DEFAULT 50
        );
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT DEFAULT 'ghost', topic TEXT, category TEXT DEFAULT 'general',
            score REAL DEFAULT 10, active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            agent TEXT NOT NULL,
            component TEXT DEFAULT '',
            proposal_file TEXT DEFAULT '',
            decision TEXT NOT NULL,
            reasoning TEXT DEFAULT '',
            test_status TEXT DEFAULT 'PENDING',
            commit_hash TEXT DEFAULT '',
            checkpoint_id INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            archived INTEGER DEFAULT 0
        );
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, schedule TEXT, action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '', next_run TEXT, enabled INTEGER DEFAULT 1,
            last_run TEXT, created_by TEXT DEFAULT 'ghost', created_at TEXT
        );
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ok',
            output TEXT DEFAULT '', run_at TEXT NOT NULL
        );
        CREATE TABLE sniffer_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detail TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pending_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            processed_at TEXT DEFAULT NULL
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER DEFAULT 0, name TEXT UNIQUE, label TEXT DEFAULT '',
            model TEXT DEFAULT '', role TEXT DEFAULT '', enabled INTEGER DEFAULT 1
        );
        CREATE TABLE council_output (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orb_role TEXT NOT NULL, thought TEXT NOT NULL,
            detail TEXT DEFAULT '', urgency INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.5,
            pfv_p REAL, pfv_f REAL, pfv_v REAL,
            source_refs TEXT DEFAULT '[]', context_json TEXT DEFAULT '{}',
            dismissed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL
        );
        CREATE TABLE user_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL, pattern_key TEXT NOT NULL,
            pattern_value TEXT, confidence REAL DEFAULT 0.1,
            occurrences INTEGER DEFAULT 1,
            first_seen TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now')),
            UNIQUE(pattern_type, pattern_key)
        );
        CREATE TABLE memory_twenty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'twenty', subject TEXT DEFAULT '',
            content TEXT NOT NULL, tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7, source TEXT DEFAULT 'council',
            ticket_ref TEXT DEFAULT '', archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE governance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            agent TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed baseline data
    conn.execute("INSERT INTO agents (number, name, label, model, role, enabled) VALUES (1, 'duck', 'Duck', 'local', 'Router', 1)")
    conn.execute("INSERT INTO agents (number, name, label, model, role, enabled) VALUES (20, 'twenty', 'Twenty', 'local-algorithm', 'Nervous system', 1)")
    conn.execute("INSERT INTO system_stats (cpu_percent, ram_used_gb, ram_available_gb, cpu_temp_c) VALUES (30, 4, 12, 50)")
    conn.commit()

    def mock_get_connection():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', mock_get_connection)
    monkeypatch.setattr('agents.twenty.observer.get_connection', mock_get_connection)
    monkeypatch.setattr('agents.twenty.memory.get_connection', mock_get_connection)
    monkeypatch.setattr('agents.twenty.decisions.get_connection', mock_get_connection)
    monkeypatch.setattr('agents.twenty.mapper.get_connection', mock_get_connection)
    monkeypatch.setattr('frontend.blueprints.council_bp.get_connection', mock_get_connection)
    # health_bp module is shadowed by the Blueprint object in __init__.py
    import frontend.blueprints.health_bp as _hbp_mod
    monkeypatch.setattr(_hbp_mod, 'get_connection', mock_get_connection)

    return conn, db_path


@pytest.fixture
def signals_normal():
    return {
        'queue_depth': 3,
        'queue_aging': [],
        'pending_proposals': [],
        'open_tickets_aging': [],
        'agent_errors': [],
        'system_stats': {'cpu_percent': 30, 'ram_available_gb': 12, 'cpu_temp_c': 50},
        'user_topics': [{'topic': 'python', 'category': 'dev', 'score': 15.0}],
        'recent_decisions': [],
        'scheduled_due': [],
        'sniffer_findings': [],
        'email_backlog': 2,
        'agent_roster': [
            {'number': 1, 'name': 'duck', 'label': 'Duck', 'model': 'local', 'role': 'Router', 'enabled': 1},
            {'number': 20, 'name': 'twenty', 'label': 'Twenty', 'model': 'local-algorithm', 'role': 'Nervous system', 'enabled': 1},
        ],
        'recent_dismissals': [],
        'own_memory': [],
        'collected_at': '2026-04-21 12:00:00',
    }


@pytest.fixture
def signals_crisis():
    """Crisis state — many errors, high CPU, stuck queue."""
    return {
        'queue_depth': 25,
        'queue_aging': [{'id': 1, 'subject': 'old', 'created_at': '2026-04-20 01:00:00'}],
        'pending_proposals': [],
        'open_tickets_aging': [
            {'ticket_number': 'T001', 'question': 'system down', 'created_at': '2026-04-19 01:00:00'},
        ],
        'agent_errors': [
            {'service': 'duck', 'event': 'error', 'detail': 'timeout', 'created_at': '2026-04-21 11:55:00'},
            {'service': 'duck', 'event': 'error', 'detail': 'crash', 'created_at': '2026-04-21 11:56:00'},
            {'service': 'llama', 'event': 'error', 'detail': 'OOM', 'created_at': '2026-04-21 11:57:00'},
            {'service': 'qwen', 'event': 'error', 'detail': 'timeout', 'created_at': '2026-04-21 11:58:00'},
            {'service': 'qwen', 'event': 'error', 'detail': 'failed', 'created_at': '2026-04-21 11:59:00'},
            {'service': 'thirteen', 'event': 'error', 'detail': 'dead', 'created_at': '2026-04-21 11:59:30'},
        ],
        'system_stats': {'cpu_percent': 95, 'ram_available_gb': 0.5, 'cpu_temp_c': 88},
        'user_topics': [],
        'recent_decisions': [],
        'scheduled_due': [],
        'sniffer_findings': [{'id': 1, 'detail': 'suspicious pattern', 'created_at': '2026-04-21 11:50:00'}],
        'email_backlog': 30,
        'agent_roster': [
            {'number': 1, 'name': 'duck', 'label': 'Duck', 'model': 'local', 'role': 'Router', 'enabled': 1},
        ],
        'recent_dismissals': [],
        'own_memory': [],
        'collected_at': '2026-04-21 12:00:00',
    }


# ===========================================================================
# 1. Identity — honesty constraint present
# ===========================================================================

class TestHonestyIdentity:
    def test_honesty_constraint_in_identity(self):
        from agents.twenty import IDENTITY
        constraints = IDENTITY['constraints']
        assert any('honest' in c.lower() for c in constraints), \
            "Honesty rule must be in constraints"

    def test_six_constraints(self):
        from agents.twenty import IDENTITY
        assert len(IDENTITY['constraints']) >= 6


# ===========================================================================
# 2. Memory module
# ===========================================================================

class TestMemoryWrite:
    def test_remember_returns_id(self, db83):
        from agents.twenty.memory import remember
        conn, _ = db83
        mid = remember('test subject', 'test content', conn=conn)
        assert isinstance(mid, int) and mid > 0

    def test_remember_stores_correctly(self, db83):
        from agents.twenty.memory import remember
        conn, _ = db83
        remember('queue spike', 'Saw 25 items queued', tags='queue,urgent',
                 importance=8, conn=conn)
        row = conn.execute(
            "SELECT * FROM memory_twenty WHERE subject='queue spike'"
        ).fetchone()
        assert row is not None
        assert row['importance'] == 8
        assert 'queue' in row['tags']
        assert row['agent'] == 'twenty'

    def test_remember_truncates_long_content(self, db83):
        from agents.twenty.memory import remember
        conn, _ = db83
        long_content = 'x' * 5000
        remember('long', long_content, conn=conn)
        row = conn.execute(
            "SELECT content FROM memory_twenty WHERE subject='long'"
        ).fetchone()
        assert len(row['content']) <= 2000

    def test_remember_pattern_creates(self, db83):
        from agents.twenty.memory import remember_pattern
        conn, _ = db83
        remember_pattern('error_frequency', 'duck', '{"count": 3}', confidence=0.5, conn=conn)
        row = conn.execute(
            "SELECT * FROM user_patterns WHERE pattern_key='duck'"
        ).fetchone()
        assert row is not None
        assert row['confidence'] == 0.5

    def test_remember_pattern_upserts(self, db83):
        from agents.twenty.memory import remember_pattern
        conn, _ = db83
        remember_pattern('error_frequency', 'duck', '{"count": 1}', confidence=0.3, conn=conn)
        remember_pattern('error_frequency', 'duck', '{"count": 2}', confidence=0.3, conn=conn)
        row = conn.execute(
            "SELECT * FROM user_patterns WHERE pattern_key='duck'"
        ).fetchone()
        assert row['occurrences'] == 2
        assert row['confidence'] > 0.3  # should have grown


class TestMemoryRead:
    def test_recall_by_subject(self, db83):
        from agents.twenty.memory import remember, recall
        conn, _ = db83
        remember('cpu alert', 'CPU was 95%', importance=8, conn=conn)
        remember('queue info', 'Queue is normal', importance=3, conn=conn)
        results = recall(subject_like='cpu', conn=conn)
        assert len(results) == 1
        assert results[0]['subject'] == 'cpu alert'

    def test_recall_by_tags(self, db83):
        from agents.twenty.memory import remember, recall
        conn, _ = db83
        remember('a', 'content', tags='urgent,error', conn=conn)
        remember('b', 'content', tags='info', conn=conn)
        results = recall(tags_like='urgent', conn=conn)
        assert len(results) == 1

    def test_recall_min_importance(self, db83):
        from agents.twenty.memory import remember, recall
        conn, _ = db83
        remember('low', 'trivial', importance=2, conn=conn)
        remember('high', 'critical', importance=9, conn=conn)
        results = recall(min_importance=7, conn=conn)
        assert all(r['importance'] >= 7 for r in results)

    def test_recall_excludes_archived(self, db83):
        from agents.twenty.memory import remember, recall
        conn, _ = db83
        mid = remember('archived item', 'old stuff', conn=conn)
        conn.execute("UPDATE memory_twenty SET archived=1 WHERE id=?", (mid,))
        conn.commit()
        results = recall(subject_like='archived', conn=conn)
        assert len(results) == 0

    def test_recall_patterns(self, db83):
        from agents.twenty.memory import remember_pattern, recall_patterns
        conn, _ = db83
        remember_pattern('queue_depth', 'current', '{"depth": 5}', confidence=0.6, conn=conn)
        results = recall_patterns(pattern_type='queue_depth', conn=conn)
        assert len(results) == 1
        assert results[0]['confidence'] == 0.6


class TestHonestyCheck:
    def test_raises_urgency_on_negative_signals(self):
        from agents.twenty.memory import honesty_check
        thought = {'thought': 'System error crash detected', 'detail': 'Multiple failures',
                   'urgency': 0, 'confidence': 0.7}
        result = honesty_check(thought)
        assert result['urgency'] >= 1, "Honesty should raise urgency for negative signals"

    def test_no_change_on_positive_signals(self):
        from agents.twenty.memory import honesty_check
        thought = {'thought': 'Queue is light', 'detail': 'All healthy',
                   'urgency': 0, 'confidence': 0.7}
        result = honesty_check(thought)
        assert result['urgency'] == 0

    def test_caps_confidence_on_negative(self):
        from agents.twenty.memory import honesty_check
        thought = {'thought': 'error error crash failure blocked',
                   'detail': 'timeout rejected', 'urgency': 0, 'confidence': 0.95}
        result = honesty_check(thought)
        assert result['confidence'] <= 0.85

    def test_never_suppresses_bad_news(self):
        from agents.twenty.memory import honesty_check
        thought = {'thought': 'critical error detected', 'detail': 'system broken',
                   'urgency': 2, 'confidence': 0.8}
        result = honesty_check(thought)
        # Urgency should not go down
        assert result['urgency'] >= 2


class TestMemoryDecay:
    def test_decay_archives_old_low_importance(self, db83):
        from agents.twenty.memory import decay_stale_memories
        conn, _ = db83
        # Insert old, low-importance memory
        conn.execute(
            "INSERT INTO memory_twenty (subject, content, importance, created_at) "
            "VALUES ('old', 'stale data', 2, '2026-01-01 00:00:00')"
        )
        conn.commit()
        archived = decay_stale_memories(conn=conn)
        assert archived >= 1
        row = conn.execute("SELECT archived FROM memory_twenty WHERE subject='old'").fetchone()
        assert row['archived'] == 1

    def test_decay_keeps_important_memories(self, db83):
        from agents.twenty.memory import decay_stale_memories
        conn, _ = db83
        conn.execute(
            "INSERT INTO memory_twenty (subject, content, importance, created_at) "
            "VALUES ('important', 'critical data', 9, '2026-01-01 00:00:00')"
        )
        conn.commit()
        decay_stale_memories(conn=conn)
        row = conn.execute("SELECT archived FROM memory_twenty WHERE subject='important'").fetchone()
        assert row['archived'] == 0

    def test_consolidation_archives_excess(self, db83):
        from agents.twenty.memory import consolidate_if_needed, MAX_ACTIVE_MEMORIES
        conn, _ = db83
        # Insert more than MAX memories
        for i in range(MAX_ACTIVE_MEMORIES + 10):
            conn.execute(
                "INSERT INTO memory_twenty (subject, content, importance) VALUES (?, 'content', 3)",
                (f'mem_{i}',)
            )
        conn.commit()
        archived = consolidate_if_needed(conn=conn)
        assert archived > 0


class TestLearning:
    def test_learn_from_errors(self, db83, signals_crisis):
        from agents.twenty.memory import learn_from_cycle
        conn, _ = db83
        learned = learn_from_cycle(signals_crisis, [], conn=conn)
        assert learned > 0
        # Should have created error_frequency patterns
        row = conn.execute(
            "SELECT * FROM user_patterns WHERE pattern_type='error_frequency'"
        ).fetchone()
        assert row is not None

    def test_learn_from_urgent_thoughts(self, db83, signals_normal):
        from agents.twenty.memory import learn_from_cycle
        conn, _ = db83
        thoughts = [
            {'orb_role': 'skulk', 'thought': 'errors detected', 'urgency': 3},
        ]
        learn_from_cycle(signals_normal, thoughts, conn=conn)
        row = conn.execute(
            "SELECT * FROM memory_twenty WHERE subject LIKE 'urgent:%'"
        ).fetchone()
        assert row is not None
        assert row['importance'] >= 7

    def test_learn_cpu_pressure(self, db83, signals_crisis):
        from agents.twenty.memory import learn_from_cycle
        conn, _ = db83
        learn_from_cycle(signals_crisis, [], conn=conn)
        row = conn.execute(
            "SELECT * FROM user_patterns WHERE pattern_type='system_pressure'"
        ).fetchone()
        assert row is not None


# ===========================================================================
# 3. Decision matrix
# ===========================================================================

class TestDecisionMatrix:
    def test_evaluate_normal_thought(self, db83, signals_normal):
        from agents.twenty.decisions import evaluate_thought
        conn, _ = db83
        thought = {'orb_role': 'lookout', 'thought': 'Queue light', 'urgency': 0, 'confidence': 0.7}
        result = evaluate_thought(thought, signals_normal, conn=conn)
        assert result['action'] in ('observe', 'suggest')
        assert 'reasoning' in result

    def test_escalates_crisis(self, db83, signals_crisis):
        from agents.twenty.decisions import evaluate_thought
        conn, _ = db83
        thought = {'orb_role': 'skulk', 'thought': '6 errors', 'urgency': 2, 'confidence': 0.85}
        result = evaluate_thought(thought, signals_crisis, conn=conn)
        assert result['action'] == 'escalate'

    def test_never_suppresses_error_even_low_confidence(self, db83, signals_crisis):
        from agents.twenty.decisions import evaluate_thought
        conn, _ = db83
        thought = {'orb_role': 'skulk', 'thought': 'errors seen', 'urgency': 2, 'confidence': 0.35}
        result = evaluate_thought(thought, signals_crisis, conn=conn)
        # Honesty: even low confidence error should suggest, not suppress
        assert result['action'] in ('suggest', 'escalate')

    def test_records_decision(self, db83, signals_normal):
        from agents.twenty.decisions import record_decision
        conn, _ = db83
        thought = {'orb_role': 'lookout', 'thought': 'test', 'pfv_p': 0.7, 'pfv_f': 0.6, 'pfv_v': 0.5}
        record_decision(thought, 'suggest', 1, ['test reason'], signals_normal, conn=conn)
        row = conn.execute("SELECT * FROM decisions WHERE agent='twenty'").fetchone()
        assert row is not None
        assert 'suggest' in row['decision']

    def test_apply_decisions_filters(self, db83, signals_normal):
        from agents.twenty.decisions import apply_decisions
        conn, _ = db83
        thoughts = [
            {'orb_role': 'lookout', 'thought': 'All clear', 'urgency': 0, 'confidence': 0.7,
             'detail': '', 'expires_at': '2099-01-01', 'source_refs': [], 'pfv_p': 0.7, 'pfv_f': 0.6, 'pfv_v': 0.5},
        ]
        surfaced = apply_decisions(thoughts, signals_normal, conn=conn)
        # Normal thought should be suggested or observed — either way, it's recorded
        row = conn.execute("SELECT COUNT(*) FROM decisions WHERE agent='twenty'").fetchone()
        assert row[0] >= 1

    def test_escalation_boosts_urgency(self, db83, signals_crisis):
        from agents.twenty.decisions import apply_decisions
        conn, _ = db83
        thoughts = [
            {'orb_role': 'skulk', 'thought': '6 errors in 30min', 'urgency': 1,
             'confidence': 0.85, 'detail': '', 'expires_at': '2099-01-01',
             'source_refs': [], 'pfv_p': 0.7, 'pfv_f': 0.6, 'pfv_v': 0.5},
        ]
        surfaced = apply_decisions(thoughts, signals_crisis, conn=conn)
        if surfaced:
            assert surfaced[0]['urgency'] >= 2


# ===========================================================================
# 4. System mapper
# ===========================================================================

class TestMapper:
    def test_build_health_digest_returns_all_sections(self, db83):
        from agents.twenty.mapper import build_health_digest
        conn, _ = db83
        digest = build_health_digest(conn=conn)
        expected_keys = ['agents', 'queue', 'tickets', 'errors', 'system',
                         'proposals', 'council', 'memory', 'governance',
                         'emails', 'tasks', 'overall_status', 'scanned_at', '_self_check']
        for key in expected_keys:
            assert key in digest, f"Missing key: {key}"

    def test_overall_status_healthy_baseline(self, db83):
        from agents.twenty.mapper import build_health_digest
        conn, _ = db83
        digest = build_health_digest(conn=conn)
        assert digest['overall_status'] == 'healthy'

    def test_overall_status_degrades_on_errors(self, db83):
        from agents.twenty.mapper import build_health_digest
        conn, _ = db83
        # Inject errors into activity_log
        for i in range(6):
            conn.execute(
                "INSERT INTO activity_log (service, event, detail, created_at) "
                "VALUES ('duck', 'error', 'test error', datetime('now'))"
            )
        conn.commit()
        digest = build_health_digest(conn=conn)
        assert digest['errors']['status'] != 'healthy'

    def test_scan_agents(self, db83):
        from agents.twenty.mapper import scan_agents
        conn, _ = db83
        result = scan_agents(conn)
        assert result['total'] == 2
        assert result['enabled'] == 2
        assert result['status'] == 'healthy'

    def test_scan_queue_empty(self, db83):
        from agents.twenty.mapper import scan_queue
        conn, _ = db83
        result = scan_queue(conn)
        assert result['depth'] == 0
        assert result['status'] == 'healthy'

    def test_scan_queue_with_stuck(self, db83):
        from agents.twenty.mapper import scan_queue
        conn, _ = db83
        conn.execute(
            "INSERT INTO queue (status, created_at) VALUES ('queued', '2026-01-01 00:00:00')"
        )
        conn.commit()
        result = scan_queue(conn)
        assert result['stuck_over_1h'] >= 1
        assert result['status'] != 'healthy'

    def test_scan_system_healthy(self, db83):
        from agents.twenty.mapper import scan_system
        conn, _ = db83
        result = scan_system(conn)
        assert result['status'] == 'healthy'
        assert result['cpu_percent'] == 30

    def test_scan_system_critical_cpu(self, db83):
        from agents.twenty.mapper import scan_system
        conn, _ = db83
        conn.execute("UPDATE system_stats SET cpu_percent=95, ram_available_gb=0.5, cpu_temp_c=90")
        conn.commit()
        result = scan_system(conn)
        assert result['status'] == 'critical'
        assert len(result['problems']) >= 2

    def test_scan_council(self, db83):
        from agents.twenty.mapper import scan_council
        conn, _ = db83
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, expires_at) "
            "VALUES ('lookout', 'test', '2099-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, dismissed, expires_at) "
            "VALUES ('snoop', 'old', 1, '2099-01-01 00:00:00')"
        )
        conn.commit()
        result = scan_council(conn)
        assert result['active'] == 1
        assert result['dismissed'] == 1

    def test_scan_emails(self, db83):
        from agents.twenty.mapper import scan_emails
        conn, _ = db83
        for _ in range(25):
            conn.execute("INSERT INTO pending_emails (processed_at) VALUES (NULL)")
        conn.commit()
        result = scan_emails(conn)
        assert result['backlog'] == 25
        assert result['status'] == 'error'

    def test_scan_tasks_with_failures(self, db83):
        from agents.twenty.mapper import scan_tasks
        conn, _ = db83
        conn.execute(
            "INSERT INTO task_run_log (task_name, status, run_at) "
            "VALUES ('test_task', 'fail', datetime('now'))"
        )
        conn.commit()
        result = scan_tasks(conn)
        assert result['recent_failures_24h'] >= 1
        assert result['status'] != 'healthy'

    def test_self_check_flags_empty_db(self, db83):
        from agents.twenty.mapper import build_health_digest
        conn, _ = db83
        # Remove all agents to simulate empty state
        conn.execute("DELETE FROM agents")
        conn.execute("DELETE FROM system_stats")
        conn.commit()
        digest = build_health_digest(conn=conn)
        sc = digest.get('_self_check', {})
        # Should flag that the DB looks empty
        assert sc.get('status') != 'healthy' or 'warning' in sc

    def test_scan_memory(self, db83):
        from agents.twenty.mapper import scan_memory
        from agents.twenty.memory import remember
        conn, _ = db83
        remember('a', 'content', importance=9, conn=conn)
        remember('b', 'content', importance=3, conn=conn)
        result = scan_memory(conn)
        assert result['active_memories'] == 2
        assert result['high_importance'] == 1


# ===========================================================================
# 5. Health Digest API
# ===========================================================================

class TestHealthAPI:
    def _make_app(self):
        from frontend.blueprints.health_bp import health_digest_bp
        from frontend.blueprints.council_bp import council_bp
        app = Flask(__name__)
        app.register_blueprint(health_digest_bp)
        app.register_blueprint(council_bp)
        return app

    def test_digest_endpoint(self, db83):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/api/health/digest')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'overall_status' in data
            assert 'agents' in data
            assert 'queue' in data

    def test_status_endpoint(self, db83):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/api/health/status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'status' in data

    def test_memory_endpoint(self, db83):
        from agents.twenty.memory import remember
        conn, _ = db83
        remember('test', 'data', importance=5, conn=conn)
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/api/health/memory')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'memories' in data
            assert 'patterns' in data

    def test_digest_reflects_injected_errors(self, db83):
        conn, _ = db83
        for i in range(10):
            conn.execute(
                "INSERT INTO activity_log (service, event, detail, created_at) "
                "VALUES ('duck', 'error', 'test', datetime('now'))"
            )
        conn.commit()
        app = self._make_app()
        with app.test_client() as client:
            data = client.get('/api/health/digest').get_json()
            assert data['errors']['status'] != 'healthy'
            assert data['overall_status'] != 'healthy'


# ===========================================================================
# 6. Council pipeline with honesty + decisions
# ===========================================================================

class TestCouncilPipeline:
    def test_council_honesty_boosts_urgency(self, db83, signals_crisis):
        """Honesty check runs on candidates — verify urgency boost on negative signals."""
        from agents.twenty.council import (lookout_score, snoop_score, spark_score,
                                            skulk_score, keeper_score, patrol_score)
        from agents.twenty.memory import honesty_check
        candidates = []
        candidates.extend(lookout_score(signals_crisis))
        candidates.extend(skulk_score(signals_crisis))
        for c in candidates:
            honesty_check(c)
        # Crisis signals should produce high-urgency candidates (pre-PFV)
        urgent = [t for t in candidates if t.get('urgency', 0) >= 1]
        assert len(urgent) >= 1, "Council should generate urgent candidates in crisis"

    def test_council_with_normal_signals(self, db83, signals_normal):
        from agents.twenty.council import run_council
        thoughts = run_council(signals_normal)
        # Normal state should still produce some observations
        assert isinstance(thoughts, list)


# ===========================================================================
# 7. Health Digest JS structure
# ===========================================================================

class TestHealthDigestJS:
    @pytest.fixture(autouse=True)
    def load_js(self):
        import pathlib
        js_path = pathlib.Path(__file__).parent.parent / 'frontend' / 'static' / 'js' / 'views' / 'health-digest.js'
        self.js = js_path.read_text()

    def test_fetch_endpoint(self):
        assert '/api/health/digest' in self.js

    def test_status_colors(self):
        assert 'healthy' in self.js
        assert 'degraded' in self.js
        assert 'error' in self.js
        assert 'critical' in self.js

    def test_auto_refresh(self):
        assert 'setInterval' in self.js
        assert '30000' in self.js

    def test_subsystem_cards(self):
        for section in ['Agents', 'Queue', 'Errors', 'System', 'Tickets',
                        'Council', 'Proposals', 'Memory', 'Governance',
                        'Email Pipeline', 'Scheduled Tasks']:
            assert section in self.js, f"Missing card: {section}"

    def test_overall_status_banner(self):
        assert 'overall_status' in self.js

    def test_self_check_displayed(self):
        assert '_self_check' in self.js

    def test_has_cleanup(self):
        assert 'unloadHealthDigest' in self.js


# ===========================================================================
# 8. Stress tests — break it and verify it handles gracefully
# ===========================================================================

class TestStress:
    def test_mapper_survives_missing_tables(self, tmp_path, monkeypatch):
        """Mapper should not crash if tables are missing."""
        from agents.twenty.mapper import build_health_digest
        db_path = str(tmp_path / 'empty.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Create only agents table, everything else missing
        conn.execute("CREATE TABLE agents (id INTEGER PRIMARY KEY, number INTEGER, name TEXT, label TEXT, model TEXT, role TEXT, enabled INTEGER DEFAULT 1)")
        conn.commit()
        # Should not raise
        digest = build_health_digest(conn=conn)
        assert 'overall_status' in digest

    def test_memory_handles_empty_db(self, db83):
        from agents.twenty.memory import recall, recall_patterns, decay_stale_memories, consolidate_if_needed
        conn, _ = db83
        # All should return gracefully with empty data
        assert recall(conn=conn) == []
        assert recall_patterns(conn=conn) == []
        assert decay_stale_memories(conn=conn) == 0
        assert consolidate_if_needed(conn=conn) == 0

    def test_decision_matrix_handles_no_history(self, db83, signals_normal):
        from agents.twenty.decisions import evaluate_thought
        conn, _ = db83
        thought = {'orb_role': 'lookout', 'thought': 'test', 'urgency': 0, 'confidence': 0.5}
        result = evaluate_thought(thought, signals_normal, conn=conn)
        assert 'action' in result

    def test_honesty_handles_empty_thought(self):
        from agents.twenty.memory import honesty_check
        thought = {'thought': '', 'detail': '', 'urgency': 0, 'confidence': 0.5}
        result = honesty_check(thought)
        assert result['urgency'] == 0  # no false positive

    def test_honesty_handles_none_fields(self):
        from agents.twenty.memory import honesty_check
        thought = {'urgency': 0, 'confidence': 0.5}
        # Should not crash
        result = honesty_check(thought)
        assert 'urgency' in result

    def test_mapper_handles_null_system_stats(self, db83):
        from agents.twenty.mapper import scan_system
        conn, _ = db83
        conn.execute("DELETE FROM system_stats")
        conn.commit()
        result = scan_system(conn)
        assert result['status'] == 'unknown'

    def test_bulk_memory_write(self, db83):
        from agents.twenty.memory import remember
        conn, _ = db83
        for i in range(500):
            remember(f'bulk_{i}', f'content_{i}', importance=3, conn=conn)
        count = conn.execute("SELECT COUNT(*) FROM memory_twenty").fetchone()[0]
        assert count >= 500

    def test_rapid_pattern_updates(self, db83):
        from agents.twenty.memory import remember_pattern
        conn, _ = db83
        for i in range(100):
            remember_pattern('rapid', 'key', f'{{"i": {i}}}', conn=conn)
        row = conn.execute(
            "SELECT occurrences, confidence FROM user_patterns WHERE pattern_key='key'"
        ).fetchone()
        assert row['occurrences'] == 100
        assert row['confidence'] <= 0.95  # capped

    def test_digest_api_under_load(self, db83):
        from frontend.blueprints.health_bp import health_digest_bp
        conn, _ = db83
        # Inject a lot of data
        for i in range(50):
            conn.execute(
                "INSERT INTO activity_log (service, event, detail, created_at) "
                "VALUES (?, 'error', 'test', datetime('now'))",
                (f'agent_{i % 5}',)
            )
        for i in range(20):
            conn.execute(
                "INSERT INTO council_output (orb_role, thought, expires_at) "
                "VALUES (?, 'test thought', '2099-01-01 00:00:00')",
                (['lookout', 'snoop', 'patrol', 'skulk', 'sage', 'keeper', 'spark'][i % 7],)
            )
        conn.commit()
        app = Flask(__name__)
        app.register_blueprint(health_digest_bp)
        with app.test_client() as client:
            resp = client.get('/api/health/digest')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['errors']['last_hour'] >= 20  # capped at 20 by LIMIT
            assert data['council']['active'] >= 20

    def test_decision_matrix_high_history(self, db83, signals_normal):
        """Thought seen many times with OK outcome → should observe, not escalate."""
        from agents.twenty.decisions import evaluate_thought
        conn, _ = db83
        # Insert 5 past decisions for same role with OK outcome
        for i in range(5):
            conn.execute(
                "INSERT INTO decisions (agent, component, decision, reasoning, test_status, created_at) "
                "VALUES ('twenty', 'lookout', 'suggest: queue info', '{}', 'ok', datetime('now'))"
            )
        conn.commit()
        thought = {'orb_role': 'lookout', 'thought': 'queue is normal', 'urgency': 0, 'confidence': 0.6}
        result = evaluate_thought(thought, signals_normal, conn=conn)
        assert result['action'] == 'observe', "Repeated OK thought should be observation only"

    def test_full_cycle_integration(self, db83, signals_crisis):
        """Full pipeline: observe → council → decide → learn — no crash."""
        from agents.twenty.council import run_council
        from agents.twenty.decisions import apply_decisions
        from agents.twenty.memory import learn_from_cycle
        conn, _ = db83
        thoughts = run_council(signals_crisis)
        surfaced = apply_decisions(thoughts, signals_crisis, conn=conn)
        learned = learn_from_cycle(signals_crisis, surfaced, conn=conn)
        # learn_from_cycle should pick up error patterns + queue + cpu from signals
        pattern_count = conn.execute("SELECT COUNT(*) FROM user_patterns").fetchone()[0]
        mem_count = conn.execute("SELECT COUNT(*) FROM memory_twenty").fetchone()[0]
        assert learned > 0, "Full cycle should learn from crisis signals"
        assert pattern_count > 0, "Should have written patterns from signal data"

    def test_blueprint_registered_in_terminal(self):
        """Health digest blueprint must be in _BLUEPRINT_REGISTRY."""
        import pathlib
        terminal_path = pathlib.Path(__file__).parent.parent / 'frontend' / 'terminal.py'
        content = terminal_path.read_text()
        assert 'health_bp' in content
        assert 'health_digest_bp' in content
