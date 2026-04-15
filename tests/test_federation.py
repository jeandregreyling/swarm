"""
tests/test_federation.py — Phase D Federation & Config tests
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - D.1: Cross-node proposal sync endpoint
  - D.2: Federated skill registry (CRUD + advertisement endpoint)
  - D.3: Bus event propagation endpoint
  - D.4: Config validator + node_config CRUD
"""

import json
import os
import sqlite3
import sys
import pytest

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Isolated DB with all tables needed for D-phase tests."""
    db_path = str(tmp_path / 'test_d.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS swarm_nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            api_key_hash TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'contributor',
            agents_json TEXT NOT NULL DEFAULT '[]',
            capabilities TEXT NOT NULL DEFAULT '[]',
            registered_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS work_proposals (
            proposal_id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            agent TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            source_conv_id TEXT DEFAULT '',
            source_node TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
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
        CREATE TABLE IF NOT EXISTS node_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            trust_level INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            available INTEGER DEFAULT 1,
            last_seen TEXT DEFAULT (datetime('now')),
            UNIQUE(node_id, skill_name)
        );
        CREATE INDEX IF NOT EXISTS idx_node_skills_name ON node_skills(skill_name);
        CREATE TABLE IF NOT EXISTS node_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            node_id TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_bus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            source_service TEXT NOT NULL DEFAULT 'local',
            created_at TEXT DEFAULT (datetime('now')),
            consumed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_swarm_bus_topic
            ON swarm_bus (topic, created_at);
        CREATE INDEX IF NOT EXISTS idx_swarm_bus_unconsumed
            ON swarm_bus (consumed_at) WHERE consumed_at IS NULL;
    """)

    # Seed agents
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) "
        "VALUES (1, 'gemma', 'Gemma3', 'gemma3:latest', 1)"
    )
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) "
        "VALUES (2, 'llama', 'LlaMA', 'llama3.2:latest', 1)"
    )
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    monkeypatch.setattr('utils.db.nodes.get_connection', _get_conn)
    # Patch node_skills module
    monkeypatch.setattr('utils.db.node_skills.get_connection', _get_conn)

    yield conn
    conn.close()


@pytest.fixture
def auth_node(db_conn):
    """Register a test node and return its (node_id, api_key) for auth headers."""
    from utils.db.nodes import register_node
    nid = register_node('test-remote', 'http://10.0.0.2:5050', 'testkey999',
                        role='contributor', conn=db_conn)
    db_conn.commit()
    return nid, 'testkey999'


@pytest.fixture
def app(db_conn, monkeypatch):
    """Minimal Flask test app with node blueprint."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    from frontend.blueprints.node import node_bp
    app.register_blueprint(node_bp)
    return app


def _auth_headers(node_id, api_key):
    return {'X-Node-ID': node_id, 'X-Node-API-Key': api_key}


# ══════════════════════════════════════════════════════════════════════════════
# D.1 — Cross-Node Proposal Sync
# ══════════════════════════════════════════════════════════════════════════════

class TestProposalSync:
    def test_sync_proposals_insert(self, app, db_conn, auth_node):
        """New proposals from remote node are inserted."""
        nid, key = auth_node
        payload = {
            'source_node': 'remote-alpha',
            'proposals': [
                {'proposal_id': 'RP1', 'title': 'Remote task A',
                 'agent': 'gemma', 'status': 'pending',
                 'created_at': '2026-01-01 00:00:00',
                 'updated_at': '2026-01-01 00:00:00'},
                {'proposal_id': 'RP2', 'title': 'Remote task B',
                 'agent': 'llama', 'status': 'in_progress',
                 'created_at': '2026-01-02 00:00:00',
                 'updated_at': '2026-01-02 00:00:00'},
            ],
        }
        with app.test_client() as c:
            resp = c.post('/api/node/sync/proposals',
                          json=payload,
                          headers=_auth_headers(nid, key))
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['synced'] == 2
            assert data['skipped'] == 0

        # Verify in DB
        rows = db_conn.execute(
            "SELECT proposal_id, source_node FROM work_proposals "
            "ORDER BY proposal_id"
        ).fetchall()
        ids = [r['proposal_id'] for r in rows]
        assert 'RP1' in ids
        assert 'RP2' in ids

    def test_sync_proposals_last_writer_wins(self, app, db_conn, auth_node):
        """Older remote proposals don't overwrite newer local ones."""
        nid, key = auth_node
        # Insert local proposal with recent timestamp
        db_conn.execute(
            "INSERT INTO work_proposals (proposal_id, title, agent, status, "
            "updated_at) VALUES ('LP1', 'Local Title', 'gemma', 'approved', "
            "'2026-06-01 00:00:00')"
        )
        db_conn.commit()

        # Try sync with older timestamp
        payload = {
            'source_node': 'remote-alpha',
            'proposals': [
                {'proposal_id': 'LP1', 'title': 'Remote Override',
                 'agent': 'llama', 'status': 'pending',
                 'updated_at': '2026-01-01 00:00:00'},
            ],
        }
        with app.test_client() as c:
            resp = c.post('/api/node/sync/proposals',
                          json=payload,
                          headers=_auth_headers(nid, key))
            data = resp.get_json()
            assert data['skipped'] == 1
            assert data['synced'] == 0

        # Local data should be preserved
        row = db_conn.execute(
            "SELECT title, status FROM work_proposals WHERE proposal_id='LP1'"
        ).fetchone()
        assert row['title'] == 'Local Title'
        assert row['status'] == 'approved'

    def test_sync_proposals_requires_auth(self, app):
        """Sync endpoint rejects unauthenticated requests."""
        with app.test_client() as c:
            resp = c.post('/api/node/sync/proposals', json={
                'source_node': 'x', 'proposals': [],
            })
            assert resp.status_code == 401

    def test_sync_proposals_missing_fields(self, app, auth_node):
        """Sync with missing source_node or empty proposals returns 400."""
        nid, key = auth_node
        with app.test_client() as c:
            resp = c.post('/api/node/sync/proposals',
                          json={'proposals': []},
                          headers=_auth_headers(nid, key))
            assert resp.status_code == 400

    def test_sync_proposals_cap_100(self, app, db_conn, auth_node):
        """Sync is capped at 100 proposals per batch."""
        nid, key = auth_node
        big_batch = [
            {'proposal_id': f'BP{i}', 'title': f'Batch {i}',
             'agent': 'gemma', 'status': 'pending',
             'created_at': '2026-01-01 00:00:00',
             'updated_at': '2026-01-01 00:00:00'}
            for i in range(120)
        ]
        payload = {'source_node': 'remote-big', 'proposals': big_batch}
        with app.test_client() as c:
            resp = c.post('/api/node/sync/proposals',
                          json=payload,
                          headers=_auth_headers(nid, key))
            data = resp.get_json()
            assert data['synced'] == 100  # Capped


# ══════════════════════════════════════════════════════════════════════════════
# D.2 — Federated Skill Registry
# ══════════════════════════════════════════════════════════════════════════════

class TestNodeSkillsCRUD:
    def test_upsert_and_list(self, db_conn):
        """Skills are inserted and can be listed."""
        from utils.db.node_skills import upsert_node_skills, list_node_skills
        skills = [
            {'skill_name': 'web_search', 'trust_level': 3, 'description': 'Search the web'},
            {'skill_name': 'email_send', 'trust_level': 2, 'description': 'Send email'},
        ]
        upsert_node_skills('node-A', skills, conn=db_conn)

        result = list_node_skills('node-A', conn=db_conn)
        assert len(result) == 2
        names = [r['skill_name'] for r in result]
        assert 'web_search' in names
        assert 'email_send' in names

    def test_upsert_updates_existing(self, db_conn):
        """Re-upserting updates trust_level and description."""
        from utils.db.node_skills import upsert_node_skills, list_node_skills
        upsert_node_skills('node-B', [
            {'skill_name': 'calc', 'trust_level': 1, 'description': 'v1'},
        ], conn=db_conn)
        upsert_node_skills('node-B', [
            {'skill_name': 'calc', 'trust_level': 5, 'description': 'v2'},
        ], conn=db_conn)
        result = list_node_skills('node-B', conn=db_conn)
        assert len(result) == 1
        assert result[0]['trust_level'] == 5
        assert result[0]['description'] == 'v2'

    def test_find_skill_node(self, db_conn):
        """find_skill_node returns best node for a skill."""
        from utils.db.node_skills import upsert_node_skills, find_skill_node
        # Need a swarm_nodes entry for JOIN
        db_conn.execute(
            "INSERT INTO swarm_nodes (node_id, name, url, api_key_hash) "
            "VALUES ('node-C', 'Node C', 'http://c:5050', 'hash')"
        )
        db_conn.commit()
        upsert_node_skills('node-C', [
            {'skill_name': 'translate', 'trust_level': 4, 'description': 'Translate text'},
        ], conn=db_conn)
        result = find_skill_node('translate', conn=db_conn)
        assert result is not None
        assert result['node_id'] == 'node-C'
        assert result['url'] == 'http://c:5050'

    def test_find_skill_node_not_found(self, db_conn):
        """find_skill_node returns None for unknown skill."""
        from utils.db.node_skills import find_skill_node
        assert find_skill_node('nonexistent', conn=db_conn) is None

    def test_mark_stale(self, db_conn):
        """mark_stale sets available=0 for all node skills."""
        from utils.db.node_skills import upsert_node_skills, mark_stale, list_node_skills
        upsert_node_skills('node-D', [
            {'skill_name': 's1', 'trust_level': 1, 'description': ''},
            {'skill_name': 's2', 'trust_level': 2, 'description': ''},
        ], conn=db_conn)
        assert len(list_node_skills('node-D', conn=db_conn)) == 2
        mark_stale('node-D', conn=db_conn)
        assert len(list_node_skills('node-D', conn=db_conn)) == 0

    def test_list_all_skills(self, db_conn):
        """list_node_skills without node_id returns all available skills."""
        from utils.db.node_skills import upsert_node_skills, list_node_skills
        upsert_node_skills('nX', [
            {'skill_name': 'x1', 'trust_level': 1, 'description': ''},
        ], conn=db_conn)
        upsert_node_skills('nY', [
            {'skill_name': 'y1', 'trust_level': 2, 'description': ''},
        ], conn=db_conn)
        result = list_node_skills(conn=db_conn)
        names = [r['skill_name'] for r in result]
        assert 'x1' in names
        assert 'y1' in names


class TestNodeSkillsEndpoint:
    def test_skills_endpoint(self, app, monkeypatch):
        """GET /api/node/skills returns this node's REGISTRY skills."""
        import types
        fake_registry = {
            'web_search': {'trust_level': 3, 'description': 'Search web'},
            'code_review': {'trust_level': 5, 'description': 'Review code'},
        }
        fake_module = types.ModuleType('fridays.skills')
        fake_module.REGISTRY = fake_registry
        monkeypatch.setitem(sys.modules, 'fridays.skills', fake_module)

        with app.test_client() as c:
            resp = c.get('/api/node/skills')
            assert resp.status_code == 200
            data = resp.get_json()
            names = [s['skill_name'] for s in data['skills']]
            assert 'web_search' in names
            assert 'code_review' in names


# ══════════════════════════════════════════════════════════════════════════════
# D.3 — Bus Event Propagation
# ══════════════════════════════════════════════════════════════════════════════

class TestEventRelay:
    def test_receive_events(self, app, db_conn, auth_node):
        """POST /api/node/events inserts relayed events."""
        nid, key = auth_node
        payload = {
            'source_node': 'remote-alpha',
            'events': [
                {'topic': 'proposal.approved', 'payload': {'id': 'P1'},
                 'created_at': '2026-01-01 12:00:00'},
                {'topic': 'skill.completed', 'payload': {'name': 'web_search'},
                 'created_at': '2026-01-01 12:01:00'},
            ],
        }
        with app.test_client() as c:
            resp = c.post('/api/node/events',
                          json=payload,
                          headers=_auth_headers(nid, key))
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['inserted'] == 2
            assert data['duplicates'] == 0

        # Verify in DB
        rows = db_conn.execute(
            "SELECT topic, source_service FROM swarm_bus ORDER BY id"
        ).fetchall()
        topics = [r['topic'] for r in rows]
        assert 'proposal.approved' in topics
        sources = [r['source_service'] for r in rows]
        assert 'remote:remote-alpha' in sources

    def test_event_dedup(self, app, db_conn, auth_node):
        """Duplicate events (same topic+source+timestamp) are rejected."""
        nid, key = auth_node
        payload = {
            'source_node': 'remote-alpha',
            'events': [
                {'topic': 'ping', 'payload': {}, 'created_at': '2026-01-01 00:00:00'},
            ],
        }
        with app.test_client() as c:
            # First request
            resp = c.post('/api/node/events', json=payload,
                          headers=_auth_headers(nid, key))
            assert resp.get_json()['inserted'] == 1

            # Second request — same event
            resp = c.post('/api/node/events', json=payload,
                          headers=_auth_headers(nid, key))
            assert resp.get_json()['duplicates'] == 1
            assert resp.get_json()['inserted'] == 0

    def test_events_requires_auth(self, app):
        """POST /api/node/events rejects unauthenticated requests."""
        with app.test_client() as c:
            resp = c.post('/api/node/events', json={
                'source_node': 'x', 'events': [],
            })
            assert resp.status_code == 401

    def test_events_missing_fields(self, app, auth_node):
        """Events endpoint requires source_node and non-empty events."""
        nid, key = auth_node
        with app.test_client() as c:
            resp = c.post('/api/node/events',
                          json={'events': []},
                          headers=_auth_headers(nid, key))
            assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# D.4 — Config Validator & Node Config
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigValidator:
    def test_validate_config_missing_swarm_root(self, monkeypatch, db_conn):
        """Validation fails when SWARM_ROOT is not set."""
        monkeypatch.delenv('SWARM_ROOT', raising=False)
        from utils.config_validator import validate_config
        ok, errors, warnings = validate_config()
        assert not ok
        assert any('SWARM_ROOT' in e for e in errors)

    def test_validate_config_success(self, monkeypatch, db_conn, tmp_path):
        """Validation succeeds with valid env and DB."""
        monkeypatch.setenv('SWARM_ROOT', str(tmp_path))
        monkeypatch.setenv('SWARM_ENV', 'test')
        from utils.config_validator import validate_config
        ok, errors, warnings = validate_config()
        assert ok
        assert len(errors) == 0


class TestNodeConfig:
    def test_set_and_get(self, db_conn):
        """set_config + get_config round-trip."""
        from utils.config_validator import set_config, get_config
        set_config('relay_batch_size', '100', conn=db_conn)
        val = get_config('relay_batch_size', conn=db_conn)
        assert val == '100'

    def test_get_falls_back_to_default(self, db_conn):
        """get_config returns CONFIG_DEFAULTS when not in table or env."""
        from utils.config_validator import get_config
        val = get_config('stale_threshold', conn=db_conn)
        assert val == '300'  # CONFIG_DEFAULTS

    def test_get_falls_back_to_env(self, db_conn, monkeypatch):
        """get_config reads env var when not in table."""
        monkeypatch.setenv('SWARM_HEARTBEAT_INTERVAL', '120')
        from utils.config_validator import get_config
        val = get_config('heartbeat_interval', conn=db_conn)
        assert val == '120'

    def test_list_config(self, db_conn):
        """list_config returns all overrides."""
        from utils.config_validator import set_config, list_config
        set_config('key_a', 'val_a', conn=db_conn)
        set_config('key_b', 'val_b', conn=db_conn)
        result = list_config(conn=db_conn)
        keys = [r['key'] for r in result]
        assert 'key_a' in keys
        assert 'key_b' in keys

    def test_set_overwrites(self, db_conn):
        """set_config overwrites existing key."""
        from utils.config_validator import set_config, get_config
        set_config('mykey', 'old', conn=db_conn)
        set_config('mykey', 'new', conn=db_conn)
        assert get_config('mykey', conn=db_conn) == 'new'
