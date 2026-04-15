"""
tests/test_onboarding.py — Onboarding wizard API tests
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - /api/onboarding/status returns local AI, cloud agents, and node status
  - /api/onboarding/test-key validates parameters
"""

import os
import sqlite3
import sys
import pytest

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_ob.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER DEFAULT 0, name TEXT NOT NULL,
            label TEXT DEFAULT '', model TEXT DEFAULT '',
            temperature REAL DEFAULT 0.3, role TEXT DEFAULT '',
            system_prompt TEXT DEFAULT '', api_key_var TEXT DEFAULT '',
            tier TEXT DEFAULT 'local', enabled INTEGER DEFAULT 1,
            memory_table TEXT DEFAULT '', display_label TEXT DEFAULT '',
            aliases TEXT DEFAULT '', eta_seconds INTEGER DEFAULT 30,
            keep_alive TEXT DEFAULT '5m'
        );
        CREATE TABLE IF NOT EXISTS swarm_nodes (
            node_id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '', api_key_hash TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'contributor',
            agents_json TEXT NOT NULL DEFAULT '[]',
            capabilities TEXT NOT NULL DEFAULT '[]',
            registered_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.execute(
        "INSERT INTO agents (number, name, label, model, tier, api_key_var, enabled) "
        "VALUES (9, 'nine', 'Nine', 'groq-llama', 'paid', 'GROQ_API_KEY', 1)"
    )
    conn.execute(
        "INSERT INTO agents (number, name, label, model, tier, api_key_var, enabled) "
        "VALUES (12, 'twelve', 'Twelve', 'claude-sonnet', 'paid', 'ANTHROPIC_API_KEY', 1)"
    )
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    yield conn
    conn.close()


@pytest.fixture
def app(db_conn, monkeypatch):
    """Flask app with onboarding blueprint."""
    monkeypatch.delenv('SWARM_UI_PASSWORD', raising=False)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    from frontend.blueprints.onboarding import onboarding_bp
    app.register_blueprint(onboarding_bp)
    return app


class TestOnboardingStatus:

    def test_status_endpoint_returns_json(self, app):
        with app.test_client() as c:
            resp = c.get('/api/onboarding/status')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'local_ai' in data
            assert 'cloud_agents' in data
            assert 'cloud_nodes' in data

    def test_local_ai_has_ollama_and_lmstudio(self, app):
        with app.test_client() as c:
            data = c.get('/api/onboarding/status').get_json()
            local = data['local_ai']
            assert 'ollama' in local
            assert 'lmstudio' in local
            assert isinstance(local['ollama']['running'], bool)
            assert isinstance(local['lmstudio']['running'], bool)

    def test_cloud_agents_lists_known_providers(self, app):
        with app.test_client() as c:
            data = c.get('/api/onboarding/status').get_json()
            agents = data['cloud_agents']
            env_vars = [a['env_var'] for a in agents]
            assert 'GROQ_API_KEY' in env_vars
            assert 'ANTHROPIC_API_KEY' in env_vars
            assert 'TAVILY_API_KEY' in env_vars

    def test_cloud_agents_count(self, app):
        with app.test_client() as c:
            data = c.get('/api/onboarding/status').get_json()
            assert data['cloud_agents_total'] == 6  # 6 known cloud agents

    def test_cloud_agents_key_set_reflects_env(self, app, monkeypatch):
        monkeypatch.setenv('GROQ_API_KEY', 'test-key-value')
        with app.test_client() as c:
            data = c.get('/api/onboarding/status').get_json()
            groq = next(a for a in data['cloud_agents'] if a['env_var'] == 'GROQ_API_KEY')
            assert groq['key_set'] is True


class TestOnboardingTestKey:

    def test_missing_params_returns_400(self, app):
        with app.test_client() as c:
            resp = c.post('/api/onboarding/test-key',
                          json={'env_var': '', 'value': ''})
            assert resp.status_code == 400

    def test_unknown_env_var_returns_400(self, app):
        with app.test_client() as c:
            resp = c.post('/api/onboarding/test-key',
                          json={'env_var': 'UNKNOWN_KEY', 'value': 'test'})
            assert resp.status_code == 400
            assert 'Unknown' in resp.get_json()['message']

    def test_valid_env_var_accepted(self, app):
        """A known env_var with a value should attempt validation (may fail connectivity in test)."""
        with app.test_client() as c:
            resp = c.post('/api/onboarding/test-key',
                          json={'env_var': 'GROQ_API_KEY', 'value': 'gsk_test123'})
            data = resp.get_json()
            # We can't test real API connectivity, but the endpoint should return ok or error
            assert 'ok' in data
            assert 'message' in data
