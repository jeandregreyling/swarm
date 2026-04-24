"""
services.auth — Authentication helpers shared across blueprints.

Extracted from services/__init__.py as part of Phase B (services.py split).
All callers continue to see these symbols via `from services import *`
because __init__.py re-exports them.
"""
from functools import wraps
from datetime import datetime, timezone

from flask import request, jsonify

from database import get_connection


def _deactivate_session(token: str) -> None:
    if not token:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE user_sessions SET is_active = 0 WHERE session_token = ?",
            (token,),
        )
        conn.commit()
    finally:
        conn.close()


def get_current_user():
    """Look up the currently logged-in user from the session cookie.
    Returns a dict with profile info, or None if not logged in."""
    token = request.cookies.get('friday_session')
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT s.username, s.expires_at, p.display_name, p.role, p.approved, p.is_active "
            "FROM user_sessions s "
            "JOIN user_profiles p ON p.username = s.username "
            "WHERE s.session_token = ? AND s.is_active = 1",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    # String comparison works for ISO-like format since it sorts lexicographically
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    if row['expires_at'] < now_str:
        _deactivate_session(token)
        return None
    if not row['is_active'] or not row['approved']:
        return None
    return {
        'username': row['username'],
        'display_name': row['display_name'],
        'role': row['role'],
        'approved': bool(row['approved']),
    }


def require_auth(f):
    """Decorator: require a valid session. Injects `current_user` kwarg."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
        kwargs['current_user'] = user
        return f(*args, **kwargs)
    return wrapper


def require_owner(f):
    """Decorator: require owner role."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user['role'] != 'owner':
            return jsonify({'ok': False, 'error': 'Owner access required'}), 403
        kwargs['current_user'] = user
        return f(*args, **kwargs)
    return wrapper
