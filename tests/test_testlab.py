"""
test_testlab.py — Session 28 Studio Test Lab
Unit tests for the registry + resolve endpoint contract.
"""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ('', 'frontend', 'utils', 'core', 'lib/email', 'lib/system', 'agents/ghost'):
    _p = os.path.join(_ROOT, _sub) if _sub else _ROOT
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from core.testlab_registry import get_registry, get_entry


# ── Registry shape ──────────────────────────────────────────────────────────

REQUIRED_FIELDS = {'id', 'group', 'label', 'description', 'command',
                   'change_aware', 'default_on'}


def test_registry_has_entries():
    assert len(get_registry()) >= 5


def test_registry_entries_have_all_required_fields():
    for entry in get_registry():
        missing = REQUIRED_FIELDS - set(entry.keys())
        assert not missing, f"{entry.get('id')} missing fields: {missing}"


def test_registry_ids_are_unique():
    ids = [e['id'] for e in get_registry()]
    assert len(ids) == len(set(ids))


def test_registry_commands_are_non_empty_strings():
    for entry in get_registry():
        assert isinstance(entry['command'], str)
        assert entry['command'].strip()


def test_registry_returns_copies_not_references():
    a = get_registry()
    a[0]['label'] = 'MUTATED'
    b = get_registry()
    assert b[0]['label'] != 'MUTATED'


def test_get_entry_known():
    entry = get_entry('smoke-endpoints')
    assert entry is not None
    assert entry['group'] == 'Smoke'


def test_get_entry_unknown_returns_none():
    assert get_entry('nonexistent-script-xyz') is None


def test_media_center_review_scripts_are_registered():
    ids = {e['id'] for e in get_registry()}
    assert 'pytest-media-center-review' in ids
    assert 'pytest-media-center-projects-chat' in ids
    assert 'pytest-media-center-daw-workspace' in ids
    assert 'pytest-local-agent-runtime-fixes' in ids
    assert 'js-syntax-media-center' in ids


# ── Blueprint endpoint contract ─────────────────────────────────────────────

@pytest.fixture
def client():
    from frontend.terminal import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_scripts_endpoint_shape(client):
    resp = client.get('/api/studio/testlab/scripts')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert isinstance(data['groups'], list)
    assert data['count'] == sum(len(g['scripts']) for g in data['groups'])
    # At least one Smoke script
    smoke = [g for g in data['groups'] if g['group'] == 'Smoke']
    assert smoke and smoke[0]['scripts']


def test_resolve_rejects_empty_list(client):
    resp = client.post('/api/studio/testlab/resolve',
                       data=json.dumps({'script_ids': []}),
                       content_type='application/json')
    assert resp.status_code == 400


def test_resolve_returns_commands(client):
    resp = client.post(
        '/api/studio/testlab/resolve',
        data=json.dumps({'script_ids': ['smoke-endpoints'], 'change_id': ''}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert len(data['items']) == 1
    assert data['items'][0]['id'] == 'smoke-endpoints'
    assert 'curl' in data['items'][0]['command']


def test_resolve_prefixes_change_id_only_for_change_aware(client):
    resp = client.post(
        '/api/studio/testlab/resolve',
        data=json.dumps({
            'script_ids': ['smoke-endpoints', 'pytest-email-guard'],
            'change_id': '1306',
        }),
        content_type='application/json',
    )
    data = resp.get_json()
    by_id = {i['id']: i for i in data['items']}
    # smoke-endpoints is NOT change_aware → no prefix
    assert 'SWARM_CHANGE_ID' not in by_id['smoke-endpoints']['command']
    # pytest-email-guard IS change_aware → gets prefix
    assert by_id['pytest-email-guard']['command'].startswith('SWARM_CHANGE_ID=1306 ')


def test_resolve_surfaces_missing_ids(client):
    resp = client.post(
        '/api/studio/testlab/resolve',
        data=json.dumps({'script_ids': ['smoke-endpoints', 'ghost-script-999']}),
        content_type='application/json',
    )
    data = resp.get_json()
    assert data['ok'] is True
    assert len(data['items']) == 1
    assert data['missing'] == ['ghost-script-999']
