import base64
import sys
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _app():
    from frontend.blueprints.media_bp import media_bp

    app = Flask(__name__)
    app.register_blueprint(media_bp)
    return app


def test_media_state_seeds_song_and_providers():
    app = _app()
    with app.test_client() as c:
        resp = c.get('/api/media/state')
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    providers = data.get('providers') or []
    names = {p.get('name') for p in providers}
    assert {'YouTube', 'YouTube Music', 'Spotify', 'Apple Music', 'SoundCloud'}.issubset(names)

    items = data.get('items') or []
    titles = {i.get('title') for i in items}
    assert 'girl in the mirror (feat. IVEY.H)' in titles


def test_media_produce_audio_runner_writes_artifact():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/produce', json={'runner_key': 'local_synth_audio_runner', 'prompt': 'test tone'})
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    out = data.get('output_path')
    assert out and out.endswith('.wav')
    path = ROOT / out
    assert path.exists()
    assert path.stat().st_size > 1000


def test_media_screenshot_upload_persists_artifact():
    # 1x1 transparent PNG
    tiny_png = base64.b64encode(
        bytes.fromhex('89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6360000002000154A24F5D0000000049454E44AE426082')
    ).decode('ascii')
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/screenshot', json={
            'data_url': 'data:image/png;base64,' + tiny_png,
            'label': 'test_capture'
        })
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    out = data.get('output_path') or ''
    assert out.endswith('.png')
    path = ROOT / out
    assert path.exists()
    assert path.stat().st_size > 40
