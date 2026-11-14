"""B36 (practice 3, 13 Nov): /api/ollama/unload is owner-only. Drafted by APEX, finished by Claude Code."""
import sys
from pathlib import Path

from flask import Flask


def _client(monkeypatch, user):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'frontend'))
    from frontend.blueprints import ollama
    auth = sys.modules[ollama.require_owner.__module__]
    monkeypatch.setattr(auth, 'get_current_user', lambda: user)
    app = Flask('unload-owner-test')
    app.register_blueprint(ollama.ollama_bp)
    return app.test_client()


def test_unload_refuses_without_an_owner_login(monkeypatch):
    response = _client(monkeypatch, None).post('/api/ollama/unload', json={'model': 'llama3.2:latest'})
    assert response.status_code in (401, 403)


def test_owner_gets_past_the_check(monkeypatch):
    response = _client(monkeypatch, {'username': 'jd', 'role': 'owner'}).post('/api/ollama/unload', json={})
    assert response.status_code == 400 and response.get_json()['error'] == 'model required'   # past the check, at the handler
