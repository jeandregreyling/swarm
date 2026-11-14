"""Owner 13 Nov: sign in to HB with a linked GitHub, Google or Microsoft account ("bind the local login to the user account").

Security rules: only identities the owner linked while signed in can sign in (matched on the provider's permanent account id, never
on an e-mail alone); every flow carries a one-time state (10 minutes) and PKCE where the provider supports it; provider app keys live in
an owner-only file outside the repository and the database (~/.local/share/hummingbird/oauth/providers.json, mode 600), never in chat,
the KC or a task.
"""
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

STORE = Path(os.path.expanduser('~/.local/share/hummingbird/oauth'))
STATE_TTL = 600
PROVIDERS = {
    'github': {'label': 'GitHub', 'authorize': 'https://github.com/login/oauth/authorize',
               'token': 'https://github.com/login/oauth/access_token', 'identity': 'https://api.github.com/user',
               'scope': 'read:user', 'pkce': False,
               'register': 'https://github.com/settings/applications/new'},
    'google': {'label': 'Google', 'authorize': 'https://accounts.google.com/o/oauth2/v2/auth',
               'token': 'https://oauth2.googleapis.com/token', 'identity': 'https://openidconnect.googleapis.com/v1/userinfo',
               'scope': 'openid email profile', 'pkce': True,
               'register': 'https://console.cloud.google.com/apis/credentials'},
    'microsoft': {'label': 'Microsoft', 'authorize': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
                  'token': 'https://login.microsoftonline.com/common/oauth2/v2.0/token', 'identity': 'https://graph.microsoft.com/v1.0/me',
                  'scope': 'openid email profile User.Read', 'pkce': True,
                  'register': 'https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade'},
}


def _keys_file():
    return STORE / 'providers.json'


def keys():
    try:
        return json.loads(_keys_file().read_text())
    except (OSError, ValueError):
        return {}


def save_keys(provider, client_id, client_secret):
    if provider not in PROVIDERS:
        raise ValueError('Unknown provider')
    client_id, client_secret = str(client_id or '').strip(), str(client_secret or '').strip()
    if not client_id or not client_secret or len(client_id) > 300 or len(client_secret) > 500:
        raise ValueError('Client ID and client secret are both required')
    STORE.mkdir(parents=True, exist_ok=True)
    os.chmod(STORE, 0o700)
    data = keys()
    data[provider] = {'client_id': client_id, 'client_secret': client_secret, 'saved_at': time.time()}
    tmp = _keys_file().with_suffix('.tmp')
    tmp.write_text(json.dumps(data))
    os.chmod(tmp, 0o600)
    os.replace(tmp, _keys_file())
    return {'provider': provider, 'configured': True}


def remove_keys(provider):
    data = keys()
    data.pop(provider, None)
    STORE.mkdir(parents=True, exist_ok=True)
    tmp = _keys_file().with_suffix('.tmp')
    tmp.write_text(json.dumps(data)); os.chmod(tmp, 0o600); os.replace(tmp, _keys_file())


def configured(provider):
    entry = keys().get(provider) or {}
    return bool(entry.get('client_id') and entry.get('client_secret'))


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_login_links(provider TEXT NOT NULL, subject TEXT NOT NULL, username TEXT NOT NULL, '
                 'label TEXT, linked_at REAL, PRIMARY KEY(provider, subject))')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_oauth_states(state TEXT PRIMARY KEY, provider TEXT NOT NULL, mode TEXT NOT NULL, '
                 'username TEXT, verifier TEXT, created REAL NOT NULL)')


def redirect_uri(base, provider):
    return base.rstrip('/') + f'/auth/oauth/{provider}/callback'


def start(conn, provider, mode, base, username=None):
    """Return the provider URL to send the browser to. mode: 'login' or 'link' (link needs the signed-in owner)."""
    if provider not in PROVIDERS:
        raise ValueError('Unknown provider')
    if not configured(provider):
        raise PermissionError(f'{PROVIDERS[provider]["label"]} sign-in is not set up yet (no app keys saved)')
    if mode not in ('login', 'link') or (mode == 'link' and not username):
        raise PermissionError('Linking needs the signed-in owner')
    ensure_schema(conn)
    conn.execute('DELETE FROM hb_oauth_states WHERE created < ?', (time.time() - STATE_TTL,))
    spec, entry = PROVIDERS[provider], keys()[provider]
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48) if spec['pkce'] else None
    conn.execute('INSERT INTO hb_oauth_states VALUES(?,?,?,?,?,?)', (state, provider, mode, username, verifier, time.time()))
    params = {'client_id': entry['client_id'], 'redirect_uri': redirect_uri(base, provider), 'scope': spec['scope'], 'state': state,
              'response_type': 'code'}
    if verifier:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        params.update(code_challenge=challenge, code_challenge_method='S256')
    if provider == 'google':
        params['prompt'] = 'select_account'
    from urllib.parse import urlencode
    return spec['authorize'] + '?' + urlencode(params)


def _identity(provider, profile):
    if provider == 'github':
        return str(profile['id']), profile.get('login') or ''
    if provider == 'google':
        return str(profile['sub']), profile.get('email') or ''
    return str(profile['id']), profile.get('userPrincipalName') or profile.get('mail') or ''


def finish(conn, provider, state, code, base, http=None):
    """Complete a provider callback. Returns {'mode': 'login', 'username': ...} or {'mode': 'link', ...}."""
    import requests
    http = http or requests
    ensure_schema(conn)
    row = conn.execute('SELECT provider, mode, username, verifier, created FROM hb_oauth_states WHERE state=?', (state or '',)).fetchone()
    conn.execute('DELETE FROM hb_oauth_states WHERE state=?', (state or '',))           # one-time
    if not row or row[0] != provider or time.time() - row[4] > STATE_TTL:
        raise PermissionError('This sign-in link expired or was already used; start again')
    if not code:
        raise PermissionError('The provider did not return a sign-in code')
    spec, entry = PROVIDERS[provider], keys()[provider]
    form = {'client_id': entry['client_id'], 'client_secret': entry['client_secret'], 'code': code,
            'redirect_uri': redirect_uri(base, provider), 'grant_type': 'authorization_code'}
    if row[3]:
        form['code_verifier'] = row[3]
    token = http.post(spec['token'], data=form, headers={'Accept': 'application/json'}, timeout=20).json()
    access = token.get('access_token')
    if not access:
        raise PermissionError('The provider refused the sign-in (' + str(token.get('error') or 'no token') + ')')
    profile = http.get(spec['identity'], headers={'Authorization': f'Bearer {access}', 'Accept': 'application/json'}, timeout=20).json()
    subject, label = _identity(provider, profile)
    if row[1] == 'link':
        conn.execute('INSERT OR REPLACE INTO hb_login_links VALUES(?,?,?,?,?)', (provider, subject, row[2], label, time.time()))
        return {'mode': 'link', 'username': row[2], 'provider': provider, 'label': label}
    linked = conn.execute('SELECT username FROM hb_login_links WHERE provider=? AND subject=?', (provider, subject)).fetchone()
    if not linked:
        raise PermissionError(f'This {spec["label"]} account is not linked to an HB account. Sign in once with your password and link it.')
    return {'mode': 'login', 'username': linked[0], 'provider': provider, 'label': label}


def links(conn, username):
    ensure_schema(conn)
    return [{'provider': p, 'label': l, 'linked_at': t} for p, l, t in
            conn.execute('SELECT provider, label, linked_at FROM hb_login_links WHERE username=? ORDER BY provider', (username,))]


def unlink(conn, username, provider):
    ensure_schema(conn)
    return conn.execute('DELETE FROM hb_login_links WHERE username=? AND provider=?', (username, provider)).rowcount
