"""Owner 13 Nov: sign in with a linked GitHub / Google / Microsoft account. Only linked identities sign in; one-time state; PKCE;
app keys in an owner-only file."""
import os
import sqlite3
import stat
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from core import hb_oauth


class FakeHTTP:
    def __init__(self, subject='4242', login='jd-gh'):
        self.subject, self.login, self.posted = subject, login, []

    class R:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def post(self, url, data=None, headers=None, timeout=None):
        self.posted.append(data)
        return self.R({'access_token': 'tok'} if data.get('code') == 'good' else {'error': 'bad_verification_code'})

    def get(self, url, headers=None, timeout=None):
        return self.R({'id': int(self.subject), 'login': self.login, 'sub': self.subject, 'email': 'x@example.com'})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(hb_oauth, 'STORE', tmp_path / 'oauth')
    conn = sqlite3.connect(':memory:')
    hb_oauth.save_keys('github', 'cid', 'secret')
    hb_oauth.save_keys('google', 'gid', 'gsecret')
    return conn


def _state(url):
    return parse_qs(urlsplit(url).query)['state'][0]


def test_keys_are_owner_only_and_never_returned(setup):
    path = hb_oauth.STORE / 'providers.json'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and hb_oauth.configured('github') and not hb_oauth.configured('microsoft')


def test_link_then_login_with_the_same_account(setup):
    conn, base = setup, 'http://localhost:5050/'
    url = hb_oauth.start(conn, 'github', 'link', base, username='ghost')
    assert 'redirect_uri=http%3A%2F%2Flocalhost%3A5050%2Fauth%2Foauth%2Fgithub%2Fcallback' in url
    assert hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP())['mode'] == 'link'
    url = hb_oauth.start(conn, 'github', 'login', base)
    assert hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP()) == \
        {'mode': 'login', 'username': 'ghost', 'provider': 'github', 'label': 'jd-gh'}


def test_an_unlinked_account_never_signs_in(setup):
    conn, base = setup, 'http://localhost:5050/'
    url = hb_oauth.start(conn, 'github', 'login', base)
    with pytest.raises(PermissionError, match='not linked'):
        hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP(subject='999'))


def test_state_is_one_time_and_expires(setup):
    conn, base = setup, 'http://localhost:5050/'
    url = hb_oauth.start(conn, 'github', 'link', base, username='ghost')
    hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP())
    with pytest.raises(PermissionError, match='expired or was already used'):
        hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP())
    url = hb_oauth.start(conn, 'github', 'login', base)
    conn.execute('UPDATE hb_oauth_states SET created=?', (time.time() - 3600,))
    with pytest.raises(PermissionError, match='expired'):
        hb_oauth.finish(conn, 'github', _state(url), 'good', base, http=FakeHTTP())


def test_pkce_for_google_and_refused_codes(setup):
    conn, base = setup, 'http://localhost:5050/'
    url = hb_oauth.start(conn, 'google', 'link', base, username='ghost')
    query = parse_qs(urlsplit(url).query)
    assert query['code_challenge_method'] == ['S256'] and query['code_challenge'][0]
    http = FakeHTTP()
    with pytest.raises(PermissionError, match='refused'):
        hb_oauth.finish(conn, 'google', _state(url), 'bad', base, http=http)
    assert http.posted[0]['code_verifier']


def test_linking_needs_the_owner_and_setup(setup):
    conn = setup
    with pytest.raises(PermissionError):
        hb_oauth.start(conn, 'github', 'link', 'http://localhost:5050/')
    with pytest.raises(PermissionError, match='not set up'):
        hb_oauth.start(conn, 'microsoft', 'login', 'http://localhost:5050/')
