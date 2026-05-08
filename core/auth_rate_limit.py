"""core/auth_rate_limit.py — in-process rate limiter + audit log for /api/auth.

Fixed-window per-IP limiter. Adequate for single-node Swarm deployments;
multi-node deployments should front the Flask app with Caddy/nginx's own
rate-limit plugin (see ops/caddy/Caddyfile.template).

Audit log is appended to ``audit/auth.log`` (one JSON record per line) so
rotation + retention can be handled by logrotate without reformatting.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from collections import defaultdict, deque
from typing import Optional

AUDIT_DIR = pathlib.Path(os.environ.get("SWARM_AUDIT_DIR", os.path.join(os.path.dirname(__file__), "..", "audit")))
AUDIT_LOG = AUDIT_DIR / "auth.log"

_lock = threading.RLock()
_buckets: dict[str, deque[float]] = defaultdict(deque)

DEFAULT_WINDOW_S = 60.0
DEFAULT_LIMIT = 10  # requests per window per key


def _prune(key: str, now: float, window_s: float) -> None:
    bucket = _buckets[key]
    cutoff = now - window_s
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def allow(key: str, *, limit: int = DEFAULT_LIMIT, window_s: float = DEFAULT_WINDOW_S) -> bool:
    """Return True if the request should be allowed. Increments the bucket on allow."""
    now = time.time()
    with _lock:
        _prune(key, now, window_s)
        bucket = _buckets[key]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def remaining(key: str, *, limit: int = DEFAULT_LIMIT, window_s: float = DEFAULT_WINDOW_S) -> int:
    now = time.time()
    with _lock:
        _prune(key, now, window_s)
        return max(0, limit - len(_buckets[key]))


def audit(event: str, *, username: Optional[str] = None, ip: Optional[str] = None,
          ok: bool = True, extra: Optional[dict] = None) -> None:
    rec = {
        "ts": time.time(),
        "event": event,
        "user": username,
        "ip": ip,
        "ok": bool(ok),
    }
    if extra:
        rec.update(extra)
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass
