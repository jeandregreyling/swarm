import base64
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _app():
    from frontend.blueprints.media_bp import media_bp

    app = Flask(__name__)
    app.register_blueprint(media_bp)
    return app


def _wav_upload(freq=220.0):
    buf = io.BytesIO()
    sr = 8000
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        frames = bytearray()
        for i in range(int(sr * 0.25)):
            val = int(16000 * math.sin(2 * math.pi * freq * (i / sr)))
            frames.extend(struct.pack('<h', val))
        wav.writeframes(bytes(frames))
    buf.seek(0)
    return buf


def _latest_media_run(run_id):
    from utils.db._connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            'SELECT run_id, prompt FROM media_runs WHERE run_id=?',
            (run_id,),
        ).fetchone()
    assert row is not None
    return {'run_id': row[0], 'prompt': row[1]}


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


def test_media_produce_image_runner_writes_png_artifact():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/produce', json={
            'runner_key': 'local_prompt_image_runner',
            'prompt': 'resilient studio agents with clear handoff lights',
            'source_agent': 'gemma',
        })
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    out = data.get('output_path') or ''
    assert out.endswith('.png')
    path = ROOT / out
    assert path.exists()
    assert path.stat().st_size > 1000


def test_media_produce_image_runner_normalizes_fenced_model_json():
    app = _app()
    model_output = """```json
    [{"image_prompt": "a bright Fridays Studio prompt card with green handoff lights",
      "video_prompt": "ignore this video prompt"}]
    ```"""
    with app.test_client() as c:
        resp = c.post('/api/media/produce', json={
            'runner_key': 'local_prompt_image_runner',
            'media_type': 'image',
            'prompt': model_output,
            'source_agent': 'gemma',
        })
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    assert data.get('prompt_info', {}).get('used_runtime_json_normalizer') is True
    assert data.get('prompt_info', {}).get('shape') == 'list'
    assert data.get('prompt_info', {}).get('selected_field') == 'image_prompt'
    row = _latest_media_run(data['run_id'])
    assert 'bright Fridays Studio prompt card' in row['prompt']
    assert 'ignore this video prompt' not in row['prompt']


def test_media_produce_video_runner_writes_video_artifact_without_ffmpeg_requirement():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/produce', json={
            'runner_key': 'local_ffmpeg_video_runner',
            'prompt': 'five second resilient local agent motion card',
            'source_agent': 'llama',
        })
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    out = data.get('output_path') or ''
    assert out.endswith(('.mp4', '.avi'))
    path = ROOT / out
    assert path.exists()
    assert path.stat().st_size > 1000


def test_media_produce_video_runner_selects_video_prompt_from_model_json():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/produce', json={
            'runner_key': 'local_ffmpeg_video_runner',
            'media_type': 'video',
            'model_output': '{"image_prompt":"still frame only","video_prompt":"five second status light handoff animation"}',
            'source_agent': 'llama',
        })
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    assert data.get('prompt_info', {}).get('selected_field') == 'video_prompt'
    row = _latest_media_run(data['run_id'])
    assert row['prompt'] == 'five second status light handoff animation'


def test_media_mix_songs_creates_remix_preview_and_manifest():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/mix-songs', json={
            'song_a': 'first reference track',
            'song_b': 'second reference track',
            'mode': 'new_song',
            'poem': 'silver wires under the rain\nwe teach the night a borrowed name',
            'suggestions': 'bright synthpop, strong hook, clean vocal guide',
            'duration_sec': 4,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        artifact_resp = c.get(data.get('artifact_url'))

    assert data.get('ok') is True
    assert data.get('mode') == 'new_song'
    assert data.get('output_path', '').endswith('.wav')
    assert data.get('manifest_path', '').endswith('.json')
    assert data.get('lyrics')
    assert any(item.get('role') == 'vocal_generation' for item in data.get('provider_handoff') or [])
    assert artifact_resp.status_code == 200

    wav_path = ROOT / data['output_path']
    manifest_path = ROOT / data['manifest_path']
    assert wav_path.exists()
    assert wav_path.stat().st_size > 1000
    with wave.open(str(wav_path), 'rb') as wav:
        assert wav.getnchannels() == 2
        assert wav.getframerate() == 22050

    manifest = json.loads(manifest_path.read_text())
    assert manifest['schema'] == 'fridays.media.remix.v1'
    assert manifest['mode'] == 'new_song'
    assert manifest['lyrics']['lines']


def test_media_mix_songs_layers_uploaded_wav_sources():
    app = _app()
    with app.test_client() as c:
        resp = c.post('/api/media/mix-songs', data={
            'song_a': 'uploaded source a',
            'song_b': 'uploaded source b',
            'mode': 'mashup',
            'suggestions': 'use the uploads as rhythmic source layers',
            'duration_sec': '4',
            'song_a_file': (_wav_upload(220), 'source-a.wav'),
            'song_b_file': (_wav_upload(330), 'source-b.wav'),
        }, content_type='multipart/form-data')
        assert resp.status_code == 200
        data = resp.get_json()

    assert data.get('ok') is True
    assert len(data.get('source_layers') or []) == 2
    assert all('layered' in note for note in data['source_layers'])


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
