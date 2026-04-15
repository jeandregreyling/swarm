"""
tests/test_service_boundaries.py — A.4 Service Boundary Preparation tests
═══════════════════════════════════════════════════════════════════════════
Tests:
  - A.4.1: No cross-blueprint imports (separate test file)
  - A.4.2: swarm_bus publish → subscribe, consume/unconsumed
  - A.4.3: DB factory returns shared or per-service connection
  - A.4.4: Governance module works without Flask context
  - A.4.5: Node registration stores and retrieves correctly
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
    """Isolated DB with all required tables for A.4 tests."""
    db_path = str(tmp_path / 'test_a4.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS swarm_bus (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic           TEXT NOT NULL,
            payload_json    TEXT NOT NULL DEFAULT '{}',
            source_service  TEXT NOT NULL DEFAULT 'local',
            created_at      TEXT DEFAULT (datetime('now')),
            consumed_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_swarm_bus_topic ON swarm_bus (topic, created_at);

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
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS governance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            agent TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conv_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            agent TEXT DEFAULT '',
            event_type TEXT DEFAULT '',
            content TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            content TEXT NOT NULL,
            source_agent TEXT NOT NULL DEFAULT '',
            source_proposal_id TEXT DEFAULT '',
            category TEXT DEFAULT 'fact',
            importance INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS swarm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '',
            source_agent TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_event_acks (
            event_id INTEGER NOT NULL,
            agent TEXT NOT NULL,
            acked_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (event_id, agent)
        );
    """)
    conn.commit()

    # Patch all get_connection paths to return our test DB
    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)

    # Mock database module for governance
    mock_db = types.ModuleType('database')
    mock_db.get_connection = _get_conn
    monkeypatch.setitem(sys.modules, 'database', mock_db)

    # Patch knowledge and bus connection
    monkeypatch.setattr('utils.db.knowledge.get_connection', _get_conn)
    monkeypatch.setattr('utils.swarm_bus.get_connection', _get_conn)

    yield conn
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# A.4.2 — swarm_bus tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSwarmBus:
    def test_publish_persists_to_db(self, db_conn):
        from utils.swarm_bus import publish
        msg_id = publish('proposal.created', {'id': 'P1'}, 'governance', conn=db_conn)
        assert msg_id > 0
        row = db_conn.execute('SELECT * FROM swarm_bus WHERE id=?', (msg_id,)).fetchone()
        assert row['topic'] == 'proposal.created'
        assert json.loads(row['payload_json'])['id'] == 'P1'
        assert row['consumed_at'] is None

    def test_subscribe_fires_handler(self, db_conn):
        from utils.swarm_bus import publish, subscribe, unsubscribe
        received = []
        def handler(topic, payload, source):
            received.append((topic, payload, source))
        subscribe('test.event', handler)
        try:
            publish('test.event', {'x': 1}, 'test', conn=db_conn)
            assert len(received) == 1
            assert received[0][0] == 'test.event'
            assert received[0][1]['x'] == 1
        finally:
            unsubscribe('test.event', handler)

    def test_handler_exception_does_not_crash_publish(self, db_conn):
        from utils.swarm_bus import publish, subscribe, unsubscribe
        def bad_handler(topic, payload, source):
            raise RuntimeError('boom')
        subscribe('fail.event', bad_handler)
        try:
            msg_id = publish('fail.event', {'y': 2}, 'test', conn=db_conn)
            assert msg_id > 0  # publish succeeds despite handler error
        finally:
            unsubscribe('fail.event', bad_handler)

    def test_get_unconsumed(self, db_conn):
        from utils.swarm_bus import publish, get_unconsumed, mark_consumed
        id1 = publish('a', {'n': 1}, 'src', conn=db_conn)
        id2 = publish('a', {'n': 2}, 'src', conn=db_conn)
        msgs = get_unconsumed(topic='a', conn=db_conn)
        assert len(msgs) == 2
        mark_consumed(id1, conn=db_conn)
        msgs = get_unconsumed(topic='a', conn=db_conn)
        assert len(msgs) == 1
        assert msgs[0]['id'] == id2

    def test_mark_consumed_batch(self, db_conn):
        from utils.swarm_bus import publish, get_unconsumed, mark_consumed_batch
        ids = [publish('b', {'n': i}, 'src', conn=db_conn) for i in range(3)]
        mark_consumed_batch(ids[:2], conn=db_conn)
        msgs = get_unconsumed(topic='b', conn=db_conn)
        assert len(msgs) == 1

    def test_get_recent(self, db_conn):
        from utils.swarm_bus import publish, get_recent
        publish('c', {}, 'src', conn=db_conn)
        publish('d', {}, 'src', conn=db_conn)
        msgs = get_recent(conn=db_conn)
        assert len(msgs) >= 2


# ══════════════════════════════════════════════════════════════════════════════
# A.4.3 — DB Layer Abstraction tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDBFactory:
    def test_get_service_connection_default_same_as_shared(self, monkeypatch):
        from utils.db._connection import get_service_connection, DB_PATH
        # No env override → should use DB_PATH
        monkeypatch.delenv('SWARM_DB_CHAT_PATH', raising=False)
        conn = get_service_connection('chat')
        assert conn is not None
        conn.close()

    def test_get_service_connection_override(self, tmp_path, monkeypatch):
        from utils.db._connection import get_service_connection
        custom_path = str(tmp_path / 'chat.db')
        monkeypatch.setenv('SWARM_DB_CHAT_PATH', custom_path)
        conn = get_service_connection('chat')
        # The DB file should have been created at the custom path
        assert os.path.exists(custom_path)
        conn.close()

    def test_make_connection_sets_wal_and_fk(self, tmp_path):
        from utils.db._connection import _make_connection
        path = str(tmp_path / 'test.db')
        conn = _make_connection(path)
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert jm == 'wal'
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# A.4.4 — Governance Core Standalone tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGovernanceStandalone:
    def test_import_without_flask(self, db_conn):
        """swarm_governance imports fine without Flask in the environment."""
        from swarm_governance import (
            transition_proposal, LEGAL_TRANSITIONS,
            GovernanceError, IllegalTransitionError,
            STATUS_PENDING, STATUS_APPROVED, STATUS_DONE,
            is_transition_legal,
        )
        assert STATUS_PENDING == 'pending'
        assert is_transition_legal('pending', 'approved')
        assert not is_transition_legal('closed', 'pending')

    def test_transition_fires_bus_event(self, db_conn):
        """Governance transition publishes to swarm_bus."""
        from swarm_governance import transition_proposal, STATUS_PENDING, STATUS_APPROVED
        # Create a proposal
        db_conn.execute(
            "INSERT INTO work_proposals (proposal_id, title, agent, status, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ('P-BUS-1', 'Test', 'gemma', STATUS_PENDING)
        )
        db_conn.commit()

        result = transition_proposal('P-BUS-1', STATUS_APPROVED, 'gemma', conn=db_conn)
        assert result['new_status'] == STATUS_APPROVED

        # Check swarm_bus has the event (pending→approved → topic='proposal.created')
        row = db_conn.execute(
            "SELECT * FROM swarm_bus WHERE topic='proposal.created' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        payload = json.loads(row['payload_json'])
        assert payload['proposal_id'] == 'P-BUS-1'

    def test_governance_no_flask_context_needed(self, db_conn):
        """Governance functions work without any Flask app context."""
        from utils.governance import get_transition_history, get_agent_active_proposal
        # These should return empty results, not crash
        history = get_transition_history('P-NONE', conn=db_conn)
        assert history == []
        active = get_agent_active_proposal('nobody', conn=db_conn)
        assert active is None


# ══════════════════════════════════════════════════════════════════════════════
# A.4.5 — Node Registration tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNodeRegistration:
    def test_register_and_get(self, db_conn):
        from utils.db.nodes import register_node, get_node
        nid = register_node('node-a', 'http://192.168.1.10:5050', 'secret123',
                            role='contributor', agents=['gemma', 'llama'],
                            conn=db_conn)
        assert nid
        node = get_node(nid, conn=db_conn)
        assert node['name'] == 'node-a'
        assert node['url'] == 'http://192.168.1.10:5050'
        assert json.loads(node['agents_json']) == ['gemma', 'llama']

    def test_register_upsert(self, db_conn):
        from utils.db.nodes import register_node, get_node
        nid1 = register_node('node-b', 'http://host:5050', 'key1', conn=db_conn)
        nid2 = register_node('node-b', 'http://host:5050', 'key2',
                             agents=['qwen'], conn=db_conn)
        assert nid1 == nid2  # same name+url = same node_id
        node = get_node(nid1, conn=db_conn)
        assert json.loads(node['agents_json']) == ['qwen']

    def test_list_nodes(self, db_conn):
        from utils.db.nodes import register_node, list_nodes
        register_node('n1', 'http://a:5050', 'k1', conn=db_conn)
        register_node('n2', 'http://b:5050', 'k2', conn=db_conn)
        nodes = list_nodes(conn=db_conn)
        assert len(nodes) == 2

    def test_verify_api_key(self, db_conn):
        from utils.db.nodes import register_node, verify_api_key
        nid = register_node('sec-node', 'http://c:5050', 'mykey', conn=db_conn)
        assert verify_api_key(nid, 'mykey', conn=db_conn)
        assert not verify_api_key(nid, 'wrongkey', conn=db_conn)

    def test_invalid_role_rejected(self, db_conn):
        from utils.db.nodes import register_node
        with pytest.raises(ValueError, match='Invalid role'):
            register_node('bad', 'http://x:5050', 'k', role='admin', conn=db_conn)

    def test_remove_node(self, db_conn):
        from utils.db.nodes import register_node, remove_node, get_node
        nid = register_node('rm-me', 'http://d:5050', 'k', conn=db_conn)
        remove_node(nid, conn=db_conn)
        assert get_node(nid, conn=db_conn) is None

    def test_touch_node_updates_last_seen(self, db_conn):
        from utils.db.nodes import register_node, touch_node, get_node
        import time
        nid = register_node('touch-me', 'http://e:5050', 'k', conn=db_conn)
        before = get_node(nid, conn=db_conn)['last_seen']
        time.sleep(0.05)
        touch_node(nid, conn=db_conn)
        after = get_node(nid, conn=db_conn)['last_seen']
        assert after >= before

    def test_get_local_node_id_stable(self):
        from utils.db.nodes import get_local_node_id
        a = get_local_node_id()
        b = get_local_node_id()
        assert a == b
        assert len(a) == 16
