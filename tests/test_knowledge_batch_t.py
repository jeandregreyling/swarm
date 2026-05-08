"""Batch T regression tests — KC owns testlab, DB-backed registry, timeline,
auto-tag triggered_by, and runs feed.

Covers:
  MD-FEATURE-C80A4299AF69       — KC owns testlab registry
  MD-SESSION30-EB84C987D775     — DB-backed scripts registry
  MD-SESSION30-CB0CE94C6B60     — change timeline
  MD-SESSION30-ECA581250AF5     — auto-tag triggered_by=change:<id>
  MD-SESSION30-FF20242F3F3D     — KC runs feed
"""
from __future__ import annotations

import json
import time

import pytest

from core.knowledge import scripts as kc_scripts


# ── Test infrastructure ───────────────────────────────────────────────────

@pytest.fixture
def fake_db(monkeypatch):
    """Replace utils.db._connection.get_connection with an in-memory sqlite
    that satisfies the schemas used by core.knowledge.scripts +
    core.knowledge.test_runs."""
    import sqlite3

    class _NoCloseConn:
        """Thin proxy that swallows .close() so call sites that close after
        each use don't drop our shared in-memory DB."""
        def __init__(self, real):
            self._real = real
        def close(self):
            return None
        def __getattr__(self, name):
            return getattr(self._real, name)
        def __setattr__(self, name, value):
            if name == '_real':
                object.__setattr__(self, name, value)
            else:
                setattr(self._real, name, value)

    real = sqlite3.connect(':memory:')
    real.row_factory = sqlite3.Row
    proxy = _NoCloseConn(real)

    def _get():
        return proxy

    import utils.db._connection as conn_mod
    monkeypatch.setattr(conn_mod, 'get_connection', _get)
    monkeypatch.setattr(kc_scripts, '_SCHEMA_READY', False)
    monkeypatch.setattr(kc_scripts, '_DB_SCHEMA_READY', False)
    from core.knowledge import test_runs as kc_runs
    monkeypatch.setattr(kc_runs, '_SCHEMA_READY', False, raising=False)

    yield proxy
    real.close()


# ── 1) KC owns testlab registry (re-export integrity) ────────────────────


class TestRegistryReExport:
    def test_get_registry_returns_legacy_shape(self):
        regs = kc_scripts.get_registry()
        assert isinstance(regs, list) and regs
        for entry in regs[:3]:
            for k in ('id', 'group', 'label', 'command'):
                assert k in entry

    def test_get_entry_lookup(self):
        regs = kc_scripts.get_registry()
        first_id = regs[0]['id']
        entry = kc_scripts.get_entry(first_id)
        assert entry is not None
        assert entry['id'] == first_id

    def test_get_entry_missing_returns_none(self):
        assert kc_scripts.get_entry('totally-not-a-real-script-id') is None

    def test_kc_namespace_exposes_required_api(self):
        for name in ('get_registry', 'get_entry', 'record_change_run',
                     'list_change_runs', 'seed_registry_to_db',
                     'list_scripts_db', 'timeline_for_change'):
            assert hasattr(kc_scripts, name), name


# ── 2) DB-backed registry ────────────────────────────────────────────────


class TestDbRegistry:
    def test_seed_writes_rows(self, fake_db):
        n = kc_scripts.seed_registry_to_db()
        assert n >= 1
        rows = kc_scripts.list_scripts_db()
        assert len(rows) >= n

    def test_seed_is_idempotent_without_force(self, fake_db):
        n1 = kc_scripts.seed_registry_to_db()
        n2 = kc_scripts.seed_registry_to_db()
        assert n1 >= 1
        assert n2 == 0  # nothing new written when rows already exist

    def test_seed_force_overwrites(self, fake_db):
        kc_scripts.seed_registry_to_db()
        n2 = kc_scripts.seed_registry_to_db(force=True)
        assert n2 >= 1

    def test_list_scripts_db_falls_back_to_legacy_when_empty(self, fake_db):
        # No seeding called yet → DB is empty → fallback to file REGISTRY.
        rows = kc_scripts.list_scripts_db()
        legacy = kc_scripts.get_registry()
        assert len(rows) == len(legacy)

    def test_list_scripts_db_reports_source(self, fake_db):
        kc_scripts.seed_registry_to_db()
        rows = kc_scripts.list_scripts_db()
        assert any(r.get('source') == 'seed' for r in rows)


# ── 3) Timeline for change ────────────────────────────────────────────────


class TestTimeline:
    def test_empty_change_id_returns_empty(self, fake_db):
        assert kc_scripts.timeline_for_change('') == []
        assert kc_scripts.timeline_for_change(None) == []

    def test_unknown_change_returns_empty(self, fake_db):
        assert kc_scripts.timeline_for_change('change-doesnt-exist') == []

    def test_change_run_only(self, fake_db):
        kc_scripts.record_change_run('chg-A', ['smoke-endpoints'])
        out = kc_scripts.timeline_for_change('chg-A')
        assert len(out) == 1
        assert out[0]['kind'] == 'change_run'
        assert out[0]['change_id'] == 'chg-A'
        assert out[0]['script_ids'] == ['smoke-endpoints']

    def test_combined_change_and_test_runs_ordered(self, fake_db):
        from core.knowledge import test_runs as kc_runs
        kc_scripts.record_change_run('chg-B', ['smoke-endpoints'])
        time.sleep(0.01)
        run_id = kc_runs.start_run(
            'smoke-endpoints', change_id='chg-B', triggered_by='change:chg-B',
        )
        assert run_id
        out = kc_scripts.timeline_for_change('chg-B')
        assert len(out) == 2
        # Oldest first
        kinds = [i['kind'] for i in out]
        assert kinds == ['change_run', 'test_run']

    def test_timeline_isolation_across_changes(self, fake_db):
        kc_scripts.record_change_run('chg-X', ['smoke-endpoints'])
        kc_scripts.record_change_run('chg-Y', ['pytest-full'])
        x = kc_scripts.timeline_for_change('chg-X')
        y = kc_scripts.timeline_for_change('chg-Y')
        assert all(i['change_id'] == 'chg-X' for i in x)
        assert all(i['change_id'] == 'chg-Y' for i in y)


# ── 4) Auto-tag triggered_by + 5) runs feed via Flask ────────────────────


@pytest.fixture
def flask_client(fake_db):
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestAutoTagAndFeed:
    def test_test_run_auto_tags_triggered_by_change(self, flask_client):
        rv = flask_client.post(
            '/api/knowledge/test-runs',
            json={'script_id': 'smoke-endpoints', 'change_id': 'chg-Z'},
        )
        assert rv.status_code == 200
        run_id = rv.get_json()['run_id']
        # Re-fetch the run and confirm triggered_by was auto-tagged.
        from core.knowledge import test_runs as kc_runs
        run = kc_runs.get_run(run_id)
        assert run is not None
        assert run.get('triggered_by') == 'change:chg-Z'

    def test_explicit_triggered_by_wins_over_auto(self, flask_client):
        rv = flask_client.post(
            '/api/knowledge/test-runs',
            json={
                'script_id': 'smoke-endpoints',
                'change_id': 'chg-Z',
                'triggered_by': 'scheduled',
            },
        )
        assert rv.status_code == 200
        run_id = rv.get_json()['run_id']
        from core.knowledge import test_runs as kc_runs
        run = kc_runs.get_run(run_id)
        assert run.get('triggered_by') == 'scheduled'

    def test_no_change_id_defaults_to_manual(self, flask_client):
        rv = flask_client.post(
            '/api/knowledge/test-runs',
            json={'script_id': 'smoke-endpoints'},
        )
        assert rv.status_code == 200
        run_id = rv.get_json()['run_id']
        from core.knowledge import test_runs as kc_runs
        run = kc_runs.get_run(run_id)
        assert run.get('triggered_by') == 'manual'

    def test_runs_feed_returns_recent_items(self, flask_client):
        # Seed a change_run + a test_run.
        kc_scripts.record_change_run('chg-feed', ['smoke-endpoints'])
        flask_client.post(
            '/api/knowledge/test-runs',
            json={'script_id': 'smoke-endpoints', 'change_id': 'chg-feed'},
        )
        rv = flask_client.get('/api/knowledge/runs/feed?limit=10')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        kinds = {i['kind'] for i in data['items']}
        assert 'change_run' in kinds
        assert 'test_run' in kinds

    def test_timeline_endpoint(self, flask_client):
        kc_scripts.record_change_run('chg-tl', ['smoke-endpoints'])
        rv = flask_client.get('/api/knowledge/changes/chg-tl/timeline')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['change_id'] == 'chg-tl'
        assert any(i['kind'] == 'change_run' for i in data['items'])

    def test_runs_feed_caps_limit(self, flask_client):
        rv = flask_client.get('/api/knowledge/runs/feed?limit=999999')
        assert rv.status_code == 200
        # Even with a huge limit request, the count is bounded.
        data = rv.get_json()
        assert data['ok'] is True
        assert data['count'] <= 200

    def test_runs_feed_handles_invalid_limit(self, flask_client):
        rv = flask_client.get('/api/knowledge/runs/feed?limit=not-a-number')
        assert rv.status_code == 200
        assert rv.get_json()['ok'] is True
