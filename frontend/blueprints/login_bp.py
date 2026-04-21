"""login_bp.py — User login, registration, session management, and approval.

The owner (ghost) is auto-approved and has 'owner' role.
New users register but must be approved by the owner before they can log in.
Sessions are cookie-based with a secure random token.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, make_response

from database import get_connection
from services import get_current_user, require_auth, require_owner

login_bp = Blueprint('login', __name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash_password(password, salt=None):
    """PBKDF2-SHA256 hash with per-user salt. Returns 'salt:hash'."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations=260000).hex()
    return f'{salt}:{h}'


def _verify_password(password, stored_hash):
    """Verify password against 'salt:hash' format."""
    if ':' not in stored_hash:
        return False
    salt, _ = stored_hash.split(':', 1)
    return _hash_password(password, salt) == stored_hash


def _resolve_login_profile(identifier, password):
    """Find the matching account for a login identifier and password.

    Supports login by username, email, or display name. If multiple rows match,
    return the one whose password verifies, preferring exact username/email hits.
    """
    key = (identifier or '').strip().lower()
    if not key or not password:
        return None

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT username, display_name, password_hash, role, approved, is_active, email "
            "FROM user_profiles "
            "WHERE lower(username) = ? OR lower(coalesce(email, '')) = ? OR lower(coalesce(display_name, '')) = ?",
            (key, key, key),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    def _priority(row):
        row_username = str(row['username'] or '').strip().lower()
        row_email = str(row['email'] or '').strip().lower()
        if row_username == key:
          return 0
        if row_email == key:
          return 1
        return 2

    for row in sorted(rows, key=_priority):
        if row['password_hash'] and _verify_password(password, row['password_hash']):
            return row
    return None


def _create_session(username, days=30):
    """Create a session token and store in DB. Returns the token."""
    token = secrets.token_urlsafe(48)
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    ip = request.remote_addr or ''
    ua = (request.headers.get('User-Agent') or '')[:200]
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_sessions (username, session_token, ip_address, user_agent, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, token, ip, ua, expires),
        )
        conn.commit()
    finally:
        conn.close()
    return token, expires






# ── Ensure owner account exists ──────────────────────────────────────────────

def _ensure_owner():
    """Make sure ghost has owner role and is approved. Idempotent."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE user_profiles SET role = 'owner', approved = 1 "
            "WHERE username = 'ghost'",
        )
        conn.commit()
    finally:
        conn.close()


# ── Routes ───────────────────────────────────────────────────────────────────

@login_bp.route('/api/auth/me')
def auth_me():
    """Return the currently logged-in user, or null."""
    user = get_current_user()
    return jsonify({'ok': True, 'user': user})


@login_bp.route('/api/auth/setup-status')
def auth_setup_status():
    """Check if the owner account has a password set (first-time setup)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT password_hash FROM user_profiles WHERE username = 'ghost'"
    ).fetchone()
    conn.close()
    has_password = bool(row and row['password_hash'])
    return jsonify({'ok': True, 'owner_has_password': has_password, 'owner_username': 'ghost'})


@login_bp.route('/api/auth/setup', methods=['POST'])
def auth_setup():
    """First-time owner password setup. Only works if ghost has no password yet."""
    data = request.get_json() or {}
    password = (data.get('password') or '').strip()
    display_name = (data.get('display_name') or '').strip()
    if not password or len(password) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters'}), 400

    conn = get_connection()
    row = conn.execute(
        "SELECT password_hash FROM user_profiles WHERE username = 'ghost'"
    ).fetchone()
    if row and row['password_hash']:
        conn.close()
        return jsonify({'ok': False, 'error': 'Owner password already set. Use login instead.'}), 409

    hashed = _hash_password(password)
    updates = "password_hash = ?, role = 'owner', approved = 1"
    params = [hashed]
    if display_name:
        updates += ", display_name = ?"
        params.append(display_name)
    params.append('ghost')
    conn.execute(f"UPDATE user_profiles SET {updates} WHERE username = ?", params)
    conn.commit()
    conn.close()

    # Auto-login
    token, expires = _create_session('ghost')
    resp = make_response(jsonify({'ok': True, 'user': {
        'username': 'ghost',
        'display_name': display_name or 'Ghost',
        'role': 'owner',
    }}))
    resp.set_cookie('friday_session', token, httponly=True, samesite='Lax', max_age=30*86400)
    return resp


@login_bp.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Authenticate with username + password."""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip().lower()
    password = (data.get('password') or '').strip()
    remember = bool(data.get('remember'))
    if not username or not password:
        return jsonify({'ok': False, 'error': 'Username and password required'}), 400

    row = _resolve_login_profile(username, password)
    if not row:
        return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401
    if not row['is_active']:
        return jsonify({'ok': False, 'error': 'Account is disabled'}), 403
    if not row['approved']:
        return jsonify({'ok': False, 'error': 'Account pending approval by the owner'}), 403

    token, expires = _create_session(row['username'], days=30 if remember else 1)
    resp = make_response(jsonify({'ok': True, 'user': {
        'username': row['username'],
        'display_name': row['display_name'],
        'role': row['role'],
    }}))
    cookie_kwargs = {'httponly': True, 'samesite': 'Lax'}
    if remember:
        cookie_kwargs['max_age'] = 30 * 86400
    resp.set_cookie('friday_session', token, **cookie_kwargs)
    return resp


@login_bp.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Invalidate the current session."""
    token = request.cookies.get('friday_session')
    if token:
        conn = get_connection()
        conn.execute(
            "UPDATE user_sessions SET is_active = 0 WHERE session_token = ?",
            (token,),
        )
        conn.commit()
        conn.close()
    resp = make_response(jsonify({'ok': True}))
    resp.set_cookie('friday_session', '', expires=0)
    return resp


@login_bp.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Register a new user. Account starts as unapproved — owner must approve."""
    data = request.get_json() or {}
    username = (data.get('username') or '').strip().lower()
    password = (data.get('password') or '').strip()
    display_name = (data.get('display_name') or username).strip()

    if not username or not password:
        return jsonify({'ok': False, 'error': 'Username and password required'}), 400
    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters'}), 400
    if len(username) < 2 or len(username) > 30:
        return jsonify({'ok': False, 'error': 'Username must be 2-30 characters'}), 400
    # Only allow alphanumeric + underscore
    import re
    if not re.match(r'^[a-z0-9_]+$', username):
        return jsonify({'ok': False, 'error': 'Username: lowercase letters, numbers, underscores only'}), 400

    hashed = _hash_password(password)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_profiles (username, display_name, user_type, password_hash, role, approved, created_by) "
            "VALUES (?, ?, 'human', ?, 'viewer', 0, 'self')",
            (username, display_name, hashed),
        )
        conn.commit()
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e).upper():
            return jsonify({'ok': False, 'error': 'Username already taken'}), 409
        return jsonify({'ok': False, 'error': 'Registration failed'}), 500
    conn.close()

    return jsonify({
        'ok': True,
        'message': 'Account created. Waiting for owner approval before you can log in.',
        'username': username,
    }), 201


# ── Owner: User Management ──────────────────────────────────────────────────

@login_bp.route('/api/auth/users')
@require_owner
def auth_list_users(current_user=None):
    """List all user profiles (owner only)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT username, display_name, email, user_type, role, approved, is_active, created_at, created_by "
        "FROM user_profiles WHERE user_type = 'human' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    users = [dict(r) for r in rows]
    return jsonify({'ok': True, 'users': users})


@login_bp.route('/api/auth/users/<username>/approve', methods=['POST'])
@require_owner
def auth_approve_user(username, current_user=None):
    """Approve a pending user (owner only)."""
    conn = get_connection()
    row = conn.execute("SELECT username FROM user_profiles WHERE username = ?", (username,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    conn.execute(
        "UPDATE user_profiles SET approved = 1, role = 'user', updated_at = datetime('now') "
        "WHERE username = ?",
        (username,),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'approved': username})


@login_bp.route('/api/auth/users/<username>/reject', methods=['POST'])
@require_owner
def auth_reject_user(username, current_user=None):
    """Reject/disable a user (owner only)."""
    if username == 'ghost':
        return jsonify({'ok': False, 'error': 'Cannot disable owner'}), 403
    conn = get_connection()
    conn.execute(
        "UPDATE user_profiles SET approved = 0, is_active = 0, updated_at = datetime('now') "
        "WHERE username = ?",
        (username,),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'rejected': username})


@login_bp.route('/api/auth/users/<username>/role', methods=['POST'])
@require_owner
def auth_set_role(username, current_user=None):
    """Change a user's role (owner only). Valid roles: viewer, user, admin, owner."""
    data = request.get_json() or {}
    role = (data.get('role') or '').strip().lower()
    if role not in ('viewer', 'user', 'admin', 'owner'):
        return jsonify({'ok': False, 'error': 'Invalid role'}), 400
    conn = get_connection()
    conn.execute(
        "UPDATE user_profiles SET role = ?, updated_at = datetime('now') WHERE username = ?",
        (role, username),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'username': username, 'role': role})


@login_bp.route('/api/auth/users/<username>/edit', methods=['POST'])
@require_owner
def auth_edit_user(username, current_user=None):
    """Edit a user's display_name and/or email (owner only)."""
    data = request.get_json() or {}
    display_name = data.get('display_name')
    email = data.get('email')
    if display_name is None and email is None:
        return jsonify({'ok': False, 'error': 'Nothing to update'}), 400

    sets, params = [], []
    if display_name is not None:
        sets.append('display_name = ?')
        params.append(display_name.strip())
    if email is not None:
        sets.append('email = ?')
        params.append(email.strip().lower())
    sets.append("updated_at = datetime('now')")
    params.append(username)

    conn = get_connection()
    conn.execute(f"UPDATE user_profiles SET {', '.join(sets)} WHERE username = ?", params)
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'username': username})


@login_bp.route('/api/auth/users/<username>/reset-password', methods=['POST'])
@require_owner
def auth_reset_password(username, current_user=None):
    """Reset a user's password (owner only). Owner provides new password."""
    data = request.get_json() or {}
    password = (data.get('password') or '').strip()
    if not password or len(password) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters'}), 400
    conn = get_connection()
    row = conn.execute("SELECT username FROM user_profiles WHERE username = ?", (username,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    hashed = _hash_password(password)
    conn.execute(
        "UPDATE user_profiles SET password_hash = ?, updated_at = datetime('now') WHERE username = ?",
        (hashed, username),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'username': username})


@login_bp.route('/api/auth/users/<username>/delete', methods=['DELETE'])
@require_owner
def auth_delete_user(username, current_user=None):
    """Delete a human user account (owner only). Cannot delete owner."""
    if username == 'ghost':
        return jsonify({'ok': False, 'error': 'Cannot delete owner account'}), 403
    conn = get_connection()
    row = conn.execute(
        "SELECT username, user_type FROM user_profiles WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'User not found'}), 404
    if row['user_type'] != 'human':
        conn.close()
        return jsonify({'ok': False, 'error': 'Cannot delete agent accounts'}), 403
    conn.execute("DELETE FROM user_sessions WHERE username = ?", (username,))
    conn.execute("DELETE FROM user_profiles WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'deleted': username})


@login_bp.route('/api/auth/users/create', methods=['POST'])
@require_owner
def auth_create_user(current_user=None):
    """Owner creates a new user. Email as identifier, preferred name as display_name."""
    import re
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    display_name = (data.get('display_name') or '').strip()
    password = (data.get('password') or '').strip()
    role = (data.get('role') or 'viewer').strip().lower()

    if not email:
        return jsonify({'ok': False, 'error': 'Email is required'}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'ok': False, 'error': 'Invalid email address'}), 400
    if not password or len(password) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters'}), 400
    if role not in ('viewer', 'user', 'admin'):
        return jsonify({'ok': False, 'error': 'Invalid role'}), 400

    # Derive username from email prefix
    username = re.sub(r'[^a-z0-9_]', '_', email.split('@')[0].lower())[:30]
    if not display_name:
        display_name = email.split('@')[0].title()

    hashed = _hash_password(password)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO user_profiles (username, display_name, email, user_type, password_hash, role, approved, created_by) "
            "VALUES (?, ?, ?, 'human', ?, ?, 1, ?)",
            (username, display_name, email, hashed, role, current_user['username']),
        )
        conn.commit()
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e).upper():
            return jsonify({'ok': False, 'error': 'A user with that email/username already exists'}), 409
        return jsonify({'ok': False, 'error': f'Failed to create user: {e}'}), 500
    conn.close()
    return jsonify({'ok': True, 'username': username, 'email': email, 'display_name': display_name}), 201
