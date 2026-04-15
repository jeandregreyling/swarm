"""
tests/test_multi_node.py — A.5 Multi-Node Foundation tests
═══════════════════════════════════════════════════════════
Tests:
  - A.5.1: Node discovery, heartbeat, ping
  - A.5.2: Local proposals endpoint
  - A.5.3: Federation roster (local only, no remote nodes needed)
  - A.5.4: Node API key auth
"""

import json
import os
import sqlite3
import sys
import types
import pytest

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Isolated DB with all required tables for A.5 tests."""
    db_path = str(tmp_path / 'test_a5.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS swarm_nodes (
            node_id         TEXT PRIMARY KEY,
            name            TEXT NOT NULL DEFAULT '',
            url             TEXT NOT NULL DEFAULT '',
            api_key_hash    TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'contributor',
            agents_json     TEXT NOT NULL DEFAULT '[]',
            capabilities    TEXT NOT NULL DEFAULT '[]',
            registered_at   TEXT DEFAULT (datetime('now')),
            last_seen       TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS work_proposals (
            proposal_id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            agent TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            source_conv_id TEXT DEFAULT '',
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
    """)
    # Seed a couple test agents
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) VALUES (1, 'gemma', 'Gemma3', 'gemma3:latest', 1)"
    )
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) VALUES (2, 'llama', 'LlaMA', 'llama3.2:latest', 1)"
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
    # Also patch modules that copied the reference via `from ._connection import get_connection`
    monkeypatch.setattr('utils.db.nodes.get_connection', _get_conn)

    yield conn
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# A.5.1 — Node Discovery tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNodeDiscovery:
    def test_ping_invalid_url_returns_none(self):
        from utils.node_discovery import ping_node
        result = ping_node('http://127.0.0.1:59999', timeout=1)
        assert result is None

    def test_heartbeat_empty_registry(self, db_conn):
        from utils.node_discovery import run_heartbeat_once
        results = run_heartbeat_once()
        assert results == {}

    def test_heartbeat_touches_local_node(self, db_conn):
        from utils.db.nodes import register_node, get_local_node_id, get_node
        local_id = get_local_node_id()
        register_node('local', 'http://localhost:5050', 'localkey',
                       role='owner', conn=db_conn)
        # Re-register under the exact local_id so heartbeat matches
        db_conn.execute(
            "UPDATE swarm_nodes SET node_id=? WHERE name='local'",
            (local_id,)
        )
        db_conn.commit()
        from utils.node_discovery import run_heartbeat_once
        results = run_heartbeat_once()
        assert results.get(local_id) is True

    def test_start_stop_heartbeat(self):
        from utils.node_discovery import start_heartbeat, stop_heartbeat
        start_heartbeat()
        start_heartbeat()  # Idempotent
        stop_heartbeat()


# ══════════════════════════════════════════════════════════════════════════════
# A.5.2 — Cross-Node Proposals tests (DB-level, no Flask)
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossNodeProposals:
    def test_local_proposals_returned(self, db_conn):
        """Proposals are queryable for remote consumption."""
        db_conn.execute(
            "INSERT INTO work_proposals (proposal_id, title, agent, status) "
            "VALUES ('P1', 'Build widget', 'gemma', 'in_progress')"
        )
        db_conn.commit()
        rows = db_conn.execute(
            "SELECT proposal_id, title, agent, status FROM work_proposals"
        ).fetchall()
        assert len(rows) == 1
        assert dict(rows[0])['proposal_id'] == 'P1'


# ══════════════════════════════════════════════════════════════════════════════
# A.5.4 — Node Authentication tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNodeAuth:
    def test_verify_correct_key(self, db_conn):
        from utils.db.nodes import register_node, verify_api_key
        nid = register_node('auth-test', 'http://x:5050', 'secretkey', conn=db_conn)
        assert verify_api_key(nid, 'secretkey', conn=db_conn)

    def test_verify_wrong_key(self, db_conn):
        from utils.db.nodes import register_node, verify_api_key
        nid = register_node('auth-test2', 'http://y:5050', 'goodkey', conn=db_conn)
        assert not verify_api_key(nid, 'badkey', conn=db_conn)

    def test_verify_unknown_node(self, db_conn):
        from utils.db.nodes import verify_api_key
        assert not verify_api_key('nonexistent', 'anykey', conn=db_conn)

    def test_role_enforcement_in_register(self, db_conn):
        """Only valid roles accepted."""
        from utils.db.nodes import register_node
        # Valid roles
        for role in ('owner', 'contributor', 'viewer'):
            register_node(f'r-{role}', f'http://{role}:5050', 'k', role=role, conn=db_conn)
        # Invalid role
        with pytest.raises(ValueError):
            register_node('r-bad', 'http://bad:5050', 'k', role='superadmin', conn=db_conn)


# ══════════════════════════════════════════════════════════════════════════════
# A.5 — Flask endpoint integration tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNodeEndpoints:
    @pytest.fixture
    def app(self, db_conn, monkeypatch):
        """Minimal Flask test app with node blueprint."""
        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        from frontend.blueprints.node import node_bp
        app.register_blueprint(node_bp)
        return app

    def test_node_info(self, app):
        with app.test_client() as c:
            resp = c.get('/api/node/info')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'node_id' in data
            assert 'agents' in data

    def test_node_register(self, app):
        with app.test_client() as c:
            resp = c.post('/api/node/register', json={
                'name': 'test-node',
                'url': 'http://192.168.1.50:5050',
                'api_key': 'testkey123',
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'node_id' in data

    def test_node_register_missing_fields(self, app):
        with app.test_client() as c:
            resp = c.post('/api/node/register', json={'name': 'bad'})
            assert resp.status_code == 400

    def test_node_list(self, app):
        with app.test_client() as c:
            # Register first
            c.post('/api/node/register', json={
                'name': 'n1', 'url': 'http://a:5050', 'api_key': 'k1'
            })
            resp = c.get('/api/node/list')
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data['nodes']) >= 1
            # api_key_hash should be stripped
            for n in data['nodes']:
                assert 'api_key_hash' not in n

    def test_proposals_requires_auth(self, app):
        """The /api/node/proposals endpoint requires node auth."""
        with app.test_client() as c:
            resp = c.get('/api/node/proposals')
            assert resp.status_code == 401

    def test_federation_proposals_local(self, app, db_conn):
        """Federation proposals returns local data even with no remote nodes."""
        db_conn.execute(
            "INSERT INTO work_proposals (proposal_id, title, agent, status) "
            "VALUES ('FP1', 'Fed test', 'llama', 'pending')"
        )
        db_conn.commit()
        with app.test_client() as c:
            resp = c.get('/api/federation/proposals')
            assert resp.status_code == 200
            data = resp.get_json()
            assert any(p['proposal_id'] == 'FP1' for p in data['proposals'])

    def test_federation_roster_local(self, app, db_conn):
        """Federation roster returns local agents."""
        with app.test_client() as c:
            resp = c.get('/api/federation/roster')
            assert resp.status_code == 200
            data = resp.get_json()
            names = [a['name'] for a in data['roster']]
            assert 'gemma' in names
            assert 'llama' in names
