from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))


def test_ollama_models_degrades_when_backend_unavailable(monkeypatch):
    from frontend.blueprints import ollama as ollama_mod
    from core import llm as llm_mod

    monkeypatch.setattr(
        llm_mod,
        'list_models',
        lambda: (_ for _ in ()).throw(ConnectionRefusedError('backend down')),
    )

    app = Flask(__name__)
    app.register_blueprint(ollama_mod.ollama_bp)
    client = app.test_client()

    resp = client.get('/api/ollama/models')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['running'] is False
    assert data['models'] == []
    assert data['error_code'] == 'RUNTIME_OFFLINE'
    assert 'backend down' in data['error']


def test_registered_model_runtime_controls_use_llama_server(monkeypatch):
    from core import llm as llm_mod
    from core.seven_llm import llama_server
    from frontend.blueprints import ollama as ollama_mod
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(llm_mod, '_direct_model', lambda model: model)
    monkeypatch.setattr(llama_server, 'ensure', lambda model: SimpleNamespace(pid=123))
    monkeypatch.setattr(llama_server, 'stop', lambda model: calls.append(('stop', model)) or 1)
    monkeypatch.setattr(llama_server, 'set_ttl', lambda model, seconds: calls.append(('ttl', model, seconds)) or seconds)
    import sys
    # Unload is owner-only since 13 Nov (B36); this contract runs as the owner.
    monkeypatch.setattr(sys.modules[ollama_mod.require_owner.__module__], 'get_current_user',
                        lambda: {'username': 'jd', 'role': 'owner'})

    app = Flask(__name__)
    app.register_blueprint(ollama_mod.ollama_bp)
    client = app.test_client()

    load = client.post('/api/ollama/load', json={'model': 'gemma3:latest'})
    assert load.status_code == 200
    assert load.get_json() == {
        'ok': True, 'model': 'gemma3:latest', 'runtime': 'llamacpp', 'pid': 123,
    }
    keepalive = client.post('/api/ollama/keepalive', json={'model': 'gemma3:latest', 'seconds': 600})
    assert keepalive.status_code == 200
    assert keepalive.get_json()['seconds'] == 600
    unload = client.post('/api/ollama/unload', json={'model': 'gemma3:latest'})
    assert unload.status_code == 200
    assert unload.get_json()['runtime'] == 'llamacpp'
    assert calls == [
        ('ttl', 'gemma3:latest', 600),
        ('stop', 'gemma3:latest'),
    ]


def test_registered_model_show_uses_shared_runtime_and_delete_is_blocked(monkeypatch):
    from types import SimpleNamespace

    from core import llm as llm_mod
    from frontend.blueprints import ollama as ollama_mod

    monkeypatch.setattr(llm_mod, '_direct_model', lambda model: model)
    monkeypatch.setattr(llm_mod, 'show', lambda model: SimpleNamespace(
        modelfile='', parameters='num_ctx 8192', template='', capabilities=['completion'],
        details=SimpleNamespace(family='', format='gguf', parameter_size='', quantization_level='Q4_K_M'),
    ))
    app = Flask(__name__)
    app.register_blueprint(ollama_mod.ollama_bp)
    client = app.test_client()

    shown = client.get('/api/ollama/show/gemma3:latest')
    assert shown.status_code == 200
    assert shown.get_json()['details']['format'] == 'gguf'

    deleted = client.post('/api/ollama/delete', json={'model': 'gemma3:latest'})
    assert deleted.status_code == 409
    assert 'llama.cpp runtime' in deleted.get_json()['error']
