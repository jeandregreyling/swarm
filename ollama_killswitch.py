#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


OLLAMA_PS_URL = 'http://127.0.0.1:11434/api/ps'


def _run(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        return {
            'ok': proc.returncode == 0,
            'returncode': proc.returncode,
            'stdout': str(proc.stdout or '').strip(),
            'stderr': str(proc.stderr or '').strip(),
        }
    except Exception as exc:
        return {
            'ok': False,
            'returncode': None,
            'stdout': '',
            'stderr': str(exc),
        }


def _active_models():
    request = urllib.request.Request(OLLAMA_PS_URL, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.load(response)
    models = []
    for item in payload.get('models') or []:
        name = str(item.get('name') or item.get('model') or '').strip()
        if name:
            models.append(name)
    return models


def _stop_service():
    attempts = []
    commands = [['systemctl', 'stop', 'ollama']]
    if os.geteuid() != 0:
        commands.append(['sudo', '-n', 'systemctl', 'stop', 'ollama'])
    for cmd in commands:
        result = _run(cmd)
        attempts.append({'command': ' '.join(cmd), **result})
        if result['ok']:
            return True, attempts
    return False, attempts


def main():
    parser = argparse.ArgumentParser(description='Stop active Ollama models and optionally the Ollama service.')
    parser.add_argument('--service', action='store_true', help='Also stop ollama.service after unloading active models.')
    args = parser.parse_args()

    errors = []
    try:
        models = _active_models()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        models = []
        errors.append(f'Unable to query Ollama runtime: {exc}')

    if models:
        print('Active Ollama models:')
        for name in models:
            print(f' - {name}')
    else:
        print('No active Ollama models reported.')

    stop_results = []
    for name in models:
        result = _run(['ollama', 'stop', name])
        stop_results.append({'model': name, **result})
        status = 'stopped' if result['ok'] else 'failed'
        detail = result['stdout'] or result['stderr'] or f'returncode={result["returncode"]}'
        print(f'[{status}] {name}: {detail}')

    service_ok = True
    service_attempts = []
    if args.service:
        service_ok, service_attempts = _stop_service()
        for attempt in service_attempts:
            status = 'stopped' if attempt['ok'] else 'failed'
            detail = attempt['stdout'] or attempt['stderr'] or f'returncode={attempt["returncode"]}'
            print(f'[{status}] {attempt["command"]}: {detail}')

    if errors:
        for message in errors:
            print(message, file=sys.stderr)

    model_failures = [item for item in stop_results if not item['ok']]
    if model_failures or not service_ok or errors:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())