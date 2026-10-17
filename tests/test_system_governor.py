from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_governor_flags_mutation_without_story(monkeypatch):
    import core.system_governor as gov

    monkeypatch.setattr(gov, '_SINGLETON', None)
    governor = gov.init_governor(node_identity='node-test', mode='advisory')
    verdict = governor.enforce({'kind': 'sync', 'mutates_state': True, 'target': 'git.sync'})

    assert verdict['status'] == 'VIOLATION_NOTICE'
    assert verdict['policy'] == 'NGAS'
    assert verdict['target'] == 'git.sync'


def test_governor_flags_people_pleasing_language(monkeypatch):
    import core.system_governor as gov

    monkeypatch.setattr(gov, '_SINGLETON', None)
    governor = gov.init_governor(node_identity='node-test', mode='advisory')
    verdict = governor.enforce({'message': "Sorry, I'd be happy to help.", 'target': 'reply'})

    assert verdict['status'] == 'VIOLATION_NOTICE'
    assert verdict['policy'] == 'DGIF'


def test_governor_accepts_storyful_mutation(monkeypatch):
    import core.system_governor as gov

    monkeypatch.setattr(gov, '_SINGLETON', None)
    governor = gov.init_governor(node_identity='node-test', mode='advisory')
    verdict = governor.enforce({
        'kind': 'sync_story',
        'origin': {'source_node': 'node-test'},
        'intent': {'branch': 'main'},
        'consequence': {'result': 'synced'},
    })

    assert verdict['status'] == 'APPROVED'
    assert verdict['story_present'] is True


def test_governor_focus_endpoint_records_focus(monkeypatch, tmp_path):
    db = str(tmp_path / 'gov.db')
    monkeypatch.setenv('SWARM_DB_PATH', db)
    monkeypatch.setenv('SWARM_HIVE_DB', str(tmp_path / 'hive.db'))
    monkeypatch.setenv('SWARM_HIVE_TOKENS', str(tmp_path / 'tokens.jsonl'))
    monkeypatch.setenv('SWARM_NODE_ID', 'potato-1-linux')

    import utils.db._connection as conn_mod
    conn_mod.DB_PATH = db
    import utils.db.trace_log as trace_log
    trace_log._SCHEMA_READY = False

    import core.system_governor as gov
    monkeypatch.setattr(gov, '_SINGLETON', None)
    import core.hive.local_node as local_node
    monkeypatch.setattr(local_node, '_SINGLETON', None)

    from frontend.terminal import create_app
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        rv = client.post('/api/governor/focus', json={
            'surface': 'agents',
            'title': 'Agents',
            'source': 'window',
            'path': 'view-agents',
        })
        assert rv.status_code == 200
        body = rv.get_json()
        assert body['ok'] is True
        assert body['focus']['surface'] == 'agents'

        state = client.get('/api/governor/state')
        assert state.status_code == 200
        payload = state.get_json()['governor']
        assert payload['node'] == 'potato-1-linux'
        assert payload['last_focus']['surface'] == 'agents'
