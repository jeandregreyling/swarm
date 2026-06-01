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
