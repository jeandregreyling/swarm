"""Serato-inspired Audio DSP (3-band EQ, Pitch/Tempo, Chromatic Auto-Tune, Dual-Deck Mix)
and Audio-Reactive YouTube / Shorts MP4 Visualizer Renderer for Media Center.

Uses system ffmpeg/ffprobe + numpy + Pillow so it runs cleanly on any Linux/OptiPlex node.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from core.media_center.audio_engine import (
    get_media_asset,
    media_library_dir,
    probe_media,
    save_media_asset,
)
from core.media_center.storage import MEDIA_STORAGE_ROOT

SCALE_INTERVALS: dict[str, list[int]] = {
    'chromatic': list(range(12)),
    'C_major': [0, 2, 4, 5, 7, 9, 11],
    'A_minor': [0, 2, 4, 5, 7, 9, 11],
    'G_major': [0, 2, 4, 6, 7, 9, 11],
    'D_minor': [0, 2, 3, 5, 7, 9, 10],
    'F_major': [0, 2, 4, 5, 7, 9, 10],
}


def _resolve_asset_file(asset: dict[str, Any], storage_root: Path | None = None) -> Path:
    root = Path(storage_root).expanduser().resolve() if storage_root else MEDIA_STORAGE_ROOT
    return (root / str(asset.get('path') or '')).resolve()


def _atempo_chain(factor: float) -> list[str]:
    """Build valid ffmpeg atempo filter chain (each stage within 0.5..2.0)."""
    f = max(0.25, min(4.0, float(factor)))
    stages: list[str] = []
    while f > 2.0:
        stages.append('atempo=2.0')
        f /= 2.0
    while f < 0.5:
        stages.append('atempo=0.5')
        f /= 0.5
    stages.append(f'atempo={f:.5f}')
    return stages


def _nearest_scale_freq(freq_hz: float, scale: str = 'chromatic') -> float:
    if freq_hz <= 50.0 or freq_hz >= 1400.0:
        return freq_hz
    midi = 69.0 + 12.0 * math.log2(freq_hz / 440.0)
    allowed = SCALE_INTERVALS.get(scale, SCALE_INTERVALS['chromatic'])
    base_oct = int(math.floor(midi / 12.0))
    candidates = []
    for oct_shift in (base_oct - 1, base_oct, base_oct + 1):
        for semi in allowed:
            candidates.append(oct_shift * 12 + semi)
    best_midi = min(candidates, key=lambda m: abs(m - midi))
    return 440.0 * (2.0 ** ((best_midi - 69.0) / 12.0))


def _autotune_pcm(samples: np.ndarray, sr: int, strength: float = 0.65, scale: str = 'chromatic') -> np.ndarray:
    """Frame-wise autocorrelation pitch tracker + smooth overlap-add nearest-note pitch snap."""
    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0.01 or samples.size < 2048:
        return samples
    frame_len = 2048
    hop = frame_len // 2
    window = np.hanning(frame_len).astype(np.float32)
    out = np.zeros_like(samples, dtype=np.float32)
    norm = np.zeros_like(samples, dtype=np.float32)
    min_lag = max(16, int(sr / 900.0))
    max_lag = min(frame_len // 2 - 1, int(sr / 75.0))

    for start in range(0, samples.size - frame_len + 1, hop):
        frame = samples[start : start + frame_len]
        rms = float(np.sqrt(np.mean(frame * frame) + 1e-12))
        ratio = 1.0
        if rms > 0.015:
            centered = frame - float(np.mean(frame))
            corr = np.correlate(centered, centered, mode='full')[frame_len - 1 :]
            if corr[0] > 1e-9:
                corr = corr / corr[0]
                seg = corr[min_lag : max_lag + 1]
                best_i = int(np.argmax(seg))
                if float(seg[best_i]) > 0.35:
                    f0 = sr / float(min_lag + best_i)
                    target = _nearest_scale_freq(f0, scale)
                    raw_ratio = target / f0
                    ratio = 1.0 + strength * (max(0.85, min(1.18, raw_ratio)) - 1.0)
        if abs(ratio - 1.0) > 0.003:
            idx = np.linspace(0, frame_len - 1, frame_len) * ratio
            idx = np.clip(idx, 0, frame_len - 1)
            shifted = np.interp(idx, np.arange(frame_len), frame).astype(np.float32)
        else:
            shifted = frame
        out[start : start + frame_len] += shifted * window
        norm[start : start + frame_len] += window

    mask = norm > 1e-5
    result = samples.copy()
    result[mask] = out[mask] / norm[mask]
    return np.clip(result, -1.0, 1.0).astype(np.float32)


def process_audio_dsp(
    asset_id: str,
    options: dict[str, Any] | None = None,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Apply real 3-band Serato EQ, pitch shift, tempo, vocal auto-tune, and -14 LUFS loudness norm."""
    asset = get_media_asset(asset_id, storage_root=storage_root)
    if not asset:
        raise FileNotFoundError(f'media asset not found: {asset_id}')
    src_path = _resolve_asset_file(asset, storage_root=storage_root)
    if not src_path.exists():
        raise FileNotFoundError(f'media file missing on disk: {src_path}')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is not installed on this machine')

    opts = dict(options or {})
    low_db = max(-12.0, min(12.0, float(opts.get('low_db', 0.0))))
    mid_db = max(-12.0, min(12.0, float(opts.get('mid_db', 0.0))))
    high_db = max(-12.0, min(12.0, float(opts.get('high_db', 0.0))))
    tempo = max(0.5, min(2.0, float(opts.get('tempo', 1.0))))
    pitch_semi = max(-12.0, min(12.0, float(opts.get('pitch_semitones', 0.0))))
    autotune = max(0.0, min(1.0, float(opts.get('autotune_strength', 0.0))))
    autotune_scale = str(opts.get('autotune_key') or 'chromatic')
    normalize = bool(opts.get('normalize', False))
    out_format = 'mp3' if str(opts.get('format') or 'wav').lower() == 'mp3' else 'wav'

    with tempfile.TemporaryDirectory(prefix='hb_dsp_') as tmp:
        tmp_dir = Path(tmp)
        work_in = src_path
        sr = 44100

        if autotune > 0.01:
            dec = subprocess.run(
                [ffmpeg, '-v', 'error', '-i', str(src_path), '-ac', '1', '-ar', str(sr), '-f', 'f32le', 'pipe:1'],
                capture_output=True, timeout=60,
            )
            if dec.returncode == 0 and dec.stdout:
                pcm = np.frombuffer(dec.stdout, dtype=np.float32).copy()
                tuned = _autotune_pcm(pcm, sr, strength=autotune, scale=autotune_scale)
                tuned_wav = tmp_dir / 'autotuned.wav'
                enc = subprocess.run(
                    [ffmpeg, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', 'pipe:0', str(tuned_wav)],
                    input=tuned.tobytes(), capture_output=True, timeout=60,
                )
                if enc.returncode == 0 and tuned_wav.exists():
                    work_in = tuned_wav

        filters: list[str] = []
        if abs(low_db) > 0.05:
            filters.append(f'bass=g={low_db:.2f}:f=120:w=0.6')
        if abs(mid_db) > 0.05:
            filters.append(f'equalizer=f=1000:width_type=o:w=1.5:g={mid_db:.2f}')
        if abs(high_db) > 0.05:
            filters.append(f'treble=g={high_db:.2f}:f=5000:w=0.6')
        if abs(pitch_semi) > 0.05:
            pitch_factor = 2.0 ** (pitch_semi / 12.0)
            filters.append(f'asetrate={sr * pitch_factor:.2f}')
            filters.append(f'aresample={sr}')
            filters.extend(_atempo_chain(tempo / pitch_factor))
        elif abs(tempo - 1.0) > 0.005:
            filters.extend(_atempo_chain(tempo))
        if normalize:
            filters.append('loudnorm=I=-14:TP=-1.5:LRA=11')

        out_path = tmp_dir / f'processed.{out_format}'
        cmd = [ffmpeg, '-v', 'error', '-y', '-i', str(work_in)]
        if filters:
            cmd.extend(['-af', ','.join(filters)])
        if out_format == 'mp3':
            cmd.extend(['-codec:a', 'libmp3lame', '-b:a', '192k'])
        cmd.append(str(out_path))
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode != 0 or not out_path.exists():
            raise RuntimeError(f'ffmpeg DSP failed: {res.stderr[:300]}')

        suffix = str(opts.get('label') or 'DSP Mix').strip()
        base_stem = Path(asset.get('filename') or 'track.wav').stem
        new_name = f'{base_stem}_{suffix.replace(" ", "_")}.{out_format}'
        saved = save_media_asset(
            new_name,
            out_path.read_bytes(),
            source='dsp_render',
            metadata={
                'title': f"{asset.get('title') or base_stem} ({suffix})",
                'artist': asset.get('artist') or '',
            },
            storage_root=storage_root,
        )
        saved['dsp_options'] = {
            'low_db': low_db, 'mid_db': mid_db, 'high_db': high_db,
            'tempo': tempo, 'pitch_semitones': pitch_semi,
            'autotune_strength': autotune, 'autotune_key': autotune_scale,
            'normalize': normalize, 'source_asset_id': asset_id,
        }
        return saved


def _render_backdrop_png(path: Path, width: int, height: int, title: str, subtitle: str) -> None:
    img = Image.new('RGB', (width, height), (8, 16, 28))
    draw = ImageDraw.Draw(img)
    # Liquid-Glass aurora gradient background
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(8 + 20 * math.sin(t * math.pi))
        g = int(18 + 38 * (1.0 - abs(t - 0.45)))
        b = int(32 + 54 * (1.0 - t * 0.6))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    # Subtle glass card frame
    pad_x, pad_y = int(width * 0.06), int(height * 0.07)
    draw.rectangle([pad_x, pad_y, width - pad_x, height - pad_y], outline=(16, 232, 164), width=2)
    draw.text((pad_x + 24, pad_y + 22), title[:64], fill=(240, 249, 255))
    draw.text((pad_x + 24, pad_y + 48), subtitle[:96], fill=(16, 232, 164))
    draw.text((pad_x + 24, height - pad_y - 34), 'Hummingbird Studio · Liquid-Glass Media Engine', fill=(192, 132, 252))
    img.save(path, format='PNG')


def render_youtube_visualizer(
    asset_id: str,
    options: dict[str, Any] | None = None,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Render an audio-reactive H.264/AAC MP4 visualizer video ready for YouTube 16:9 or Shorts 9:16."""
    asset = get_media_asset(asset_id, storage_root=storage_root)
    if not asset:
        raise FileNotFoundError(f'media asset not found: {asset_id}')
    src_path = _resolve_asset_file(asset, storage_root=storage_root)
    if not src_path.exists():
        raise FileNotFoundError(f'media file missing on disk: {src_path}')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is not installed on this machine')

    opts = dict(options or {})
    aspect = str(opts.get('aspect') or '16:9').strip()
    if aspect == '9:16':
        width, height = int(opts.get('width') or 720), int(opts.get('height') or 1280)
    else:
        width, height = int(opts.get('width') or 1280), int(opts.get('height') or 720)
    wave_h = max(120, int(height * 0.34))
    wave_w = max(320, int(width * 0.84))
    wave_x = (width - wave_w) // 2
    wave_y = int(height * 0.42)
    max_sec = opts.get('max_duration_sec')

    title = str(opts.get('title') or asset.get('title') or 'Hummingbird Session')
    bpm = (asset.get('analysis') or {}).get('bpm', 120.0)
    artist = str(opts.get('artist') or asset.get('artist') or 'Hummingbird Studio')
    subtitle = f'{artist}  |  {bpm} BPM  |  {aspect}'

    with tempfile.TemporaryDirectory(prefix='hb_ytvid_') as tmp:
        tmp_dir = Path(tmp)
        bg_path = tmp_dir / 'backdrop.png'
        _render_backdrop_png(bg_path, width, height, title, subtitle)
        out_mp4 = tmp_dir / 'visualizer.mp4'

        filter_complex = (
            f"[1:a]showwaves=s={wave_w}x{wave_h}:mode=cline:rate=25:colors=0x10e8a4|0x38bdf8[waves];"
            f"[0:v][waves]overlay={wave_x}:{wave_y}:format=auto,format=yuv420p[v]"
        )
        cmd = [
            ffmpeg, '-v', 'error', '-y',
            '-loop', '1', '-i', str(bg_path),
            '-i', str(src_path),
            '-filter_complex', filter_complex,
            '-map', '[v]', '-map', '1:a',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-movflags', '+faststart',
        ]
        if max_sec:
            cmd.extend(['-t', str(max(1.0, float(max_sec)))])
        cmd.append(str(out_mp4))
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0 or not out_mp4.exists():
            raise RuntimeError(f'ffmpeg visualizer render failed: {res.stderr[:300]}')

        base_stem = Path(asset.get('filename') or 'track').stem
        tag = 'Shorts' if aspect == '9:16' else 'YouTube'
        saved = save_media_asset(
            f'{base_stem}_{tag}_Visualizer.mp4',
            out_mp4.read_bytes(),
            source='youtube_visualizer',
            metadata={'title': f'{title} ({tag} Visualizer)', 'artist': artist},
            storage_root=storage_root,
        )
        saved['youtube_draft'] = {
            'title': f'{title} — Official Audio Visualizer ({bpm} BPM)',
            'description': (
                f'Produced and mastered inside Hummingbird Liquid-Glass Media Studio.\n'
                f'Artist: {artist}\nTempo: {bpm} BPM\nFormat: {aspect} ({width}x{height})\n'
            ),
            'tags': ['music', 'visualizer', 'hummingbird', 'electronic', 'remix', f'{int(round(float(bpm)))}bpm'],
            'aspect': aspect,
            'resolution': f'{width}x{height}',
        }
        return saved


def mix_two_decks(
    deck_a_id: str,
    deck_b_id: str,
    crossfade_sec: float = 3.0,
    gain_a_db: float = 0.0,
    gain_b_db: float = 0.0,
    mode: str = 'crossfade',
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Mix Deck A and Deck B via ffmpeg (DJ crossfade transition or layered mashup)."""
    a = get_media_asset(deck_a_id, storage_root=storage_root)
    b = get_media_asset(deck_b_id, storage_root=storage_root)
    if not a or not b:
        raise FileNotFoundError('both deck_a_id and deck_b_id must exist in Media Center library')
    pa = _resolve_asset_file(a, storage_root=storage_root)
    pb = _resolve_asset_file(b, storage_root=storage_root)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is not installed on this machine')

    ga = max(-24.0, min(12.0, float(gain_a_db)))
    gb = max(-24.0, min(12.0, float(gain_b_db)))
    dur_a = float((a.get('probe') or {}).get('duration_sec') or 2.0)
    dur_b = float((b.get('probe') or {}).get('duration_sec') or 2.0)
    xf = max(0.25, min(float(crossfade_sec), max(0.25, min(dur_a, dur_b) * 0.45)))

    with tempfile.TemporaryDirectory(prefix='hb_mix_') as tmp:
        out_wav = Path(tmp) / 'deck_mix.wav'
        if mode == 'mashup':
            fc = f"[0:a]volume={ga:.2f}dB[a0];[1:a]volume={gb:.2f}dB[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=2[out]"
        else:
            fc = f"[0:a]volume={ga:.2f}dB[a0];[1:a]volume={gb:.2f}dB[a1];[a0][a1]acrossfade=d={xf:.2f}:c1=tri:c2=tri[out]"
        cmd = [
            ffmpeg, '-v', 'error', '-y',
            '-i', str(pa), '-i', str(pb),
            '-filter_complex', fc, '-map', '[out]',
            str(out_wav),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0 or not out_wav.exists():
            raise RuntimeError(f'ffmpeg deck mix failed: {res.stderr[:300]}')

        title = f"{a.get('title') or 'Deck A'} x {b.get('title') or 'Deck B'} ({mode})"
        return save_media_asset(
            f'Serato_Mix_{mode}.wav',
            out_wav.read_bytes(),
            source='deck_mix',
            metadata={'title': title, 'artist': 'Hummingbird Dual-Deck'},
            storage_root=storage_root,
        )
