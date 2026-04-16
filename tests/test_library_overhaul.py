"""
tests/test_library_overhaul.py — Knowledge Library overhaul tests
═══════════════════════════════════════════════════════════════════════════════
Coverage:
  - Categories: tree_json, get_category, parent_of, all_ids_for, infer
  - Store: ensure_schema, add_source, check_duplicate (dedup), list_sources
    with category filter, source_stats with by_category
  - API: /api/library/categories, /api/library/seed, /api/library/context,
    /api/library/search?category=, /api/library/ingest (dedup 409)
"""

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
    """Stand up an in-memory-like SQLite for the store module."""
    db_path = str(tmp_path / 'test_lib.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()

    def _get_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr('utils.db._connection.get_connection', _get_conn)
    monkeypatch.setattr('utils.db._connection.DB_PATH', db_path)
    # Also patch the store's internal _conn so imports via sys.path work
    monkeypatch.setattr('lib.knowledge.store._conn', _get_conn)
    yield conn
    conn.close()


@pytest.fixture
def app(db_conn, monkeypatch):
    """Flask app with library blueprint."""
    monkeypatch.delenv('SWARM_UI_PASSWORD', raising=False)

    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True

    from frontend.blueprints.library import library_bp
    app.register_blueprint(library_bp)
    return app


# ── Category module tests ─────────────────────────────────────────────────────

class TestCategories:

    def test_tree_json_has_four_top_level(self):
        from lib.knowledge.categories import tree_json
        tree = tree_json()
        assert len(tree) == 4
        ids = [c['id'] for c in tree]
        assert 'sap_corner' in ids
        assert 'programming' in ids
        assert 'fridays' in ids
        assert 'general' in ids

    def test_tree_json_no_internal_keys(self):
        from lib.knowledge.categories import tree_json
        tree = tree_json()
        for cat in tree:
            assert '_parent' not in cat
            for sub in cat.get('subcategories', []):
                assert '_parent' not in sub

    def test_get_category_top_level(self):
        from lib.knowledge.categories import get_category
        cat = get_category('sap_corner')
        assert cat is not None
        assert cat['label'] == 'SAP Corner'

    def test_get_category_subcategory(self):
        from lib.knowledge.categories import get_category
        sub = get_category('payroll_au')
        assert sub is not None
        assert sub['label'] == 'Payroll (Australia)'

    def test_get_category_missing(self):
        from lib.knowledge.categories import get_category
        assert get_category('nonexistent') is None

    def test_parent_of_subcategory(self):
        from lib.knowledge.categories import parent_of
        assert parent_of('abap') == 'sap_corner'
        assert parent_of('python') == 'programming'
        assert parent_of('architecture') == 'fridays'

    def test_parent_of_top_level_returns_none(self):
        from lib.knowledge.categories import parent_of
        assert parent_of('sap_corner') is None

    def test_all_ids_for_sap_corner(self):
        from lib.knowledge.categories import all_ids_for
        ids = all_ids_for('sap_corner')
        assert 'sap_corner' in ids
        assert 'payroll_au' in ids
        assert 'abap' in ids
        assert 'ec_ecp' in ids
        assert len(ids) >= 13  # 1 parent + 12 subcategories

    def test_all_ids_for_missing_returns_empty(self):
        from lib.knowledge.categories import all_ids_for
        assert all_ids_for('nonexistent') == set()

    def test_infer_category_from_tags(self):
        from lib.knowledge.categories import infer_category_from_tags
        cat, sub = infer_category_from_tags(['abap', 'sap_hcm'])
        assert cat == 'sap_corner'
        assert sub == 'abap'

    def test_infer_category_empty_tags(self):
        from lib.knowledge.categories import infer_category_from_tags
        cat, sub = infer_category_from_tags([])
        assert cat is None
        assert sub is None


# ── Store module tests ────────────────────────────────────────────────────────

class TestStore:

    def test_ensure_schema_creates_tables(self, db_conn):
        from lib.knowledge.store import ensure_schema
        ensure_schema()
        tables = [r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert 'knowledge_sources' in tables
        assert 'knowledge_chunks' in tables

    def test_ensure_schema_idempotent(self, db_conn):
        from lib.knowledge.store import ensure_schema
        ensure_schema()
        ensure_schema()  # should not raise

    def test_add_source_with_category(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source
        ensure_schema()
        sid = add_source(
            title='Test SAP Doc',
            source_type='text',
            raw_text='SAP payroll schema AU01',
            category='sap_corner',
            subcategory='payroll_au',
        )
        assert isinstance(sid, int)
        assert sid > 0

    def test_content_hash_set_on_add(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source
        ensure_schema()
        sid = add_source(title='Hash Test', source_type='text',
                         raw_text='unique content here')
        row = db_conn.execute(
            "SELECT content_hash FROM knowledge_sources WHERE source_id=?",
            (sid,)
        ).fetchone()
        assert row['content_hash'] is not None
        assert len(row['content_hash']) == 64  # SHA-256 hex

    def test_check_duplicate_detects_same_content(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source, check_duplicate
        ensure_schema()
        add_source(title='Original', source_type='text',
                   raw_text='This content is unique for dedup test.')
        existing = check_duplicate('This content is unique for dedup test.')
        assert existing is not None

    def test_check_duplicate_normalises_whitespace(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source, check_duplicate
        ensure_schema()
        add_source(title='Spaced', source_type='text',
                   raw_text='normalise  whitespace   here')
        existing = check_duplicate('normalise whitespace here')
        assert existing is not None

    def test_check_duplicate_returns_none_for_novel(self, db_conn):
        from lib.knowledge.store import ensure_schema, check_duplicate
        ensure_schema()
        assert check_duplicate('completely novel content xyz123') is None

    def test_list_sources_category_filter(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source, list_sources
        ensure_schema()
        add_source(title='SAP Doc', source_type='text',
                   raw_text='sap doc a', category='sap_corner')
        add_source(title='Python Doc', source_type='text',
                   raw_text='python doc b', category='programming')
        all_src = list_sources()
        sap_src = list_sources(category='sap_corner')
        prog_src = list_sources(category='programming')
        assert len(all_src) >= 2
        assert all(s['category'] == 'sap_corner' for s in sap_src)
        assert all(s['category'] == 'programming' for s in prog_src)

    def test_source_stats_includes_by_category(self, db_conn):
        from lib.knowledge.store import ensure_schema, add_source, source_stats
        ensure_schema()
        add_source(title='S1', source_type='text',
                   raw_text='stats test content 1', category='sap_corner')
        add_source(title='S2', source_type='text',
                   raw_text='stats test content 2', category='programming')
        stats = source_stats()
        assert 'by_category' in stats
        assert stats['by_category'].get('sap_corner', 0) >= 1
        assert stats['by_category'].get('programming', 0) >= 1


# ── API endpoint tests ───────────────────────────────────────────────────────

class TestCategoriesAPI:

    def test_categories_endpoint(self, app):
        with app.test_client() as c:
            resp = c.get('/api/library/categories')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['ok'] is True
            assert 'categories' in data
            assert 'by_category' in data
            ids = [cat['id'] for cat in data['categories']]
            assert 'sap_corner' in ids

    def test_categories_have_subcategories(self, app):
        with app.test_client() as c:
            data = c.get('/api/library/categories').get_json()
            sap = next(cat for cat in data['categories'] if cat['id'] == 'sap_corner')
            assert len(sap['subcategories']) >= 10
            sub_ids = [s['id'] for s in sap['subcategories']]
            assert 'payroll_au' in sub_ids
            assert 'abap' in sub_ids


class TestSeedAPI:

    def test_seed_endpoint_returns_ok(self, app, monkeypatch):
        # Mock process_source to avoid Ollama dependency
        monkeypatch.setattr(
            'lib.knowledge.ingest.process_source',
            lambda sid, text: None,
        )
        with app.test_client() as c:
            resp = c.post('/api/library/seed',
                          json={'collection': 'all'},
                          content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['ok'] is True
            assert data['added'] > 0

    def test_seed_idempotent(self, app, monkeypatch):
        monkeypatch.setattr(
            'lib.knowledge.ingest.process_source',
            lambda sid, text: None,
        )
        with app.test_client() as c:
            r1 = c.post('/api/library/seed', json={'collection': 'all'},
                        content_type='application/json').get_json()
            r2 = c.post('/api/library/seed', json={'collection': 'all'},
                        content_type='application/json').get_json()
            assert r2['added'] == 0
            assert r2['skipped'] == r1['added']


class TestIngestDedupAPI:

    def test_duplicate_content_returns_409(self, app, monkeypatch):
        monkeypatch.setattr(
            'lib.knowledge.ingest.process_source',
            lambda sid, text: None,
        )
        with app.test_client() as c:
            payload = {
                'type': 'text',
                'title': 'Dedup Test',
                'content': 'This exact content for duplicate testing ABC123.',
                'tags': [],
                'category': 'general',
            }
            r1 = c.post('/api/library/ingest', json=payload,
                        content_type='application/json')
            assert r1.status_code == 200

            r2 = c.post('/api/library/ingest', json=payload,
                        content_type='application/json')
            assert r2.status_code == 409
            data = r2.get_json()
            assert data['ok'] is False
            assert 'duplicate_source_id' in data

    def test_ingest_with_category(self, app, monkeypatch):
        monkeypatch.setattr(
            'lib.knowledge.ingest.process_source',
            lambda sid, text: None,
        )
        with app.test_client() as c:
            payload = {
                'type': 'text',
                'title': 'SAP Schema Doc',
                'content': 'Schema AU01 drives Australian payroll processing.',
                'tags': ['schema'],
                'category': 'sap_corner',
                'subcategory': 'schemas_pcr',
            }
            resp = c.post('/api/library/ingest', json=payload,
                          content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['ok'] is True
            assert data['source_id'] > 0


class TestContextAPI:

    def test_context_requires_query(self, app):
        with app.test_client() as c:
            resp = c.get('/api/library/context')
            assert resp.status_code == 400

    def test_context_returns_empty_for_no_data(self, app, monkeypatch):
        monkeypatch.setattr(
            'lib.knowledge.retrieval.search',
            lambda query, top_k=4, category=None: [],
        )
        with app.test_client() as c:
            resp = c.get('/api/library/context?q=payroll')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['ok'] is True
            assert data['context'] == ''

    def test_context_auto_detects_sap_category(self, app, monkeypatch):
        captured = {}

        def mock_search(query, top_k=4, category=None):
            captured['category'] = category
            return []

        monkeypatch.setattr('lib.knowledge.retrieval.search', mock_search)
        with app.test_client() as c:
            c.get('/api/library/context?q=ABAP%20SE38%20program')
            assert captured.get('category') == 'sap_corner'

    def test_context_respects_explicit_category(self, app, monkeypatch):
        captured = {}

        def mock_search(query, top_k=4, category=None):
            captured['category'] = category
            return []

        monkeypatch.setattr('lib.knowledge.retrieval.search', mock_search)
        with app.test_client() as c:
            c.get('/api/library/context?q=python&category=programming')
            assert captured.get('category') == 'programming'


class TestSearchCategoryAPI:

    def test_search_passes_category(self, app, monkeypatch):
        captured = {}

        def mock_search(query, top_k=8, category=None):
            captured['category'] = category
            return []

        monkeypatch.setattr('lib.knowledge.retrieval.search', mock_search)
        with app.test_client() as c:
            resp = c.get('/api/library/search?q=test&category=sap_corner')
            assert resp.status_code == 200
            assert captured.get('category') == 'sap_corner'

    def test_search_no_category_passes_none(self, app, monkeypatch):
        captured = {}

        def mock_search(query, top_k=8, category=None):
            captured['category'] = category
            return []

        monkeypatch.setattr('lib.knowledge.retrieval.search', mock_search)
        with app.test_client() as c:
            c.get('/api/library/search?q=test')
            assert captured.get('category') is None


class TestSourcesCategoryAPI:

    def test_sources_filtered_by_category(self, app, monkeypatch):
        monkeypatch.setattr(
            'lib.knowledge.ingest.process_source',
            lambda sid, text: None,
        )
        with app.test_client() as c:
            # Add two sources in different categories
            c.post('/api/library/ingest', json={
                'type': 'text', 'title': 'SAP One',
                'content': 'SAP source filter test content A.',
                'category': 'sap_corner',
            }, content_type='application/json')
            c.post('/api/library/ingest', json={
                'type': 'text', 'title': 'Prog One',
                'content': 'Programming source filter test content B.',
                'category': 'programming',
            }, content_type='application/json')

            # Get all
            all_data = c.get('/api/library/sources').get_json()
            assert all_data['ok'] is True
            assert len(all_data['sources']) >= 2

            # Get SAP only
            sap_data = c.get('/api/library/sources?category=sap_corner').get_json()
            assert all(s['category'] == 'sap_corner' for s in sap_data['sources'])
