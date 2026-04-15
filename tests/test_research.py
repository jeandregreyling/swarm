"""
tests/test_research.py — Phase B research integration tests
═══════════════════════════════════════════════════════════════════════════════
Tests B.1 (tables/CRUD), B.2 (workflow), B.3 (skills), B.5 (learning cycle).
"""

import json
import os
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def research_db(tmp_path, monkeypatch):
    """Isolated DB with full schema including research tables."""
    db_path = str(tmp_path / 'test_research.db')

    def _get_conn():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    # Create schema
    from utils.db._schema import SCHEMA
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()

    # Monkeypatch all connection sources
    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    monkeypatch.setattr('utils.db.research.get_connection', _get_conn)

    # Also patch knowledge and bus connections
    try:
        monkeypatch.setattr('utils.db.knowledge.get_connection', _get_conn)
    except Exception:
        pass
    try:
        monkeypatch.setattr('utils.swarm_bus.get_connection', _get_conn)
    except Exception:
        pass

    yield conn
    conn.close()


# ── B.1 — Research Tables + CRUD ─────────────────────────────────────────

class TestResearchCRUD:
    """B.1.1 + B.1.2: session and evidence CRUD."""

    def test_create_session(self, research_db):
        from utils.db.research import create_session, get_session
        sid = create_session('Python 3.13', conn=research_db)
        assert sid is not None
        sess = get_session(sid, conn=research_db)
        assert sess['topic'] == 'Python 3.13'
        assert sess['depth'] == 'standard'
        assert sess['status'] == 'planning'

    def test_create_session_with_depth(self, research_db):
        from utils.db.research import create_session, get_session
        sid = create_session('AI safety', depth='deep', conn=research_db)
        sess = get_session(sid, conn=research_db)
        assert sess['depth'] == 'deep'

    def test_invalid_depth_raises(self, research_db):
        from utils.db.research import create_session
        with pytest.raises(ValueError, match='Invalid depth'):
            create_session('test', depth='extreme', conn=research_db)

    def test_update_session_status(self, research_db):
        from utils.db.research import create_session, update_session, get_session
        sid = create_session('test topic', conn=research_db)
        update_session(sid, status='searching', conn=research_db)
        sess = get_session(sid, conn=research_db)
        assert sess['status'] == 'searching'

    def test_update_session_phases(self, research_db):
        from utils.db.research import create_session, update_session, get_session
        sid = create_session('test', conn=research_db)
        questions = ['q1', 'q2', 'q3']
        update_session(sid, phases_json=questions, conn=research_db)
        sess = get_session(sid, conn=research_db)
        assert json.loads(sess['phases_json']) == ['q1', 'q2', 'q3']

    def test_update_session_summary(self, research_db):
        from utils.db.research import create_session, update_session, get_session
        sid = create_session('test', conn=research_db)
        update_session(sid, summary='Key finding X', conn=research_db)
        sess = get_session(sid, conn=research_db)
        assert sess['summary'] == 'Key finding X'

    def test_invalid_status_raises(self, research_db):
        from utils.db.research import create_session, update_session
        sid = create_session('test', conn=research_db)
        with pytest.raises(ValueError, match='Invalid status'):
            update_session(sid, status='exploding', conn=research_db)

    def test_list_sessions(self, research_db):
        from utils.db.research import create_session, list_sessions
        create_session('topic A', conn=research_db)
        create_session('topic B', conn=research_db)
        create_session('topic C', conn=research_db)
        sessions = list_sessions(conn=research_db)
        assert len(sessions) == 3

    def test_list_sessions_filter_status(self, research_db):
        from utils.db.research import create_session, update_session, list_sessions
        s1 = create_session('t1', conn=research_db)
        s2 = create_session('t2', conn=research_db)
        update_session(s1, status='done', conn=research_db)
        done = list_sessions(status='done', conn=research_db)
        assert len(done) == 1
        assert done[0]['topic'] == 't1'

    def test_add_evidence(self, research_db):
        from utils.db.research import create_session, add_evidence, get_evidence_for_session
        sid = create_session('test', conn=research_db)
        eid = add_evidence(sid, source_url='https://example.com',
                           title='Test', snippet='Content here',
                           confidence=0.8, collecting_agent='seeker',
                           conn=research_db)
        assert eid is not None
        evidence = get_evidence_for_session(sid, conn=research_db)
        assert len(evidence) == 1
        assert evidence[0]['source_url'] == 'https://example.com'
        assert evidence[0]['confidence'] == 0.8

    def test_evidence_deduplication(self, research_db):
        from utils.db.research import create_session, add_evidence
        sid = create_session('test', conn=research_db)
        e1 = add_evidence(sid, source_url='https://example.com',
                          snippet='Same content', conn=research_db)
        e2 = add_evidence(sid, source_url='https://example.com',
                          snippet='Same content', conn=research_db)
        assert e1 is not None
        assert e2 is None  # Duplicate rejected

    def test_count_evidence(self, research_db):
        from utils.db.research import create_session, add_evidence, count_evidence
        sid = create_session('test', conn=research_db)
        add_evidence(sid, snippet='a', conn=research_db)
        add_evidence(sid, snippet='b', conn=research_db)
        add_evidence(sid, snippet='c', conn=research_db)
        assert count_evidence(sid, conn=research_db) == 3

    def test_get_nonexistent_session(self, research_db):
        from utils.db.research import get_session
        assert get_session(99999, conn=research_db) is None


# ── B.2 — Research Workflow ──────────────────────────────────────────────

class TestResearchWorkflow:
    """B.2: workflow engine with mocked search + synthesis."""

    def test_full_workflow_quick(self, research_db):
        """Quick depth: one question, one search, synthesis, archive."""
        from utils.db.research import get_session, get_evidence_for_session

        fake_search_results = [
            {'url': 'https://a.com', 'title': 'Result A', 'snippet': 'Content A',
             'confidence': 0.8, 'source_type': 'web', 'agent': 'seeker'},
            {'url': 'https://b.com', 'title': 'Result B', 'snippet': 'Content B',
             'confidence': 0.6, 'source_type': 'web', 'agent': 'seeker'},
        ]

        with patch('fridays.research_workflow._search', return_value=fake_search_results), \
             patch('fridays.research_workflow._decompose', return_value=['test question']), \
             patch('fridays.research_workflow._synthesise', return_value='Summary of findings'), \
             patch('fridays.research_workflow._archive_to_knowledge'):

            from fridays.research_workflow import run_research
            sid, summary = run_research('test topic', depth='quick',
                                        requesting_agent='scholar', conn=research_db)

        sess = get_session(sid, conn=research_db)
        assert sess['status'] == 'done'
        assert sess['depth'] == 'quick'
        evidence = get_evidence_for_session(sid, conn=research_db)
        assert len(evidence) == 2

    def test_workflow_standard_depth(self, research_db):
        """Standard depth: 3 questions, searches each with unique results."""
        call_count = [0]

        def _unique_results(query, *, max_results=5):
            """Return unique results per call to avoid dedup collapsing."""
            batch = call_count[0]
            call_count[0] += 1
            return [
                {'url': f'https://b{batch}-{i}.com', 'title': f'R{batch}-{i}',
                 'snippet': f'Snippet batch {batch} item {i}',
                 'confidence': 0.7, 'source_type': 'web', 'agent': 'seeker'}
                for i in range(3)
            ]

        with patch('fridays.research_workflow._search', side_effect=_unique_results), \
             patch('fridays.research_workflow._decompose', return_value=['q1', 'q2', 'q3']), \
             patch('fridays.research_workflow._synthesise', return_value='Standard summary'), \
             patch('fridays.research_workflow._archive_to_knowledge'):

            from fridays.research_workflow import run_research
            sid, summary = run_research('topic', depth='standard', conn=research_db)

        from utils.db.research import get_session, count_evidence
        sess = get_session(sid, conn=research_db)
        assert sess['status'] == 'done'
        # 3 questions × 3 unique results = 9 evidence records
        assert count_evidence(sid, conn=research_db) == 9

    def test_workflow_pauses_on_error(self, research_db):
        """Workflow sets status to paused on failure."""
        with patch('fridays.research_workflow._decompose', side_effect=RuntimeError('boom')):
            from fridays.research_workflow import run_research
            with pytest.raises(RuntimeError, match='boom'):
                run_research('fail topic', depth='quick', conn=research_db)

        from utils.db.research import list_sessions
        sessions = list_sessions(conn=research_db)
        assert len(sessions) == 1
        assert sessions[0]['status'] == 'paused'

    def test_resume_workflow(self, research_db):
        """Resume picks up from where it paused."""
        from utils.db.research import create_session, update_session

        # Create a paused session with sub-questions already set
        sid = create_session('resume test', conn=research_db)
        update_session(sid, status='paused',
                       phases_json=json.dumps(['q1']), conn=research_db)

        fake_results = [
            {'url': 'https://r.com', 'title': 'R', 'snippet': 'S',
             'confidence': 0.5, 'source_type': 'web', 'agent': 'seeker'},
        ]

        with patch('fridays.research_workflow._search', return_value=fake_results), \
             patch('fridays.research_workflow._synthesise', return_value='Resumed summary'), \
             patch('fridays.research_workflow._archive_to_knowledge'):

            from fridays.research_workflow import resume_research
            ret_sid, summary = resume_research(sid, conn=research_db)

        assert ret_sid == sid
        assert 'Resumed summary' in summary

    def test_decompose_heuristic(self, research_db):
        """Heuristic decomposition produces correct number of questions."""
        from fridays.research_workflow import _decompose_heuristic
        qs = _decompose_heuristic('Python async', 3)
        assert len(qs) == 3
        assert qs[0] == 'Python async'

    def test_synthesise_fallback(self, research_db):
        """Fallback synthesis produces structured output from evidence."""
        from fridays.research_workflow import _synthesise_fallback
        evidence = [
            {'title': 'Finding 1', 'snippet': 'Detail about finding 1',
             'confidence': 0.8, 'source_url': 'https://a.com'},
            {'title': 'Finding 2', 'snippet': 'Detail about finding 2',
             'confidence': 0.3, 'source_url': 'https://b.com'},
        ]
        result = _synthesise_fallback('test', ['q1'], evidence)
        assert 'Finding 1' in result
        assert 'HIGH' in result
        assert 'LOW' in result


# ── B.3 — Research Skills ────────────────────────────────────────────────

class TestResearchSkills:
    """B.3: SKILL commands invoke the workflow correctly."""

    def test_skill_research_in_registry(self):
        from fridays.skills import REGISTRY
        assert 'research' in REGISTRY
        assert 'deep_dive' in REGISTRY
        assert 'research_status' in REGISTRY
        assert 'research_resume' in REGISTRY

    def test_skill_research_trust_level(self):
        from fridays.skills import REGISTRY
        assert REGISTRY['research']['trust_level'] == 1
        assert REGISTRY['deep_dive']['trust_level'] == 1
        assert REGISTRY['research_status']['trust_level'] == 0

    def test_skill_research_calls_workflow(self, research_db):
        from fridays.skills import _HANDLERS
        with patch('fridays.research_workflow.run_research',
                   return_value=(1, 'Mock summary')) as mock_run:
            ok, msg = _HANDLERS['research']('Python 3.13', 'scholar')
            assert ok is True
            assert 'session #1' in msg.lower()
            mock_run.assert_called_once()

    def test_skill_deep_dive_uses_deep_depth(self, research_db):
        from fridays.skills import _HANDLERS
        with patch('fridays.research_workflow.run_research',
                   return_value=(2, 'Deep summary')) as mock_run:
            ok, msg = _HANDLERS['deep_dive']('SQLite WAL', 'scholar')
            assert ok is True
            mock_run.assert_called_with('SQLite WAL', depth='deep',
                                        requesting_agent='scholar')

    def test_skill_research_status(self, research_db):
        from utils.db.research import create_session, add_evidence
        from fridays.skills import _HANDLERS

        sid = create_session('status test', conn=research_db)
        add_evidence(sid, snippet='evidence 1', conn=research_db)
        add_evidence(sid, snippet='evidence 2', conn=research_db)

        ok, msg = _HANDLERS['research_status'](str(sid), 'ghost')
        assert ok is True
        assert 'status test' in msg
        assert 'Evidence: 2' in msg

    def test_skill_research_empty_topic_fails(self, research_db):
        from fridays.skills import _HANDLERS
        ok, msg = _HANDLERS['research']('', 'scholar')
        assert ok is False

    def test_skill_research_resume_calls_workflow(self, research_db):
        from fridays.skills import _HANDLERS
        with patch('fridays.research_workflow.resume_research',
                   return_value=(5, 'Resumed')) as mock_resume:
            ok, msg = _HANDLERS['research_resume']('5', 'ghost')
            assert ok is True
            mock_resume.assert_called_once_with(5)


# ── B.5 — Learning Cycle ────────────────────────────────────────────────

class TestLearningCycle:
    """B.5: auto-lessons, pattern detection, knowledge archival."""

    def test_archive_writes_knowledge(self, research_db):
        """Completed research writes fact + lesson to swarm_knowledge."""
        from fridays.research_workflow import _archive_to_knowledge

        # Patch lesson extraction to return a known lesson
        with patch('fridays.research_workflow._extract_lesson',
                   return_value='Always validate inputs'):
            _archive_to_knowledge(1, 'validation tips',
                                  'Summary about input validation best practices',
                                  'scholar', conn=research_db)

        # Check knowledge was written
        rows = research_db.execute(
            "SELECT key, category, content FROM swarm_knowledge ORDER BY id"
        ).fetchall()
        assert len(rows) >= 2  # fact + lesson
        keys = [r[0] for r in rows]
        cats = [r[1] for r in rows]
        assert any('research:validation' in k for k in keys)
        assert 'fact' in cats
        assert 'lesson' in cats

    def test_archive_emits_bus_event(self, research_db):
        """Archive stage publishes research.done to the bus."""
        with patch('fridays.research_workflow._extract_lesson', return_value=None):
            from fridays.research_workflow import _archive_to_knowledge
            _archive_to_knowledge(42, 'bus test', 'summary', 'agent', conn=research_db)

        row = research_db.execute(
            "SELECT topic, payload_json FROM swarm_bus WHERE topic='research.done'"
        ).fetchone()
        assert row is not None
        payload = json.loads(row[1])
        assert payload['session_id'] == 42

    def test_extract_lesson_fallback(self, research_db):
        """Lesson extraction fallback returns first meaningful sentence."""
        from fridays.research_workflow import _extract_lesson
        # Mock the agent call to fail
        with patch('requests.post', side_effect=Exception('no agent')):
            lesson = _extract_lesson('testing', 'First finding is that X is important for reliability.\nSecond note.')
        assert lesson is not None
        assert 'testing' in lesson.lower() or 'First finding' in lesson

    def test_pattern_detection_writes_pattern(self, research_db):
        """Cross-session detection creates a pattern entry when overlap found."""
        # Seed existing knowledge
        research_db.execute(
            "INSERT INTO swarm_knowledge (key, content, source_agent, category, importance) "
            "VALUES (?, ?, ?, ?, ?)",
            ('existing:topic', 'This is about testing reliability with error handling and validation',
             'old_agent', 'fact', 5)
        )
        research_db.commit()

        from fridays.research_workflow import _detect_patterns
        _detect_patterns(
            'testing reliability',
            'New research on testing reliability with error handling and validation approaches',
            'new_agent',
            conn=research_db,
        )

        patterns = research_db.execute(
            "SELECT key, category FROM swarm_knowledge WHERE category='pattern'"
        ).fetchall()
        assert len(patterns) >= 1

    def test_full_cycle_knowledge_to_broadcast(self, research_db):
        """End-to-end: research → knowledge → broadcast block picks it up."""
        # Write knowledge as research archive would
        from utils.db.knowledge import write_knowledge
        write_knowledge(
            key='research:test cycle',
            content='Full cycle test content',
            source_agent='scholar',
            category='fact',
            importance=7,
            conn=research_db,
        )

        # Check that the broadcast block can pick it up
        from utils.db.knowledge import get_unacked_events
        events = get_unacked_events('gemma', event_type='knowledge.new', limit=10,
                                    conn=research_db)
        # At least one event should be present
        assert len(events) >= 1
        # Verify payload contains our key
        found = False
        for ev in events:
            payload = json.loads(ev['payload'])
            if 'research:test cycle' in payload.get('key', ''):
                found = True
                break
        assert found, 'Research knowledge event not found in broadcast'
