#!/usr/bin/env python3
"""Swarm API bogus-body (type confusion) probe.

Sends structurally wrong payloads to every non-destructive mutation endpoint
and looks for unhandled type errors. Where `api_mutation_probe` sends ``{}``
to ensure missing-field validation, this probe sends wrong-type values to
ensure input-validation catches them before they hit the domain layer.

Payload variants tried per endpoint (first 5xx / STUCK wins):

  V1 — lists where strings expected:
       {"title": [], "description": [], "name": [],
        "message": [], "label": [], "id": [], "kind": [],
        "status": [], "methodology": [], "query": []}
  V2 — dicts where strings expected:
       same keys with ``{}`` values.
  V3 — numbers where strings expected:
       same keys with ``12345`` values.
  V4 — None where strings expected:
       same keys with ``None`` values.
  V5 — oversized string (4 KB) in ``title``:
       noisy reject good; crash bad.

Classifications (most severe wins across V1..V5):

  VALIDATED   400/404/405/415/422 — schema rejected cleanly
  ACCEPTED    200/201/202/204     — endpoint accepted garbage
  AUTH        401/403             — auth fired first
  DEPENDENCY  503                 — optional integration refused
  BROKEN      5xx (not 503)       — unhandled on bad input  ← real bug
  STUCK       timeout             — hangs on bad input      ← real bug

Exit 0 only if BROKEN=0 and STUCK=0. ACCEPTED is diagnostic only.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request

# Reuse the mutation probe's SKIP list verbatim so we stay consistent
# across the four-tier audit hierarchy.
from api_mutation_probe import SKIP  # type: ignore

BASE = "http://127.0.0.1:5050"
TIMEOUT = 8.0

_STR_KEYS = (
    'title', 'description', 'name', 'message', 'label', 'id',
    'kind', 'status', 'methodology', 'query', 'prompt', 'text',
    'subject', 'content', 'script_id', 'proposal_id',
)


def _payload(value):
    return {k: value for k in _STR_KEYS}


_VARIANTS = [
    ('V1_list',   _payload([])),
    ('V2_dict',   _payload({})),
    ('V3_number', _payload(12345)),
    ('V4_null',   _payload(None)),
    ('V5_huge',   {'title': 'x' * 4096}),
]


def _discover():
    with urllib.request.urlopen(BASE + "/api/_introspect/routes", timeout=5) as r:
        return json.loads(r.read().decode())


def _probe(method: str, path: str, payload: dict):
    url = BASE + path
    data = json.dumps(payload).encode()
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
    if code == 503:
        return 'DEPENDENCY'
    if code in (400, 404, 405, 409, 413, 415, 422, 502):
        return 'VALIDATED'
    if 500 <= code < 600:
        return 'BROKEN'
    return 'VALIDATED'


# Severity rank: worst outcome across variants determines the classification
# assigned to the endpoint overall.
_SEVERITY = {
    'STUCK': 6,
    'BROKEN': 5,
    'ACCEPTED': 4,
    'DEPENDENCY': 3,
    'AUTH': 2,
    'VALIDATED': 1,
}


def main() -> int:
    routes = _discover()
    skip = set(SKIP)
    for p in list(SKIP):
        if p.startswith('/api/') and not p.startswith('/api/v1/'):
            skip.add('/api/v1/' + p[len('/api/'):])
    targets = []
    for r in routes:
        path = r['path']
        if '<' in path or path in skip:
            continue
        for m in r.get('methods', []):
            if m in ('POST', 'PATCH', 'PUT'):
                targets.append((m, path))
    print(f"probing {len(targets)} mutation endpoints "
          f"with {len(_VARIANTS)} bogus-body variants each",
          file=sys.stderr)

    counts = {k: 0 for k in ('VALIDATED', 'ACCEPTED', 'AUTH',
                             'DEPENDENCY', 'BROKEN', 'STUCK')}
    broken = []
    stuck = []
    accepted = []

    t0 = time.time()
    for method, path in targets:
        worst_cat = 'VALIDATED'
        worst_evidence = None
        for vname, payload in _VARIANTS:
            code, body = _probe(method, path, payload)
            cat = _classify(code)
            if _SEVERITY[cat] > _SEVERITY[worst_cat]:
                worst_cat = cat
                worst_evidence = (vname, code, (body or '')[:160])
            # Early-out on worst case — no point probing further variants
            if worst_cat == 'BROKEN' or worst_cat == 'STUCK':
                break
        counts[worst_cat] += 1
        if worst_cat == 'BROKEN':
            broken.append((method, path, worst_evidence))
        elif worst_cat == 'STUCK':
            stuck.append((method, path, worst_evidence))
        elif worst_cat == 'ACCEPTED':
            accepted.append((method, path, worst_evidence))

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k:10s} {v}", file=sys.stderr)

    if broken:
        print("\nBROKEN (5xx on bogus body):", file=sys.stderr)
        for m, p, ev in broken:
            vname, code, body = ev or ('?', '?', '')
            print(f"  {code} {m:6s} {p}  [{vname}]\n    {body}", file=sys.stderr)
    if stuck:
        print("\nSTUCK:", file=sys.stderr)
        for m, p, ev in stuck:
            vname = ev[0] if ev else '?'
            print(f"  {m:6s} {p}  [{vname}]", file=sys.stderr)
    if accepted:
        print(f"\nACCEPTED (garbage accepted — review): {len(accepted)}",
              file=sys.stderr)
        for m, p, ev in accepted:
            vname, code, _ = ev or ('?', '?', '')
            print(f"  {code} {m:6s} {p}  [{vname}]", file=sys.stderr)

    bad = counts['BROKEN'] + counts['STUCK']
    print(f"\nscore: {bad} bad / {len(targets)} probed")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
