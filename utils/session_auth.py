"""
utils/session_auth.py — Session-based UI authentication (R.1)
═══════════════════════════════════════════════════════════════════════════════
Provides login/logout routes and a @login_required decorator.
Set SWARM_UI_PASSWORD to enable (disabled when unset).
"""

import os
import hashlib
import hmac
import secrets
from functools import wraps

from flask import (
    Blueprint, request, redirect, url_for, session,
    render_template_string, jsonify,
)

session_auth_bp = Blueprint('session_auth', __name__)

# When SWARM_UI_PASSWORD is set, all UI + API routes (except health/login) require auth.
_UI_PASSWORD = os.environ.get('SWARM_UI_PASSWORD', '')
_EXCLUDED_PREFIXES = ('/_health', '/api/node/', '/login', '/logout', '/static/')
_EXCLUDED_EXACT = ('/', '/_health')


def _hash_password(pw):
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()


def is_auth_enabled():
    """Return True if UI password protection is active."""
    return bool(_UI_PASSWORD)


def login_required(f):
    """Decorator: require valid session when auth is enabled."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not is_auth_enabled():
            return f(*args, **kwargs)
        if session.get('authenticated'):
            return f(*args, **kwargs)
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('session_auth.login_page'))
    return wrapped


def init_session_auth(app):
    """Wire session auth into a Flask app. Call once in create_app()."""
    # Persist secret key so sessions survive restarts
    _key_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.secret_key')
    secret = os.environ.get('SWARM_SECRET_KEY', '')
    if not secret:
        try:
            with open(_key_file, 'r') as f:
                secret = f.read().strip()
        except FileNotFoundError:
            secret = secrets.token_hex(32)
            with open(_key_file, 'w') as f:
                f.write(secret)
            os.chmod(_key_file, 0o600)
    app.secret_key = secret

    app.register_blueprint(session_auth_bp)

    if not is_auth_enabled():
        return  # No password set — skip auth middleware

    @app.before_request
    def _check_auth():
        path = request.path
        # Allow excluded paths
        if path in _EXCLUDED_EXACT:
            return None
        for prefix in _EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return None
        # Check session
        if session.get('authenticated'):
            return None
        # API routes get 401
        if request.is_json or path.startswith('/api/'):
            from flask import abort
            abort(401)
        # UI routes redirect to login
        return redirect(url_for('session_auth.login_page'))


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login — Seven's Swarm</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #eef3fb; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; }
  .card { background: #fff; padding: 2.5rem; border-radius: 12px;
          box-shadow: 0 14px 42px rgba(20,52,96,.12); max-width: 380px; width: 100%; }
  h1 { font-size: 1.4rem; margin-bottom: 1.5rem; color: #13243b; text-align: center; }
  label { display: block; font-size: .85rem; color: #617590; margin-bottom: .4rem; }
  input[type=password] { width: 100%; padding: .65rem .8rem; border: 1px solid #d6e0ef;
          border-radius: 6px; font-size: 1rem; margin-bottom: 1.2rem; }
  button { width: 100%; padding: .7rem; background: #2f6bff; color: #fff; border: none;
           border-radius: 6px; font-size: 1rem; cursor: pointer; }
  button:hover { background: #5486ff; }
  .err { color: #e03c3c; font-size: .85rem; margin-bottom: 1rem; text-align: center; }
</style>
</head>
<body>
<div class="card">
  <h1>Seven's Swarm</h1>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <form method="POST">
    <label for="pw">Password</label>
    <input type="password" id="pw" name="password" autofocus required>
    <button type="submit">Sign In</button>
  </form>
</div>
</body>
</html>"""


@session_auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if not is_auth_enabled():
        return redirect('/ui')
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if hmac.compare_digest(_hash_password(pw), _hash_password(_UI_PASSWORD)):
            session['authenticated'] = True
            session.permanent = True
            return redirect('/ui')
        return render_template_string(_LOGIN_HTML, error='Invalid password'), 403
    return render_template_string(_LOGIN_HTML, error=None)


@session_auth_bp.route('/logout')
def logout_page():
    session.clear()
    if is_auth_enabled():
        return redirect(url_for('session_auth.login_page'))
    return redirect('/ui')
