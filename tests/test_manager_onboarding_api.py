"""
tests/test_manager_onboarding_api.py

Dry-run API checks for manager onboarding workflow.
Run: python3 tests/test_manager_onboarding_api.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'utils'))
sys.path.insert(0, str(ROOT / 'core' / 'pipeline'))

for _mod in ('database', 'frontend', 'frontend.services', 'frontend.terminal',
             'services', 'terminal', 'utils.database'):
    sys.modules.pop(_mod, None)
from frontend.terminal import create_app

app = create_app()


def _request(client, method, path, body=None):
    resp = client.open(path, method=method, json=body)
    return resp.status_code, resp.get_json(silent=True) or {}


def test_dry_run_plan():
    with app.test_client() as client:
        code, obj = _request(client, 'POST', '/api/access/manager/onboard', {
            'manager_email': 'manager.test@example.com',
            'manager_name': 'Manager Test',
            'manager_telegram_chat_id': '123456789',
            'add_as_moderator': True,
            'dry_run': True,
        })
    assert code == 200, f'expected 200, got {code}'
    assert obj.get('ok') is True, f'expected ok=true, got {obj}'
    assert obj.get('dry_run') is True, f'expected dry_run=true, got {obj}'
    plan = obj.get('plan') or {}
    entries = plan.get('trusted_entries_to_add') or []
    assert 'manager.test@example.com' in entries, 'manager email missing from plan'
    assert 'telegram:123456789' in entries, 'telegram entry missing from plan'
    assert plan.get('tailscale_step_required') is True, 'tailscale step should be required'


def test_invalid_email_rejected():
    with app.test_client() as client:
        code, obj = _request(client, 'POST', '/api/access/manager/onboard', {
            'manager_email': 'not-an-email',
            'dry_run': True,
        })
    assert code == 400, f'expected 400, got {code}'
    assert obj.get('ok') is False, f'expected ok=false, got {obj}'


def test_invalid_telegram_id_rejected():
    with app.test_client() as client:
        code, obj = _request(client, 'POST', '/api/access/manager/onboard', {
            'manager_email': 'manager.test@example.com',
            'manager_telegram_chat_id': 'abc123',
            'dry_run': True,
        })
    assert code == 400, f'expected 400, got {code}'
    assert obj.get('ok') is False, f'expected ok=false, got {obj}'


if __name__ == '__main__':
    failures = []
    tests = [
        ('test_dry_run_plan', test_dry_run_plan),
        ('test_invalid_email_rejected', test_invalid_email_rejected),
        ('test_invalid_telegram_id_rejected', test_invalid_telegram_id_rejected),
    ]

    print('Manager onboarding API tests')
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

    print('All manager onboarding tests passed')
    sys.exit(0)
