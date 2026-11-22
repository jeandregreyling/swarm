"""Tests for Phase 1A Media Center FFmpeg/NumPy Audio Engine and Email Audio Intake."""
from __future__ import annotations

import base64
import io
import math
import wave
from pathlib import Path

from core.media_center.audio_engine import (
    analyze_waveform_and_bpm,
    get_media_asset,
    list_media_assets,
    probe_media,
    save_media_asset,
)


def _make_pulsed_wav(duration_sec: float = 4.0, bpm: float = 120.0, sr: int = 22050) -> bytes:
    buf = io.BytesIO()
    n = int(sr * duration_sec)
    beat_period = 60.0 / bpm
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            beat_phase = (t % beat_period) / beat_period
            env = math.exp(-beat_phase * 10.0)
            sig = env * (0.65 * math.sin(2 * math.pi * 110.0 * t) + 0.25 * math.sin(2 * math.pi * 880.0 * t) + 0.1 * math.sin(2 * math.pi * 4200.0 * t))
            val = int(max(-1.0, min(1.0, sig)) * 30000)
            frames.extend(val.to_bytes(2, 'little', signed=True))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def test_save_probe_and_serato_rgb_waveform_analysis(tmp_path: Path):
    wav_bytes = _make_pulsed_wav(duration_sec=4.0, bpm=120.0)
    asset = save_media_asset('Brand New Day (Extended Remix).wav', wav_bytes, source='test', storage_root=tmp_path)
    assert asset['id'].startswith('asset-')
    assert asset['kind'] == 'audio'
    assert asset['url'].startswith('/api/media-center/artifacts/artifacts/media_center/library/')
    assert asset['probe']['has_audio'] is True
    assert 3.8 <= asset['probe']['duration_sec'] <= 4.2
    analysis = asset['analysis']
    assert len(analysis['peaks']) == 160
    assert len(analysis['low_peaks']) == 160
    assert len(analysis['mid_peaks']) == 160
    assert len(analysis['high_peaks']) == 160
    assert max(analysis['peaks']) == 1.0
    assert 70.0 <= analysis['bpm'] <= 180.0
    assert len(analysis['cue_points']) == 4
    listed = list_media_assets(storage_root=tmp_path)
    assert any(a['id'] == asset['id'] for a in listed)
    loaded = get_media_asset(asset['id'], storage_root=tmp_path)
    assert loaded and loaded['id'] == asset['id']


def test_email_intake_accepts_audio_attachment_into_media_center(tmp_path: Path, monkeypatch):
    import core.media_center.audio_engine as ae
    monkeypatch.setattr(ae, 'MEDIA_STORAGE_ROOT', tmp_path)
    from core import hb_email_intake
    wav_bytes = _make_pulsed_wav(duration_sec=2.5, bpm=120.0)
    text, why = hb_email_intake.attachment_text('Brand New Day (Extended Remix).wav', 'audio/wav', wav_bytes)
    assert why is None
    assert text is not None
    assert 'Media Center Asset Ingested' in text
    assert 'Estimated BPM:' in text
    assert 'Auto Cue Points:' in text


def test_media_center_library_blueprint_endpoints(tmp_path: Path, monkeypatch):
    import core.media_center.audio_engine as ae
    import frontend.blueprints.media_center as mc_bp
    monkeypatch.setattr(ae, 'MEDIA_STORAGE_ROOT', tmp_path)
    monkeypatch.setattr(mc_bp, 'MEDIA_STORAGE_ROOT', tmp_path)
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(mc_bp.media_center_bp)
    client = app.test_client()

    wav_bytes = _make_pulsed_wav(duration_sec=2.0, bpm=120.0)
    resp = client.post('/api/media-center/library/upload', json={
        'filename': 'Test Track.wav',
        'title': 'Test Track',
        'artist': 'JD',
        'data_base64': base64.b64encode(wav_bytes).decode('ascii'),
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['ok'] is True
    aid = body['asset']['id']

    list_resp = client.get('/api/media-center/library')
    assert list_resp.status_code == 200
    assert any(a['id'] == aid for a in list_resp.get_json()['assets'])

    get_resp = client.get(f'/api/media-center/library/{aid}')
    assert get_resp.status_code == 200
    assert len(get_resp.get_json()['asset']['analysis']['peaks']) == 160
