"""
Unit checks for ALM gate enforcement on newly hardened endpoints.

Run:
    python3 tests/test_alm_gate_endpoints.py
"""

import sys
from pathlib import Path
from flask import jsonify

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'utils'))
sys.path.insert(0, str(ROOT / 'core' / 'pipeline'))
sys.path.insert(0, str(ROOT / 'frontend'))

from frontend import terminal as term

app = term.create_app()

# After create_app() the blueprint modules are loaded; import them directly
# so we can patch _alm_gate_or_response in the right namespace.
import blueprints.auth as _auth_mod
import blueprints.time_wizard_bp as _tw_mod


def _request(client, method, path, body=None):
    resp = client.open(path, method=method, json=body)
    return resp.status_code, resp.get_json(silent=True) or {}


def test_senders_add_is_alm_gated():
    called = {'action': None}
    original_gate = _auth_mod._alm_gate_or_response

    def fake_gate(data, action_name):
        called['action'] = action_name
        return jsonify({'ok': False, 'error': 'blocked by fake gate'}), 428

    _auth_mod._alm_gate_or_response = fake_gate
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'POST', '/api/senders', {
                'list': 'trusted',
                'address': 'unit.test@example.com',
                'note': 'unit test',
            })
        assert code == 428, f'expected 428, got {code}'
        assert called['action'] == 'senders_add', f"expected action senders_add, got {called['action']}"
        assert obj.get('ok') is False
    finally:
        _auth_mod._alm_gate_or_response = original_gate


def test_senders_remove_is_alm_gated():
    called = {'action': None}
    original_gate = _auth_mod._alm_gate_or_response

    def fake_gate(data, action_name):
        called['action'] = action_name
        return jsonify({'ok': False, 'error': 'blocked by fake gate'}), 428

    _auth_mod._alm_gate_or_response = fake_gate
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'DELETE', '/api/senders', {
                'list': 'trusted',
                'address': 'unit.test@example.com',
            })
        assert code == 428, f'expected 428, got {code}'
        assert called['action'] == 'senders_remove', f"expected action senders_remove, got {called['action']}"
        assert obj.get('ok') is False
    finally:
        _auth_mod._alm_gate_or_response = original_gate


def test_manager_onboard_non_dry_run_is_alm_gated():
    called = {'action': None}
    original_gate = _auth_mod._alm_gate_or_response

    def fake_gate(data, action_name):
        called['action'] = action_name
        return jsonify({'ok': False, 'error': 'blocked by fake gate'}), 428

    _auth_mod._alm_gate_or_response = fake_gate
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'POST', '/api/access/manager/onboard', {
                'manager_email': 'manager.unit@example.com',
                'dry_run': False,
            })
        assert code == 428, f'expected 428, got {code}'
        assert called['action'] == 'manager_onboard', f"expected action manager_onboard, got {called['action']}"
        assert obj.get('ok') is False
    finally:
        _auth_mod._alm_gate_or_response = original_gate


def test_manager_onboard_dry_run_bypasses_gate():
    called = {'count': 0}
    original_gate = _auth_mod._alm_gate_or_response

    def fake_gate(data, action_name):
        called['count'] += 1
        return jsonify({'ok': False, 'error': 'should not be called'}), 428

    _auth_mod._alm_gate_or_response = fake_gate
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'POST', '/api/access/manager/onboard', {
                'manager_email': 'manager.unit@example.com',
                'manager_telegram_chat_id': '123456789',
                'dry_run': True,
            })
        assert code == 200, f'expected 200, got {code}'
        assert obj.get('ok') is True
        assert obj.get('dry_run') is True
        assert called['count'] == 0, f"gate should not be called in dry_run path, got {called['count']}"
    finally:
        _auth_mod._alm_gate_or_response = original_gate


def test_time_restore_non_dry_run_is_alm_gated():
    called = {'action': None}
    original_gate = _tw_mod._alm_gate_or_response
    original_restore = _tw_mod.time_wizard.restore_workflow_state

    def fake_gate(data, action_name):
        called['action'] = action_name
        return jsonify({'ok': False, 'error': 'blocked by fake gate'}), 428

    def fake_restore(**kwargs):
        return {'ok': True, 'dry_run': kwargs.get('dry_run', True)}

    _tw_mod._alm_gate_or_response = fake_gate
    _tw_mod.time_wizard.restore_workflow_state = fake_restore
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'POST', '/api/time/restore', {
                'checkpoint_name': 'unit-checkpoint',
                'dry_run': False,
            })
        assert code == 428, f'expected 428, got {code}'
        assert called['action'] == 'time_restore', f"expected action time_restore, got {called['action']}"
        assert obj.get('ok') is False
    finally:
        _tw_mod._alm_gate_or_response = original_gate
        _tw_mod.time_wizard.restore_workflow_state = original_restore


def test_time_restore_dry_run_bypasses_gate():
    called = {'count': 0}
    original_gate = _tw_mod._alm_gate_or_response
    original_restore = _tw_mod.time_wizard.restore_workflow_state

    def fake_gate(data, action_name):
        called['count'] += 1
        return jsonify({'ok': False, 'error': 'should not be called'}), 428

    def fake_restore(**kwargs):
        return {'ok': True, 'dry_run': kwargs.get('dry_run', True), 'summary': 'preview'}

    _tw_mod._alm_gate_or_response = fake_gate
    _tw_mod.time_wizard.restore_workflow_state = fake_restore
    try:
        with app.test_client() as client:
            code, obj = _request(client, 'POST', '/api/time/restore', {
                'checkpoint_name': 'unit-checkpoint',
                'dry_run': True,
            })
        assert code == 200, f'expected 200, got {code}'
        assert obj.get('ok') is True
        assert obj.get('dry_run') is True
        assert called['count'] == 0, f"gate should not be called in dry_run path, got {called['count']}"
    finally:
        _tw_mod._alm_gate_or_response = original_gate
        _tw_mod.time_wizard.restore_workflow_state = original_restore


if __name__ == '__main__':
    failures = []
    tests = [
        ('test_senders_add_is_alm_gated', test_senders_add_is_alm_gated),
        ('test_senders_remove_is_alm_gated', test_senders_remove_is_alm_gated),
        ('test_manager_onboard_non_dry_run_is_alm_gated', test_manager_onboard_non_dry_run_is_alm_gated),
        ('test_manager_onboard_dry_run_bypasses_gate', test_manager_onboard_dry_run_bypasses_gate),
        ('test_time_restore_non_dry_run_is_alm_gated', test_time_restore_non_dry_run_is_alm_gated),
        ('test_time_restore_dry_run_bypasses_gate', test_time_restore_dry_run_bypasses_gate),
    ]

    print('ALM gate endpoint tests')
    print('=' * 36)

    for name, fn in tests:
        try:
            fn()
            print(f'PASS  {name}')
        except Exception as e:
            failures.append((name, str(e)))
            print(f'FAIL  {name} -> {e}')

    print('-' * 36)
    if failures:
        print(f'{len(failures)} failed')
        for name, msg in failures:
            print(f'- {name}: {msg}')
        sys.exit(1)

    print('All ALM gate endpoint tests passed')
    sys.exit(0)
