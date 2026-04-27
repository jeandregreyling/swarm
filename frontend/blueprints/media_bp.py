"""Media Center API — consume/produce media with local runners."""
from __future__ import annotations

import base64
import json
import math
import os
import struct
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request
from utils.db._connection import get_connection

media_bp = Blueprint('media_bp', __name__)

_MEDIA_ROOT = Path(os.environ.get('SWARM_ROOT', Path(__file__).resolve().parents[2]))
_MEDIA_ARTIFACT_DIR = _MEDIA_ROOT / 'artifacts' / 'media_center'


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


def _run_ffmpeg_video(out_path: Path) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
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

@media_bp.route('/api/media/produce', methods=['POST'])
def api_media_produce():
    body = request.get_json(silent=True) or {}
    runner_key = str(body.get('runner_key') or 'local_synth_audio_runner').strip()
    prompt = str(body.get('prompt') or '').strip()
    media_type = str(body.get('media_type') or ('video' if 'video' in runner_key else 'audio')).strip().lower()

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
        if runner_key == 'local_ffmpeg_video_runner':
            out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}.mp4'
            log_text = _run_ffmpeg_video(out_path)
        else:
            out_path = _MEDIA_ARTIFACT_DIR / f'{stamp}_{run_id}.wav'
            log_text = _write_sine_wav(out_path, seconds=6.0, freq=392.0)

        conn.execute(
            "UPDATE media_runs SET status='completed', output_path=?, log_text=?, finished_at=? WHERE run_id=?",
            (str(out_path.relative_to(_MEDIA_ROOT)), log_text, _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'run_id': run_id, 'output_path': str(out_path.relative_to(_MEDIA_ROOT)), 'log': log_text})
    except Exception as exc:
        conn.execute(
            "UPDATE media_runs SET status='failed', log_text=?, finished_at=? WHERE run_id=?",
            (str(exc), _now_iso(), run_id),
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'run_id': run_id, 'error': str(exc)}), 500
