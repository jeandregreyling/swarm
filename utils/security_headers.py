"""
utils/security_headers.py — Security headers + input validation middleware (E.1)
═══════════════════════════════════════════════════════════════════════════════
Wire into Flask app via: init_security(app)
"""

import os
import re

# Max request body (default 1MB)
MAX_CONTENT_LENGTH = int(os.environ.get('SWARM_MAX_REQUEST_MB', '1')) * 1024 * 1024

# Allowed CORS origins (comma-separated) — auto-include all known ports
_DEFAULT_CORS = 'http://localhost:5050,http://127.0.0.1:5050,http://localhost:5051,http://127.0.0.1:5051,http://localhost:5053,http://127.0.0.1:5053'
CORS_ORIGINS = os.environ.get('SWARM_CORS_ORIGINS', _DEFAULT_CORS).split(',')


def init_security(app):
    """Register security middleware on a Flask app."""
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

    @app.after_request
    def _set_security_headers(response):
        # Strip hop-by-hop headers that wsgiref rejects (Connection, etc.)
        response.headers.pop('Connection', None)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # CORS
        origin = None
        from flask import request
        req_origin = request.headers.get('Origin', '')
        if req_origin in CORS_ORIGINS:
            origin = req_origin
        if origin:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Headers'] = (
                'Content-Type, Authorization, X-Node-ID, X-Node-API-Key, X-Request-ID'
            )
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response


def sanitize_text(text, max_length=10000):
    """Sanitize user-provided text: strip control chars, enforce length."""
    if not isinstance(text, str):
        return ''
    # Remove control characters except newline/tab
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text[:max_length]


def validate_id(value, *, max_length=64):
    """Validate a string ID parameter. Returns sanitized value or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    # Allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_\-]+$', value):
        return None
    return value


def validate_int(value, *, min_val=0, max_val=2**31):
    """Validate an integer parameter. Returns int or None."""
    try:
        n = int(value)
        if min_val <= n <= max_val:
            return n
    except (TypeError, ValueError):
        pass
    return None
