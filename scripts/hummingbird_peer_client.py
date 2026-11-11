#!/usr/bin/env python3
"""Connect an existing terminal instructor to Hummingbird without new inference.

Credentials are issued by `python -m core.peer_bridge issue codex-instructor
--out <private-file>`. This client does not use operator cookies, start another
Codex session, run incoming requests or approve source changes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

MAX_RESPONSE = 128 * 1024
PRINCIPAL = 'codex-instructor'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Peer redirects are refused')


class PeerClient:
    def __init__(self, credentials: Path):
        # Refuse symlinked or shared credentials, and never place tokens on argv.
        info = credentials.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Peer credentials must be an owned regular file with mode 0600')
        data = json.loads(credentials.read_text(encoding='utf-8'))
        origin = urlsplit(data.get('base_url', ''))
        if (origin.scheme != 'http' or origin.hostname not in {'127.0.0.1', '::1'}
                or not origin.port or origin.username or origin.password
                or origin.path not in {'', '/'} or origin.query or origin.fragment):
            raise ValueError('Peer endpoint must be a literal loopback HTTP origin with a port')
        if data.get('principal') != PRINCIPAL:
            raise ValueError('A dedicated codex-instructor token is required')
        token = data.get('token')
        if not isinstance(token, str) or not token.startswith('hbp_') or not 24 <= len(token) <= 128 or not all(
                ch.isascii() and (ch.isalnum() or ch in '_-') for ch in token):
            raise ValueError('Invalid peer service token format')
        self.origin = data['base_url'].rstrip('/')
        self._token = token
        self._opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path: str, body=None) -> dict:
        request = Request(self.origin + path,
                          data=None if body is None else json.dumps(body).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + self._token,
                                   'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            with self._opener.open(request, timeout=10) as response:
                if response.headers.get_content_type() != 'application/json':
                    raise ValueError('Peer API did not return JSON')
                payload = response.read(MAX_RESPONSE + 1)
        except HTTPError as exc:
            # Do not reflect remote bodies, headers or credentials into logs.
            raise ValueError(f'Peer API returned HTTP {exc.code}') from None
        except URLError:
            raise ValueError('Local Hummingbird peer connection failed') from None
        if len(payload) > MAX_RESPONSE:
            raise ValueError('Peer response exceeded the output limit')
        result = json.loads(payload)
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ValueError('Peer API returned an unsuccessful response')
        return result

    def whoami(self):
        result = self.request('/api/peer/v1/whoami')
        if result.get('principal') != PRINCIPAL:
            raise ValueError('Peer server returned a different principal')
        return result


def positive(value):
    parsed = int(value)
    if not 0 < parsed < 2**53:
        raise argparse.ArgumentTypeError('Expected a positive safe integer')
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('whoami')
    inbox = sub.add_parser('inbox')
    inbox.add_argument('--after', type=positive, default=0)
    inbox.add_argument('--limit', type=positive, default=4)
    thread = sub.add_parser('thread')
    thread.add_argument('conversation_id', type=positive)
    post = sub.add_parser('post')
    post.add_argument('conversation_id', type=positive)
    post.add_argument('--text-file', type=Path, required=True)
    ack = sub.add_parser('ack')
    ack.add_argument('ids', type=positive, nargs='+')
    args = parser.parse_args(argv)
    client = PeerClient(args.credentials)
    # Authenticate the identity on every invocation, before reads or writes.
    identity = client.whoami()
    if args.action == 'whoami':
        result = identity
    elif args.action == 'inbox':
        result = client.request('/api/peer/v1/inbox?' + urlencode({'after': args.after, 'limit': min(20, args.limit)}))
    elif args.action == 'thread':
        result = client.request(f'/api/peer/v1/threads/{args.conversation_id}?limit=12')
    elif args.action == 'post':
        if args.text_file.stat().st_size > 16000:
            raise ValueError('Reply file exceeds the 4000-character peer limit')
        text = args.text_file.read_text(encoding='utf-8')
        if not text.strip() or len(text) > 4000:
            raise ValueError('Reply must contain 1-4000 characters')
        result = client.request('/api/peer/v1/messages', {'conversation_id': args.conversation_id, 'text': text})
    else:
        if len(args.ids) > 20:
            raise ValueError('At most 20 message IDs can be acknowledged')
        result = client.request('/api/peer/v1/inbox/ack', {'ids': args.ids})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print('Hummingbird peer error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
