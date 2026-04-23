"""test_knowledge.py — Session 29.2 tests for core/knowledge/scripts.py
and the knowledge_bp API surface."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ('', 'frontend', 'utils', 'core'):
    _p = os.path.join(_ROOT, _sub) if _sub else _ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def isolated_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setenv('SWARM_DB_PATH', tmp.name)
    from utils.db import _connection
    monkeypatch.setattr(_connection, 'DB_PATH', tmp.name)
    from core.knowledge import scripts as kc
    monkeypatch.setattr(kc, '_SCHEMA_READY', False)
    yield tmp.name
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture
def app():
    from frontend.terminal import create_app
    a = create_app()
    a.config['TESTING'] = True
    return a


# ── Registry re-export ─────────────────────────────────────────────────────

def test_kc_get_registry_matches_legacy():
    from core.knowledge import scripts as kc
    from core import testlab_registry as legacy
    assert kc.get_registry() == legacy.get_registry()


def test_kc_get_entry_hit_and_miss():
    from core.knowledge import scripts as kc
    entries = kc.get_registry()
    assert entries, 'registry must not be empty'
    first_id = entries[0]['id']
    assert kc.get_entry(first_id)['id'] == first_id
    assert kc.get_entry('does-not-exist') is None


# ── Change-run history ─────────────────────────────────────────────────────

def test_record_and_list_change_runs(isolated_db):
    from core.knowledge import scripts as kc
    assert kc.record_change_run('change-42', ['smoke-endpoints', 'pytest-full']) is True
    assert kc.record_change_run('change-42', ['smoke-endpoints']) is True
    assert kc.record_change_run('change-99', ['js-syntax']) is True
    rows = kc.list_change_runs('change-42')
    assert len(rows) == 2
    assert all(r['change_id'] == 'change-42' for r in rows)
    # Most recent first
    assert rows[0]['script_ids'] == ['smoke-endpoints']
    assert rows[1]['script_ids'] == ['smoke-endpoints', 'pytest-full']
    all_rows = kc.list_change_runs()
    assert len(all_rows) == 3


def test_record_change_run_rejects_empty_change_id(isolated_db):
    from core.knowledge import scripts as kc
    assert kc.record_change_run('', ['any']) is False
    assert kc.list_change_runs() == []


# ── Blueprint ──────────────────────────────────────────────────────────────

def test_kc_scripts_endpoint_shape(app):
    client = app.test_client()
    r = client.get('/api/knowledge/testlab/scripts')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['count'] >= 1
    assert isinstance(data['groups'], list)
    assert all('name' in g and 'scripts' in g for g in data['groups'])


def test_kc_change_runs_recent_endpoint(app, isolated_db):
    from core.knowledge import scripts as kc
    kc.record_change_run('c1', ['a'])
    kc.record_change_run('c2', ['b', 'c'])
    client = app.test_client()
    r = client.get('/api/knowledge/change-runs?limit=10')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    ids = {row['change_id'] for row in data['items']}
    assert {'c1', 'c2'} <= ids


def test_kc_change_runs_for_change_endpoint(app, isolated_db):
    from core.knowledge import scripts as kc
    kc.record_change_run('target', ['x'])
    kc.record_change_run('other', ['y'])
    client = app.test_client()
    r = client.get('/api/knowledge/change-runs/target')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert data['change_id'] == 'target'
    assert len(data['items']) == 1
    assert data['items'][0]['script_ids'] == ['x']


# ── Persistence from testlab resolve ──────────────────────────────────────

def test_testlab_resolve_persists_change_run(app, isolated_db):
    """When change_id + ids are provided, resolve() should record into KC."""
    from core.knowledge import scripts as kc
    client = app.test_client()
    registry_ids = [e['id'] for e in kc.get_registry()]
    pick = registry_ids[:2]
    r = client.post(
        '/api/studio/testlab/resolve',
        json={'script_ids': pick, 'change_id': 'kc-test-1'},
    )
    assert r.status_code == 200
    rows = kc.list_change_runs('kc-test-1')
    assert len(rows) == 1
    assert rows[0]['script_ids'] == pick
