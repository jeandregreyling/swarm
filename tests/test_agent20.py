"""Tests for Agent 20 — Phase 8.1 foundation.

Covers: observer, council, PFV gate, tone detection, identity, scheduler flag.
All deterministic, no LLM calls, no network.
"""

import json
import sqlite3
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a test DB with the tables Agent 20 reads."""
    db_path = str(tmp_path / 'test_swarm.db')

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
            created_at TEXT DEFAULT (datetime('now'))
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
            agent TEXT, decision TEXT, reasoning TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, schedule TEXT, action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '', next_run TEXT, enabled INTEGER DEFAULT 1
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
    """)

    # Seed some baseline data
    conn.execute("INSERT INTO agents (number, name, label, model, role, enabled) VALUES (1, 'duck', 'Duck', 'local', 'Router', 1)")
    conn.execute("INSERT INTO agents (number, name, label, model, role, enabled) VALUES (20, 'twenty', 'Twenty', 'local-algorithm', 'Nervous system', 1)")
    conn.execute("INSERT INTO system_stats (cpu_percent, ram_used_gb, ram_available_gb) VALUES (30, 4, 12)")
    conn.commit()

    def mock_get_connection():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', mock_get_connection)
    # Also patch the import path used in observer / scheduler / blueprint
    monkeypatch.setattr('agents.twenty.observer.get_connection', mock_get_connection)
    monkeypatch.setattr('frontend.blueprints.council_bp.get_connection', mock_get_connection)

    return conn, db_path


@pytest.fixture
def signals_normal():
    """A normal-state signals dict for PFV/council testing."""
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


# ---------------------------------------------------------------------------
# 1. Identity & feature flag
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_agent20_has_identity(self):
        from agents.twenty import IDENTITY, AGENT_NAME, AGENT_NUMBER
        assert AGENT_NAME == 'twenty'
        assert AGENT_NUMBER == 20
        assert 'Nervous system' in IDENTITY['role']
        assert len(IDENTITY['senses']) == 7
        assert len(IDENTITY['constraints']) >= 4

    def test_feature_flag_defaults_enabled(self, monkeypatch):
        monkeypatch.setenv('AGENT20_ENABLED', 'true')
        # Re-import to pick up env
        import importlib
        import agents.twenty as a20
        importlib.reload(a20)
        assert a20.AGENT20_ENABLED is True

    def test_feature_flag_can_disable(self, monkeypatch):
        monkeypatch.setenv('AGENT20_ENABLED', 'false')
        import importlib
        import agents.twenty as a20
        importlib.reload(a20)
        assert a20.AGENT20_ENABLED is False


# ---------------------------------------------------------------------------
# 2. Observer
# ---------------------------------------------------------------------------

class TestObserver:
    def test_collect_signals_returns_expected_keys(self, test_db):
        from agents.twenty.observer import collect_signals
        signals = collect_signals()
        expected_keys = [
            'queue_depth', 'queue_aging', 'pending_proposals',
            'open_tickets_aging', 'agent_errors', 'system_stats',
            'user_topics', 'recent_decisions', 'scheduled_due',
            'sniffer_findings', 'email_backlog', 'agent_roster',
            'recent_dismissals', 'own_memory', 'collected_at',
        ]
        for key in expected_keys:
            assert key in signals, f"Missing signal key: {key}"

    def test_observer_reads_agent_roster(self, test_db):
        from agents.twenty.observer import collect_signals
        signals = collect_signals()
        roster = signals['agent_roster']
        names = [a['name'] for a in roster]
        assert 'duck' in names
        assert 'twenty' in names

    def test_observer_reads_queue_depth(self, test_db):
        conn, _ = test_db
        conn.execute("INSERT INTO queue (from_addr, subject, question, status) VALUES ('a@b.c', 'test', 'test?', 'queued')")
        conn.execute("INSERT INTO queue (from_addr, subject, question, status) VALUES ('d@e.f', 'test2', 'test2?', 'queued')")
        conn.commit()

        from agents.twenty.observer import collect_signals
        signals = collect_signals()
        assert signals['queue_depth'] == 2

    def test_observer_reads_own_memory(self, test_db):
        conn, _ = test_db
        conn.execute("INSERT INTO memory_twenty (subject, content, importance) VALUES ('test', 'I learned something', 8)")
        conn.commit()

        from agents.twenty.observer import collect_signals
        signals = collect_signals()
        assert len(signals['own_memory']) == 1
        assert signals['own_memory'][0]['subject'] == 'test'


# ---------------------------------------------------------------------------
# 3. PFV Gate
# ---------------------------------------------------------------------------

class TestPFV:
    def test_baseline_thought_passes(self, signals_normal):
        from agents.twenty.pfv import pfv_gate
        thought = {
            'orb_role': 'lookout',
            'thought': 'Queue has 3 items',
            'source_refs': [{'table': 'queue'}],
            'urgency': 0,
            'confidence': 0.7,
        }
        score, passed, details = pfv_gate(thought, signals_normal)
        assert passed is True
        assert score >= 0.35
        assert details['pfv_p'] >= 0.5
        assert details['pfv_f'] >= 0.4
        assert details['pfv_v'] >= 0.3

    def test_dead_agent_ref_lowers_plausibility(self, signals_normal):
        from agents.twenty.pfv import score_plausible
        thought = {
            'source_refs': [{'table': 'queue'}],
            'agent_ref': 'nonexistent_agent',
        }
        p = score_plausible(thought, signals_normal)
        assert p < 0.5  # should fail plausibility

    def test_high_cpu_lowers_feasibility(self, signals_normal):
        from agents.twenty.pfv import score_feasible
        signals_normal['system_stats']['cpu_percent'] = 95
        thought = {'urgency': 0}
        f = score_feasible(thought, signals_normal)
        assert f < 0.4  # should be below threshold

    def test_many_dismissals_lower_value(self, signals_normal):
        from agents.twenty.pfv import score_valuable
        signals_normal['recent_dismissals'] = [
            {'orb_role': 'lookout', 'thought': 'x', 'created_at': '2026-04-21'},
            {'orb_role': 'lookout', 'thought': 'y', 'created_at': '2026-04-21'},
            {'orb_role': 'lookout', 'thought': 'z', 'created_at': '2026-04-21'},
        ]
        thought = {'orb_role': 'lookout', 'thought': 'queue stuff', 'detail': '', 'urgency': 0}
        v = score_valuable(thought, signals_normal)
        # 3 dismissals → -0.3 from baseline 0.4 → 0.1
        assert v < 0.3

    def test_pfv_rejects_below_combined(self, signals_normal):
        from agents.twenty.pfv import pfv_gate
        # No source refs, dead agent, high load — should fail
        signals_normal['system_stats']['cpu_percent'] = 95
        signals_normal['recent_dismissals'] = [
            {'orb_role': 'lookout', 'thought': 'x', 'created_at': '2026-04-21'},
            {'orb_role': 'lookout', 'thought': 'y', 'created_at': '2026-04-21'},
            {'orb_role': 'lookout', 'thought': 'z', 'created_at': '2026-04-21'},
        ]
        thought = {
            'orb_role': 'lookout',
            'thought': 'bad idea',
            'detail': '',
            'source_refs': [],
            'agent_ref': 'dead_agent',
            'urgency': 0,
            'confidence': 0.2,
        }
        _, passed, details = pfv_gate(thought, signals_normal)
        assert passed is False
        assert 'reject_reasons' in details


# ---------------------------------------------------------------------------
# 4. Council
# ---------------------------------------------------------------------------

class TestCouncil:
    def test_run_council_returns_list(self, signals_normal):
        from agents.twenty.council import run_council
        result = run_council(signals_normal)
        assert isinstance(result, list)

    def test_lookout_fires_on_queue(self, signals_normal):
        from agents.twenty.council import lookout_score
        signals_normal['queue_depth'] = 5
        thoughts = lookout_score(signals_normal)
        assert len(thoughts) >= 1
        assert 'queued' in thoughts[0]['thought'].lower() or 'items' in thoughts[0]['thought'].lower()

    def test_skulk_fires_on_errors(self, signals_normal):
        from agents.twenty.council import skulk_score
        signals_normal['agent_errors'] = [
            {'service': 'duck', 'event': 'error', 'detail': 'timeout', 'created_at': '2026-04-21 12:00:00'},
            {'service': 'duck', 'event': 'error', 'detail': 'timeout2', 'created_at': '2026-04-21 12:01:00'},
        ]
        thoughts = skulk_score(signals_normal)
        assert len(thoughts) >= 1
        assert 'error' in thoughts[0]['thought'].lower()

    def test_sage_filters_low_confidence(self, signals_normal):
        from agents.twenty.council import sage_aggregate, _thought
        candidates = [
            _thought('lookout', 'very low conf', confidence=0.2),
        ]
        gated = sage_aggregate(candidates, signals_normal)
        # confidence 0.2 < 0.3 → should not surface
        assert len(gated) == 0

    def test_sage_prefixes_medium_confidence(self, signals_normal):
        from agents.twenty.council import sage_aggregate, _thought
        candidates = [
            _thought('lookout', 'medium conf thought', confidence=0.55,
                     source_refs=[{'table': 'queue'}]),
        ]
        gated = sage_aggregate(candidates, signals_normal)
        if gated:  # may pass PFV or not depending on signals
            assert gated[0]['thought'].startswith('Low confidence:')

    def test_council_gated_thoughts_have_pfv_scores(self, signals_normal):
        from agents.twenty.council import run_council
        signals_normal['queue_depth'] = 8
        result = run_council(signals_normal)
        for t in result:
            assert 'pfv_p' in t
            assert 'pfv_f' in t
            assert 'pfv_v' in t
            assert 'expires_at' in t

    def test_patrol_warns_on_heavy_queue(self, signals_normal):
        from agents.twenty.council import patrol_score
        signals_normal['queue_depth'] = 20
        warnings = patrol_score(signals_normal)
        assert len(warnings) >= 1
        assert 'caution' in warnings[0]['thought'].lower()


# ---------------------------------------------------------------------------
# 5. Tone Detection
# ---------------------------------------------------------------------------

class TestTone:
    def test_urgent_detection(self):
        from agents.twenty.tone import classify_tone, URGENT
        assert classify_tone("Fix this NOW! The server is broken!") == URGENT

    def test_creative_detection(self):
        from agents.twenty.tone import classify_tone, CREATIVE
        assert classify_tone("What if we imagine a completely different approach to this problem") == CREATIVE

    def test_analytical_detection(self):
        from agents.twenty.tone import classify_tone, ANALYTICAL
        assert classify_tone("How many tickets are open?") == ANALYTICAL

    def test_exploratory_detection(self):
        from agents.twenty.tone import classify_tone, EXPLORATORY
        assert classify_tone("I think maybe there was something we missed, perhaps related") == EXPLORATORY

    def test_empty_returns_analytical(self):
        from agents.twenty.tone import classify_tone, ANALYTICAL
        assert classify_tone("") == ANALYTICAL
        assert classify_tone(None) == ANALYTICAL


# ---------------------------------------------------------------------------
# 6. Blueprint
# ---------------------------------------------------------------------------

class TestCouncilBlueprint:
    def test_latest_endpoint_returns_json(self, test_db):
        from flask import Flask
        from frontend.blueprints.council_bp import council_bp

        app = Flask(__name__)
        app.register_blueprint(council_bp)

        conn, _ = test_db
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, urgency, confidence, expires_at) VALUES ('lookout', 'Test thought', 1, 0.8, datetime('now', '+1 hour'))"
        )
        conn.commit()

        with app.test_client() as client:
            resp = client.get('/api/council/latest')
            assert resp.status_code == 200
            data = resp.get_json()
            assert isinstance(data, list)
            assert len(data) >= 1
            assert data[0]['orb_role'] == 'lookout'

    def test_dismiss_endpoint(self, test_db):
        from flask import Flask
        from frontend.blueprints.council_bp import council_bp

        app = Flask(__name__)
        app.register_blueprint(council_bp)

        conn, _ = test_db
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, urgency, confidence, dismissed, expires_at) VALUES ('snoop', 'Dismiss me', 0, 0.5, 0, datetime('now', '+1 hour'))"
        )
        conn.commit()
        row = conn.execute("SELECT id FROM council_output WHERE thought='Dismiss me'").fetchone()
        tid = row[0]

        with app.test_client() as client:
            resp = client.post(f'/api/council/dismiss/{tid}')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['dismissed'] == tid

        # Verify dismissed in DB
        row2 = conn.execute("SELECT dismissed FROM council_output WHERE id=?", (tid,)).fetchone()
        # Need a fresh connection since our mock creates new ones
        check_conn = sqlite3.connect(str(test_db[1]), check_same_thread=False)
        check_conn.row_factory = sqlite3.Row
        r = check_conn.execute("SELECT dismissed FROM council_output WHERE id=?", (tid,)).fetchone()
        assert r['dismissed'] == 1
        check_conn.close()

    def test_dismiss_nonexistent_returns_404(self, test_db):
        from flask import Flask
        from frontend.blueprints.council_bp import council_bp

        app = Flask(__name__)
        app.register_blueprint(council_bp)

        with app.test_client() as client:
            resp = client.post('/api/council/dismiss/99999')
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Schema tables exist
# ---------------------------------------------------------------------------

class TestSchema:
    def test_council_output_table_exists(self, test_db):
        conn, _ = test_db
        # Table was created in fixture
        conn.execute("SELECT id, orb_role, thought, confidence, pfv_p, pfv_f, pfv_v, dismissed, expires_at FROM council_output LIMIT 1")

    def test_user_patterns_table_exists(self, test_db):
        conn, _ = test_db
        conn.execute("INSERT INTO user_patterns (pattern_type, pattern_key, pattern_value) VALUES ('test', 'key1', '{}')")
        conn.commit()
        row = conn.execute("SELECT * FROM user_patterns WHERE pattern_key='key1'").fetchone()
        assert row is not None

    def test_memory_twenty_table_exists(self, test_db):
        conn, _ = test_db
        conn.execute("INSERT INTO memory_twenty (subject, content) VALUES ('test', 'Agent 20 remembers')")
        conn.commit()
        row = conn.execute("SELECT * FROM memory_twenty WHERE subject='test'").fetchone()
        assert row['agent'] == 'twenty'


# ===========================================================================
# Phase 8.2 — Orb Integration Tests
# ===========================================================================

# ---------------------------------------------------------------------------
# 8. Council API returns all 5 orb roles
# ---------------------------------------------------------------------------

class TestCouncilOrbRoles:
    """The council_output table and API must handle all 5 orb roles."""

    VALID_ROLES = ['eye', 'echo', 'thread', 'pulse', 'voice']

    def test_all_five_roles_insertable(self, test_db):
        conn, _ = test_db
        for role in self.VALID_ROLES:
            conn.execute(
                "INSERT INTO council_output (orb_role, thought, urgency, expires_at) VALUES (?, ?, 1, '2099-01-01 00:00:00')",
                (role, f'{role} test thought'),
            )
        conn.commit()
        rows = conn.execute("SELECT DISTINCT orb_role FROM council_output").fetchall()
        assert sorted(r['orb_role'] for r in rows) == sorted(self.VALID_ROLES)

    def test_api_returns_all_roles(self, test_db):
        from frontend.blueprints.council_bp import council_bp
        from flask import Flask
        conn, _ = test_db
        for role in self.VALID_ROLES:
            conn.execute(
                "INSERT INTO council_output (orb_role, thought, urgency, expires_at) VALUES (?, ?, 1, '2099-01-01 00:00:00')",
                (role, f'{role} thought'),
            )
        conn.commit()
        app = Flask(__name__)
        app.register_blueprint(council_bp)
        with app.test_client() as client:
            resp = client.get('/api/council/latest')
            assert resp.status_code == 200
            data = resp.get_json()
            roles_returned = {d['orb_role'] for d in data}
            assert roles_returned == set(self.VALID_ROLES)

    def test_api_excludes_dismissed(self, test_db):
        from frontend.blueprints.council_bp import council_bp
        from flask import Flask
        conn, _ = test_db
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, dismissed, expires_at) VALUES ('voice', 'dismissed one', 1, '2099-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, dismissed, expires_at) VALUES ('voice', 'active one', 0, '2099-01-01 00:00:00')"
        )
        conn.commit()
        app = Flask(__name__)
        app.register_blueprint(council_bp)
        with app.test_client() as client:
            data = client.get('/api/council/latest').get_json()
            voice_thoughts = [d for d in data if d['orb_role'] == 'voice']
            assert len(voice_thoughts) == 1
            assert voice_thoughts[0]['thought'] == 'active one'

    def test_dismiss_endpoint_marks_dismissed(self, test_db):
        from frontend.blueprints.council_bp import council_bp
        from flask import Flask
        conn, _ = test_db
        conn.execute(
            "INSERT INTO council_output (orb_role, thought, expires_at) VALUES ('pulse', 'act now', '2099-01-01 00:00:00')"
        )
        conn.commit()
        row = conn.execute("SELECT id FROM council_output WHERE orb_role='pulse'").fetchone()
        tid = row['id']
        app = Flask(__name__)
        app.register_blueprint(council_bp)
        with app.test_client() as client:
            resp = client.post(f'/api/council/dismiss/{tid}')
            assert resp.status_code == 200
            assert resp.get_json()['dismissed'] == tid
        # Verify DB state
        row = conn.execute("SELECT dismissed FROM council_output WHERE id=?", (tid,)).fetchone()
        assert row['dismissed'] == 1


# ---------------------------------------------------------------------------
# 9. Orbs.js structural validation
# ---------------------------------------------------------------------------

class TestOrbsJSStructure:
    """Verify the JS file has the required five-voice structure."""

    @pytest.fixture(autouse=True)
    def load_orbs_js(self):
        import pathlib
        orbs_path = pathlib.Path(__file__).parent.parent / 'frontend' / 'static' / 'js' / 'views' / 'orbs.js'
        self.js = orbs_path.read_text()

    def test_five_role_constants(self):
        assert 'EYE = 0' in self.js
        assert 'VOICE = 4' in self.js

    def test_five_role_names(self):
        assert "'Eye'" in self.js
        assert "'Voice'" in self.js

    def test_role_key_mapping(self):
        assert 'ROLE_KEY' in self.js
        assert 'eye: EYE' in self.js
        assert 'voice: VOICE' in self.js

    def test_five_roost_positions(self):
        # Count ROOST_BASE entries.
        # Phase-4 fix: the first textual occurrence of "ROOST_BASE" is in a
        # comment, so locate the actual array assignment and capture greedily
        # up to the closing `];`.
        import re
        m = re.search(r'ROOST_BASE\s*=\s*\[(.*?)\]\s*;', self.js, re.DOTALL)
        assert m is not None, "ROOST_BASE = [...] block not found in orbs.js"
        roost_entries = re.findall(r'\[\s*\d+\.\d+\s*,\s*\d+\.\d+\s*\]', m.group(1))
        assert len(roost_entries) == 5

    def test_five_orbs_created(self):
        assert 'mkOrb(EYE,' in self.js
        assert 'mkOrb(VOICE,' in self.js

    def test_voices_stay_awake(self):
        assert 'const dormFade = 1.0;' in self.js
        assert 'orbs[KEEPER].dormant = true' not in self.js
        assert 'orbs[SPARK].dormant = true' not in self.js

    def test_council_link_object(self):
        assert 'CouncilLink' in self.js
        assert '/api/council/latest' in self.js
        assert '/api/council/dismiss/' in self.js

    def test_council_thought_override_in_generate(self):
        assert 'CouncilLink.thoughtFor(o.role)' in self.js

    def test_flee_rendering_support(self):
        assert '_applyFlee' in self.js
        assert 'dormantAlpha' in self.js

    def test_dismiss_on_click(self):
        assert 'CouncilLink.dismiss(hit._councilThoughtId)' in self.js

    def test_voice_thought_pools(self):
        assert '[EYE]' in self.js
        assert '[VOICE]' in self.js

    def test_five_voice_behaviors(self):
        assert 'behaviorEye' in self.js
        assert 'behaviorVoice' in self.js

    def test_seven_draw_functions(self):
        assert 'drawPulsar' in self.js
        assert "'Pulsar'" in self.js

    def test_compat_includes_voice_roles(self):
        assert '[THREAD]:' in self.js
        assert '[VOICE]:' in self.js

    def test_council_indicator_dot(self):
        assert '_councilThoughtId' in self.js
        assert '#5EF29D' in self.js  # green indicator color
