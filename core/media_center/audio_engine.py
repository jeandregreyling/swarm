"""Real FFmpeg/FFprobe + NumPy audio/video analysis & library engine for Media Center.

Provides Serato-style RGB frequency-band waveform extraction, BPM estimation,
loudness metering, auto cue-point detection, and safe asset storage under
MEDIA_STORAGE_ROOT/artifacts/media_center/library.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from core.media_center.storage import MEDIA_STORAGE_ROOT

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.opus', '.aiff'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.mkv'}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def media_library_dir(storage_root: Path | None = None) -> Path:
    root = Path(storage_root).expanduser().resolve() if storage_root else MEDIA_STORAGE_ROOT
    d = root / 'artifacts' / 'media_center' / 'library'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(storage_root: Path | None = None) -> Path:
    return media_library_dir(storage_root) / 'library_index.json'


def _load_index(storage_root: Path | None = None) -> list[dict[str, Any]]:
    p = _index_path(storage_root)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_index(items: list[dict[str, Any]], storage_root: Path | None = None) -> None:
    p = _index_path(storage_root)
    p.write_text(json.dumps(items, indent=2), encoding='utf-8')


def is_media_filename(filename: str, content_type: str = '') -> bool:
    ext = Path(str(filename or '')).suffix.lower()
    if ext in MEDIA_EXTENSIONS:
        return True
    ct = str(content_type or '').lower()
    return ct.startswith('audio/') or ct.startswith('video/')


def probe_media(path: Path) -> dict[str, Any]:
    """Run ffprobe on a local audio/video file and return clean metadata."""
    p = Path(path)
    info: dict[str, Any] = {
        'duration_sec': 0.0,
        'sample_rate': 0,
        'channels': 0,
        'codec': '',
        'bit_rate': 0,
        'format_name': p.suffix.lstrip('.').lower(),
        'size_bytes': p.stat().st_size if p.exists() else 0,
        'has_audio': False,
        'has_video': False,
        'title': p.stem,
        'artist': '',
    }
    ffprobe = shutil.which('ffprobe')
    if not ffprobe or not p.exists():
        return info
    try:
        res = subprocess.run(
            [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(p)],
            capture_output=True, text=True, timeout=20,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return info
        raw = json.loads(res.stdout)
        fmt = raw.get('format') or {}
        tags = {str(k).lower(): str(v) for k, v in (fmt.get('tags') or {}).items()}
        info['duration_sec'] = round(float(fmt.get('duration') or 0.0), 3)
        info['bit_rate'] = int(fmt.get('bit_rate') or 0)
        info['format_name'] = str(fmt.get('format_name') or info['format_name'])
        if tags.get('title'):
            info['title'] = tags['title']
        if tags.get('artist'):
            info['artist'] = tags['artist']
        for st in raw.get('streams') or []:
            ctype = st.get('codec_type')
            if ctype == 'audio' and not info['has_audio']:
                info['has_audio'] = True
                info['sample_rate'] = int(st.get('sample_rate') or 0)
                info['channels'] = int(st.get('channels') or 0)
                info['codec'] = str(st.get('codec_name') or '')
                if not info['duration_sec'] and st.get('duration'):
                    info['duration_sec'] = round(float(st['duration']), 3)
            elif ctype == 'video':
                info['has_video'] = True
    except Exception:
        pass
    return info


def _estimate_bpm(samples: np.ndarray, sr: int) -> tuple[float, float]:
    """Autocorrelation onset-envelope BPM estimator (musical range 70..180 BPM)."""
    if samples.size < sr * 2:
        return 120.0, 0.0
    hop = 512
    n_frames = samples.size // hop
    if n_frames < 16:
        return 120.0, 0.0
    framed = samples[: n_frames * hop].reshape(n_frames, hop)
    energy = np.sqrt(np.mean(framed * framed, axis=1) + 1e-12)
    onset = np.maximum(0.0, np.diff(energy, prepend=energy[0]))
    onset = onset - np.mean(onset)
    if float(np.std(onset)) < 1e-6:
        return 120.0, 0.0
    fps = sr / float(hop)
    min_lag = max(1, int(round(fps * 60.0 / 180.0)))
    max_lag = min(onset.size // 2, int(round(fps * 60.0 / 70.0)))
    if max_lag <= min_lag:
        return 120.0, 0.0
    corr = np.correlate(onset, onset, mode='full')[onset.size - 1 :]
    if corr[0] <= 0:
        return 120.0, 0.0
    corr = corr / corr[0]
    window = corr[min_lag : max_lag + 1]
    best_idx = int(np.argmax(window))
    best_lag = min_lag + best_idx
    bpm = round(60.0 * fps / float(best_lag), 1)
    conf = round(float(max(0.0, min(1.0, window[best_idx]))), 3)
    return bpm, conf


def analyze_waveform_and_bpm(path: Path, buckets: int = 160) -> dict[str, Any]:
    """Decode audio with ffmpeg into mono 22.05kHz PCM and compute Serato-style RGB waveform, loudness, BPM & cues."""
    p = Path(path)
    buckets = max(32, min(512, int(buckets)))
    empty = {
        'peaks': [0.0] * buckets,
        'low_peaks': [0.0] * buckets,
        'mid_peaks': [0.0] * buckets,
        'high_peaks': [0.0] * buckets,
        'rms_db': -60.0,
        'peak_db': -60.0,
        'bpm': 120.0,
        'bpm_confidence': 0.0,
        'cue_points': [],
    }
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not p.exists():
        return empty
    sr = 22050
    try:
        proc = subprocess.run(
            [ffmpeg, '-v', 'error', '-i', str(p), '-ac', '1', '-ar', str(sr), '-f', 'f32le', 'pipe:1'],
            capture_output=True, timeout=45,
        )
        if proc.returncode != 0 or not proc.stdout:
            return empty
        samples = np.frombuffer(proc.stdout, dtype=np.float32)
        if samples.size == 0:
            return empty
    except Exception:
        return empty

    duration = samples.size / float(sr)
    peak_val = float(np.max(np.abs(samples)))
    rms_val = float(np.sqrt(np.mean(samples * samples)))
    peak_db = round(20.0 * math.log10(max(peak_val, 1e-6)), 2)
    rms_db = round(20.0 * math.log10(max(rms_val, 1e-6)), 2)

    edges = np.linspace(0, samples.size, buckets + 1, dtype=int)
    peaks, lows, mids, highs = [], [], [], []
    for i in range(buckets):
        seg = samples[edges[i] : edges[i + 1]]
        if seg.size == 0:
            peaks.append(0.0); lows.append(0.0); mids.append(0.0); highs.append(0.0)
            continue
        peaks.append(float(np.max(np.abs(seg))))
        n_fft = min(seg.size, 1024)
        spec = np.abs(np.fft.rfft(seg[:n_fft] * np.hanning(n_fft)))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
        low_e = float(np.mean(spec[(freqs >= 20) & (freqs < 250)])) if np.any((freqs >= 20) & (freqs < 250)) else 0.0
        mid_e = float(np.mean(spec[(freqs >= 250) & (freqs < 2500)])) if np.any((freqs >= 250) & (freqs < 2500)) else 0.0
        high_e = float(np.mean(spec[freqs >= 2500])) if np.any(freqs >= 2500) else 0.0
        lows.append(low_e); mids.append(mid_e); highs.append(high_e)

    def _norm(arr: list[float]) -> list[float]:
        mx = max(arr) if arr else 0.0
        if mx <= 1e-9:
            return [0.0 for _ in arr]
        return [round(v / mx, 4) for v in arr]

    norm_peaks = _norm(peaks)
    norm_lows = _norm(lows)
    norm_mids = _norm(mids)
    norm_highs = _norm(highs)
    bpm, bpm_conf = _estimate_bpm(samples, sr)

    # Auto cue points: Intro (first audible), Drop (loudest peak), Mid/Breakdown, Outro
    intro_idx = next((i for i, v in enumerate(norm_peaks) if v >= 0.12), 0)
    drop_idx = int(np.argmax(norm_peaks)) if norm_peaks else 0
    outro_idx = next((i for i in range(buckets - 1, -1, -1) if norm_peaks[i] >= 0.12), buckets - 1)
    cues = [
        {'label': 'Intro', 'color': '#38bdf8', 'time_sec': round((intro_idx / buckets) * duration, 2)},
        {'label': 'Peak / Drop', 'color': '#f97316', 'time_sec': round((drop_idx / buckets) * duration, 2)},
        {'label': 'Midpoint', 'color': '#10e8a4', 'time_sec': round(duration * 0.5, 2)},
        {'label': 'Outro', 'color': '#c084fc', 'time_sec': round((outro_idx / buckets) * duration, 2)},
    ]

    return {
        'peaks': norm_peaks,
        'low_peaks': norm_lows,
        'mid_peaks': norm_mids,
        'high_peaks': norm_highs,
        'rms_db': rms_db,
        'peak_db': peak_db,
        'bpm': bpm,
        'bpm_confidence': bpm_conf,
        'cue_points': cues,
    }


def _safe_filename(name: str) -> str:
    base = Path(str(name or 'track.wav')).name
    clean = re.sub(r'[^A-Za-z0-9._-]+', '_', base).strip('._')
    return clean or 'track.wav'


def save_media_asset(
    filename: str,
    data: bytes,
    source: str = 'upload',
    metadata: dict[str, Any] | None = None,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Persist an audio/video file into Media Center library, probe & analyze it, and index it."""
    root = Path(storage_root).expanduser().resolve() if storage_root else MEDIA_STORAGE_ROOT
    lib_dir = media_library_dir(root)
    digest = hashlib.sha256(data).hexdigest()[:12]
    safe = _safe_filename(filename)
    asset_id = f'asset-{digest}'
    file_path = lib_dir / f'{digest}-{safe}'
    file_path.write_bytes(data)

    probe = probe_media(file_path)
    analysis = analyze_waveform_and_bpm(file_path) if probe.get('has_audio') or Path(safe).suffix.lower() in AUDIO_EXTENSIONS else {}
    rel_path = file_path.relative_to(root).as_posix()
    meta = dict(metadata or {})
    record = {
        'id': asset_id,
        'filename': safe,
        'title': str(meta.get('title') or probe.get('title') or Path(safe).stem),
        'artist': str(meta.get('artist') or probe.get('artist') or ''),
        'source': source,
        'path': rel_path,
        'url': f'/api/media-center/artifacts/{rel_path}',
        'ext': Path(safe).suffix.lower(),
        'kind': 'video' if Path(safe).suffix.lower() in VIDEO_EXTENSIONS else 'audio',
        'probe': probe,
        'analysis': analysis,
        'created_at': _now_iso(),
    }
    sidecar = lib_dir / f'{asset_id}.analysis.json'
    sidecar.write_text(json.dumps(record, indent=2), encoding='utf-8')

    items = [it for it in _load_index(root) if it.get('id') != asset_id]
    summary = {k: v for k, v in record.items() if k != 'analysis'}
    summary['bpm'] = analysis.get('bpm', 120.0)
    summary['rms_db'] = analysis.get('rms_db', -60.0)
    summary['cue_count'] = len(analysis.get('cue_points') or [])
    items.insert(0, summary)
    _save_index(items, root)
    return record


def list_media_assets(storage_root: Path | None = None) -> list[dict[str, Any]]:
    return _load_index(storage_root)


def get_media_asset(asset_id: str, storage_root: Path | None = None) -> dict[str, Any] | None:
    lib_dir = media_library_dir(storage_root)
    sidecar = lib_dir / f'{asset_id}.analysis.json'
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding='utf-8'))
    except Exception:
        return None
