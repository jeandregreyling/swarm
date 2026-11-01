"""Shared localhost qBittorrent Web API client and read-only status report."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re

import requests

logger = logging.getLogger(__name__)

DOWNLOAD_QUESTION_RE = re.compile(r'\b(q\s?bit\s?torrent|qbit|q\s?torrent|torrents?|downloading|my downloads|seeders?)\b', re.I)


class QbitError(RuntimeError):
    pass


class QbitClient:
    def __init__(self):
        path = Path(os.environ.get(
            'SWARM_QBIT_CONFIG', str(Path.home() / '.config/swarm/qbittorrent.json')
        ))
        try:
            config = json.loads(path.read_text())
            port = int(config['port'])
            username, password = config['username'], config['password']
            if not 1 <= port <= 65535 or not username or not password:
                raise ValueError('Invalid connection settings')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise QbitError(
                'qBittorrent is not configured. Close qBittorrent, run '
                'scripts/configure_qbittorrent.py, then reopen qBittorrent.'
            ) from exc
        self.base = f'http://127.0.0.1:{port}/api/v2/'
        self.session = requests.Session()
        self.session.trust_env = False
        try:
            response = self.call('auth/login', data={'username': username, 'password': password})
        except QbitError:
            self.session.close()
            raise
        if response.status_code != 204 and response.text.strip() != 'Ok.':
            self.session.close()
            raise QbitError('qBittorrent rejected the saved Web API credentials. Run setup again.')

    def call(self, endpoint, *, data=None, files=None, params=None):
        try:
            response = self.session.request(
                'POST' if data is not None or files else 'GET',
                self.base + endpoint, data=data, files=files, params=params,
                timeout=(3, 20), allow_redirects=False,
                headers={'Referer': self.base},
            )
        except requests.RequestException as exc:
            raise QbitError('Cannot reach qBittorrent. Open the app and check its localhost Web API.') from exc
        if not 200 <= response.status_code < 300:
            raise QbitError(f'qBittorrent rejected {endpoint} (HTTP {response.status_code}).')
        return response

    def json(self, endpoint, **kwargs):
        try:
            return self.call(endpoint, **kwargs).json()
        except requests.exceptions.JSONDecodeError as exc:
            raise QbitError(f'qBittorrent returned invalid JSON for {endpoint}.') from exc

    def close(self):
        try:
            self.call('auth/logout', data={})
        except QbitError as exc:
            logger.warning('Downloads session logout failed: %s', exc)
        finally:
            self.session.close()


def _human_size(value):
    size = float(value or 0)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def _eta(seconds):
    seconds = int(seconds or 0)
    if seconds <= 0 or seconds >= 8640000:
        return 'unknown'
    hours, rest = divmod(seconds, 3600)
    return f'{hours}h {rest // 60}m' if hours else f'{rest // 60}m {rest % 60}s'


def downloads_snapshot(client_factory=QbitClient):
    """Return live qBittorrent state, or ``{'ok': False, 'error': ...}``."""
    try:
        client = client_factory()
    except QbitError as exc:
        return {'ok': False, 'error': str(exc)}
    try:
        return {
            'ok': True,
            'version': client.call('app/version').text.strip(),
            'transfer': client.json('transfer/info'),
            'torrents': client.json('torrents/info', params={'sort': 'added_on', 'reverse': 'true'}),
        }
    except QbitError as exc:
        return {'ok': False, 'error': str(exc)}
    finally:
        client.close()


def format_downloads_report(snapshot):
    """Plain factual summary of a snapshot for chat replies."""
    if not snapshot.get('ok'):
        return (
            'qBittorrent is not reachable right now, so I cannot see any downloads. '
            'Open it from Fridays → Downloads → Open qBittorrent, then ask again.\n'
            f"Detail: {snapshot.get('error') or 'unknown error'}"
        )
    transfer = snapshot.get('transfer') or {}
    torrents = snapshot.get('torrents') or []
    lines = [
        f"qBittorrent {snapshot.get('version') or ''} is running "
        f"(connection: {transfer.get('connection_status') or 'unknown'}, "
        f"{transfer.get('dht_nodes', 0)} DHT nodes, "
        f"↓ {_human_size(transfer.get('dl_info_speed'))}/s, ↑ {_human_size(transfer.get('up_info_speed'))}/s)."
    ]
    if not torrents:
        lines.append('\nNo torrents are in the list.')
        return '\n'.join(lines)
    active = [t for t in torrents if float(t.get('progress') or 0) < 1]
    lines.append('')
    lines.append(f'{len(active)} of {len(torrents)} torrent(s) still downloading:' if active
                 else f'All {len(torrents)} torrent(s) are complete:')
    for item in (active or torrents)[:15]:
        lines.append(
            f"- {item.get('name') or 'unnamed'} — {float(item.get('progress') or 0) * 100:.1f}% "
            f"of {_human_size(item.get('size'))}, {item.get('state') or 'unknown'}, "
            f"↓ {_human_size(item.get('dlspeed'))}/s, seeds {item.get('num_seeds', 0)}"
            f"/{item.get('num_complete', 0)}, ETA {_eta(item.get('eta'))}"
        )
    return '\n'.join(lines)


def is_downloads_question(text):
    return bool(DOWNLOAD_QUESTION_RE.search(str(text or '')))
