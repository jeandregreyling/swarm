"""
tests/test_shared_knowledge.py — A.3 Shared Memory + Living Landscape tests
═══════════════════════════════════════════════════════════════════════════════
Tests:
  - A.3.1: Knowledge write/read, governed writes, ghost direct
  - A.3.2: Auto-publish on proposal → done
  - A.3.3: search_landscape finds known entries, JSON generation
  - A.3.4: Events emitted, unacked/ack flow
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
def mem_conn(tmp_path, monkeypatch):
    """In-memory DB with all required tables for knowledge tests."""
    db_path = str(tmp_path / 'test.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Create tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS swarm_knowledge (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            key             TEXT NOT NULL,
            content         TEXT NOT NULL,
            source_agent    TEXT NOT NULL DEFAULT '',
            source_proposal_id TEXT DEFAULT '',
            category        TEXT NOT NULL DEFAULT 'fact',
            importance      INTEGER DEFAULT 5,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '',
            source_agent TEXT NOT NULL DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS swarm_event_acks (
            event_id    INTEGER NOT NULL,
            agent       TEXT NOT NULL,
            acked_at    TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (event_id, agent)
        );
        CREATE TABLE IF NOT EXISTS work_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE NOT NULL,
            agent TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            updated_at TEXT DEFAULT (datetime('now')),
            source_conv_id INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS governance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            old_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            agent TEXT DEFAULT '',
            actor TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS conv_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER NOT NULL,
            agent TEXT DEFAULT '',
            event_type TEXT NOT NULL,
            payload TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            job_id TEXT DEFAULT ''
        );
    """)
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)

    # Patch database module (governance.py imports from database)
    try:
        import database
        monkeypatch.setattr(database, 'get_connection', _get_conn)
    except ImportError:
        # Create a mock database module
        import types
        database_mod = types.ModuleType('database')
        database_mod.get_connection = _get_conn
        database_mod.DB_PATH = db_path
        monkeypatch.setitem(sys.modules, 'database', database_mod)

    # Patch utils.db.knowledge directly (module-level import)
    try:
        import utils.db.knowledge
        monkeypatch.setattr(utils.db.knowledge, 'get_connection', _get_conn)
    except Exception:
        pass

    # Patch utils.db.auth (used by trust gate)
    try:
        import utils.db.auth
        monkeypatch.setattr(utils.db.auth, 'get_connection', _get_conn)
    except Exception:
        pass

    yield conn
    conn.close()


# ── A.3.1: Knowledge CRUD ────────────────────────────────────────────────────

class TestKnowledgeCRUD:

    def test_write_and_search(self, mem_conn):
        from utils.db.knowledge import write_knowledge, search_knowledge
        row_id = write_knowledge('test-key', 'test content value', 'gemma',
                                 category='lesson', importance=7, conn=mem_conn)
        mem_conn.commit()
        assert row_id is not None
        results = search_knowledge('test content', conn=mem_conn)
        assert len(results) >= 1
        assert results[0]['key'] == 'test-key'
        assert results[0]['category'] == 'lesson'

    def test_search_no_results(self, mem_conn):
        from utils.db.knowledge import search_knowledge
        results = search_knowledge('zzz_nonexistent_zzz', conn=mem_conn)
        assert results == []

    def test_invalid_category_rejected(self, mem_conn):
        from utils.db.knowledge import write_knowledge
        with pytest.raises(ValueError, match='Invalid category'):
            write_knowledge('k', 'c', 'ghost', category='invalid', conn=mem_conn)

    def test_search_by_category_filter(self, mem_conn):
        from utils.db.knowledge import write_knowledge, search_knowledge
        write_knowledge('warn-key', 'something dangerous', 'ghost',
                        category='warning', conn=mem_conn)
        write_knowledge('fact-key', 'something factual', 'ghost',
                        category='fact', conn=mem_conn)
        mem_conn.commit()
        warnings = search_knowledge('something', category='warning', conn=mem_conn)
        assert len(warnings) == 1
        assert warnings[0]['category'] == 'warning'

    def test_ghost_direct_write(self, mem_conn):
        """Ghost can write directly (no proposal context needed)."""
        from utils.db.knowledge import write_knowledge
        row_id = write_knowledge('ghost-direct', 'ghost writes directly', 'ghost',
                                 category='decision', conn=mem_conn)
        mem_conn.commit()
        assert row_id > 0

    def test_get_by_proposal(self, mem_conn):
        from utils.db.knowledge import write_knowledge, get_knowledge_by_proposal
        write_knowledge('p1-entry', 'content for proposal', 'gemma',
                        source_proposal_id='WP-0099', category='fact', conn=mem_conn)
        mem_conn.commit()
        entries = get_knowledge_by_proposal('WP-0099', conn=mem_conn)
        assert len(entries) == 1
        assert entries[0]['source_proposal_id'] == 'WP-0099'


# ── A.3.2: Auto-Publish on Done ──────────────────────────────────────────────

class TestAutoPublish:

    def test_proposal_done_creates_knowledge(self, mem_conn, monkeypatch):
        """Completing a proposal auto-publishes to swarm_knowledge."""
        # Seed a proposal
        mem_conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, description, status, updated_at) "
            "VALUES ('WP-TEST-AP', 'gemma', 'Test Proposal', 'Description here', 'in_progress', datetime('now'))"
        )
        mem_conn.commit()

        # Disable auto-checkpoint to avoid GitPython dependency
        monkeypatch.setattr('utils.governance._auto_checkpoint', lambda *a, **kw: None)

        from utils.governance import transition_proposal
        result = transition_proposal('WP-TEST-AP', 'done', 'gemma', conn=mem_conn)
        mem_conn.commit()

        assert result['new_status'] == 'done'

        # Check that knowledge was auto-published
        rows = mem_conn.execute(
            "SELECT * FROM swarm_knowledge WHERE source_proposal_id='WP-TEST-AP'"
        ).fetchall()
        assert len(rows) >= 1
        assert 'Test Proposal' in rows[0]['content']

    def test_non_done_transition_no_knowledge(self, mem_conn, monkeypatch):
        """Non-done transitions should NOT create knowledge entries."""
        mem_conn.execute(
            "INSERT INTO work_proposals (proposal_id, agent, title, description, status, updated_at) "
            "VALUES ('WP-TEST-ND', 'llama', 'Another Prop', 'Desc', 'pending', datetime('now'))"
        )
        mem_conn.commit()

        monkeypatch.setattr('utils.governance._auto_checkpoint', lambda *a, **kw: None)

        from utils.governance import transition_proposal
        transition_proposal('WP-TEST-ND', 'approved', 'llama', conn=mem_conn)
        mem_conn.commit()

        rows = mem_conn.execute(
            "SELECT * FROM swarm_knowledge WHERE source_proposal_id='WP-TEST-ND'"
        ).fetchall()
        assert len(rows) == 0


# ── A.3.3: Living Landscape ──────────────────────────────────────────────────

class TestLivingLandscape:

    def test_json_generation(self):
        """generate_landscape_json produces valid JSON with expected sections."""
        from scripts.generate_landscape_json import generate
        path, count = generate()
        assert os.path.exists(path)
        assert count > 0
        with open(path) as f:
            data = json.load(f)
        for key in ['python_modules', 'blueprints', 'db_tables', 'agents', 'skills']:
            assert key in data, f'Missing section: {key}'
            assert isinstance(data[key], list)

    def test_search_landscape_skill(self, mem_conn):
        """SKILL search_landscape finds known entries in the JSON."""
        # Ensure JSON index exists
        from scripts.generate_landscape_json import generate
        generate()

        from fridays.skills import call
        ok, output = call('search_landscape', 'proposals', agent='ghost')
        assert ok
        assert 'proposals' in output.lower() or 'No landscape' not in output

    def test_search_landscape_no_match(self, mem_conn):
        from scripts.generate_landscape_json import generate
        generate()
        from fridays.skills import call
        ok, output = call('search_landscape', 'zzz_nonexistent_zzz_widget', agent='ghost')
        assert ok
        assert 'No landscape matches' in output

    def test_md_still_generated(self):
        """update_landscape also regenerates the MD index."""
        from scripts.generate_system_index import generate
        path, lines = generate()
        assert os.path.exists(path)
        assert lines > 0


# ── A.3.4: Memory Broadcast / Events ─────────────────────────────────────────

class TestMemoryBroadcast:

    def test_knowledge_write_emits_event(self, mem_conn):
        """Writing knowledge auto-emits a knowledge.new event."""
        from utils.db.knowledge import write_knowledge
        write_knowledge('event-test', 'some content', 'gemma',
                        category='fact', conn=mem_conn)
        mem_conn.commit()
        events = mem_conn.execute(
            "SELECT * FROM swarm_events WHERE event_type='knowledge.new'"
        ).fetchall()
        assert len(events) >= 1
        payload = json.loads(events[0]['payload'])
        assert payload['key'] == 'event-test'
        assert payload['source_agent'] == 'gemma'

    def test_unacked_events_visible(self, mem_conn):
        """Agent sees unacked events."""
        from utils.db.knowledge import write_knowledge, get_unacked_events
        write_knowledge('vis-test', 'content', 'ghost', category='lesson', conn=mem_conn)
        mem_conn.commit()
        events = get_unacked_events('llama', event_type='knowledge.new', conn=mem_conn)
        assert len(events) >= 1

    def test_ack_hides_event(self, mem_conn):
        """After acking, the event is no longer visible to that agent."""
        from utils.db.knowledge import write_knowledge, get_unacked_events, ack_event
        write_knowledge('ack-test', 'content', 'ghost', category='pattern', conn=mem_conn)
        mem_conn.commit()
        events = get_unacked_events('qwen', conn=mem_conn)
        assert len(events) >= 1
        ack_event(events[0]['id'], 'qwen', conn=mem_conn)
        mem_conn.commit()
        events_after = get_unacked_events('qwen', event_type='knowledge.new', conn=mem_conn)
        assert len(events_after) == 0

    def test_ack_only_for_that_agent(self, mem_conn):
        """Acking for one agent doesn't hide from another."""
        from utils.db.knowledge import write_knowledge, get_unacked_events, ack_event
        write_knowledge('cross-test', 'content', 'ghost', category='fact', conn=mem_conn)
        mem_conn.commit()
        events = get_unacked_events('gemma', conn=mem_conn)
        assert len(events) >= 1
        ack_event(events[0]['id'], 'gemma', conn=mem_conn)
        mem_conn.commit()
        # llama should still see it
        llama_events = get_unacked_events('llama', event_type='knowledge.new', conn=mem_conn)
        assert len(llama_events) >= 1

    def test_prompt_broadcast_block(self, mem_conn, monkeypatch):
        """The broadcast block injects unacked knowledge into agent prompts."""
        from utils.db.knowledge import write_knowledge
        write_knowledge('prompt-test', 'important insight', 'ghost',
                        category='warning', conn=mem_conn)
        mem_conn.commit()

        from frontend.blueprints.chat import _build_knowledge_broadcast_block
        block = _build_knowledge_broadcast_block('gemma')
        assert 'New swarm knowledge' in block
        assert 'prompt-test' in block

        # After building, events should be acked
        block2 = _build_knowledge_broadcast_block('gemma')
        assert block2 == ''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
