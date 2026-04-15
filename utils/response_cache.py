"""
utils/response_cache.py — Simple TTL cache for Flask JSON responses (E.2.3)
═══════════════════════════════════════════════════════════════════════════════
"""

import hashlib
import json
import time
import threading
from functools import wraps

_cache_lock = threading.Lock()
_cache: dict[str, tuple] = {}  # key -> (data_json, etag, expires_at)


def cached_json(ttl_seconds=30):
    """Decorator: cache JSON responses with TTL and ETag support."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            from flask import request, jsonify, make_response

            cache_key = f'{f.__name__}:{request.path}:{request.query_string.decode()}'

            with _cache_lock:
                entry = _cache.get(cache_key)
                if entry:
                    data_json, etag, expires_at = entry
                    if time.monotonic() < expires_at:
                        # Check If-None-Match
                        if_none_match = request.headers.get('If-None-Match', '')
                        if if_none_match == etag:
                            return make_response('', 304)
                        resp = make_response(data_json)
                        resp.headers['Content-Type'] = 'application/json'
                        resp.headers['ETag'] = etag
                        resp.headers['Cache-Control'] = f'max-age={ttl_seconds}'
                        return resp

            # Cache miss — call the real function
            result = f(*args, **kwargs)

            # Only cache 200 JSON responses
            if hasattr(result, 'status_code') and result.status_code == 200:
                data_bytes = result.get_data()
                etag = '"' + hashlib.md5(data_bytes).hexdigest()[:16] + '"'
                with _cache_lock:
                    _cache[cache_key] = (
                        data_bytes.decode(),
                        etag,
                        time.monotonic() + ttl_seconds,
                    )
                result.headers['ETag'] = etag
                result.headers['Cache-Control'] = f'max-age={ttl_seconds}'

            return result
        return wrapped
    return decorator


def invalidate(prefix=''):
    """Invalidate cache entries matching a prefix."""
    with _cache_lock:
        if not prefix:
            _cache.clear()
        else:
            stale = [k for k in _cache if k.startswith(prefix)]
            for k in stale:
                del _cache[k]
