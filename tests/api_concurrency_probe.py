#!/usr/bin/env python3
"""Swarm API concurrency / idempotency probe.

Sixth tier of the audit hierarchy. Where the mutation probe asked
"does the schema reject empty input?" and the bogus probe asked "does
the handler survive wrong-type input?", this probe asks:

    "Does the handler survive CONCURRENT calls?"

Fires N=5 parallel empty-body requests at every non-destructive
POST/PATCH/PUT endpoint. Catches:

  * UNIQUE-constraint races (two workers pick the same default key)
  * Lock contention / deadlocks surfacing as 500
  * TOCTOU checks that pass single-threaded but fail in parallel
  * STUCK endpoints whose single-threaded code races on a shared file

Classification is **worst outcome across the N parallel calls**:

  VALIDATED   all responses in 400/404/405/409/415/422/502
  ACCEPTED    all in 2xx                 (possible duplicate-row smell)
  AUTH        all 401/403
  DEPENDENCY  all 503
  FLAKY       mixed VALIDATED/ACCEPTED/AUTH across the 5 (not a bug)
  BROKEN      any 5xx (race surfaces as unhandled exception)
  STUCK       any timeout

Exit 0 only when BROKEN+STUCK == 0. FLAKY is reported but not a fail.

Reuses SKIP from api_mutation_probe for DRY + v1 alias expansion.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from api_mutation_probe import SKIP  # type: ignore

BASE = "http://127.0.0.1:5050"
TIMEOUT = 10.0
FANOUT = 5  # parallel requests per endpoint


def _discover():
    with urllib.request.urlopen(BASE + "/api/_introspect/routes", timeout=5) as r:
        return json.loads(r.read().decode())


def _one(method: str, path: str):
    url = BASE + path
    req = urllib.request.Request(
        url, data=b'{}', method=method,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code = r.getcode()
            r.read(256)
            return code, None
    except urllib.error.HTTPError as e:
        try:
            body = e.read(256).decode('utf-8', 'replace')
        except Exception:
            body = ''
        return e.code, body
    except (socket.timeout, urllib.error.URLError):
        return None, 'timeout'
    except Exception as e:  # noqa: BLE001
        return None, f'{type(e).__name__}: {e}'


def _cat(code):
    if code is None:
        return 'STUCK'
    if 200 <= code < 300:
        return 'ACCEPTED'
    if code in (401, 403):
        return 'AUTH'
    if code in (400, 404, 405, 409, 415, 422, 502):
        return 'VALIDATED'
    if code == 503:
        return 'DEPENDENCY'
    if 500 <= code < 600:
        return 'BROKEN'
    return 'VALIDATED'


def _burst(method: str, path: str):
    """Fire FANOUT parallel requests, return list of (code, body)."""
    with ThreadPoolExecutor(max_workers=FANOUT) as pool:
        futures = [pool.submit(_one, method, path) for _ in range(FANOUT)]
        return [f.result() for f in futures]


def _worst(results):
    """Worst-outcome classifier across the parallel batch."""
    cats = [_cat(c) for c, _ in results]
    # Severity order: BROKEN > STUCK > DEPENDENCY > FLAKY > ACCEPTED > AUTH > VALIDATED
    if 'BROKEN' in cats:
        return 'BROKEN'
    if 'STUCK' in cats:
        return 'STUCK'
    unique = set(cats)
    if unique == {'DEPENDENCY'}:
        return 'DEPENDENCY'
    # If mixed non-bad categories show up, endpoint is non-deterministic
    # under load. Flag as FLAKY (report-only, not a failure).
    non_bad = unique - {'BROKEN', 'STUCK'}
    if len(non_bad) > 1:
        return 'FLAKY'
    if unique == {'ACCEPTED'}:
        return 'ACCEPTED'
    if unique == {'AUTH'}:
        return 'AUTH'
    return 'VALIDATED'


def main() -> int:
    routes = _discover()
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

    print(f"probing {len(targets)} endpoints at fanout={FANOUT}", file=sys.stderr)

    counts = {k: 0 for k in ('VALIDATED', 'ACCEPTED', 'AUTH',
                             'DEPENDENCY', 'FLAKY', 'BROKEN', 'STUCK')}
    broken, stuck, flaky = [], [], []

    t0 = time.time()
    for method, path in targets:
        results = _burst(method, path)
        cat = _worst(results)
        counts[cat] += 1
        codes = [c for c, _ in results]
        bodies = [b for _, b in results if b]
        if cat == 'BROKEN':
            # pick the first 5xx body for triage
            bad_body = next(
                (b for c, b in results if c is not None and 500 <= c < 600),
                '',
            )
            broken.append((method, path, codes, (bad_body or '')[:200]))
            # Early exit if we've seen 10+ broken already
            if len(broken) >= 10:
                print(
                    f"\n(early-exit: {len(broken)} BROKEN, halting to surface pattern)",
                    file=sys.stderr,
                )
                break
        elif cat == 'STUCK':
            stuck.append((method, path, codes))
        elif cat == 'FLAKY':
            flaky.append((method, path, codes))

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k:10s} {v}", file=sys.stderr)

    if broken:
        print("\nBROKEN (race condition / unhandled exception under load):",
              file=sys.stderr)
        for m, p, cs, b in broken:
            print(f"  {cs} {m:6s} {p}\n    {b}", file=sys.stderr)
    if stuck:
        print("\nSTUCK (timeout under load):", file=sys.stderr)
        for m, p, cs in stuck:
            print(f"  {cs} {m:6s} {p}", file=sys.stderr)
    if flaky:
        print(f"\nFLAKY (mixed outcomes across {FANOUT} parallel calls): "
              f"{len(flaky)}", file=sys.stderr)
        for m, p, cs in flaky[:20]:
            print(f"  {cs} {m:6s} {p}", file=sys.stderr)

    bad = counts['BROKEN'] + counts['STUCK']
    print(f"\nscore: {bad} bad / {len(targets)} probed")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
