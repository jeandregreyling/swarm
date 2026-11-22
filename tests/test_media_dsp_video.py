"""Tests for Phase 1B Serato Audio DSP, Auto-Tune, Dual-Deck Mixdown, and YouTube MP4 Visualizer."""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path

from core.media_center.audio_engine import save_media_asset
from core.media_center.dsp_video import (
    mix_two_decks,
    process_audio_dsp,
    render_youtube_visualizer,
)


def _tone_wav(freq: float = 228.0, duration: float = 2.0, sr: int = 22050) -> bytes:
    buf = io.BytesIO()
    n = int(sr * duration)
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            sig = 0.55 * math.sin(2 * math.pi * freq * t) + 0.2 * math.sin(2 * math.pi * freq * 2.0 * t)
            frames.extend(int(sig * 28000).to_bytes(2, 'little', signed=True))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def test_dsp_eq_pitch_tempo_autotune_and_normalize(tmp_path: Path):
    base = save_media_asset('vocal_take.wav', _tone_wav(228.0, 2.0), source='test', storage_root=tmp_path)
    out = process_audio_dsp(
        base['id'],
        {
            'low_db': 3.0,
            'mid_db': -1.5,
            'high_db': 2.5,
            'pitch_semitones': 2.0,
            'tempo': 1.1,
            'autotune_strength': 0.8,
            'autotune_key': 'C_major',
            'normalize': True,
            'label': 'Autotune Master',
        },
        storage_root=tmp_path,
    )
    assert out['id'] != base['id']
    assert out['source'] == 'dsp_render'
    assert out['probe']['has_audio'] is True
    assert out['probe']['duration_sec'] > 1.2
    assert len(out['analysis']['peaks']) == 160


def test_youtube_audio_reactive_mp4_visualizer(tmp_path: Path):
    base = save_media_asset('brand_new_day.wav', _tone_wav(220.0, 2.0), source='test', storage_root=tmp_path)
    vid = render_youtube_visualizer(
        base['id'],
        {'aspect': '16:9', 'width': 640, 'height': 360, 'max_duration_sec': 2.0, 'title': 'Brand New Day'},
        storage_root=tmp_path,
    )
    assert vid['kind'] == 'video'
    assert vid['ext'] == '.mp4'
    assert vid['probe']['has_video'] is True
    assert vid['probe']['has_audio'] is True
    assert vid['youtube_draft']['resolution'] == '640x360'
    assert 'Brand New Day' in vid['youtube_draft']['title']


def test_dual_deck_crossfade_and_endpoints(tmp_path: Path, monkeypatch):
    import core.media_center.audio_engine as ae
    import core.media_center.dsp_video as dv
    import frontend.blueprints.media_center as mc_bp
    monkeypatch.setattr(ae, 'MEDIA_STORAGE_ROOT', tmp_path)
    monkeypatch.setattr(dv, 'MEDIA_STORAGE_ROOT', tmp_path)
    monkeypatch.setattr(mc_bp, 'MEDIA_STORAGE_ROOT', tmp_path)

    a = save_media_asset('deck_a.wav', _tone_wav(220.0, 2.0), source='test', storage_root=tmp_path)
    b = save_media_asset('deck_b.wav', _tone_wav(330.0, 2.0), source='test', storage_root=tmp_path)
    mixed = mix_two_decks(a['id'], b['id'], crossfade_sec=0.5, mode='crossfade', storage_root=tmp_path)
    assert mixed['probe']['has_audio'] is True
    assert mixed['probe']['duration_sec'] >= 3.0

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(mc_bp.media_center_bp)
    client = app.test_client()

    r1 = client.post(f"/api/media-center/library/{a['id']}/dsp", json={'low_db': 2.0, 'tempo': 1.05})
    assert r1.status_code == 200 and r1.get_json()['ok'] is True

    r2 = client.post('/api/media-center/decks/mix', json={'deck_a_id': a['id'], 'deck_b_id': b['id'], 'mode': 'mashup'})
    assert r2.status_code == 200 and r2.get_json()['ok'] is True
