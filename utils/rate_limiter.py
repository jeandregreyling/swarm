"""
utils/rate_limiter.py — Token-bucket rate limiter middleware (E.1.2)
═══════════════════════════════════════════════════════════════════════════════
Provides per-IP rate limiting for Flask endpoints.
"""

import time
import threading
import os
from functools import wraps

# Configuration
DEFAULT_RATE = int(os.environ.get('SWARM_RATE_LIMIT', '60'))  # req/min
AUTH_RATE = int(os.environ.get('SWARM_AUTH_RATE_LIMIT', '10'))  # req/min for auth
WINDOW = 60  # seconds

_lock = threading.Lock()
_buckets: dict[str, list] = {}  # ip -> [timestamps]
_CLEANUP_INTERVAL = 300  # cleanup stale entries every 5 min
_last_cleanup = time.monotonic()


def _cleanup():
    """Remove entries older than 2x window."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    cutoff = now - WINDOW * 2
    stale = [ip for ip, ts in _buckets.items() if not ts or ts[-1] < cutoff]
    for ip in stale:
        del _buckets[ip]


def _check_rate(ip, limit):
    """Check if IP is within rate limit. Returns (allowed, retry_after)."""
    now = time.monotonic()
    with _lock:
        _cleanup()
        if ip not in _buckets:
            _buckets[ip] = []
        # Drop timestamps outside window
        cutoff = now - WINDOW
        _buckets[ip] = [t for t in _buckets[ip] if t > cutoff]
        if len(_buckets[ip]) >= limit:
            oldest = _buckets[ip][0]
            retry_after = int(oldest + WINDOW - now) + 1
            return False, max(retry_after, 1)
        _buckets[ip].append(now)
        return True, 0


def rate_limit(limit=None):
    """Decorator: apply rate limiting to a Flask endpoint."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            from flask import request, jsonify
            ip = request.remote_addr or '127.0.0.1'
            allowed, retry_after = _check_rate(ip, limit or DEFAULT_RATE)
            if not allowed:
                resp = jsonify({'error': 'Rate limit exceeded'})
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_after)
                return resp
            return f(*args, **kwargs)
        return wrapped
    return decorator


def rate_limit_auth(f):
    """Decorator: stricter rate limit for auth endpoints."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        from flask import request, jsonify
        ip = request.remote_addr or '127.0.0.1'
        allowed, retry_after = _check_rate(f'auth:{ip}', AUTH_RATE)
        if not allowed:
            resp = jsonify({'error': 'Rate limit exceeded'})
            resp.status_code = 429
            resp.headers['Retry-After'] = str(retry_after)
            return resp
        return f(*args, **kwargs)
    return wrapped
