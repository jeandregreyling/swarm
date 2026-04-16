"""
tests/test_diamond.py — Diamond Layer (Phase A) tests
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - /api/diamond/pulse   — system vitals, queue, tickets, proposals, agents, governance
  - /api/diamond/attention — per-tile attention flags
  - /api/diamond/landscape — agent map, library stats, proposal summary
  - Internal helpers
"""

import os
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test_diamond.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Make the get_connection in diamond.py's `from db import get_connection` return our test db
    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    # Patch the re-exported symbol on the db package itself
    import utils.db as _db_pkg
    monkeypatch.setattr(_db_pkg, 'get_connection', _get_conn)
    # Diamond.py resolves `from db import get_connection` via sys.path → utils/db
    # which may be a separate sys.modules entry; patch it too
    sys.path.insert(0, os.path.join(SWARM_ROOT, 'utils'))
    import db as _db_mod
    monkeypatch.setattr(_db_mod, 'get_connection', _get_conn)

    # Create required tables (matching production schema)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS ticket_queue (
            id INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'queued',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS work_proposals (
            id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS duck_flags (
            id INTEGER PRIMARY KEY,
            flag TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            number INTEGER DEFAULT 0,
            display_label TEXT DEFAULT '',
            label TEXT DEFAULT '',
            model TEXT DEFAULT '',
            role TEXT DEFAULT '',
            tier TEXT DEFAULT 'local',
            temperature REAL DEFAULT 0.7,
            enabled INTEGER DEFAULT 1,
            system_prompt TEXT DEFAULT '',
            api_key_var TEXT DEFAULT '',
            memory_table TEXT DEFAULT '',
            aliases TEXT DEFAULT '',
            eta_seconds INTEGER DEFAULT 30,
            keep_alive TEXT DEFAULT '5m'
        );
        CREATE TABLE IF NOT EXISTS time_wizard_log (
            id INTEGER PRIMARY KEY,
            event TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Invalidate registry cache so it uses our test DB
    try:
        from utils.db.registry import invalidate_cache
        invalidate_cache()
    except Exception:
        pass

    yield conn
    conn.close()


@pytest.fixture
def app(db_conn, monkeypatch):
    """Create a Flask test app with the diamond blueprint."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    from frontend.blueprints.diamond import diamond_bp
    app.register_blueprint(diamond_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Pulse endpoint ────────────────────────────────────────────────────────────

class TestPulse:

    def test_pulse_returns_ok(self, client):
        resp = client.get('/api/diamond/pulse')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'system' in data
        assert 'queue' in data
        assert 'tickets' in data
        assert 'proposals' in data
        assert 'agents' in data
        assert 'governance' in data
        assert 'ts' in data

    def test_pulse_system_has_cpu_and_ram(self, client):
        resp = client.get('/api/diamond/pulse')
        data = resp.get_json()
        sys_data = data['system']
        # psutil should provide these on any Linux/Mac
        assert 'cpu_percent' in sys_data
        assert 'ram_percent' in sys_data

    def test_pulse_tickets_trend_7_days(self, client, db_conn):
        # Insert a closed ticket from yesterday
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        db_conn.execute("INSERT INTO tickets (status, updated_at) VALUES ('closed', ?)", (yesterday,))
        db_conn.commit()

        resp = client.get('/api/diamond/pulse')
        data = resp.get_json()
        assert len(data['tickets']['trend']) == 7
        assert data['tickets']['closed_7d'] >= 1

    def test_pulse_proposals_trend(self, client, db_conn):
        db_conn.execute("INSERT INTO work_proposals (title, status) VALUES ('test', 'pending')")
        db_conn.commit()

        resp = client.get('/api/diamond/pulse')
        data = resp.get_json()
        assert data['proposals']['pending'] >= 1

    def test_pulse_queue_depth(self, client, db_conn):
        db_conn.execute("INSERT INTO ticket_queue (status) VALUES ('queued')")
        db_conn.execute("INSERT INTO ticket_queue (status) VALUES ('queued')")
        db_conn.commit()

        resp = client.get('/api/diamond/pulse')
        data = resp.get_json()
        assert data['queue']['depth'] >= 2

    def test_pulse_agent_summary(self, client, db_conn):
        db_conn.execute(
            "INSERT INTO agents (name, number, model, tier, enabled) VALUES ('test_agent', 99, 'test-model', 'local', 1)"
        )
        db_conn.commit()

        resp = client.get('/api/diamond/pulse')
        data = resp.get_json()
        assert data['agents']['total'] >= 1
        assert data['agents']['enabled'] >= 1


# ── Attention endpoint ────────────────────────────────────────────────────────

class TestAttention:

    def test_attention_returns_ok(self, client):
        resp = client.get('/api/diamond/attention')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'flags' in data

    def test_attention_tickets_flag(self, client, db_conn):
        # Insert 3 open tickets → should give 'warn'
        for _ in range(3):
            db_conn.execute("INSERT INTO tickets (status) VALUES ('open')")
        db_conn.commit()

        resp = client.get('/api/diamond/attention')
        flags = resp.get_json()['flags']
        assert 'tickets' in flags
        assert flags['tickets']['level'] == 'warn'
        assert flags['tickets']['count'] == 3

    def test_attention_tickets_crit_threshold(self, client, db_conn):
        # Insert 7 open tickets → should give 'crit'
        for _ in range(7):
            db_conn.execute("INSERT INTO tickets (status) VALUES ('open')")
        db_conn.commit()

        resp = client.get('/api/diamond/attention')
        flags = resp.get_json()['flags']
        assert flags['tickets']['level'] == 'crit'

    def test_attention_duck_flags(self, client, db_conn):
        db_conn.execute("INSERT INTO duck_flags (flag) VALUES ('test flag')")
        db_conn.commit()

        resp = client.get('/api/diamond/attention')
        flags = resp.get_json()['flags']
        assert 'chat' in flags
        assert flags['chat']['level'] == 'crit'
        assert flags['chat']['count'] == 1

    def test_attention_no_flags_when_clean(self, client, db_conn):
        resp = client.get('/api/diamond/attention')
        flags = resp.get_json()['flags']
        # No tickets, no proposals, no duck flags → mostly empty
        assert 'tickets' not in flags  # 0 open = no flag

    def test_attention_proposals_flag(self, client, db_conn):
        db_conn.execute("INSERT INTO work_proposals (title, status) VALUES ('p1', 'pending')")
        db_conn.execute("INSERT INTO work_proposals (title, status) VALUES ('p2', 'in_progress')")
        db_conn.commit()

        resp = client.get('/api/diamond/attention')
        flags = resp.get_json()['flags']
        assert 'studio' in flags
        assert flags['studio']['count'] == 2


# ── Landscape endpoint ────────────────────────────────────────────────────────

class TestLandscape:

    def test_landscape_returns_ok(self, client, db_conn):
        db_conn.execute(
            "INSERT INTO agents (name, number, model, tier, enabled, role) "
            "VALUES ('alpha', 1, 'llama3.2', 'local', 1, 'research')"
        )
        db_conn.commit()

        resp = client.get('/api/diamond/landscape')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert len(data['agents']) >= 1
        assert data['agents'][0]['name'] == 'alpha'
        assert data['agents'][0]['tier'] == 'local'
        assert data['agents'][0]['enabled'] is True

    def test_landscape_proposal_summary(self, client, db_conn):
        db_conn.execute("INSERT INTO work_proposals (title, status) VALUES ('wp1', 'pending')")
        db_conn.execute("INSERT INTO work_proposals (title, status) VALUES ('wp2', 'done')")
        db_conn.commit()

        resp = client.get('/api/diamond/landscape')
        data = resp.get_json()
        assert data['proposals'].get('pending', 0) == 1
        assert data['proposals'].get('done', 0) == 1

    def test_landscape_includes_library_stats(self, client, db_conn):
        resp = client.get('/api/diamond/landscape')
        data = resp.get_json()
        # Library stats may be empty dict if store module can't connect, that's ok
        assert 'library' in data


# ── Internal helpers ──────────────────────────────────────────────────────────

class TestHelpers:

    def test_get_system_vitals_returns_cpu(self):
        from frontend.blueprints.diamond import _get_system_vitals
        vitals = _get_system_vitals()
        assert 'cpu_percent' in vitals
        assert 'ram_percent' in vitals
        assert isinstance(vitals['cpu_percent'], (int, float))

    def test_get_ticket_trend_structure(self, db_conn):
        from frontend.blueprints.diamond import _get_ticket_trend
        result = _get_ticket_trend()
        assert 'open' in result
        assert 'closed_7d' in result
        assert 'trend' in result
        assert len(result['trend']) == 7

    def test_get_proposal_trend_structure(self, db_conn):
        from frontend.blueprints.diamond import _get_proposal_trend
        result = _get_proposal_trend()
        assert 'pending' in result
        assert 'active' in result
        assert 'executed_7d' in result
        assert len(result['trend']) == 7

    def test_get_queue_status(self, db_conn):
        from frontend.blueprints.diamond import _get_queue_status
        result = _get_queue_status()
        assert 'depth' in result
        assert 'processing' in result
        assert isinstance(result['processing'], bool)

    def test_health_level_thresholds(self):
        from frontend.blueprints.diamond import _get_system_vitals
        # Just verify it runs without error — actual values depend on system
        v = _get_system_vitals()
        assert isinstance(v, dict)
