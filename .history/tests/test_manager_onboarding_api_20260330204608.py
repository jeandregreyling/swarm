"""
tests/test_manager_onboarding_api.py

Dry-run API checks for manager onboarding workflow.
Run: python3 tests/test_manager_onboarding_api.py
"""

import json
import sys
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:5050'


def _request(method, path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.getcode(), json.loads(r.read().decode('utf-8'))


def _request_expect_error(method, path, body=None):
    try:
        return _request(method, path, body)
    except urllib.error.HTTPError as e:
        payload = e.read().decode('utf-8')
        try:
            obj = json.loads(payload)
        except Exception:
            obj = {'raw': payload}
        return e.code, obj


def test_dry_run_plan():
    code, obj = _request('POST', '/api/access/manager/onboard', {
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
    code, obj = _request_expect_error('POST', '/api/access/manager/onboard', {
        'manager_email': 'not-an-email',
        'dry_run': True,
    })
    assert code == 400, f'expected 400, got {code}'
    assert obj.get('ok') is False, f'expected ok=false, got {obj}'


def test_invalid_telegram_id_rejected():
    code, obj = _request_expect_error('POST', '/api/access/manager/onboard', {
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
