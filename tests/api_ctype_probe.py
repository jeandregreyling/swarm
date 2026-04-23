#!/usr/bin/env python3
"""Swarm API content-type confusion probe.

Seventh tier of the audit hierarchy. Prior probes all sent valid JSON
with ``Content-Type: application/json``. This one asks:

    "Does the handler survive when the Content-Type is wrong, missing,
    or lying about the body?"

Fires 5 content-type/body variants at every non-destructive mutation
endpoint. Classifies worst outcome across the batch:

  V1  body={} but Content-Type header omitted entirely
  V2  body={} with Content-Type: text/plain
  V3  body="not json at all"  with Content-Type: application/json (lie)
  V4  body={} with Content-Type: application/xml
  V5  body="<xml/>" with Content-Type: application/json (lie #2)

Real attack surface: Flask's ``request.get_json()`` raises on malformed
bodies and some blueprints never guard that call. Surfaces as BROKEN 500.

Classifications (worst across V1..V5):

  VALIDATED   400/404/405/409/413/415/422/502 — parser / schema rejected
  ACCEPTED    2xx                              — handler tolerates garbage
  AUTH        401/403
  DEPENDENCY  503
  BROKEN      5xx                              — real bug
  STUCK       timeout                          — real bug

Exit 0 only when BROKEN+STUCK == 0. Reuses SKIP from api_mutation_probe.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request

from api_mutation_probe import SKIP  # type: ignore

BASE = "http://127.0.0.1:5050"
TIMEOUT = 8.0

# (name, body_bytes, headers_dict) — empty dict means send no Content-Type
_VARIANTS = [
    ('V1_no_ctype',      b'{}',                {}),
    ('V2_text_plain',    b'{}',                {'Content-Type': 'text/plain'}),
    ('V3_lying_json',    b'not json at all',   {'Content-Type': 'application/json'}),
    ('V4_xml_ctype',     b'{}',                {'Content-Type': 'application/xml'}),
    ('V5_xml_as_json',   b'<xml/>',            {'Content-Type': 'application/json'}),
]

_SEVERITY = {
    'STUCK': 6,
    'BROKEN': 5,
    'ACCEPTED': 4,
    'DEPENDENCY': 3,
    'AUTH': 2,
    'VALIDATED': 1,
}


def _discover():
    with urllib.request.urlopen(BASE + "/api/_introspect/routes", timeout=5) as r:
        return json.loads(r.read().decode())


def _probe(method, path, body, headers):
    url = BASE + path
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
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

    print(f"probing {len(targets)} endpoints with {len(_VARIANTS)} "
          f"content-type variants each", file=sys.stderr)

    counts = {k: 0 for k in ('VALIDATED', 'ACCEPTED', 'AUTH',
                             'DEPENDENCY', 'BROKEN', 'STUCK')}
    broken, stuck, accepted = [], [], []

    t0 = time.time()
    for method, path in targets:
        worst_cat = 'VALIDATED'
        worst_ev = None
        for vname, body, headers in _VARIANTS:
            code, resp_body = _probe(method, path, body, headers)
            cat = _classify(code)
            if _SEVERITY[cat] > _SEVERITY[worst_cat]:
                worst_cat = cat
                worst_ev = (vname, code, (resp_body or '')[:160])
            if worst_cat in ('BROKEN', 'STUCK'):
                break
        counts[worst_cat] += 1
        if worst_cat == 'BROKEN':
            broken.append((method, path, worst_ev))
            if len(broken) >= 15:
                print(f"\n(early-exit at {len(broken)} BROKEN)", file=sys.stderr)
                break
        elif worst_cat == 'STUCK':
            stuck.append((method, path, worst_ev))
        elif worst_cat == 'ACCEPTED':
            accepted.append((method, path, worst_ev))

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k:10s} {v}", file=sys.stderr)

    if broken:
        print("\nBROKEN (5xx on wrong content-type):", file=sys.stderr)
        for m, p, ev in broken:
            vname, code, body = ev or ('?', '?', '')
            print(f"  {code} {m:6s} {p}  [{vname}]\n    {body}", file=sys.stderr)
    if stuck:
        print("\nSTUCK:", file=sys.stderr)
        for m, p, ev in stuck:
            vname = ev[0] if ev else '?'
            print(f"  {m:6s} {p}  [{vname}]", file=sys.stderr)
    if accepted:
        print(f"\nACCEPTED (tolerated wrong type): {len(accepted)}", file=sys.stderr)
        for m, p, ev in accepted[:20]:
            vname, code, _ = ev or ('?', '?', '')
            print(f"  {code} {m:6s} {p}  [{vname}]", file=sys.stderr)

    bad = counts['BROKEN'] + counts['STUCK']
    print(f"\nscore: {bad} bad / {len(targets)} probed")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
