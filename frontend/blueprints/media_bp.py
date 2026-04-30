"""Media Center API — consume/produce media with local runners."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory
from utils.db._connection import get_connection

media_bp = Blueprint('media_bp', __name__)

_MEDIA_ROOT = Path(os.environ.get('SWARM_ROOT', Path(__file__).resolve().parents[2]))
_MEDIA_ARTIFACT_DIR = _MEDIA_ROOT / 'artifacts' / 'media_center'
_REMIX_MODES = {'mashup', 'new', 'new_song', 'original'}
_MEDIA_PROMPT_FIELDS = {
    'image': ('image_prompt', 'visual_prompt', 'prompt'),
    'video': ('video_prompt', 'motion_prompt', 'visual_prompt', 'prompt'),
    'audio': ('audio_prompt', 'music_prompt', 'song_prompt', 'prompt'),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'music',
            base_url TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT,
            media_type TEXT NOT NULL DEFAULT 'music',
            provider_id TEXT,
            source_url TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_runs (
            run_id TEXT PRIMARY KEY,
            runner_key TEXT NOT NULL,
            prompt TEXT,
            media_type TEXT NOT NULL,
            output_path TEXT,
            status TEXT NOT NULL,
            log_text TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT
        )
        """
    )


def _seed_defaults(conn) -> None:
    now = _now_iso()
    defaults = [
        ('youtube', 'YouTube', 'video', 'https://www.youtube.com'),
        ('youtube_music', 'YouTube Music', 'music', 'https://music.youtube.com'),
        ('apple_music', 'Apple Music', 'music', 'https://music.apple.com'),
        ('spotify', 'Spotify', 'music', 'https://open.spotify.com'),
        ('soundcloud', 'SoundCloud', 'music', 'https://soundcloud.com'),
        ('bandcamp', 'Bandcamp', 'music', 'https://bandcamp.com'),
        ('rss_custom', 'RSS / Custom', 'mixed', ''),
    ]
    for pid, name, category, base_url in defaults:
        conn.execute(
            """
            INSERT OR IGNORE INTO media_providers (id, name, category, base_url, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (pid, name, category, base_url, now, now),
        )

    # Seed requested test song once.
    existing = conn.execute("SELECT id FROM media_items WHERE title=? LIMIT 1", ('girl in the mirror (feat. IVEY.H)',)).fetchone()
    if not existing:
        item_id = f"media-{uuid.uuid4().hex[:12]}"
        search_url = "https://music.youtube.com/search?q=girl%20in%20the%20mirror%20feat.%20IVEY.H"
        conn.execute(
            """
            INSERT INTO media_items (id, title, artist, media_type, provider_id, source_url, notes, created_at, updated_at)
            VALUES (?, ?, ?, 'music', 'youtube_music', ?, ?, ?, ?)
            """,
            (
                item_id,
                'girl in the mirror (feat. IVEY.H)',
                'Bebe Rexha feat. IVEY.H',
                search_url,
                'Seeded test track for Media Center runner pipeline validation.',
                now,
                now,
            ),
        )


def _seed_knowledge(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name TEXT NOT NULL,
            content TEXT DEFAULT "",
            tags TEXT DEFAULT "all",
            updated_at TEXT
        )
    """)
    doc_name = 'MEDIA_CENTER_BOOTSTRAP.md'
    content = (
        '# Media Center bootstrap\n\n'
        'Media Center now supports both consumption and production workflows.\n\n'
        '## Connected media feed targets\n'
        '- YouTube / YouTube Music\n'
        '- Spotify\n'
        '- Apple Music\n'
        '- SoundCloud\n'
        '- RSS / custom providers\n\n'
        '## Seed test track\n'
        '- girl in the mirror (feat. IVEY.H)\n\n'
        '## Production runners\n'
        '- local_synth_audio_runner: writes a real WAV artifact to artifacts/media_center\n'
        '- local_remix_lab_runner: mixes two song references into a mashup/new-song WAV preview with vocal guide and provider handoff manifest\n'
        '- local_ffmpeg_video_runner: writes a real MP4 artifact when ffmpeg exists\n'
    )
    now = _now_iso()
    row = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
    if row:
        conn.execute(
            "UPDATE project_docs SET content=?, tags=?, updated_at=? WHERE id=?",
            (content, 'media,studio,knowledge', now, row['id']),
        )
    else:
        conn.execute(
            "INSERT INTO project_docs (doc_name, content, tags, updated_at) VALUES (?, ?, ?, ?)",
            (doc_name, content, 'media,studio,knowledge', now),
        )


def _list_state(conn):
    providers = [dict(r) for r in conn.execute(
        "SELECT id, name, category, base_url, enabled, created_at, updated_at FROM media_providers ORDER BY name"
    ).fetchall()]
    items = [dict(r) for r in conn.execute(
        """
        SELECT id, title, artist, media_type, provider_id, source_url, notes, created_at, updated_at
        FROM media_items
        ORDER BY updated_at DESC
        """
    ).fetchall()]
    runs = [dict(r) for r in conn.execute(
        """
        SELECT run_id, runner_key, prompt, media_type, output_path, status, log_text, created_at, finished_at
        FROM media_runs
        ORDER BY created_at DESC
        LIMIT 40
        """
    ).fetchall()]
    return providers, items, runs


def _write_sine_wav(out_path: Path, seconds: float = 4.0, freq: float = 440.0) -> str:
    sr = 44100
    amp = 0.35
    total = int(sr * seconds)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        frames = bytearray()
        for i in range(total):
            val = int(32767 * amp * math.sin(2.0 * math.pi * freq * (i / sr)))
            frames.extend(struct.pack('<h', val))
        wav.writeframes(bytes(frames))
    return f'wrote {out_path.name} ({seconds:.1f}s @ {freq:.1f}Hz)'


def _resolve_media_prompt(body: dict, media_type: str) -> tuple[str, dict]:
    raw_prompt = str(body.get('prompt') or body.get('model_output') or '').strip()
    prompt_info = {
        'used_runtime_json_normalizer': False,
        'shape': 'text',
        'truncated': False,
        'selected_field': 'prompt',
        'raw_chars': len(raw_prompt),
    }
    if not raw_prompt:
        return '', prompt_info

    text = raw_prompt
    stripped = raw_prompt.lstrip()
    if stripped.startswith(('```', '{', '[')):
        try:
            from core.model_runtime_gateway import normalize_model_json
            normalized = normalize_model_json(raw_prompt)
            prompt_info.update({
                'used_runtime_json_normalizer': True,
                'shape': normalized.get('shape') or 'text',
                'truncated': bool(normalized.get('truncated')),
                'normalizer_ok': bool(normalized.get('ok')),
            })
            value = normalized.get('value') if isinstance(normalized, dict) else None
            if isinstance(value, dict):
                fields = _MEDIA_PROMPT_FIELDS.get(media_type, ('prompt',))
                for field in fields:
                    candidate = str(value.get(field) or '').strip()
                    if candidate:
                        text = candidate
                        prompt_info['selected_field'] = field
                        break
        except Exception as exc:
            prompt_info.update({
                'used_runtime_json_normalizer': True,
                'normalizer_ok': False,
                'normalizer_error': str(exc)[:200],
            })
    return text, prompt_info


def _wrap_prompt_lines(prompt: str, width: int = 38, max_lines: int = 6) -> list[str]:
    words = re.findall(r'\S+', str(prompt or ''))
    lines: list[str] = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word[:width]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines] or ['Fridays Studio local render']


def _write_prompt_image(out_path: Path, prompt: str, agent: str = '') -> str:
    from PIL import Image, ImageDraw, ImageFont

    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    seed = _stable_int(prompt, agent, out_path.name)
    base = (
        24 + (seed % 70),
        34 + ((seed >> 8) % 70),
        44 + ((seed >> 16) % 70),
    )
    accent = (
        160 + ((seed >> 24) % 80),
        120 + ((seed >> 32) % 100),
        70 + ((seed >> 40) % 130),
    )
    image = Image.new('RGB', (width, height), base)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        blend = y / max(1, height - 1)
        color = tuple(int(base[i] * (1 - blend) + accent[i] * blend * 0.65) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    for idx in range(9):
        x = int((seed >> (idx * 5)) % width)
        y = int((seed >> (idx * 7 + 3)) % height)
        radius = 70 + int((seed >> (idx * 3 + 11)) % 170)
        outline = tuple(min(255, c + 35) for c in accent)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=outline, width=3)

    try:
        title_font = ImageFont.truetype('DejaVuSans-Bold.ttf', 44)
        body_font = ImageFont.truetype('DejaVuSans.ttf', 30)
        meta_font = ImageFont.truetype('DejaVuSans.ttf', 22)
    except Exception:
        title_font = body_font = meta_font = ImageFont.load_default()

    label = (agent or 'local agent').strip()
    draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=18, fill=(12, 16, 22), outline=(230, 230, 220), width=2)
    draw.text((105, 105), f'{label} · Fridays Studio Image', fill=(245, 245, 238), font=title_font)
    y = 190
    for line in _wrap_prompt_lines(prompt, width=50, max_lines=7):
        draw.text((105, y), line, fill=(220, 226, 232), font=body_font)
        y += 42
    draw.text((105, height - 125), 'local prompt-image runner · provenance kept in Media Center', fill=(170, 178, 188), font=meta_font)
    image.save(out_path, 'PNG')
    return f'wrote {out_path.name} prompt image ({width}x{height})'


def _avi_chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')


def _avi_list(tag: bytes, payload: bytes) -> bytes:
    body = tag + payload
    return b'LIST' + struct.pack('<I', len(body)) + body + (b'\0' if len(body) % 2 else b'')


def _write_prompt_avi(out_path: Path, prompt: str, agent: str = '', seconds: float = 5.0) -> str:
    from PIL import Image, ImageDraw, ImageFont

    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = 640, 360, 8
    total_frames = max(1, int(seconds * fps))
    row_stride = ((width * 3 + 3) // 4) * 4
    frame_size = row_stride * height
    seed = _stable_int(prompt, agent, out_path.name)
    lines = _wrap_prompt_lines(prompt, width=44, max_lines=5)
    try:
        title_font = ImageFont.truetype('DejaVuSans-Bold.ttf', 28)
        body_font = ImageFont.truetype('DejaVuSans.ttf', 18)
    except Exception:
        title_font = body_font = ImageFont.load_default()

    frames: list[bytes] = []
    for frame_idx in range(total_frames):
        t = frame_idx / max(1, total_frames - 1)
        c1 = (20 + int((seed + frame_idx * 7) % 80), 35 + int((seed >> 9) % 70), 55 + int((seed >> 17) % 80))
        c2 = (90 + int(100 * t), 80 + int((seed >> 25) % 120), 150 - int(70 * t))
        image = Image.new('RGB', (width, height), c1)
        draw = ImageDraw.Draw(image)
        for y in range(height):
            blend = y / max(1, height - 1)
            color = tuple(int(c1[i] * (1 - blend) + c2[i] * blend) for i in range(3))
            draw.line([(0, y), (width, y)], fill=color)
        x = int(80 + t * (width - 180))
        draw.rounded_rectangle((x - 45, 46, x + 45, 136), radius=20, fill=(245, 226, 140), outline=(255, 255, 255), width=2)
        draw.rounded_rectangle((38, 178, width - 38, height - 32), radius=12, fill=(8, 10, 16), outline=(230, 235, 240), width=1)
        draw.text((42, 30), f'{(agent or "local agent").strip()} · Studio video test', fill=(250, 250, 246), font=title_font)
        y = 200
        for line in lines:
            draw.text((58, y), line, fill=(222, 228, 235), font=body_font)
            y += 26
        raw = image.tobytes('raw', 'BGR')
        padded_rows = []
        pad = b'\0' * (row_stride - width * 3)
        for row in range(height - 1, -1, -1):
            start = row * width * 3
            padded_rows.append(raw[start:start + width * 3] + pad)
        frames.append(b''.join(padded_rows))

    avih = struct.pack(
        '<IIIIIIIIII4I',
        int(1_000_000 / fps), frame_size * fps, 0, 0x10, total_frames, 0, 1,
        frame_size, width, height, 0, 0, 0, 0,
    )
    strh = (
        b'vids' + b'DIB ' +
        struct.pack('<IHHIIIIIIIIhhhh', 0, 0, 0, 0, 1, fps, 0, total_frames, frame_size, 0xFFFFFFFF, 0, 0, 0, width, height)
    )
    strf = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, frame_size, 0, 0, 0, 0)
    hdrl = _avi_list(b'hdrl', _avi_chunk(b'avih', avih) + _avi_list(b'strl', _avi_chunk(b'strh', strh) + _avi_chunk(b'strf', strf)))

    movi_payload = bytearray()
    index_entries = []
    for frame in frames:
        offset = 4 + len(movi_payload)
        chunk = _avi_chunk(b'00db', frame)
        movi_payload.extend(chunk)
        index_entries.append(struct.pack('<4sIII', b'00db', 0x10, offset, len(frame)))
    movi = _avi_list(b'movi', bytes(movi_payload))
    idx1 = _avi_chunk(b'idx1', b''.join(index_entries))
    riff_body = b'AVI ' + hdrl + movi + idx1
    out_path.write_bytes(b'RIFF' + struct.pack('<I', len(riff_body)) + riff_body)
    return f'wrote {out_path.name} pure-python AVI fallback ({seconds:.1f}s @ {fps}fps)'


def _clean_text(value, limit: int = 2000) -> str:
    text = str(value or '').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text[:limit].strip()


def _song_label(value, fallback: str = '') -> str:
    if isinstance(value, dict):
        title = _clean_text(value.get('title') or value.get('name') or '', 180)
        artist = _clean_text(value.get('artist') or '', 120)
        label = f'{title} - {artist}' if title and artist else title or artist
    else:
        label = _clean_text(value, 220)
    return label or fallback


def _normalise_remix_mode(value) -> str:
    mode = _clean_text(value or 'mashup', 32).lower().replace('-', '_').replace(' ', '_')
    if mode not in _REMIX_MODES:
        return 'mashup'
    return 'new_song' if mode in {'new', 'original'} else mode


def _stable_int(*parts) -> int:
    seed = '||'.join(str(part or '') for part in parts).encode('utf-8', errors='ignore')
    return int(hashlib.sha256(seed).hexdigest()[:12], 16)


def _song_signature(label: str) -> dict:
    roots = [174.61, 196.00, 207.65, 220.00, 246.94, 261.63, 293.66, 329.63]
    seed = _stable_int(label)
    return {
        'seed': seed,
        'root_hz': roots[seed % len(roots)],
        'tempo_bpm': 86 + (seed % 58),
        'brightness': 0.55 + ((seed // 11) % 35) / 100.0,
    }


def _scale_freq(root_hz: float, degree: int, minor: bool = False, octave: int = 0) -> float:
    scale = [0, 2, 3, 5, 7, 8, 10, 12] if minor else [0, 2, 4, 5, 7, 9, 11, 12]
    semitone = scale[degree % len(scale)] + (12 * octave)
    return root_hz * (2.0 ** (semitone / 12.0))


def _lyric_lines_from_inputs(song_a: str, song_b: str, poem: str, suggestions: str) -> list[str]:
    source = _clean_text(poem or suggestions, 1800)
    lines = [_clean_text(line, 110) for line in source.split('\n') if _clean_text(line, 110)]
    if len(lines) < 3 and source:
        words = re.findall(r"[^\s]+", source)
        chunks = [' '.join(words[i:i + 7]) for i in range(0, min(len(words), 56), 7)]
        if len(chunks) > len(lines):
            lines = [_clean_text(chunk, 110) for chunk in chunks if chunk]

    if suggestions and len(lines) < 5:
        for piece in re.split(r'[.;\n]+', suggestions):
            cleaned = _clean_text(piece, 100)
            if cleaned and cleaned not in lines:
                lines.append(cleaned)
            if len(lines) >= 5:
                break

    fallback = [
        f'{song_a} opens the door',
        f'{song_b} answers in light',
        'two signals bend into one chorus',
        'and the new hook wakes up tonight',
    ]
    for line in fallback:
        if len(lines) >= 4:
            break
        lines.append(line)
    return lines[:8]


def _remix_manifest(
    song_a: str,
    song_b: str,
    mode: str,
    lyric_lines: list[str],
    lyric_source: str,
    suggestions: str,
    vocal_style: str,
    render: dict,
) -> dict:
    section_names = ['intro blend', 'first lift', 'hook collision', 'outro resolve']
    section_len = round(float(render['duration_sec']) / len(section_names), 2)
    return {
        'schema': 'fridays.media.remix.v1',
        'created_at': _now_iso(),
        'mode': mode,
        'inputs': {
            'song_a': song_a,
            'song_b': song_b,
            'suggestions': suggestions,
            'vocal_style': vocal_style,
        },
        'lyrics': {
            'source': lyric_source,
            'lines': lyric_lines,
            'full_text': '\n'.join(lyric_lines),
        },
        'arrangement': [
            {
                'name': name,
                'start_sec': round(idx * section_len, 2),
                'duration_sec': section_len,
                'intent': (
                    'alternate recognizable motifs from both references'
                    if mode == 'mashup'
                    else 'use both references as DNA for a new progression'
                ),
            }
            for idx, name in enumerate(section_names)
        ],
        'render': render,
        'provider_handoff': [
            {'role': 'stem_separation', 'status': 'ready_for_adapter', 'input': 'song_a/song_b source files or licensed URLs'},
            {'role': 'music_generation', 'status': 'ready_for_adapter', 'input': 'arrangement plus style suggestions'},
            {'role': 'vocal_generation', 'status': 'ready_for_adapter', 'input': 'lyrics plus vocal_style'},
            {'role': 'mix_master', 'status': 'ready_for_adapter', 'input': 'generated stems and vocal take'},
        ],
    }


def _read_uploaded_wav_samples(storage, target_sr: int, max_seconds: float):
    if not storage or not getattr(storage, 'filename', ''):
        return None, ''
    filename = storage.filename or 'uploaded-audio'
    if not filename.lower().endswith('.wav'):
        return None, f'{filename}: kept as provider reference (local preview currently layers WAV uploads)'

    try:
        storage.stream.seek(0)
        with wave.open(storage.stream, 'rb') as wav:
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            source_sr = wav.getframerate()
            frame_limit = min(wav.getnframes(), int(source_sr * max_seconds))
            raw = wav.readframes(frame_limit)
    except Exception as exc:
        return None, f'{filename}: could not read WAV source ({exc})'

    if channels < 1 or sampwidth not in (1, 2, 4):
        return None, f'{filename}: unsupported WAV layout'

    frame_size = channels * sampwidth
    source = []
    for pos in range(0, len(raw) - frame_size + 1, frame_size):
        total = 0.0
        for ch in range(channels):
            start = pos + ch * sampwidth
            sample = raw[start:start + sampwidth]
            if sampwidth == 1:
                total += (sample[0] - 128) / 128.0
            elif sampwidth == 2:
                total += struct.unpack('<h', sample)[0] / 32768.0
            else:
                total += struct.unpack('<i', sample)[0] / 2147483648.0
        source.append(total / channels)

    if not source:
        return None, f'{filename}: empty WAV source'

    target_len = min(int(max_seconds * target_sr), int(len(source) * target_sr / max(1, source_sr)))
    resampled = [source[min(len(source) - 1, int(idx * source_sr / target_sr))] for idx in range(target_len)]
    return resampled, f'{filename}: layered {len(resampled) / target_sr:.1f}s WAV source'


def _write_remix_wav(
    out_path: Path,
    song_a: str,
    song_b: str,
    mode: str,
    lyric_lines: list[str],
    suggestions: str,
    vocal_style: str,
    duration_sec: float = 14.0,
    source_a: list[float] | None = None,
    source_b: list[float] | None = None,
) -> dict:
    sig_a = _song_signature(song_a)
    sig_b = _song_signature(song_b)
    sr = 22050
    seconds = max(4.0, min(float(duration_sec or 14.0), 45.0))
    total = int(sr * seconds)
    tempo = round((sig_a['tempo_bpm'] + sig_b['tempo_bpm']) / 2)
    beat = 60.0 / max(60, tempo)
    minor = 'dark' in suggestions.lower() or 'minor' in suggestions.lower()
    new_song = mode == 'new_song'
    root_a = sig_a['root_hz']
    root_b = sig_b['root_hz']
    root_new = math.sqrt(root_a * root_b)
    lyric_words = re.findall(r"[A-Za-z0-9']+", ' '.join(lyric_lines)) or ['ah']
    word_span = max(0.24, min(0.55, (seconds - 1.2) / max(1, len(lyric_words))))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for i in range(total):
        t = i / sr
        fade = min(1.0, t / 0.45, max(0.0, (seconds - t) / 0.75))
        bar = int(t / max(beat * 4.0, 0.01))
        step = int(t / max(beat / 2.0, 0.01))
        pulse = 1.0 if (t % beat) < beat * 0.54 else 0.32
        kick_pos = t % beat
        kick_env = max(0.0, 1.0 - kick_pos / 0.09) if kick_pos < 0.09 else 0.0
        chord = [0, 4, 5, 3, 6, 2][bar % 6]
        melody_degree = [0, 2, 4, 7, 5, 4, 2, 1][step % 8]

        freq_a = _scale_freq(root_a, chord, minor=minor, octave=0)
        freq_b = _scale_freq(root_b, chord + 2, minor=minor, octave=0)
        lead_root = root_new if new_song else root_b
        lead = _scale_freq(lead_root, melody_degree + (bar % 3), minor=minor, octave=1)
        bass_root = root_new if new_song else root_a
        bass = math.sin(2.0 * math.pi * (bass_root / 2.0) * t) * pulse * 0.25
        pad_a = math.sin(2.0 * math.pi * freq_a * t) * 0.18
        pad_b = math.sin(2.0 * math.pi * freq_b * t + 0.35) * 0.18
        lead_tone = math.sin(2.0 * math.pi * lead * t) * (0.18 + 0.08 * math.sin(2.0 * math.pi * 0.25 * t))
        kick = math.sin(2.0 * math.pi * (48.0 + 42.0 * kick_env) * t) * kick_env * 0.34
        src_a = source_a[i % len(source_a)] * 0.34 if source_a else 0.0
        src_b = source_b[i % len(source_b)] * 0.34 if source_b else 0.0

        vocal = 0.0
        word_idx = int((t - 0.65) / word_span)
        if 0 <= word_idx < len(lyric_words):
            pos = ((t - 0.65) / word_span) - word_idx
            if 0.05 <= pos <= 0.88:
                word_seed = _stable_int(lyric_words[word_idx], vocal_style, song_a, song_b)
                note = _scale_freq(root_new, word_seed % 8, minor=minor, octave=1)
                env = math.sin(math.pi * min(1.0, max(0.0, (pos - 0.05) / 0.83)))
                vibrato = 1.0 + 0.007 * math.sin(2.0 * math.pi * (5.0 + (word_seed % 3)) * t)
                vocal = env * (
                    math.sin(2.0 * math.pi * note * vibrato * t) * 0.20
                    + math.sin(2.0 * math.pi * note * 2.0 * t) * 0.05
                )

        if new_song:
            left = (bass + (pad_a + pad_b) * 0.72 + lead_tone * 0.55 + kick + vocal * 0.8 + src_a * 0.38 + src_b * 0.18) * fade
            right = (bass * 0.9 + (pad_b + pad_a * 0.5) + lead_tone * 0.75 + kick + vocal + src_b * 0.38 + src_a * 0.18) * fade
        else:
            cross = 0.5 + 0.5 * math.sin(2.0 * math.pi * t / max(seconds / 2.0, 1.0))
            left = (bass + pad_a * (1.1 - cross * 0.35) + lead_tone * 0.35 + kick + vocal * 0.72 + src_a * (0.55 - cross * 0.12)) * fade
            right = (bass * 0.85 + pad_b * (0.75 + cross * 0.35) + lead_tone * 0.85 + kick + vocal + src_b * (0.45 + cross * 0.12)) * fade

        left_i = int(max(-1.0, min(1.0, left)) * 30000)
        right_i = int(max(-1.0, min(1.0, right)) * 30000)
        frames.extend(struct.pack('<hh', left_i, right_i))

    with wave.open(str(out_path), 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(bytes(frames))

    return {
        'sample_rate': sr,
        'duration_sec': round(seconds, 2),
        'tempo_bpm': tempo,
        'mode': mode,
        'channels': 2,
        'log': f'wrote {out_path.name} ({seconds:.1f}s remix preview with vocal guide)',
    }


def _run_ffmpeg_video(out_path: Path, prompt: str = '', agent: str = '') -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which('ffmpeg'):
        fallback = out_path.with_suffix('.avi')
        return _write_prompt_avi(fallback, prompt, agent=agent)
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', 'testsrc=size=1280x720:rate=30',
        '-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=44100',
        '-t', '5',
        '-pix_fmt', 'yuv420p',
        '-c:v', 'libx264', '-c:a', 'aac',
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or 'ffmpeg failed')[:1000])
    return f'wrote {out_path.name} via ffmpeg testsrc+sine'


@media_bp.route('/api/media/state', methods=['GET'])
def api_media_state():
    conn = get_connection()
    _ensure_schema(conn)
    _seed_defaults(conn)
    _seed_knowledge(conn)
    conn.commit()
    providers, items, runs = _list_state(conn)
    conn.close()
    return jsonify({'ok': True, 'providers': providers, 'items': items, 'runs': runs})


@media_bp.route('/api/media/providers', methods=['POST'])
def api_media_add_provider():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'}), 400
    pid = str(body.get('id') or f"provider-{uuid.uuid4().hex[:10]}").strip().lower().replace(' ', '_')
    category = str(body.get('category') or 'music').strip().lower()
    base_url = str(body.get('base_url') or '').strip()

    conn = get_connection()
    _ensure_schema(conn)
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO media_providers (id, name, category, base_url, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          category=excluded.category,
          base_url=excluded.base_url,
          updated_at=excluded.updated_at
        """,
        (pid, name, category, base_url, now, now),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'provider_id': pid})


@media_bp.route('/api/media/items', methods=['POST'])
def api_media_add_item():
    body = request.get_json(silent=True) or {}
    title = str(body.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    mid = f"media-{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    conn = get_connection()
    _ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO media_items (id, title, artist, media_type, provider_id, source_url, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            title,
            str(body.get('artist') or '').strip(),
            str(body.get('media_type') or 'music').strip().lower(),
            str(body.get('provider_id') or '').strip(),
            str(body.get('source_url') or '').strip(),
            str(body.get('notes') or '').strip(),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'item_id': mid})


@media_bp.route('/api/media/seed-song', methods=['POST'])
def api_media_seed_song():
    conn = get_connection()
    _ensure_schema(conn)
    _seed_defaults(conn)
    conn.commit()
    conn.close()
    return jsonify({'ok': True})




@media_bp.route('/api/media/screenshot', methods=['POST'])
def api_media_screenshot():
    body = request.get_json(silent=True) or {}
    data_url = str(body.get('data_url') or '').strip()
    label = str(body.get('label') or 'fridays_capture').strip()
    if not data_url.startswith('data:image/') or ',' not in data_url:
        return jsonify({'ok': False, 'error': 'data_url (image data URI) required'}), 400

    header, b64 = data_url.split(',', 1)
    ext = 'png'
    if 'image/jpeg' in header:
        ext = 'jpg'
    elif 'image/webp' in header:
        ext = 'webp'

    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return jsonify({'ok': False, 'error': 'invalid base64 payload'}), 400

    safe_label = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in label)[:48] or 'capture'
    stamp = int(time.time())
    out_path = _MEDIA_ARTIFACT_DIR / 'screenshots' / f'{stamp}_{safe_label}.{ext}'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)

    conn = get_connection()
    _ensure_schema(conn)
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO media_runs (run_id, runner_key, prompt, media_type, output_path, status, log_text, created_at, finished_at) VALUES (?, 'fridays_screenshot_capture', ?, 'image', ?, 'completed', ?, ?, ?)",
        (run_id, label, str(out_path.relative_to(_MEDIA_ROOT)), f'saved screenshot ({len(raw)} bytes)', _now_iso(), _now_iso()),
    )
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'run_id': run_id, 'output_path': str(out_path.relative_to(_MEDIA_ROOT))})


@media_bp.route('/api/media/artifacts/<path:artifact_path>', methods=['GET'])
def api_media_artifact(artifact_path: str):
    root = _MEDIA_ARTIFACT_DIR.resolve()
    candidate = (_MEDIA_ARTIFACT_DIR / artifact_path.strip().lstrip('/\\')).resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return jsonify({'ok': False, 'error': 'artifact not found'}), 404
    if not candidate.is_file():
        return jsonify({'ok': False, 'error': 'artifact not found'}), 404
    return send_from_directory(str(root), str(relative), as_attachment=False)


@media_bp.route('/api/media/remix', methods=['POST'])
@media_bp.route('/api/media/mix-songs', methods=['POST'])
def api_media_remix():
    body = request.form.to_dict() if request.files else (request.get_json(silent=True) or {})
    file_a = request.files.get('song_a_file') or request.files.get('file_a')
    file_b = request.files.get('song_b_file') or request.files.get('file_b')
    song_a = _song_label(body.get('song_a') or body.get('song_a_title') or (file_a.filename if file_a else ''))
    song_b = _song_label(body.get('song_b') or body.get('song_b_title') or (file_b.filename if file_b else ''))
    if not song_a or not song_b:
        return jsonify({'ok': False, 'error': 'song_a and song_b are required'}), 400

    mode = _normalise_remix_mode(body.get('mode'))
    poem = _clean_text(body.get('poem') or body.get('lyrics') or '', 1800)
    suggestions = _clean_text(body.get('suggestions') or body.get('prompt') or '', 1800)
    vocal_style = _clean_text(body.get('vocal_style') or 'clear guide vocal', 180)
    try:
        duration_sec = float(body.get('duration_sec') or 14.0)
    except (TypeError, ValueError):
        duration_sec = 14.0
    if not math.isfinite(duration_sec):
        duration_sec = 14.0
    lyric_lines = _lyric_lines_from_inputs(song_a, song_b, poem, suggestions)
    lyric_source = 'poem' if poem else ('suggestions' if suggestions else 'generated')
    source_a, source_a_note = _read_uploaded_wav_samples(file_a, 22050, max(4.0, min(duration_sec, 45.0)))
    source_b, source_b_note = _read_uploaded_wav_samples(file_b, 22050, max(4.0, min(duration_sec, 45.0)))
    source_notes = [note for note in (source_a_note, source_b_note) if note]
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    created_at = _now_iso()
    prompt = json.dumps(
        {
            'song_a': song_a,
            'song_b': song_b,
            'mode': mode,
            'poem': poem,
            'suggestions': suggestions,
            'vocal_style': vocal_style,
        },
        ensure_ascii=True,
    )[:4000]

    conn = get_connection()
    _ensure_schema(conn)
    conn.execute(
        "INSERT INTO media_runs (run_id, runner_key, prompt, media_type, output_path, status, log_text, created_at, finished_at) VALUES (?, 'local_remix_lab_runner', ?, 'audio', '', 'running', '', ?, NULL)",
        (run_id, prompt, created_at),
    )
    conn.commit()

    try:
        _MEDIA_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}_remix.wav'
        render = _write_remix_wav(
            out_path,
            song_a=song_a,
            song_b=song_b,
            mode=mode,
            lyric_lines=lyric_lines,
            suggestions=suggestions,
            vocal_style=vocal_style,
            duration_sec=duration_sec,
            source_a=source_a,
            source_b=source_b,
        )
        if source_notes:
            render['source_layers'] = source_notes
        manifest = _remix_manifest(song_a, song_b, mode, lyric_lines, lyric_source, suggestions, vocal_style, render)
        manifest_path = out_path.with_suffix('.json')
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
        output_rel = str(out_path.relative_to(_MEDIA_ROOT))
        manifest_rel = str(manifest_path.relative_to(_MEDIA_ROOT))
        log_text = f"{render['log']}; wrote {manifest_path.name}"
        conn.execute(
            "UPDATE media_runs SET status='completed', output_path=?, log_text=?, finished_at=? WHERE run_id=?",
            (output_rel, log_text, _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({
            'ok': True,
            'run_id': run_id,
            'mode': mode,
            'output_path': output_rel,
            'manifest_path': manifest_rel,
            'artifact_url': f"/api/media/artifacts/{out_path.name}",
            'manifest_url': f"/api/media/artifacts/{manifest_path.name}",
            'lyrics': lyric_lines,
            'render': render,
            'source_layers': source_notes,
            'provider_handoff': manifest['provider_handoff'],
            'log': log_text,
        })
    except Exception as exc:
        conn.execute(
            "UPDATE media_runs SET status='failed', log_text=?, finished_at=? WHERE run_id=?",
            (str(exc), _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'run_id': run_id, 'error': str(exc)}), 500


@media_bp.route('/api/media/produce', methods=['POST'])
def api_media_produce():
    body = request.get_json(silent=True) or {}
    runner_key = str(body.get('runner_key') or 'local_synth_audio_runner').strip()
    source_agent = str(body.get('source_agent') or body.get('agent') or '').strip()
    default_media_type = 'image' if 'image' in runner_key else ('video' if 'video' in runner_key else 'audio')
    media_type = str(body.get('media_type') or default_media_type).strip().lower()
    prompt, prompt_info = _resolve_media_prompt(body, media_type)

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    created_at = _now_iso()
    conn = get_connection()
    _ensure_schema(conn)
    conn.execute(
        "INSERT INTO media_runs (run_id, runner_key, prompt, media_type, output_path, status, log_text, created_at, finished_at) VALUES (?, ?, ?, ?, '', 'running', '', ?, NULL)",
        (run_id, runner_key, prompt, media_type, created_at),
    )
    conn.commit()

    try:
        _MEDIA_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        if runner_key == 'local_prompt_image_runner':
            out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}.png'
            log_text = _write_prompt_image(out_path, prompt, agent=source_agent)
        elif runner_key == 'local_ffmpeg_video_runner':
            out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}.mp4'
            log_text = _run_ffmpeg_video(out_path, prompt, agent=source_agent)
            if 'pure-python AVI fallback' in log_text:
                out_path = out_path.with_suffix('.avi')
        else:
            out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}.wav'
            log_text = _write_sine_wav(out_path, seconds=6.0, freq=392.0)

        conn.execute(
            "UPDATE media_runs SET status='completed', output_path=?, log_text=?, finished_at=? WHERE run_id=?",
            (str(out_path.relative_to(_MEDIA_ROOT)), log_text, _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({
            'ok': True,
            'run_id': run_id,
            'output_path': str(out_path.relative_to(_MEDIA_ROOT)),
            'log': log_text,
            'prompt_info': prompt_info,
        })
    except Exception as exc:
        conn.execute(
            "UPDATE media_runs SET status='failed', log_text=?, finished_at=? WHERE run_id=?",
            (str(exc), _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'run_id': run_id, 'error': str(exc)}), 500
