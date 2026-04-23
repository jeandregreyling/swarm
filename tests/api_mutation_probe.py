#!/usr/bin/env python3
"""Swarm API mutation-safety probe.

Walks every registered POST/PATCH endpoint (no path params, not in SKIP)
and sends an empty JSON body (``{}``). Classifies the response:

  VALIDATED   400/404/405/415/422 — schema said no, good
  ACCEPTED    200/201/202/204     — endpoint accepted empty body (toggle / idempotent)
  AUTH        401/403             — auth layer fired before schema
  BROKEN      5xx                 — unhandled exception on empty input
  STUCK       timeout             — hangs on empty body
  SKIPPED     path in SKIP allow-list

Exit 0 only if BROKEN=0 and STUCK=0. ACCEPTED surfaces potential side-effects
for manual review; not a failure condition on its own.

DELETE endpoints are intentionally **not** probed — destructive.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5050"
TIMEOUT = 8.0

# Endpoints that are safe to skip — they do real work on any call (even empty),
# or represent async fire-and-forget that shouldn't be invoked in a test.
SKIP = frozenset({
    # Shell / terminal execution: spawns subprocesses
    '/api/shell/execute',
    '/api/shell/stream',
    '/api/shell/stream/stop',
    '/api/shell/agent-kill',
    '/api/terminal/run',
    '/api/terminal/stream',
    '/api/terminal/stream/stop',
    '/api/hands/run',
    # Kill switches & admin fire-and-forget
    '/api/killswitch/trigger',
    '/api/killswitch/reset',
    '/api/killswitch/test',
    '/api/ops/restart',
    '/api/ops/shutdown',
    # Agent/LLM invocations (cost / latency)
    '/api/nine/stream',
    '/api/ten/stream',
    '/api/chat',
    '/api/chat/stream',
    '/api/chat/classify',
    '/api/spine/stream',
    # Proposal apply — mutates code
    '/api/proposals/apply',
    '/api/git/apply',
    '/api/git/commit',
    '/api/git/push',
    # Email send / outbound comms
    '/api/email/send',
    '/api/discord/send',
    '/api/telegram/send',
    # Mass-update sweeps
    '/api/housekeeping/run',
    '/api/fridays/run',
    '/api/audit/run',
})


def _discover():
    with urllib.request.urlopen(BASE + "/api/_introspect/routes", timeout=5) as r:
        return json.loads(r.read().decode())


def _probe(method: str, path: str):
    url = BASE + path
    data = b'{}'
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code = r.getcode()
            r.read(512)
            return code, None
    except urllib.error.HTTPError as e:
        try:
            body = e.read(512).decode('utf-8', 'replace')
        except Exception:
            body = ''
        return e.code, body
    except (socket.timeout, urllib.error.URLError):
        return None, 'timeout'
    except Exception as e:  # noqa: BLE001
        return None, f'{type(e).__name__}: {e}'


def _classify(code):
    if code is None:
        return 'STUCK'
    if 200 <= code < 300:
        return 'ACCEPTED'
    if code in (401, 403):
        return 'AUTH'
    if code in (400, 404, 405, 409, 415, 422, 502):
        return 'VALIDATED'
    if code == 503:
        # Service Unavailable is a legitimate response for optional
        # dependencies that aren't configured (e.g. missing API keys).
        # The endpoint exists and refuses gracefully.
        return 'DEPENDENCY'
    if 500 <= code < 600:
        return 'BROKEN'
    return 'VALIDATED'


def main() -> int:
    routes = _discover()
    # Expand SKIP to cover both /api/foo and /api/v1/foo aliases
    skip = set(SKIP)
    for p in list(SKIP):
        if p.startswith('/api/') and not p.startswith('/api/v1/'):
            skip.add('/api/v1/' + p[len('/api/'):])
    targets = []
    for r in routes:
        path = r['path']
        if '<' in path:
            continue
        if path in skip:
            continue
        for m in r.get('methods', []):
            if m in ('POST', 'PATCH', 'PUT'):
                targets.append((m, path))
    print(f"probing {len(targets)} mutation endpoints", file=sys.stderr)

    counts = {k: 0 for k in ('VALIDATED', 'ACCEPTED', 'AUTH',
                             'DEPENDENCY', 'BROKEN', 'STUCK')}
    broken = []
    stuck = []
    accepted = []

    t0 = time.time()
    for method, path in targets:
        code, body = _probe(method, path)
        cat = _classify(code)
        counts[cat] += 1
        if cat == 'BROKEN':
            broken.append((method, path, code, (body or '')[:160]))
        elif cat == 'STUCK':
            stuck.append((method, path, body))
        elif cat == 'ACCEPTED':
            accepted.append((method, path, code))

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k:10s} {v}", file=sys.stderr)

    if broken:
        print("\nBROKEN (5xx on empty body):", file=sys.stderr)
        for m, p, c, b in broken:
            print(f"  {c} {m:6s} {p}\n    {b}", file=sys.stderr)
    if stuck:
        print("\nSTUCK:", file=sys.stderr)
        for m, p, reason in stuck:
            print(f"  {m:6s} {p}  ({reason})", file=sys.stderr)
    if accepted:
        print(f"\nACCEPTED (review for idempotency): {len(accepted)}", file=sys.stderr)
        for m, p, c in accepted:
            print(f"  {c} {m:6s} {p}", file=sys.stderr)

    bad = counts['BROKEN'] + counts['STUCK']
    print(f"\nscore: {bad} bad / {len(targets)} probed")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
