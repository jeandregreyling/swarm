"""Local qBittorrent bridge; credentials never leave the server."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, g, jsonify, request
import requests

from services.auth import require_owner
from utils.qbit_bridge import QbitClient, QbitError

downloads_bp = Blueprint('downloads', __name__)
logger = logging.getLogger(__name__)
DOWNLOAD_DIR = Path.home() / 'Downloads'
WINDOWS_EXTENSIONS = {'.exe', '.msi'}
BOTTLES_APP = 'com.usebottles.bottles'
BOTTLE_NAME = os.environ.get('SWARM_BOTTLE_NAME', 'Fridays')
QBIT_APPIMAGE = 'qbittorrent-5.3.0_x86_64.AppImage'


def _client():
    if 'qbit' not in g:
        g.qbit = QbitClient()
    return g.qbit


@downloads_bp.teardown_request
def _close_client(_error):
    client = g.pop('qbit', None)
    if client is not None:
        client.close()


@downloads_bp.before_request
def _same_origin():
    if request.method != 'GET':
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (
            origin and urlparse(origin).netloc != request.host
        ):
            return jsonify(ok=False, error='Cross-site download controls are not allowed.'), 403


@downloads_bp.errorhandler(QbitError)
def _qbit_error(exc):
    logger.warning('Downloads: %s', exc)
    return jsonify(ok=False, error=str(exc)), 502


def _valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', value)


@downloads_bp.get('/api/downloads')
@require_owner
def status(current_user):
    client = _client()
    return jsonify(
        ok=True, download_dir=str(DOWNLOAD_DIR),
        version=client.call('app/version').text.strip(),
        transfer=client.json('transfer/info'),
        torrents=client.json('torrents/info', params={'sort': 'added_on', 'reverse': 'true'}),
        plugins=client.json('search/plugins'),
    )


@downloads_bp.get('/api/downloads/files')
@require_owner
def files(current_user):
    try:
        items = [
            {'name': path.name, 'directory': path.is_dir(), 'size': path.stat().st_size,
             'windows': path.is_file() and path.suffix.lower() in WINDOWS_EXTENSIONS,
             'qbittorrent': path.name == QBIT_APPIMAGE and path.is_file()}
            for path in sorted(DOWNLOAD_DIR.iterdir(), key=lambda p: p.name.lower())
            if not path.is_symlink()
        ]
    except OSError:
        logger.exception('Cannot list Downloads directory')
        return jsonify(ok=False, error='Cannot read the Downloads directory.'), 500
    return jsonify(ok=True, path=str(DOWNLOAD_DIR), files=items)


@downloads_bp.post('/api/downloads/open-qbittorrent')
@require_owner
def open_qbittorrent(current_user):
    path = DOWNLOAD_DIR / QBIT_APPIMAGE
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        return jsonify(ok=False, error=f'Executable {QBIT_APPIMAGE} was not found in Downloads.'), 409
    uid = os.getuid()
    env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{uid}',
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{uid}/bus'}
    try:
        result = subprocess.run(
            ['systemd-run', '--user', '--collect', '--quiet',
             f'--unit=fridays-qbittorrent-{time.time_ns()}', str(path)],
            env=env, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning('qBittorrent launch failed: %s', exc)
        return jsonify(ok=False, error='Could not launch qBittorrent in the desktop session.'), 502
    if result.returncode:
        logger.warning('qBittorrent launch failed: %s', result.stderr.strip())
        return jsonify(ok=False, error='qBittorrent did not launch: ' + result.stderr.strip()[:300]), 502
    for attempt in range(10):
        try:
            client = _client()
            version = client.call('app/version').text.strip()
            return jsonify(ok=True, version=version, download_dir=str(DOWNLOAD_DIR))
        except QbitError as exc:
            if attempt == 9:
                logger.warning('qBittorrent launched but API is unavailable: %s', exc)
                return jsonify(ok=False, error='Launch requested, but the qBittorrent Web API is not ready. ' + str(exc)), 502
            time.sleep(1)


@downloads_bp.post('/api/downloads/run-windows')
@require_owner
def run_windows(current_user):
    payload = request.get_json(silent=True)
    name = payload.get('name') if isinstance(payload, dict) else None
    if not isinstance(name, str) or not name or Path(name).name != name:
        return jsonify(ok=False, error='Choose a file directly inside Downloads.'), 400
    path = DOWNLOAD_DIR / name
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in WINDOWS_EXTENSIONS:
        return jsonify(ok=False, error='Only .exe or .msi files in Downloads can be run.'), 400
    uid = os.getuid()
    # Swarm runs as a system service; launch in the desktop user session so the window is visible
    # and the program outlives Fridays restarts.
    env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{uid}',
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{uid}/bus'}
    command = [
        'systemd-run', '--user', '--collect', '--quiet',
        f'--unit=fridays-bottles-{int(time.time())}',
        'flatpak', 'run', '--command=bottles-cli', BOTTLES_APP,
        'run', '-b', BOTTLE_NAME, '-e', str(path),
    ]
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning('Bottles launch failed: %s', exc)
        return jsonify(ok=False, error='Could not start Bottles.'), 502
    if result.returncode != 0:
        logger.warning('Bottles launch failed: %s', result.stderr.strip())
        return jsonify(ok=False, error='Bottles did not start: ' + (result.stderr.strip()[:300] or 'unknown error')), 502
    return jsonify(ok=True, bottle=BOTTLE_NAME, file=name)


@downloads_bp.post('/api/downloads/add')
@require_owner
def add(current_user):
    data = {'savepath': str(DOWNLOAD_DIR), 'autoTMM': 'false'}
    upload = request.files.get('torrent')
    if upload:
        content = upload.stream.read(10 * 1024 * 1024 + 1)
        if not upload.filename.lower().endswith('.torrent') or len(content) > 10 * 1024 * 1024:
            return jsonify(ok=False, error='Choose a .torrent file no larger than 10 MiB.'), 400
        response = _client().call(
            'torrents/add', data=data, files={'torrents': ('download.torrent', content)}
        )
    else:
        payload = request.get_json(silent=True)
        magnet = payload.get('magnet') if isinstance(payload, dict) else None
        if not isinstance(magnet, str) or len(magnet) > 16384:
            return jsonify(ok=False, error='Supply a magnet link or a .torrent file.'), 400
        parsed = urlparse(magnet.strip())
        topics = parse_qs(parsed.query).get('xt', [])
        if parsed.scheme != 'magnet' or not any(
            re.fullmatch(r'urn:btih:(?:[0-9a-fA-F]{40}|[A-Za-z2-7]{32})|urn:btmh:1220[0-9a-fA-F]{64}', t)
            for t in topics
        ):
            return jsonify(ok=False, error='Invalid BitTorrent magnet link.'), 400
        response = _client().call('torrents/add', data={**data, 'urls': magnet.strip()})
    if response.status_code != 204 and response.text.strip() != 'Ok.':
        try:
            result = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise QbitError('qBittorrent returned an invalid torrent-add response.') from exc
        if (
            not isinstance(result, dict) or result.get('failure_count', 0)
            or result.get('success_count', 0) + result.get('pending_count', 0) < 1
        ):
            raise QbitError('qBittorrent could not add this torrent. Check the file or magnet link.')
    return jsonify(ok=True)


@downloads_bp.post('/api/downloads/action')
@require_owner
def action(current_user):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error='A torrent hash and action are required.'), 400
    torrent_hash, operation = payload.get('hash'), payload.get('action')
    endpoints = {'start': 'start', 'stop': 'stop', 'reannounce': 'reannounce', 'remove': 'delete'}
    if not _valid_hash(torrent_hash) or operation not in endpoints:
        return jsonify(ok=False, error='Invalid torrent hash or action.'), 400
    data = {'hashes': torrent_hash}
    if operation == 'remove':
        data['deleteFiles'] = 'false'
    _client().call('torrents/' + endpoints[operation], data=data)
    return jsonify(ok=True)


@downloads_bp.get('/api/downloads/<torrent_hash>/trackers')
@require_owner
def trackers(torrent_hash, current_user):
    if not _valid_hash(torrent_hash):
        return jsonify(ok=False, error='Invalid torrent hash.'), 400
    return jsonify(ok=True, trackers=_client().json('torrents/trackers', params={'hash': torrent_hash}))


@downloads_bp.post('/api/downloads/search')
@require_owner
def search(current_user):
    payload = request.get_json(silent=True)
    query = payload.get('query') if isinstance(payload, dict) else None
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
        return jsonify(ok=False, error='Enter a search term between 2 and 200 characters.'), 400
    client = _client()
    if not any(plugin.get('enabled') for plugin in client.json('search/plugins')):
        return jsonify(ok=False, error='No enabled search engines. Install one in qBittorrent: Search > Search plugins.'), 409
    result = client.json('search/start', data={'pattern': query.strip(), 'plugins': 'enabled', 'category': 'all'})
    return jsonify(ok=True, id=result['id'])


@downloads_bp.get('/api/downloads/search/<int:search_id>')
@require_owner
def results(search_id, current_user):
    client = _client()
    statuses = client.json('search/status', params={'id': search_id})
    result = client.json('search/results', params={'id': search_id, 'limit': 100, 'offset': 0})
    return jsonify(ok=True, searches=statuses, **result)


@downloads_bp.delete('/api/downloads/search/<int:search_id>')
@require_owner
def clear_search(search_id, current_user):
    client = _client()
    client.call('search/stop', data={'id': search_id})
    client.call('search/delete', data={'id': search_id})
    return jsonify(ok=True)
