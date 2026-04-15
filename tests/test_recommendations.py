"""
tests/test_recommendations.py — Tests for R.1–R.6 recommendations
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - R.1: Session authentication (login/logout, protected routes)
  - R.2: SSE endpoint (event stream, publish)
  - R.4: datetime.utcnow() removed (deprecation regression guard)
  - R.5: API versioning (/api/v1/* aliases)
  - R.6: Prometheus metrics format
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
    """Isolated DB for recommendation tests."""
    db_path = str(tmp_path / 'test_r.db')
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
        CREATE TABLE IF NOT EXISTS work_proposals (
            proposal_id TEXT PRIMARY KEY, title TEXT DEFAULT '',
            description TEXT DEFAULT '', agent TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', source_conv_id TEXT DEFAULT '',
            source_node TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_bus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
            source_service TEXT NOT NULL DEFAULT 'local',
            created_at TEXT DEFAULT (datetime('now')), consumed_at TEXT
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
        CREATE TABLE IF NOT EXISTS research_sessions (
            session_id TEXT PRIMARY KEY, question TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS shared_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT DEFAULT '', content TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tool_builds (
            build_id TEXT PRIMARY KEY, tool_name TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '', status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) "
        "VALUES (1, 'gemma', 'Gemma3', 'gemma3:latest', 1)"
    )
    conn.execute(
        "INSERT INTO work_proposals (proposal_id, title, status) "
        "VALUES ('P001', 'Test', 'approved')"
    )
    conn.execute(
        "INSERT INTO swarm_bus (topic, payload_json) VALUES ('test', '{}')"
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
def app_no_auth(db_conn, monkeypatch):
    """Flask app WITHOUT auth enabled."""
    monkeypatch.delenv('SWARM_UI_PASSWORD', raising=False)
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    from utils.session_auth import init_session_auth
    # Reload to pick up env change
    import utils.session_auth as sa
    monkeypatch.setattr(sa, '_UI_PASSWORD', '')
    init_session_auth(app)

    from utils.security_headers import init_security
    init_security(app)

    from frontend.blueprints.metrics import metrics_bp
    from frontend.blueprints.sse import sse_bp
    app.register_blueprint(metrics_bp)
    app.register_blueprint(sse_bp)

    @app.route('/api/test-plain')
    def _plain():
        from flask import jsonify
        return jsonify({'ok': True})

    @app.route('/ui')
    def _ui():
        return 'UI page'

    return app


@pytest.fixture
def app_with_auth(db_conn, monkeypatch):
    """Flask app WITH auth enabled (password=testpass)."""
    monkeypatch.setenv('SWARM_UI_PASSWORD', 'testpass')
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    import utils.session_auth as sa
    monkeypatch.setattr(sa, '_UI_PASSWORD', 'testpass')
    from utils.session_auth import init_session_auth
    init_session_auth(app)

    from frontend.blueprints.metrics import metrics_bp
    app.register_blueprint(metrics_bp)

    @app.route('/api/test-protected')
    def _protected():
        from flask import jsonify
        return jsonify({'ok': True})

    @app.route('/ui')
    def _ui():
        return 'UI page'

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# R.1 — Session Authentication
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionAuth:

    def test_no_auth_allows_all(self, app_no_auth):
        """When SWARM_UI_PASSWORD is unset, all routes are open."""
        with app_no_auth.test_client() as c:
            assert c.get('/api/test-plain').status_code == 200
            assert c.get('/ui').status_code == 200

    def test_auth_blocks_ui(self, app_with_auth):
        """When auth is enabled, /ui redirects to /login."""
        with app_with_auth.test_client() as c:
            resp = c.get('/ui')
            assert resp.status_code == 302
            assert '/login' in resp.headers['Location']

    def test_auth_blocks_api(self, app_with_auth):
        """When auth is enabled, API routes return 401."""
        with app_with_auth.test_client() as c:
            resp = c.get('/api/test-protected',
                         headers={'Content-Type': 'application/json'})
            assert resp.status_code == 401

    def test_auth_allows_health(self, app_with_auth):
        """/_health is always accessible even with auth enabled."""
        with app_with_auth.test_client() as c:
            # /_health might not exist in test app, but at least it
            # shouldn't redirect to /login
            resp = c.get('/_health')
            # Either 200 (if route exists) or 404, but NOT 302
            assert resp.status_code != 302

    def test_login_wrong_password(self, app_with_auth):
        """Wrong password returns 403."""
        with app_with_auth.test_client() as c:
            resp = c.post('/login', data={'password': 'wrong'})
            assert resp.status_code == 403

    def test_login_correct_password(self, app_with_auth):
        """Correct password sets session and redirects to /ui."""
        with app_with_auth.test_client() as c:
            resp = c.post('/login', data={'password': 'testpass'})
            assert resp.status_code == 302
            assert '/ui' in resp.headers['Location']

    def test_login_then_access(self, app_with_auth):
        """After login, protected routes are accessible."""
        with app_with_auth.test_client() as c:
            c.post('/login', data={'password': 'testpass'})
            resp = c.get('/api/test-protected')
            assert resp.status_code == 200

    def test_logout(self, app_with_auth):
        """After logout, session is cleared."""
        with app_with_auth.test_client() as c:
            c.post('/login', data={'password': 'testpass'})
            c.get('/logout')
            resp = c.get('/ui')
            assert resp.status_code == 302  # redirect to login


# ═══════════════════════════════════════════════════════════════════════════════
# R.2 — SSE Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestSSE:

    def test_event_stream_content_type(self, app_no_auth):
        """SSE endpoint returns text/event-stream."""
        with app_no_auth.test_client() as c:
            resp = c.get('/api/events')
            assert 'text/event-stream' in resp.content_type

    def test_publish_creates_events(self):
        """publish() queues events for subscribers."""
        from frontend.blueprints.sse import publish, _subscribers, _sub_lock
        import queue as q
        test_q = q.Queue(maxsize=10)
        with _sub_lock:
            _subscribers.append(test_q)
        try:
            publish('test', {'key': 'value'})
            msg = test_q.get_nowait()
            assert 'event: test' in msg
            assert '"key"' in msg
        finally:
            with _sub_lock:
                try:
                    _subscribers.remove(test_q)
                except ValueError:
                    pass


# ═══════════════════════════════════════════════════════════════════════════════
# R.4 — datetime.utcnow() deprecation guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatetimeDeprecation:

    def test_no_utcnow_in_source(self):
        """Ensure no datetime.utcnow() calls remain in source code."""
        import subprocess
        result = subprocess.run(
            ['grep', '-rn', 'utcnow()', '--include=*.py',
             '--exclude=test_recommendations.py',
             'frontend/', 'utils/', 'core/', 'tests/', 'lib/', 'scripts/'],
            capture_output=True, text=True, cwd=SWARM_ROOT,
        )
        matches = [
            line for line in result.stdout.strip().split('\n')
            if line and '__pycache__' not in line
        ]
        assert matches == [], f"Found utcnow() calls:\n" + '\n'.join(matches)


# ═══════════════════════════════════════════════════════════════════════════════
# R.5 — API Versioning
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIVersioning:

    def test_v1_alias_registered(self, app_no_auth):
        """/api/v1/* routes are registered alongside /api/*."""
        from utils.api_versioning import register_versioned_routes
        register_versioned_routes(app_no_auth, version='v1')

        rules = [r.rule for r in app_no_auth.url_map.iter_rules()]
        assert '/api/test-plain' in rules
        assert '/api/v1/test-plain' in rules

    def test_v1_alias_works(self, app_no_auth):
        """Versioned endpoint returns same response as unversioned."""
        from utils.api_versioning import register_versioned_routes
        register_versioned_routes(app_no_auth, version='v1')

        with app_no_auth.test_client() as c:
            orig = c.get('/api/test-plain')
            versioned = c.get('/api/v1/test-plain')
            assert orig.status_code == versioned.status_code == 200
            assert orig.get_json() == versioned.get_json()


# ═══════════════════════════════════════════════════════════════════════════════
# R.6 — Prometheus Metrics
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrometheusMetrics:

    def test_prometheus_endpoint_returns_text(self, app_no_auth, db_conn):
        """Prometheus endpoint returns text/plain exposition format."""
        with app_no_auth.test_client() as c:
            resp = c.get('/api/metrics/prometheus')
            assert resp.status_code == 200
            assert 'text/plain' in resp.content_type

    def test_prometheus_has_metrics(self, app_no_auth, db_conn):
        """Prometheus output includes expected metric names."""
        with app_no_auth.test_client() as c:
            resp = c.get('/api/metrics/prometheus')
            body = resp.data.decode()
            assert 'swarm_agents_total' in body
            assert 'swarm_agents_active' in body
            assert 'swarm_proposals' in body
            assert 'swarm_bus_events_24h' in body
            assert 'swarm_nodes_total' in body

    def test_prometheus_valid_format(self, app_no_auth, db_conn):
        """Prometheus lines follow name{labels} value format."""
        with app_no_auth.test_client() as c:
            resp = c.get('/api/metrics/prometheus')
            for line in resp.data.decode().strip().split('\n'):
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.split()
                assert len(parts) >= 2, f"Invalid prometheus line: {line}"
