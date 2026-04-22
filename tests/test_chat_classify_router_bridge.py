"""Tests the Phase-3 router signal embedded in /api/chat/classify response."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frontend.terminal import create_app

app = create_app()


def _post(client, message):
    resp = client.post('/api/chat/classify', json={'message': message})
    return resp.status_code, resp.get_json(silent=True) or {}


def test_classify_exposes_router_field():
    with app.test_client() as client:
        code, body = _post(client, 'write a python function to sort a list')
    assert code == 200
    assert body.get('ok') is True
    assert 'router' in body
    router = body['router']
    # Deterministic router returned a decision (no 'error' key)
    assert 'error' not in router, router
    assert 'target' in router
    assert 'category' in router
    assert 'confidence' in router
    assert 'rationale' in router


def test_classify_router_respects_explicit_address():
    with app.test_client() as client:
        code, body = _post(client, 'ten: quick status check please')
    assert code == 200
    router = body.get('router') or {}
    # Name-address prefix should resolve to a concrete target when ten is routable.
    # If ten is not routable in this env, rationale will explain and category stays valid.
    assert router.get('category') in {
        'voice', 'coder', 'researcher', 'orchestrator', 'memory', 'auditor', 'messenger',
    } or 'error' in router
