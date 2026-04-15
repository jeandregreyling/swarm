"""
tests/test_security_perf.py — Phase E Security, Performance & Observability tests
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - E.1: Rate limiter, security headers, input validation
  - E.2: Response cache (TTL + ETag + invalidation)
  - E.3: Structured logger, metrics endpoint, enhanced health check
"""

import json
import os
import sqlite3
import sys
import time
import logging
import pytest

SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SWARM_ROOT)
sys.path.insert(0, os.path.join(SWARM_ROOT, 'frontend'))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """Reset rate limiter state between tests."""
    from utils.rate_limiter import _buckets
    _buckets.clear()
    yield
    _buckets.clear()


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Isolated DB with tables needed for E-phase tests."""
    db_path = str(tmp_path / 'test_e.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
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
        CREATE TABLE IF NOT EXISTS swarm_bus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            source_service TEXT NOT NULL DEFAULT 'local',
            created_at TEXT DEFAULT (datetime('now')),
            consumed_at TEXT
        );
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
        CREATE TABLE IF NOT EXISTS research_sessions (
            session_id TEXT PRIMARY KEY,
            question TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS shared_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT DEFAULT '',
            content TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tool_builds (
            build_id TEXT PRIMARY KEY,
            tool_name TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed some data for metrics
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) "
        "VALUES (1, 'gemma', 'Gemma3', 'gemma3:latest', 1)"
    )
    conn.execute(
        "INSERT INTO agents (number, name, label, model, enabled) "
        "VALUES (2, 'llama', 'LLaMA', 'llama3.2:latest', 0)"
    )
    conn.execute(
        "INSERT INTO work_proposals (proposal_id, title, status) "
        "VALUES ('P001', 'Test Proposal', 'approved')"
    )
    conn.execute(
        "INSERT INTO swarm_bus (topic, payload_json) VALUES ('test.event', '{}')"
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
    """Minimal Flask app with security headers and metrics blueprint."""
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    from utils.security_headers import init_security
    init_security(app)

    from frontend.blueprints.metrics import metrics_bp
    app.register_blueprint(metrics_bp)

    @app.route('/api/test-plain')
    def _test_plain():
        from flask import jsonify
        return jsonify({'ok': True})

    @app.route('/api/test-rate-limited')
    def _test_rate_limited():
        from flask import jsonify
        from utils.rate_limiter import rate_limit
        @rate_limit(limit=3)
        def _inner():
            return jsonify({'ok': True})
        return _inner()

    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# E.1 — Security Headers + Input Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityHeaders:
    """E.1.1: Security headers are set on every response."""

    def test_nosniff_header(self, client):
        resp = client.get('/api/test-plain')
        assert resp.headers['X-Content-Type-Options'] == 'nosniff'

    def test_frame_options(self, client):
        resp = client.get('/api/test-plain')
        assert resp.headers['X-Frame-Options'] == 'SAMEORIGIN'

    def test_xss_protection(self, client):
        resp = client.get('/api/test-plain')
        assert resp.headers['X-XSS-Protection'] == '1; mode=block'

    def test_referrer_policy(self, client):
        resp = client.get('/api/test-plain')
        assert resp.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'

    def test_cors_allowed_origin(self, client):
        resp = client.get('/api/test-plain', headers={'Origin': 'http://localhost:5050'})
        assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5050'

    def test_cors_blocked_origin(self, client):
        resp = client.get('/api/test-plain', headers={'Origin': 'http://evil.com'})
        assert 'Access-Control-Allow-Origin' not in resp.headers


class TestInputValidation:
    """E.1.3: Input sanitisation helpers."""

    def test_sanitize_text_strips_control_chars(self):
        from utils.security_headers import sanitize_text
        assert sanitize_text('hello\x00world') == 'helloworld'
        assert sanitize_text('tabs\tok\nnewlines') == 'tabs\tok\nnewlines'

    def test_sanitize_text_enforces_length(self):
        from utils.security_headers import sanitize_text
        assert len(sanitize_text('a' * 20000, max_length=100)) == 100

    def test_sanitize_text_non_string(self):
        from utils.security_headers import sanitize_text
        assert sanitize_text(None) == ''
        assert sanitize_text(42) == ''

    def test_validate_id_valid(self):
        from utils.security_headers import validate_id
        assert validate_id('abc-123_XYZ') == 'abc-123_XYZ'

    def test_validate_id_rejects_special_chars(self):
        from utils.security_headers import validate_id
        assert validate_id('abc; DROP TABLE') is None
        assert validate_id('../etc/passwd') is None
        assert validate_id('<script>') is None

    def test_validate_id_empty_or_long(self):
        from utils.security_headers import validate_id
        assert validate_id('') is None
        assert validate_id('a' * 100) is None

    def test_validate_int_valid(self):
        from utils.security_headers import validate_int
        assert validate_int('42', min_val=0, max_val=100) == 42
        assert validate_int(7, min_val=0, max_val=100) == 7

    def test_validate_int_out_of_range(self):
        from utils.security_headers import validate_int
        assert validate_int('200', min_val=0, max_val=100) is None
        assert validate_int('-5', min_val=0, max_val=100) is None

    def test_validate_int_non_numeric(self):
        from utils.security_headers import validate_int
        assert validate_int('abc') is None
        assert validate_int(None) is None


# ═══════════════════════════════════════════════════════════════════════════════
# E.1.2 — Rate Limiter
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    """E.1.2: Token-bucket rate limiting."""

    def test_allows_within_limit(self):
        from utils.rate_limiter import _check_rate
        for _ in range(5):
            allowed, _ = _check_rate('1.2.3.4', 10)
            assert allowed

    def test_blocks_over_limit(self):
        from utils.rate_limiter import _check_rate
        for _ in range(3):
            _check_rate('5.6.7.8', 3)
        allowed, retry = _check_rate('5.6.7.8', 3)
        assert not allowed
        assert retry >= 1

    def test_different_ips_independent(self):
        from utils.rate_limiter import _check_rate
        for _ in range(5):
            _check_rate('10.0.0.1', 5)
        allowed_a, _ = _check_rate('10.0.0.1', 5)
        allowed_b, _ = _check_rate('10.0.0.2', 5)
        assert not allowed_a
        assert allowed_b

    def test_http_429_returned(self, client):
        """Rate-limited endpoint returns 429 after exceeding limit."""
        for _ in range(3):
            resp = client.get('/api/test-rate-limited')
            assert resp.status_code == 200
        resp = client.get('/api/test-rate-limited')
        assert resp.status_code == 429
        data = json.loads(resp.data)
        assert 'Rate limit' in data['error']
        assert 'Retry-After' in resp.headers


# ═══════════════════════════════════════════════════════════════════════════════
# E.2 — Response Cache
# ═══════════════════════════════════════════════════════════════════════════════

class TestResponseCache:
    """E.2.3: TTL cache with ETag support."""

    def _reset_cache(self):
        from utils.response_cache import _cache
        _cache.clear()

    def test_cached_json_returns_etag(self):
        """Decorated endpoint includes ETag header."""
        from flask import Flask, jsonify
        from utils.response_cache import cached_json

        app = Flask(__name__)

        @app.route('/cached')
        @cached_json(ttl_seconds=60)
        def cached_ep():
            return jsonify({'value': 42})

        self._reset_cache()
        with app.test_client() as c:
            resp = c.get('/cached')
            assert resp.status_code == 200
            assert 'ETag' in resp.headers
            assert resp.headers['Cache-Control'] == 'max-age=60'

    def test_etag_304_not_modified(self):
        """If-None-Match with matching ETag returns 304."""
        from flask import Flask, jsonify
        from utils.response_cache import cached_json

        app = Flask(__name__)

        @app.route('/cached2')
        @cached_json(ttl_seconds=60)
        def cached_ep2():
            return jsonify({'value': 99})

        self._reset_cache()
        with app.test_client() as c:
            resp1 = c.get('/cached2')
            etag = resp1.headers['ETag']
            resp2 = c.get('/cached2', headers={'If-None-Match': etag})
            assert resp2.status_code == 304

    def test_invalidate_clears_cache(self):
        """invalidate() clears cached entries."""
        from utils.response_cache import _cache, invalidate
        self._reset_cache()
        _cache['test_key'] = ('data', '"etag"', time.monotonic() + 999)
        invalidate()
        assert len(_cache) == 0

    def test_invalidate_by_prefix(self):
        """invalidate(prefix) clears only matching entries."""
        from utils.response_cache import _cache, invalidate
        self._reset_cache()
        _cache['foo:1'] = ('data', '"e1"', time.monotonic() + 999)
        _cache['foo:2'] = ('data', '"e2"', time.monotonic() + 999)
        _cache['bar:1'] = ('data', '"e3"', time.monotonic() + 999)
        invalidate('foo')
        assert 'bar:1' in _cache
        assert 'foo:1' not in _cache


# ═══════════════════════════════════════════════════════════════════════════════
# E.3 — Observability
# ═══════════════════════════════════════════════════════════════════════════════

class TestStructuredLogger:
    """E.3.1: JSON structured logging."""

    def test_json_formatter_output(self):
        from utils.structured_logger import JSONFormatter
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='hello world', args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed['level'] == 'INFO'
        assert parsed['message'] == 'hello world'
        assert 'timestamp' in parsed

    def test_json_formatter_with_exception(self):
        from utils.structured_logger import JSONFormatter
        fmt = JSONFormatter()
        try:
            raise ValueError('boom')
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name='test', level=logging.ERROR, pathname='', lineno=0,
            msg='failed', args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert 'exception' in parsed
        assert 'ValueError' in parsed['exception']

    def test_get_request_id_outside_flask(self):
        """get_request_id works outside Flask context (returns uuid)."""
        from utils.structured_logger import get_request_id
        rid = get_request_id()
        assert isinstance(rid, str)
        assert len(rid) >= 8


class TestMetricsEndpoint:
    """E.3.2: /api/metrics operational counters."""

    def test_metrics_returns_json(self, client, db_conn):
        resp = client.get('/api/metrics')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'agents_total' in data
        assert 'agents_active' in data
        assert 'proposals_by_status' in data
        assert 'bus_events_24h' in data
        assert 'node_count' in data

    def test_metrics_values_match_seed(self, client, db_conn):
        resp = client.get('/api/metrics')
        data = json.loads(resp.data)
        assert data['agents_total'] == 2
        assert data['agents_active'] == 1  # only gemma enabled
        assert data['proposals_by_status'].get('approved') == 1
        assert data['bus_events_24h'] >= 1
