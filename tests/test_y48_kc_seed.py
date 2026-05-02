"""Y.48 — KC seed + overview tests.

Verifies:
  * `scripts.seed_kc_y48.main(db_path)` is idempotent and produces the
    expected curriculum + user_interests rows.
  * `/api/kc/overview` surfaces the new pillars (app_center, synth_board,
    video_editor) and curriculum kinds (including the new `app` and `game`).
  * media_curriculum now accepts the new kinds.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def seeded_db():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    yield tmp.name
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_seed_is_idempotent(seeded_db):
    from scripts import seed_kc_y48
    r1 = seed_kc_y48.main(seeded_db)
    assert r1['ok']
    # First run: every row should be inserted, none merged
    assert r1['curriculum']['inserted'] == len(seed_kc_y48.CURRICULUM)
    assert r1['curriculum']['merged'] == 0
    assert r1['user_interests']['inserted'] == len(seed_kc_y48.USER_INTERESTS)
    assert r1['user_interests']['merged'] == 0
    total_curr = r1['curriculum']['total']
    total_int = r1['user_interests']['seed_total']

    # Second run: no new rows; everything merged
    r2 = seed_kc_y48.main(seeded_db)
    assert r2['curriculum']['inserted'] == 0
    assert r2['curriculum']['merged'] == len(seed_kc_y48.CURRICULUM)
    assert r2['user_interests']['inserted'] == 0
    assert r2['user_interests']['merged'] == len(seed_kc_y48.USER_INTERESTS)
    assert r2['curriculum']['total'] == total_curr
    assert r2['user_interests']['seed_total'] == total_int


def test_seed_covers_new_pillars(seeded_db):
    from scripts import seed_kc_y48
    seed_kc_y48.main(seeded_db)
    conn = sqlite3.connect(seeded_db)
    try:
        kinds = {row[0] for row in conn.execute(
            'SELECT DISTINCT kind FROM kc_media_curriculum').fetchall()}
        # All historical + new kinds must be present
        for required in {'music', 'image', 'video', 'style', 'genre',
                          'production', 'app', 'game'}:
            assert required in kinds, f'missing kind: {required}'

        # App Center frameworks/targets should appear as curriculum tools
        tools = {row[0] for row in conn.execute(
            "SELECT DISTINCT tool FROM kc_media_curriculum WHERE kind='app'"
        ).fetchall()}
        for fw in ('flutter', 'react-native', 'tauri', 'next', 'sveltekit'):
            assert fw in tools, f'missing app tool: {fw}'

        game_tools = {row[0] for row in conn.execute(
            "SELECT DISTINCT tool FROM kc_media_curriculum WHERE kind='game'"
        ).fetchall()}
        for engine in ('godot', 'unity', 'unreal', 'phaser', 'pygame'):
            assert engine in game_tools, f'missing game engine: {engine}'

        # user_interests categories should include the new pillar groupings
        cats = {row[0] for row in conn.execute(
            'SELECT DISTINCT category FROM user_interests').fetchall()}
        for required in {'apps', 'apps_framework', 'apps_target', 'games',
                          'games_engine', 'media_synth', 'media_video'}:
            assert required in cats, f'missing category: {required}'
    finally:
        conn.close()


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    tmp.close()
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv('SWARM_DB', tmp.name)
    # Run the seed BEFORE creating app so kc_overview reads from it.
    from scripts import seed_kc_y48
    seed_kc_y48.main(tmp.name)
    # create_app adds frontend/ to sys.path; do that first so 'services' imports.
    import sys as _sys
    from frontend.terminal import create_app
    app = create_app()
    # Patch services.get_connection AND each blueprint module's local
    # `get_connection` binding (they `from services import get_connection`
    # which captures the original reference at import time).
    import services as _svc
    _conn_factory = lambda: sqlite3.connect(tmp.name)  # noqa: E731
    monkeypatch.setattr(_svc, 'get_connection', _conn_factory)
    for mod_name in (
        'blueprints.kc_overview', 'blueprints.media_curriculum',
        'frontend.blueprints.kc_overview', 'frontend.blueprints.media_curriculum',
    ):
        if mod_name in _sys.modules:
            monkeypatch.setattr(
                _sys.modules[mod_name], 'get_connection', _conn_factory,
                raising=False,
            )
    for mod_name in ('blueprints.app_center', 'blueprints.synth_board',
                     'blueprints.video_editor'):
        if mod_name in _sys.modules:
            monkeypatch.setattr(_sys.modules[mod_name], '_DB_PATH', tmp.name)
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_overview_endpoint_reports_new_pillars(client):
    r = client.get('/api/kc/overview')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok']
    # Curriculum surfaced
    assert data['curriculum']['total'] > 0
    by_kind = data['curriculum']['by_kind']
    for required in ('music', 'image', 'video', 'app', 'game'):
        assert required in by_kind and by_kind[required] > 0

    # user_interests surfaced
    ui = data['user_interests']
    assert ui['seeded'] > 0
    cats = ui['by_category']
    for required in ('apps', 'games', 'apps_framework', 'games_engine'):
        assert required in cats and cats[required] > 0

    # App Center pillar block exists (table created on first POST/GET)
    # — create one project to trigger schema, then re-check.
    from frontend.blueprints import app_center  # noqa
    client.post('/api/app-center/projects', json={
        'name': 'KCSeedTest', 'kind': 'mobile', 'framework': 'flutter',
        'targets': ['ios'],
    })
    r2 = client.get('/api/kc/overview').get_json()
    assert 'app_center' in r2['pillars']
    assert r2['pillars']['app_center']['projects'] >= 1


def test_media_curriculum_accepts_new_kinds(client):
    # Endpoint validation should now permit 'app' and 'game'.
    r1 = client.post('/api/kc/media/curriculum', json={
        'topic': 'mobile app extra', 'kind': 'app', 'tool': 'flutter',
        'notes': 'extra entry',
    })
    assert r1.status_code == 200, r1.get_data(as_text=True)
    r2 = client.post('/api/kc/media/curriculum', json={
        'topic': '2d arcade extra', 'kind': 'game', 'tool': 'godot',
        'notes': 'extra entry',
    })
    assert r2.status_code == 200, r2.get_data(as_text=True)
    # Filter by kind=app should return at least 1
    listing = client.get('/api/kc/media/curriculum?kind=app').get_json()
    assert listing['ok'] and listing['count'] >= 1
