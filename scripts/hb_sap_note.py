#!/usr/bin/python3
"""Look up an SAP Note on SAP for Me with JD's own S-user (owner 15 Nov 2026).

    hb_sap_note.py 2382421            the note as plain text (number, title, component, dates, text)
    hb_sap_note.py 2382421 --json     the note as SAP returned it
    hb_sap_note.py --check            sign in only and say whether it worked

The S-user and password come from the system keyring (scripts/hb_secure_creds.py) at the moment of sign-in and are sent only to
SAP's own sign-in pages (hosts ending in .sap.com / .hana.ondemand.com). They are never printed or written anywhere. After a
successful sign-in the session cookies are kept in a private file (mode 600) so HB signs in rarely, not on every lookup.
Runs under the system Python (it needs the keyring); HB calls it as a separate process (core/hb_sap_notes.py)."""
import argparse
import html
import json
import os
import pickle
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import requests

BASE = 'https://me.sap.com'
NOTE = '/backend/raw/sapnotes/Detail?q={n}&t=E&isVTEnabled=false'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'hummingbird' / 'sap'
COOKIES = STATE / 'session.pickle'
TRUSTED = ('.sap.com', '.hana.ondemand.com')
AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'
USER_FIELDS = ('j_username', 'username', 'login', 'email', 'loginname')
PASS_FIELDS = ('j_password', 'password')
OTP_WORDS = ('otp', 'passcode', 'totp', 'twofactor', 'two-factor', 'tfa', 'verification code', 'authenticator')


class SignInError(RuntimeError):
    pass


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms, self.cur = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.cur = {'action': a.get('action') or '', 'method': (a.get('method') or 'get').lower(), 'inputs': {}, 'types': {}}
            self.forms.append(self.cur)
        elif tag == 'input' and self.cur is not None and a.get('name'):
            if (a.get('type') or 'text').lower() in ('checkbox', 'radio') and 'checked' not in a:
                return
            self.cur['inputs'][a['name']] = a.get('value') or ''
            self.cur['types'][a['name']] = (a.get('type') or 'text').lower()

    def handle_endtag(self, tag):
        if tag == 'form':
            self.cur = None


def forms(text):
    parser = _Forms()
    parser.feed(text)
    return parser.forms


def _trusted(url):
    host = urlsplit(url).hostname or ''
    return urlsplit(url).scheme == 'https' and any(host == t[1:] or host.endswith(t) for t in TRUSTED)


def _where(url):
    return (urlsplit(url).hostname or '') + urlsplit(url).path[:60]


def next_step(url, text, user, password):
    """What to do with a sign-in page: ('done', None) | ('get', url) | ('post', url, data) | raises SignInError. Pure: no network."""
    low = text.lower()
    for form in forms(text):
        names = {n.lower(): n for n in form['inputs']}
        target = urljoin(url, html.unescape(form['action'])) if form['action'] else url
        pw = next((names[f] for f in PASS_FIELDS if f in names), None) or next((n for n, t in form['types'].items() if t == 'password'), None)
        un = next((names[f] for f in USER_FIELDS if f in names), None)
        if any(w in n.lower() for n in form['inputs'] for w in ('otp', 'passcode', 'totp')):
            raise SignInError('SAP asks for a second factor (a code from your authenticator). HB cannot sign in by itself while that is on.')
        if pw or un:
            if not _trusted(target):
                raise SignInError(f'the sign-in form posts to {_where(target)}, which is not an SAP host; nothing was sent')
            data = dict(form['inputs'])
            if un and form['types'].get(un) != 'hidden' or un and not data.get(un):
                data[un] = user
            if pw:
                data[pw] = password
            return 'post', target, data, bool(pw)
        if any(k in names for k in ('samlrequest', 'samlresponse', 'code', 'relaystate', 'id_token')):
            if not _trusted(target):
                raise SignInError(f'the sign-in chain leaves SAP ({_where(target)}); stopped')
            return 'post' if form['method'] == 'post' else 'get', target, dict(form['inputs']), False
    meta = re.search(r'<meta name="redirect" content="([^"]+)"', text)
    if meta:
        return 'get', urljoin(url, html.unescape(meta.group(1))), None, False
    script = re.search(r'location(?:\.href)?\s*=\s*"(https://[^"]+)"', text)
    if script and _trusted(script.group(1)):
        return 'get', script.group(1), None, False
    if any(w in low for w in OTP_WORDS):
        raise SignInError('SAP asks for a second factor (a code from your authenticator). HB cannot sign in by itself while that is on.')
    return 'done', None, None, False


def _approuter_cookies(session, path, text):
    """SAP for Me's first page sets three cookies with JavaScript before it redirects; do the same."""
    sig = re.search(r'signature=([^;"]+);', text)
    if sig:
        for key, value in (('fragmentAfterLogin', ''), ('locationAfterLogin', quote(path, safe='')), ('signature', sig.group(1))):
            session.cookies.set(key, value, domain='me.sap.com', path='/')


def fetch(session, path, creds, trace=None, max_steps=14):
    """GET a SAP for Me backend path, signing in on the way when SAP asks. creds: callable -> (user, password). Returns the response."""
    response = session.get(BASE + path, timeout=40)
    sent_password = False
    for _ in range(max_steps):
        if trace is not None:
            trace.append(f'{response.status_code} {_where(response.url)}')
        kind = response.headers.get('content-type', '')
        if 'json' in kind:
            return response
        if urlsplit(response.url).hostname == 'me.sap.com' and 'signature=' in response.text:
            _approuter_cookies(session, path, response.text)
        user, password = ('', '')
        step = next_step(response.url, response.text, '\0user', '\0pass')
        if step[0] == 'done':
            break
        needs_creds = step[2] is not None and any(v in ('\0user', '\0pass') for v in step[2].values())
        if needs_creds:
            if sent_password:
                raise SignInError('SAP showed the sign-in form again after the password: the user ID or password was not accepted. '
                                  'HB stops here so the account is not locked; re-enter it with hb_secure_creds.py.')
            user, password = creds()
            step = next_step(response.url, response.text, user, password)
            sent_password = sent_password or step[3]
        action, target, data = step[0], step[1], step[2]
        response = session.post(target, data=data, timeout=40) if action == 'post' else session.get(target, params=data if data else None, timeout=40)
    if 'json' not in response.headers.get('content-type', ''):
        raise SignInError(f'sign-in did not reach the note service (stopped at {_where(response.url)})')
    return response


def _session():
    session = requests.Session()
    session.headers['User-Agent'] = AGENT
    try:
        if COOKIES.is_file() and COOKIES.stat().st_mode & 0o077 == 0:
            session.cookies.update(pickle.loads(COOKIES.read_bytes()))
    except Exception:
        pass
    return session


def _keep(session):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = COOKIES.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        pickle.dump(session.cookies, handle)
    tmp.replace(COOKIES)


def _creds():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hb_secure_creds
    found = hb_secure_creds.read('sap')
    if not found:
        raise SignInError('no SAP login is saved; open the gold window: scripts/hb_secure_creds.py')
    return found[0], found[1]


def _plain(markup):
    text = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>', '\n', str(markup or ''))
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', text)).strip()


def as_text(data, limit=600000):
    """A note as plain text from SAP's JSON (the layout differs a little between notes, so every lookup is forgiving)."""
    r = data.get('Response') or data
    note = r.get('SAPNote') or r
    head = note.get('Header') or {}
    pick = lambda d, *keys: next((str((d.get(k) or {}).get('value') if isinstance(d.get(k), dict) else d.get(k)) for k in keys if d.get(k)), '')
    lines = [f"SAP Note {pick(head, 'Number') or pick(note, 'Number')}: {pick(note, 'Title') or pick(head, 'Title')}",
             ' | '.join(x for x in (f"component {pick(head, 'SAPComponentKey')}" if pick(head, 'SAPComponentKey') else '',
                                    f"version {pick(head, 'Version')}" if pick(head, 'Version') else '',
                                    f"released {pick(head, 'ReleasedOn')}" if pick(head, 'ReleasedOn') else '',
                                    pick(head, 'Type'), pick(head, 'Priority')) if x)]
    body = note.get('LongText') or {}
    lines.append(_plain(body.get('value') if isinstance(body, dict) else body)[:limit])
    return '\n'.join(l for l in lines if l)


def main():
    parser = argparse.ArgumentParser(description='Look up an SAP Note with the S-user in the keyring')
    parser.add_argument('number', nargs='?')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--trace', action='store_true', help='show the hosts visited (never any value)')
    args = parser.parse_args()
    if not args.check and not re.fullmatch(r'\d{4,10}', args.number or ''):
        parser.error('give a note number, e.g. 2382421')
    session, trace = _session(), []
    try:
        response = fetch(session, NOTE.format(n=args.number or '2382421'), _creds, trace)
        _keep(session)
        data = response.json()
    except SignInError as exc:
        print(f'SAP sign-in failed: {exc}', file=sys.stderr)
        if args.trace:
            print('\n'.join(trace), file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f'SAP could not be reached: {type(exc).__name__}', file=sys.stderr)
        return 3
    if args.trace:
        print('\n'.join(trace), file=sys.stderr)
    if args.check:
        print('signed in to SAP for Me; the note service answers')
    elif args.json:
        print(json.dumps(data))
    else:
        print(as_text(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
