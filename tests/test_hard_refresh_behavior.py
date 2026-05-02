"""Batch W regression tests — hard-refresh behaviour locks +
seven memory_backfill coverage.

Stories covered:
  MD-FEATURE-32DFD66D8BA4   Hard refresh: main chat not opening new thread
  MD-FEATURE-9792296AF505   Hard refresh in main chat doesn't open new thread or prompt for login
  MD-FEATURE-A138E31DED58   Hard refresh: no login prompt
  MD-FEATURE-CF62818FFAF0   Seven thought-thread bug (memory_backfill module)

The first three stories were filed as "needs clarification" investigations;
the right resolution is to lock the *current* observable behaviour with
behaviour-locking tests so any future regression is loud, and to leave a
clear comment in the JS pointing at this file. (See conversations.js header.)

The fourth story exercises the existing repair tool end-to-end against an
in-memory schema so the contract is no longer untested.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Hard-refresh trio (behaviour locks) ──────────────────────────────────


@pytest.fixture
def flask_client():
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestAuthHardRefresh:
    def test_auth_me_returns_ok_shape_when_logged_out(self, flask_client):
        rv = flask_client.get('/api/auth/me')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        # When not logged in, user is None; the JS uses this to decide whether
        # to show the login overlay. (Hard-refresh: no login prompt issue.)
        assert 'user' in data

    def test_setup_status_returns_owner_username(self, flask_client):
        rv = flask_client.get('/api/auth/setup-status')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert data['owner_username'] == 'ghost'
        assert 'owner_has_password' in data

    def test_auth_check_endpoints_match_friday_auth_js(self):
        """Friday-auth.js calls these endpoints on DOMContentLoaded.
        Locking the URL strings so a refactor doesn't silently break the
        hard-refresh path."""
        js = (REPO_ROOT / 'frontend' / 'static' / 'js' / 'friday-auth.js').read_text()
        assert "fetch('/api/auth/me')" in js
        assert "/api/auth/setup-status" in js


class TestChatHardRefresh:
    def test_load_chat_data_defaults_to_fresh_thread(self):
        js = (REPO_ROOT / 'frontend' / 'static' / 'js' / 'views' / 'conversations.js').read_text()
        # The "default to fresh thread" Session 28 behaviour must remain locked.
        assert '__fridaysChatOpenWithConvId' in js
        assert '__fridaysChatForceNewThread = true' in js

    def test_load_chat_data_one_shot_open_with_conv_id(self):
        js = (REPO_ROOT / 'frontend' / 'static' / 'js' / 'views' / 'conversations.js').read_text()
        # Should null the window var after reading it (one-shot semantics).
        assert 'window.__fridaysChatOpenWithConvId = null' in js

    def test_hard_refresh_doc_pointer_present(self):
        """The header comment block in conversations.js must reference all
        three investigation tickets so future readers find this lock."""
        js = (REPO_ROOT / 'frontend' / 'static' / 'js' / 'views' / 'conversations.js').read_text()
        for ticket in (
            'MD-FEATURE-32DFD66D8BA4',
            '-9792296AF505',
            '-A138E31DED58',
        ):
            assert ticket in js, f'conversations.js missing pointer to {ticket}'


# ── Seven memory_backfill (CF62818FFAF0) ─────────────────────────────────


@pytest.fixture
def db_with_gap(monkeypatch):
    """Build an in-memory db with a Seven thread that has a queue->memory gap."""
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
        CREATE TABLE queue (
            id INTEGER PRIMARY KEY,
            thread_id INTEGER,
            prompt TEXT,
            response TEXT,
            created_at REAL
        );
        CREATE TABLE agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT,
            message TEXT,
            context TEXT,
            tags TEXT,
            importance INTEGER,
            created_at REAL
        );
    """)
    # Three queue turns on thread 2112; only the first one has a memory row.
    conn.executemany(
        "INSERT INTO queue (id, thread_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 2112, 'q1', 'a1', 1000.0),
            (2, 2112, 'q2', 'a2', 1010.0),
            (3, 2112, 'q3', 'a3', 1020.0),
        ],
    )
    conn.execute(
        "INSERT INTO agent_memory (agent, message, context, tags, importance, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ('seven', 'q1\n---\na1', 'thread_2112:queue_1', 'live', 5, 1000.0),
    )
    conn.commit()

    # Patch database.get_connection to return our in-memory conn.
    import database as db_mod
    monkeypatch.setattr(db_mod, 'get_connection', lambda: _ProxyConn(conn))
    yield conn
    conn.close()


class _ProxyConn:
    """Swallows close() so a single in-memory db survives multiple callers."""
    def __init__(self, real):
        object.__setattr__(self, '_real', real)
    def close(self):
        return None
    def __getattr__(self, name):
        return getattr(self._real, name)
    def __setattr__(self, name, value):
        if name == '_real':
            object.__setattr__(self, name, value)
        else:
            setattr(self._real, name, value)


class TestMemoryBackfill:
    def test_module_exposes_run_and_repair_thread(self):
        from agents.seven import memory_backfill as mb
        assert callable(mb.run)
        assert callable(mb.repair_thread)
        assert callable(mb._iter_gap_threads)

    def test_repair_writes_missing_rows(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        monkeypatch.setattr(mb, 'AUDIT_LOG', tmp_path / 'repair.log')
        before = db_with_gap.execute(
            "SELECT COUNT(*) FROM agent_memory WHERE agent='seven'"
        ).fetchone()[0]
        assert before == 1
        out = mb.run()
        assert out['ok'] is True
        assert out['rows_written'] == 2  # turns 2 and 3 backfilled
        after = db_with_gap.execute(
            "SELECT COUNT(*) FROM agent_memory WHERE agent='seven'"
        ).fetchone()[0]
        assert after == 3

    def test_repair_is_idempotent(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        monkeypatch.setattr(mb, 'AUDIT_LOG', tmp_path / 'repair.log')
        first = mb.run()
        second = mb.run()
        assert first['rows_written'] == 2
        assert second['rows_written'] == 0

    def test_repair_tags_backfilled_rows(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        monkeypatch.setattr(mb, 'AUDIT_LOG', tmp_path / 'repair.log')
        mb.run()
        rows = db_with_gap.execute(
            "SELECT tags FROM agent_memory WHERE context LIKE 'thread_2112:queue_2'"
        ).fetchall()
        assert rows
        assert any('thread_repair' in (r[0] or '') for r in rows)

    def test_dry_run_writes_nothing(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        monkeypatch.setattr(mb, 'AUDIT_LOG', tmp_path / 'repair.log')
        out = mb.run(dry_run=True)
        assert out['rows_written'] == 0
        # Memory still has only the original row.
        cnt = db_with_gap.execute(
            "SELECT COUNT(*) FROM agent_memory WHERE agent='seven'"
        ).fetchone()[0]
        assert cnt == 1

    def test_audit_log_emitted(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        log_path = tmp_path / 'seven_repair.log'
        monkeypatch.setattr(mb, 'AUDIT_LOG', log_path)
        mb.run()
        assert log_path.exists()
        text = log_path.read_text()
        assert '"ok": true' in text or '"rows_written": 2' in text

    def test_repair_thread_helper_returns_count(self, db_with_gap, tmp_path, monkeypatch):
        from agents.seven import memory_backfill as mb
        monkeypatch.setattr(mb, 'AUDIT_LOG', tmp_path / 'repair.log')
        n = mb.repair_thread(db_with_gap, 2112)
        assert n == 2
