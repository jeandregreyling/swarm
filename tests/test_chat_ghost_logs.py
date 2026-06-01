import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.terminal import create_app

chat_mod = importlib.import_module('blueprints.chat')


def test_chat_logs_owner_thoughts_to_ghost_circle_with_jeandre_alias(monkeypatch):
    app = create_app()
    captured = []

    monkeypatch.setattr(chat_mod, '_reg_routable', lambda: [])
    monkeypatch.setattr(chat_mod, '_chat_prompt_needs_clarification', lambda message: True)
    monkeypatch.setattr(chat_mod, 'get_current_user', lambda: {
        'username': 'ghost',
        'display_name': 'Jeandre',
        'role': 'owner',
        'approved': True,
    })
    monkeypatch.setattr(chat_mod, '_resolve_identity_or_response', lambda data: ({
        'acting_user': 'ghost',
        'proxy_as': '',
        'effective_user': 'ghost',
        'can_proxy': True,
        'actor': {'username': 'ghost', 'display_name': 'Jeandre'},
        'effective': {'username': 'ghost', 'display_name': 'Jeandre'},
    }, None))
    monkeypatch.setattr(chat_mod, 'new_conversation', lambda *a, **k: 77)
    monkeypatch.setattr(chat_mod, 'log_message', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, '_trace', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, 'log_ghost_circle', lambda *a, **k: captured.append((a, k)))

    with app.test_client() as client:
        resp = client.post('/api/chat', json={
            'message': 'What now?',
            'acting_user': 'ghost',
        })

    assert resp.status_code == 200
    assert captured, 'expected ghost_circle write'
    args, kwargs = captured[0]
    assert args[0] == 'developer_thought'
    assert args[1] == 'jeandre'
    assert 'What now?' in args[2]
    assert 'acting_user=ghost' in args[2]
    assert kwargs['ticket_ref'] == 'conv:77'


def test_chat_logs_non_owner_operator_prompts_under_effective_username(monkeypatch):
    app = create_app()
    captured = []

    monkeypatch.setattr(chat_mod, '_reg_routable', lambda: [])
    monkeypatch.setattr(chat_mod, '_chat_prompt_needs_clarification', lambda message: True)
    monkeypatch.setattr(chat_mod, 'get_current_user', lambda: None)
    monkeypatch.setattr(chat_mod, '_resolve_identity_or_response', lambda data: ({
        'acting_user': 'jeandre',
        'proxy_as': '',
        'effective_user': 'jeandre',
        'can_proxy': False,
        'actor': {'username': 'jeandre', 'display_name': 'Jeandre'},
        'effective': {'username': 'jeandre', 'display_name': 'Jeandre'},
    }, None))
    monkeypatch.setattr(chat_mod, 'new_conversation', lambda *a, **k: 88)
    monkeypatch.setattr(chat_mod, 'log_message', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, '_trace', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, 'log_ghost_circle', lambda *a, **k: captured.append((a, k)))

    with app.test_client() as client:
        resp = client.post('/api/chat', json={
            'message': 'fix it',
            'acting_user': 'jeandre',
        })

    assert resp.status_code == 200
    assert captured, 'expected ghost_circle write'
    args, kwargs = captured[0]
    assert args[0] == 'operator_prompt'
    assert args[1] == 'jeandre'
    assert args[2].startswith('fix it')
    assert kwargs['ticket_ref'] == 'conv:88'
