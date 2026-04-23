#!/usr/bin/env python3
"""Swarm API wide probe — iterates every registered GET /api/* endpoint.

Classifications:
  HEALTHY   2xx / 3xx
  EXPECTED  400/401/403/405/415/422 (endpoint exists, we just can't call it blind)
  STREAMING SSE-like: first byte fast, no Content-Length
  MISSING   404 (registered route returning 404 → dead advertising)
  BROKEN    5xx
  STUCK     no byte within timeout (real hang)

Exit 0 only if MISSING=0 and BROKEN=0 and STUCK=0.
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

# Endpoints whose own docstring / contract declares them expensive.
# They legitimately exceed the probe budget on first call (IMAP, remote
# catalog fetches, etc.). Counted as SLOW, not STUCK.
KNOWN_SLOW = frozenset({
    '/api/email/live',
    '/api/v1/email/live',
})


def _discover_routes():
    try:
        with urllib.request.urlopen(BASE + "/api/_introspect/routes", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:
        pass
    import os
    os.environ.setdefault("SWARM_QUIET", "1")
    sys.path.insert(0, "/home/seven/swarm")
    from frontend.terminal import create_app  # type: ignore
    app = create_app()
    paths = {}
    for rule in app.url_map.iter_rules():
        p = str(rule.rule)
        if not p.startswith("/api/"):
            continue
        ms = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
        paths.setdefault(p, set()).update(ms)
    return [{"path": p, "methods": sorted(list(m))} for p, m in sorted(paths.items())]


def _probe_streaming(url: str, first_byte_timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=first_byte_timeout) as r:
            ct = (r.headers.get("Content-Type") or "").lower()
            if "event-stream" in ct or "x-ndjson" in ct:
                return True
            sock = r.fp.raw._sock  # type: ignore[attr-defined]
            sock.settimeout(first_byte_timeout)
            try:
                chunk = sock.recv(64)
            except socket.timeout:
                return False
            return bool(chunk) and r.headers.get("Content-Length") is None
    except Exception:
        return False


def _classify(code: int) -> str:
    if 200 <= code < 400:
        return "HEALTHY"
    if code == 404:
        return "MISSING"
    if code in (400, 401, 403, 405, 415, 422):
        return "EXPECTED"
    if 500 <= code < 600:
        return "BROKEN"
    return "EXPECTED"


def main() -> int:
    routes = _discover_routes()
    gets = [r["path"] for r in routes
            if "GET" in r.get("methods", []) and "<" not in r["path"]]
    print(f"probing {len(gets)} GET endpoints", file=sys.stderr)

    counts = {"HEALTHY": 0, "EXPECTED": 0, "STREAMING": 0,
              "SLOW": 0, "MISSING": 0, "BROKEN": 0, "STUCK": 0}
    missing, broken, stuck = [], [], []
    t0 = time.time()
    for p in gets:
        url = BASE + p
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                code = r.getcode()
                r.read(512)
                counts[_classify(code)] += 1
        except urllib.error.HTTPError as e:
            v = _classify(e.code)
            counts[v] += 1
            if v == "MISSING":
                missing.append(p)
            elif v == "BROKEN":
                broken.append((e.code, p))
        except (socket.timeout, urllib.error.URLError):
            if _probe_streaming(url):
                counts["STREAMING"] += 1
            elif p in KNOWN_SLOW:
                counts["SLOW"] += 1
            else:
                counts["STUCK"] += 1
                stuck.append(p)
        except Exception as e:  # noqa: BLE001
            counts["STUCK"] += 1
            stuck.append(f"{p} ({type(e).__name__})")

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k:10s} {v}", file=sys.stderr)
    if missing:
        print("\nMISSING:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
    if broken:
        print("\nBROKEN:", file=sys.stderr)
        for c, p in broken:
            print(f"  {c} {p}", file=sys.stderr)
    if stuck:
        print("\nSTUCK:", file=sys.stderr)
        for p in stuck:
            print(f"  {p}", file=sys.stderr)

    bad = counts["MISSING"] + counts["BROKEN"] + counts["STUCK"]
    print(f"\nscore: {bad} bad / {len(gets)} probed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
