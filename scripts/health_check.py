#!/usr/bin/env python3
"""
scripts/health_check.py — Swarm health smoke test
══════════════════════════════════════════════════
Checks that the running swarm server is healthy: API endpoints respond,
tile data shapes are correct, and local services are reachable.

Usage:
    python3 scripts/health_check.py             # quick mode (default, ~5s)
    python3 scripts/health_check.py --full      # full mode (~30s, includes agent ping)
    python3 scripts/health_check.py --port 5051 # target a specific port

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.
Output is structured so agents can parse PASS/FAIL lines.
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_PORT = 5050
TIMEOUT_SEC  = 8

# ── Result tracking ───────────────────────────────────────────────────────────

_results = []

def _check(name, fn):
    """Run fn(), record PASS/FAIL with timing."""
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f'Exception: {e}'
    elapsed = round((time.time() - t0) * 1000)
    status = 'PASS' if ok else 'FAIL'
    _results.append({'name': name, 'ok': ok, 'detail': detail, 'ms': elapsed})
    icon = '✓' if ok else '✗'
    print(f'  {icon} [{status}] {name} ({elapsed}ms){": " + detail if not ok else ""}')
    return ok


def _get(base, path, expect_keys=None):
    """HTTP GET, return (ok, detail). Optionally check response keys."""
    url = f'{base}{path}'
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if resp.status != 200:
                return False, f'HTTP {resp.status}'
            body = json.loads(resp.read().decode('utf-8'))
            if expect_keys:
                missing = [k for k in expect_keys if k not in body]
                if missing:
                    return False, f'Missing keys: {missing}'
            return True, ''
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}'
    except urllib.error.URLError as e:
        return False, f'Connection refused or timeout: {e.reason}'
    except Exception as e:
        return False, str(e)


# ── Check suites ──────────────────────────────────────────────────────────────

def run_quick(base):
    print('\n── Quick checks ──────────────────────────────────────────────')

    # Core server
    _check('server reachable',
           lambda: _get(base, '/api/monitor'))

    # Monitor tile data
    _check('monitor: cpu_percent present',
           lambda: _get(base, '/api/monitor', ['cpu_percent', 'ram_percent']))

    # ALM / proposals
    _check('work-proposals endpoint',
           lambda: _get(base, '/api/work-proposals', ['proposals']))

    # Queue (POST-only — check via work-proposals which reflects queue state)
    _check('queue depth (via monitor)',
           lambda: _get(base, '/api/monitor', ['queue_depth']))

    # Conversations
    _check('conversations endpoint',
           lambda: _get(base, '/api/conversations'))

    # Ghost circle (activity log)
    _check('ghost-circle endpoint',
           lambda: _get(base, '/api/ghost_circle'))

    # Tickets
    _check('tickets endpoint',
           lambda: _get(base, '/api/tickets'))

    # ALM status
    _check('alm/status endpoint',
           lambda: _get(base, '/api/alm/status', ['status']))

    # Services panel
    _check('services endpoint',
           lambda: _get(base, '/api/services'))

    # Brief
    _check('brief endpoint',
           lambda: _get(base, '/api/brief'))


def run_full(base):
    run_quick(base)

    print('\n── Full checks (agent connectivity) ──────────────────────────')

    # Ollama local models
    def _check_ollama():
        try:
            req = urllib.request.Request(
                'http://localhost:11434/api/tags',
                headers={'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                models = body.get('models', [])
                names = [m.get('name', '') for m in models]
                return True, f'{len(models)} models: {", ".join(names[:3])}{"…" if len(names)>3 else ""}'
        except Exception as e:
            return False, f'Ollama not reachable: {e}'
    _check('ollama reachable', _check_ollama)

    # DB integrity — check core tables exist via monitor
    _check('DB tables accessible (via monitor)',
           lambda: _get(base, '/api/monitor', ['queue_depth', 'open_tickets']))

    # Shell API
    _check('shell whitelist endpoint',
           lambda: _get(base, '/api/terminal/sudo-whitelist'))

    # Memory / agents
    _check('agent memory endpoint',
           lambda: _get(base, '/api/agent-memory'))


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary():
    total  = len(_results)
    passed = sum(1 for r in _results if r['ok'])
    failed = total - passed
    slowest = sorted(_results, key=lambda r: r['ms'], reverse=True)[:3]

    print(f'\n══ Health check summary: {passed}/{total} passed', end='')
    if failed:
        print(f'  ({failed} FAILED)', end='')
    print(f' ══')

    if failed:
        print('\nFailed checks:')
        for r in _results:
            if not r['ok']:
                print(f'  ✗ {r["name"]}: {r["detail"]}')

    if slowest:
        slow_str = ', '.join(f'{r["name"]} {r["ms"]}ms' for r in slowest)
        print(f'\nSlowest: {slow_str}')

    print(f'Checked at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
    return failed == 0


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Swarm health check')
    parser.add_argument('--full',  action='store_true', help='Run full check suite')
    parser.add_argument('--port',  type=int, default=DEFAULT_PORT, help='Server port (default 5050)')
    parser.add_argument('--host',  default='localhost', help='Server host')
    args = parser.parse_args()

    base = f'http://{args.host}:{args.port}'
    print(f'Swarm health check — {base}  ({"full" if args.full else "quick"} mode)')

    if args.full:
        run_full(base)
    else:
        run_quick(base)

    ok = print_summary()
    sys.exit(0 if ok else 1)
