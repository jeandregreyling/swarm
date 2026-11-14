"""Owner 13 Nov: local models can be turned On / Off / Auto from Live status; routing and Fred obey it."""
import sqlite3
from types import SimpleNamespace

import pytest

from core import apex_routing, hb_model_switches as sw


def entry(name, ram=4.0, role='general', endpoint=None, ngl=None):
    return SimpleNamespace(name=name, driver='llamacpp', role=role, ctx=16384, options={'ngl': ngl} if ngl is not None else {},
                           path='/m/' + name, endpoint=endpoint, ram_gb=ram)


CATALOGUE = [entry('qwen2.5:14b-instruct'), entry('apex-direct:7b', 6, 'coder'), entry('llama-direct:3.2', 3),
             entry('fred-cpu:24b', 15, ngl=0)]


def route(message, switches):
    return apex_routing.select_local_model(message, CATALOGUE, exists=lambda p: True, switches=switches).model


def test_off_is_never_routed_and_on_is_preferred():
    assert route('fix core/x.py', {}) == 'apex-direct:7b'
    assert route('fix core/x.py', {'apex-direct:7b': 'off'}) != 'apex-direct:7b'
    assert route('hello there, how are you today?', {'llama-direct:3.2': 'on'}) == 'llama-direct:3.2'


@pytest.fixture
def conn(monkeypatch):
    from core.seven_llm import registry
    monkeypatch.setattr(registry, 'list_models', lambda: CATALOGUE)
    db = sqlite3.connect(':memory:')
    return db


def test_switch_validates_and_keeps_one_chat_model(conn):
    assert sw.set_mode(conn, 'apex-direct:7b', 'off', 'jd') == {'model': 'apex-direct:7b', 'mode': 'off'}
    with pytest.raises(ValueError):
        sw.set_mode(conn, 'apex-direct:7b', 'maybe', 'jd')
    with pytest.raises(ValueError):
        sw.set_mode(conn, 'not-a-model', 'off', 'jd')
    sw.set_mode(conn, 'llama-direct:3.2', 'off', 'jd')
    with pytest.raises(ValueError, match='At least one'):
        sw.set_mode(conn, 'qwen2.5:14b-instruct', 'off', 'jd')
    sw.set_mode(conn, 'fred-cpu:24b', 'off', 'jd')                # Fred is the reviewer, not a chat model
    rows = {r['model']: r for r in sw.catalogue(conn, residents={'fred-cpu:24b'}, served=set())}
    assert rows['fred-cpu:24b']['mode'] == 'off' and rows['fred-cpu:24b']['loaded'] and rows['fred-cpu:24b']['where'] == 'CPU (RAM)'
    assert rows['qwen2.5:14b-instruct']['mode'] == 'auto'


def test_fred_off_blocks_the_reviewer_and_local_help(monkeypatch):
    monkeypatch.setattr(sw, 'current_modes', lambda: {'fred-cpu:24b': 'off'})
    with pytest.raises(RuntimeError, match='switched Off'):
        apex_routing.assigned_local_model('fred-cpu:24b', available_gb=60)
    from core import hb_local_review
    with pytest.raises(RuntimeError, match='switched Off'):
        hb_local_review.review({}, {}, lambda *_: None)


def test_models_endpoint_is_owner_only(monkeypatch):
    import sys
    from pathlib import Path
    from flask import Flask
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'frontend'))
    from frontend.blueprints import peer_bridge
    auth = sys.modules[peer_bridge.require_owner.__module__]
    monkeypatch.setattr(auth, 'get_current_user', lambda: None)
    app = Flask('models-owner-test'); app.register_blueprint(peer_bridge.peer_bridge_bp)
    client = app.test_client()
    assert client.get('/api/peer/v1/hb/models').status_code in (401, 403)
    assert client.post('/api/peer/v1/hb/models', json={'model': 'apex-direct:7b', 'mode': 'off'}).status_code in (401, 403)


def test_claude_mention_is_detected_again():
    from core import peer_bridge
    assert peer_bridge.mentioned_peers('@claude are you there?') == ['claude-code']
    assert peer_bridge.mentioned_peers('@tiered-assistant and @mistral-vibe') == ['tiered-assistant', 'mistral-vibe']
    assert peer_bridge.mentioned_peers('mail me at a@claude.dev') == []


def test_model_mention_means_apex_on_that_model(monkeypatch):
    from core.seven_llm import registry
    from core import peer_bridge
    monkeypatch.setattr(registry, 'list_models', lambda: CATALOGUE)
    monkeypatch.setattr(registry, 'get', lambda name: next((e for e in CATALOGUE if e.name == name), None))
    sw._ALIAS_CACHE.update(at=0, map={})
    monkeypatch.setattr(sw, 'current_modes', lambda: {})
    assert sw.model_from_mention('@llama-direct-3.2 summarise this') == 'llama-direct:3.2'
    assert sw.model_from_mention('ask @fred please') == 'fred-cpu:24b'
    assert sw.model_from_mention('@nobody here') is None
    assert peer_bridge.mentioned_peers('@apex-direct-7b fix it') == ['apex']
    assert apex_routing.owner_chosen_model('llama-direct:3.2').model == 'llama-direct:3.2'
    monkeypatch.setattr(apex_routing, 'assigned_local_model', lambda name, **k: apex_routing.LocalRoute(name, 'local-repair', 8192, 'fred'))
    assert apex_routing.owner_chosen_model('fred-cpu:24b').model == 'fred-cpu:24b'
    monkeypatch.setattr(sw, 'current_modes', lambda: {'llama-direct:3.2': 'off'})
    assert sw.model_from_mention('@llama-direct-3.2 hi') is None
    with pytest.raises(RuntimeError, match='switched Off'):
        apex_routing.owner_chosen_model('llama-direct:3.2')
    with pytest.raises(PermissionError):
        apex_routing.owner_chosen_model('gemma3:12b')
    monkeypatch.undo()
    from core.apex_routing import assigned_local_model
    with pytest.raises(PermissionError):
        assigned_local_model('llama-direct:3.2')          # the repair path stays Fred-only


def test_mentions_endpoint_is_owner_only(monkeypatch):
    import sys
    from pathlib import Path
    from flask import Flask
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'frontend'))
    from frontend.blueprints import peer_bridge
    auth = sys.modules[peer_bridge.require_owner.__module__]
    monkeypatch.setattr(auth, 'get_current_user', lambda: None)
    app = Flask('mentions-owner-test'); app.register_blueprint(peer_bridge.peer_bridge_bp)
    assert app.test_client().get('/api/peer/v1/hb/mentions').status_code in (401, 403)
