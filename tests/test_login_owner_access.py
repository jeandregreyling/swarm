import sqlite3
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if 'database' not in sys.modules:
    db_stub = types.ModuleType('database')
    db_stub.get_connection = lambda: None
    sys.modules['database'] = db_stub

if 'services' not in sys.modules:
    services_stub = types.ModuleType('services')
    services_stub.get_current_user = lambda: None
    services_stub.require_auth = lambda fn: fn
    services_stub.require_owner = lambda fn: fn
    sys.modules['services'] = services_stub

_SPEC = importlib.util.spec_from_file_location(
    'swarm_login_bp_test',
    ROOT / 'frontend' / 'blueprints' / 'login_bp.py',
)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

_AUTH_SPEC = importlib.util.spec_from_file_location(
    'swarm_auth_service_test',
    ROOT / 'frontend' / 'services' / 'auth.py',
)
assert _AUTH_SPEC and _AUTH_SPEC.loader
_AUTH_MOD = importlib.util.module_from_spec(_AUTH_SPEC)
_AUTH_SPEC.loader.exec_module(_AUTH_MOD)

login_bp = _MOD.login_bp
_hash_password = _MOD._hash_password


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_expiry(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)


def _seed_db(db_path):
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE user_profiles (
                username TEXT PRIMARY KEY,
                display_name TEXT,
                password_hash TEXT,
                role TEXT,
                approved INTEGER,
                is_active INTEGER,
                email TEXT,
                user_type TEXT DEFAULT 'human',
                updated_at TEXT,
                created_by TEXT
            );

            CREATE TABLE user_sessions (
                username TEXT,
                session_token TEXT,
                ip_address TEXT,
                user_agent TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1
            );
            """
        )
        conn.execute(
            "INSERT INTO user_profiles (username, display_name, password_hash, role, approved, is_active, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('ghost', 'Jeandre', _hash_password('------'), 'viewer', 0, 0, 'sevenpotato9@gmail.com'),
        )
        conn.commit()
    finally:
        conn.close()


def test_owner_login_normalizes_email_and_accepts_email_or_display_name(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()

    for identifier in ('jeandre.greyling@gmail.com', 'Jeandre'):
        resp = client.post('/api/auth/login', json={'username': identifier, 'password': '------'})
        assert resp.status_code == 200, identifier
        body = resp.get_json()
        assert body['ok'] is True
        assert body['user']['username'] == 'ghost'

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT email, role, approved, is_active FROM user_profiles WHERE username = 'ghost'"
        ).fetchone()
    finally:
        conn.close()

    assert row['email'] == 'jeandre.greyling@gmail.com'
    assert row['role'] == 'owner'
    assert row['approved'] == 1
    assert row['is_active'] == 1


def test_owner_setup_normalizes_owner_identity_without_setup_status_probe(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE user_profiles SET password_hash = NULL, role = 'viewer', approved = 0, is_active = 0, email = ? WHERE username = 'ghost'",
            ('sevenpotato9@gmail.com',),
        )
        conn.commit()
    finally:
        conn.close()

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()

    resp = client.post('/api/auth/setup', json={'password': '------', 'display_name': 'Jeandre'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['ok'] is True
    assert body['user']['username'] == 'ghost'

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT password_hash, email, role, approved, is_active FROM user_profiles WHERE username = 'ghost'"
        ).fetchone()
    finally:
        conn.close()

    assert row['password_hash']
    assert row['email'] == 'jeandre.greyling@gmail.com'
    assert row['role'] == 'owner'
    assert row['approved'] == 1
    assert row['is_active'] == 1


def test_login_remember_me_controls_cookie_and_session_duration(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()

    now = datetime.now(timezone.utc)

    resp = client.post('/api/auth/login', json={'username': 'jeandre', 'password': '------', 'remember': False})
    assert resp.status_code == 200
    session_cookie = resp.headers.get('Set-Cookie', '')
    assert 'Max-Age=' not in session_cookie

    conn = _connect(db_path)
    try:
        short_session = conn.execute(
            "SELECT expires_at FROM user_sessions ORDER BY rowid ASC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    short_expiry = _parse_expiry(short_session['expires_at'])
    short_delta = (short_expiry - now).total_seconds()
    assert 23 * 3600 <= short_delta <= 25 * 3600

    resp = client.post('/api/auth/login', json={'username': 'jeandre', 'password': '------', 'remember': True})
    assert resp.status_code == 200
    persistent_cookie = resp.headers.get('Set-Cookie', '')
    assert 'Max-Age=2592000' in persistent_cookie

    conn = _connect(db_path)
    try:
        long_session = conn.execute(
            "SELECT expires_at FROM user_sessions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    long_expiry = _parse_expiry(long_session['expires_at'])
    long_delta = (long_expiry - now).total_seconds()
    assert 29 * 24 * 3600 <= long_delta <= 31 * 24 * 3600


def test_owner_setup_uses_non_persistent_session_defaults(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE user_profiles SET password_hash = NULL WHERE username = 'ghost'"
        )
        conn.commit()
    finally:
        conn.close()

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()

    now = datetime.now(timezone.utc)

    resp = client.post('/api/auth/setup', json={'password': '------', 'display_name': 'Jeandre'})
    assert resp.status_code == 200
    session_cookie = resp.headers.get('Set-Cookie', '')
    assert 'Max-Age=' not in session_cookie

    conn = _connect(db_path)
    try:
        session_row = conn.execute(
            "SELECT expires_at FROM user_sessions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    expiry = _parse_expiry(session_row['expires_at'])
    delta = (expiry - now).total_seconds()
    assert 23 * 3600 <= delta <= 25 * 3600


def test_owner_edit_rejects_duplicate_email_assignment(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    conn = _connect(db_path)
    try:
        # Promote ghost to a real owner so the owner-only edit route is callable.
        conn.execute(
            "UPDATE user_profiles SET role='owner', approved=1, is_active=1, email=? "
            "WHERE username='ghost'",
            ('jeandre.greyling@gmail.com',),
        )
        conn.execute(
            "INSERT INTO user_profiles (username, display_name, password_hash, role, approved, is_active, email, user_type, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'human', 'self')",
            ('helper', 'Helper', _hash_password('helperpw'), 'viewer', 1, 1, 'helper@example.com'),
        )
        # Active session cookie for ghost so @require_owner passes.
        conn.execute(
            "INSERT INTO user_sessions (username, session_token, ip_address, user_agent, expires_at, is_active) "
            "VALUES ('ghost', 'owner-token', '', '', datetime('now', '+1 day'), 1)",
        )
        conn.commit()
    finally:
        conn.close()

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)
    # `require_owner` / `get_current_user` live in services — redirect their
    # connection helper at the same seeded DB so the session lookup works.
    import services as _services_mod
    if hasattr(_services_mod, 'get_connection'):
        monkeypatch.setattr(_services_mod, 'get_connection', fake_get_connection)
    # The real session lookup lives in frontend.services.auth which imports
    # get_connection from the `database` module at import time. Patch both
    # so this test is order-independent in the full suite.
    try:
        import database as _db_mod
        if hasattr(_db_mod, 'get_connection'):
            monkeypatch.setattr(_db_mod, 'get_connection', fake_get_connection)
    except Exception:
        pass
    # Short-circuit the auth lookup itself: when another test in the session
    # has left stale module-level state in frontend.services.auth, patching
    # its get_connection isn't enough. Replace get_current_user on every
    # module that re-exported it so require_owner sees a valid owner.
    _fake_user = {
        'username': 'ghost', 'display_name': 'Ghost',
        'role': 'owner', 'approved': True,
    }
    try:
        from frontend.services import auth as _auth_mod
        monkeypatch.setattr(_auth_mod, 'get_connection', fake_get_connection)
        monkeypatch.setattr(_auth_mod, 'get_current_user', lambda: _fake_user)
    except Exception:
        pass
    # If `frontend/` is on sys.path, the same auth.py can also be loaded
    # under the sibling name `services.auth`. Patch that module too.
    import sys as _sys
    for _modname in ('services.auth', 'services'):
        _m = _sys.modules.get(_modname)
        if _m is not None:
            if hasattr(_m, 'get_current_user'):
                monkeypatch.setattr(_m, 'get_current_user', lambda: _fake_user)
            if hasattr(_m, 'get_connection'):
                monkeypatch.setattr(_m, 'get_connection', fake_get_connection)
    if hasattr(_services_mod, 'get_current_user'):
        monkeypatch.setattr(_services_mod, 'get_current_user', lambda: _fake_user)
    # login_bp captured get_current_user / require_owner at import time via
    # `from services import ...`, so the decorator bound to login_bp routes
    # already closed over the original get_current_user. Patch the name on
    # login_bp's module too — require_owner re-looks-up nothing, but its
    # inner wrapper calls get_current_user from auth.py, which we patched
    # above. The final safety net: patch login_bp's own re-bind.
    from frontend.blueprints import login_bp as _login_mod
    if hasattr(_login_mod, 'get_current_user'):
        monkeypatch.setattr(_login_mod, 'get_current_user', lambda: _fake_user)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()
    client.set_cookie('friday_session', 'owner-token')

    resp = client.post(
        '/api/auth/users/helper/edit',
        json={'email': 'jeandre.greyling@gmail.com'},
    )
    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body['ok'] is False

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT email FROM user_profiles WHERE username = 'helper'"
        ).fetchone()
    finally:
        conn.close()

    assert row['email'] == 'helper@example.com'


def test_expired_session_is_deactivated_when_checked(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE user_profiles SET role = 'owner', approved = 1, is_active = 1, email = ? WHERE username = 'ghost'",
            ('jeandre.greyling@gmail.com',),
        )
        conn.execute(
            "INSERT INTO user_sessions (username, session_token, ip_address, user_agent, expires_at, is_active) VALUES (?, ?, '', '', ?, 1)",
            ('ghost', 'expired-token', '2000-01-01 00:00:00'),
        )
        conn.commit()
    finally:
        conn.close()

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_AUTH_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    with app.test_request_context(headers={'Cookie': 'friday_session=expired-token'}):
        user = _AUTH_MOD.get_current_user()

    assert user is None

    conn = _connect(db_path)
    try:
        session_row = conn.execute(
            "SELECT is_active FROM user_sessions WHERE session_token = 'expired-token'"
        ).fetchone()
    finally:
        conn.close()

    assert session_row['is_active'] == 0


def test_logout_deactivates_session_and_expires_cookie(tmp_path, monkeypatch):
    db_path = tmp_path / 'auth.db'
    _seed_db(db_path)

    def fake_get_connection():
        return _connect(db_path)

    monkeypatch.setattr(_MOD, 'get_connection', fake_get_connection)

    app = Flask(__name__)
    app.register_blueprint(login_bp)
    client = app.test_client()

    login_resp = client.post('/api/auth/login', json={'username': 'jeandre', 'password': '------', 'remember': True})
    assert login_resp.status_code == 200

    conn = _connect(db_path)
    try:
        session_row = conn.execute(
            "SELECT session_token, is_active FROM user_sessions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert session_row['is_active'] == 1

    logout_resp = client.post('/api/auth/logout', headers={'Cookie': f"friday_session={session_row['session_token']}"})
    assert logout_resp.status_code == 200
    assert 'friday_session=' in logout_resp.headers.get('Set-Cookie', '')

    conn = _connect(db_path)
    try:
        session_row = conn.execute(
            "SELECT is_active FROM user_sessions WHERE session_token = ?",
            (session_row['session_token'],),
        ).fetchone()
    finally:
        conn.close()

    assert session_row['is_active'] == 0