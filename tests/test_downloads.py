import configparser
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import base64

import pytest
from flask import Flask
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'frontend'))
sys.path.insert(0, str(ROOT / 'utils'))

from frontend.blueprints import downloads as dl
from services import auth
from scripts import configure_qbittorrent as setup


@pytest.fixture
def bridge(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dl.downloads_bp)
    monkeypatch.setattr(auth, 'get_current_user', lambda: {'role': 'owner', 'username': 'ghost'})
    calls = []

    class Client:
        def call(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return SimpleNamespace(status_code=204, text='')

        def json(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return {
                'search/plugins': [{'name': 'test', 'enabled': True}],
                'search/start': {'id': 1},
                'search/status': [{'id': 1, 'status': 'Stopped'}],
                'search/results': {'status': 'Stopped', 'results': [], 'total': 0},
                'torrents/trackers': [{'url': '** [DHT] **', 'num_peers': 3}],
            }[endpoint]

    monkeypatch.setattr(dl, '_client', lambda: Client())
    return app.test_client(), calls


def test_downloads_requires_owner(bridge, monkeypatch):
    client, calls = bridge
    monkeypatch.setattr(auth, 'get_current_user', lambda: None)
    assert client.get('/api/downloads').status_code == 403
    assert client.post('/api/downloads/add', json={}).status_code == 403
    assert client.post('/api/downloads/open-qbittorrent').status_code == 403
    assert calls == []


def test_open_qbittorrent_launches_native_app(bridge, monkeypatch, tmp_path):
    client, calls = bridge
    app = tmp_path / dl.QBIT_APPIMAGE
    app.write_bytes(b'test')
    app.chmod(0o700)
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    launched = []

    def run(command, **kwargs):
        launched.append(command)
        assert kwargs['env']['DBUS_SESSION_BUS_ADDRESS'].endswith('/bus')
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr(dl.subprocess, 'run', run)
    assert client.get('/api/downloads/files').json['files'][0]['qbittorrent'] is True
    assert client.post('/api/downloads/open-qbittorrent').json['ok'] is True
    assert launched[0][:3] == ['systemd-run', '--user', '--collect']
    assert launched[0][-1] == str(app)
    assert calls == [('app/version', {})]


@pytest.mark.parametrize('kind', ['missing', 'symlink', 'not-executable'])
def test_open_qbittorrent_rejects_unusable_app(bridge, monkeypatch, tmp_path, kind):
    client, _ = bridge
    app = tmp_path / dl.QBIT_APPIMAGE
    if kind == 'symlink':
        app.symlink_to('/bin/true')
    elif kind == 'not-executable':
        app.write_bytes(b'test')
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(dl.subprocess, 'run', lambda *a, **k: pytest.fail('must not launch'))
    assert client.post('/api/downloads/open-qbittorrent').status_code == 409


def test_open_qbittorrent_reports_launch_failure(bridge, monkeypatch, tmp_path):
    client, _ = bridge
    app = tmp_path / dl.QBIT_APPIMAGE
    app.write_bytes(b'test')
    app.chmod(0o700)
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(dl.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='No desktop session'))
    result = client.post('/api/downloads/open-qbittorrent')
    assert result.status_code == 502
    assert 'No desktop session' in result.json['error']


def test_open_qbittorrent_requires_ready_api(bridge, monkeypatch, tmp_path):
    client, _ = bridge
    app = tmp_path / dl.QBIT_APPIMAGE
    app.write_bytes(b'test')
    app.chmod(0o700)
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(dl.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(dl.time, 'sleep', lambda _: None)

    def unavailable():
        raise dl.QbitError('Connection refused')

    monkeypatch.setattr(dl, '_client', unavailable)
    result = client.post('/api/downloads/open-qbittorrent')
    assert result.status_code == 502
    assert 'not ready' in result.json['error']


def test_add_magnet_forces_local_save_directory(bridge):
    client, calls = bridge
    magnet = 'magnet:?xt=urn:btih:' + 'a' * 40
    response = client.post('/api/downloads/add', json={'magnet': magnet, 'savepath': '/tmp'})
    assert response.status_code == 200
    assert calls == [('torrents/add', {'data': {
        'savepath': str(Path.home() / 'Downloads'), 'autoTMM': 'false', 'urls': magnet,
    }})]


@pytest.mark.parametrize('result,expected', [
    ({'success_count': 1, 'failure_count': 0, 'pending_count': 0}, 200),
    ({'success_count': 0, 'failure_count': 0, 'pending_count': 1}, 200),
    ({'success_count': 0, 'failure_count': 1, 'pending_count': 0}, 502),
    ({}, 502),
])
def test_qbit_53_add_response(bridge, monkeypatch, result, expected):
    client, _ = bridge
    monkeypatch.setattr(dl, '_client', lambda: SimpleNamespace(
        call=lambda *a, **kw: SimpleNamespace(status_code=200, text=json.dumps(result), json=lambda: result)
    ))
    assert client.post('/api/downloads/add', json={
        'magnet': 'magnet:?xt=urn:btih:' + 'b' * 40,
    }).status_code == expected


@pytest.mark.parametrize('payload', [
    {}, [], {'magnet': 'https://localhost/secret'}, {'magnet': 'magnet:?xt=invalid'},
    {'magnet': 123}, {'magnet': 'x' * 16385},
])
def test_bad_magnet_is_rejected_before_qbit(bridge, payload):
    client, calls = bridge
    assert client.post('/api/downloads/add', json=payload).status_code == 400
    assert not calls


def test_upload_torrent(bridge):
    client, calls = bridge
    assert client.post('/api/downloads/add', data={
        'torrent': (io.BytesIO(b'd4:infodee'), 'legal.torrent')
    }).status_code == 200
    assert calls[0][0] == 'torrents/add'
    assert calls[0][1]['files']['torrents'][1] == b'd4:infodee'


def test_upload_limit_and_extension(bridge):
    client, calls = bridge
    for filename, content in [('bad.py', b'bad'), ('big.torrent', b'x' * (10 * 1024 * 1024 + 1))]:
        assert client.post('/api/downloads/add', data={
            'torrent': (io.BytesIO(content), filename),
        }).status_code == 400
    assert not calls


def test_remove_task_always_keeps_files(bridge):
    client, calls = bridge
    assert client.post('/api/downloads/action', json={
        'hash': 'a' * 40, 'action': 'remove', 'deleteFiles': True,
    }).status_code == 200
    assert calls == [('torrents/delete', {'data': {'hashes': 'a' * 40, 'deleteFiles': 'false'}})]


@pytest.mark.parametrize('operation,endpoint', [('stop', 'stop'), ('start', 'start'), ('reannounce', 'reannounce')])
def test_controls_use_qbit_5_endpoints(bridge, operation, endpoint):
    client, calls = bridge
    assert client.post('/api/downloads/action', json={'hash': 'a' * 40, 'action': operation}).status_code == 200
    assert calls[0][0] == 'torrents/' + endpoint


def test_invalid_action_and_cross_site_controls(bridge):
    client, calls = bridge
    assert client.post('/api/downloads/action', json={'hash': 'all', 'action': 'remove'}).status_code == 400
    assert client.post('/api/downloads/action', json={}, headers={'Origin': 'https://other.example'}).status_code == 403
    assert not calls


def test_search_shape_and_cleanup(bridge):
    client, calls = bridge
    assert client.post('/api/downloads/search', json={'query': 'linux'}).json['id'] == 1
    result = client.get('/api/downloads/search/1')
    assert result.status_code == 200
    assert result.json['status'] == 'Stopped'
    assert result.json['searches'] == [{'id': 1, 'status': 'Stopped'}]
    assert client.delete('/api/downloads/search/1').status_code == 200
    assert [call[0] for call in calls][-2:] == ['search/stop', 'search/delete']


def test_no_engines_is_explicit_error(bridge, monkeypatch):
    client, _ = bridge
    monkeypatch.setattr(dl, '_client', lambda: SimpleNamespace(json=lambda *a: []))
    result = client.post('/api/downloads/search', json={'query': 'linux'})
    assert result.status_code == 409
    assert 'No enabled search engines' in result.json['error']


def test_connection_error_is_not_success(bridge, monkeypatch):
    client, _ = bridge

    def fail():
        raise dl.QbitError('Cannot reach qBittorrent.')

    monkeypatch.setattr(dl, '_client', fail)
    result = client.get('/api/downloads')
    assert result.status_code == 502
    assert result.json['ok'] is False


def test_list_local_files_skips_symlinks(bridge, monkeypatch, tmp_path):
    client, _ = bridge
    (tmp_path / 'file.txt').write_text('abc')
    (tmp_path / 'folder').mkdir()
    (tmp_path / 'symlink').symlink_to('/etc/passwd')
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    result = client.get('/api/downloads/files').json
    assert [row['name'] for row in result['files']] == ['file.txt', 'folder']
    assert result['files'][0]['size'] == 3


@pytest.mark.parametrize('status,text', [(200, 'Ok.'), (204, '')])
def test_client_accepts_old_and_new_login_success(monkeypatch, tmp_path, status, text):
    config = tmp_path / 'qbit.json'
    config.write_text(json.dumps({'port': 8085, 'username': 'test', 'password': 'test-only'}))
    monkeypatch.setenv('SWARM_QBIT_CONFIG', str(config))
    calls = []

    def send(self, method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=status, text=text)

    monkeypatch.setattr(requests.Session, 'request', send)
    client = dl.QbitClient()
    assert client.session.trust_env is False
    assert calls[0][1] == 'http://127.0.0.1:8085/api/v2/auth/login'
    assert calls[0][2]['allow_redirects'] is False
    client.session.close()


def test_setup_uses_qbit_53_section_and_private_credentials(monkeypatch, tmp_path):
    config_dir = tmp_path / '.config/qBittorrent'
    config_dir.mkdir(parents=True)
    path = config_dir / 'qBittorrent.conf'
    original = '[BitTorrent]\nSession\\Port=19470\n[Preferences]\nGeneral\\Locale=en_AU\n'
    path.write_text(original)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(sys, 'argv', ['configure_qbittorrent.py'])
    setup.main()
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    assert config['WebUI']['Address'] == '127.0.0.1'
    assert config['WebUI']['LocalHostAuth'] == 'true'
    assert config['BitTorrent']['Session\\Port'] == '19470'
    credentials = tmp_path / '.config/swarm/qbittorrent.json'
    assert credentials.stat().st_mode & 0o777 == 0o600
    secret = json.loads(credentials.read_text())['password']
    salt, digest = config['WebUI']['Password_PBKDF2'][11:-1].split(':')
    assert hashlib.pbkdf2_hmac('sha512', secret.encode(), base64.b64decode(salt), 100000) == base64.b64decode(digest)
    assert path.with_suffix('.conf.before-fridays').read_text() == original


def test_files_flag_windows_programs(bridge, monkeypatch, tmp_path):
    client, _ = bridge
    (tmp_path / 'setup.EXE').write_bytes(b'MZ')
    (tmp_path / 'notes.txt').write_text('x')
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    rows = {row['name']: row['windows'] for row in client.get('/api/downloads/files').json['files']}
    assert rows == {'notes.txt': False, 'setup.EXE': True}


@pytest.mark.parametrize('name', ['../setup.exe', 'sub/setup.exe', 'notes.txt', 'missing.exe', 'link.exe', ''])
def test_run_windows_rejects_unsafe_or_wrong_files(bridge, monkeypatch, tmp_path, name):
    client, _ = bridge
    (tmp_path / 'notes.txt').write_text('x')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'setup.exe').write_bytes(b'MZ')
    (tmp_path / 'link.exe').symlink_to(tmp_path / 'notes.txt')
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(dl.subprocess, 'run', lambda *a, **k: pytest.fail('must not launch'))
    assert client.post('/api/downloads/run-windows', json={'name': name}).status_code == 400


def test_run_windows_launches_bottle_in_user_session(bridge, monkeypatch, tmp_path):
    client, _ = bridge
    (tmp_path / 'setup.msi').write_bytes(b'x')
    monkeypatch.setattr(dl, 'DOWNLOAD_DIR', tmp_path)
    seen = {}

    def fake_run(command, **kwargs):
        seen['command'], seen['env'] = command, kwargs['env']
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr(dl.subprocess, 'run', fake_run)
    result = client.post('/api/downloads/run-windows', json={'name': 'setup.msi'})
    assert result.json['ok'] is True
    assert seen['command'][:3] == ['systemd-run', '--user', '--collect']
    assert seen['command'][-4:] == ['-b', 'Fridays', '-e', str(tmp_path / 'setup.msi')]
    assert seen['env']['DBUS_SESSION_BUS_ADDRESS'].endswith('/bus')
