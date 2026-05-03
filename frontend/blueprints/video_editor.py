"""Video editor timeline persistence + render-job hand-off.

STEP-MEDIA-CENTER-VIDEO-EDITOR-20260430.

Stores JSON timelines (clips, generated scenes, audio tracks, transitions)
so the Media Center video editor can save/load projects with Studio/KC
traceability. Render execution is delegated to the existing media_jobs
queue (kind='video_graph' / 'ffmpeg').
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from flask import Blueprint, jsonify, request

video_editor_bp = Blueprint('video_editor', __name__)

_DB_PATH = 'swarm_memory.db'
_VALID_TRACK_KINDS = {'video', 'audio', 'caption', 'effect', 'overlay'}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())


def _ensure_tables(c: sqlite3.Connection) -> None:
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS video_timelines (
            timeline_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner TEXT,
            project_id TEXT,
            timeline_json TEXT NOT NULL,
            duration_seconds REAL,
            fps REAL,
            resolution TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        '''
    )
    c.execute(
        '''
        CREATE TABLE IF NOT EXISTS video_render_jobs (
            render_id TEXT PRIMARY KEY,
            timeline_id TEXT NOT NULL,
            media_job_id TEXT,
            status TEXT NOT NULL,
            asset_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (timeline_id) REFERENCES video_timelines(timeline_id)
        )
        '''
    )
    c.commit()


def _validate_timeline(tl: Any) -> tuple[bool, str]:
    if not isinstance(tl, dict):
        return False, 'timeline must be an object'
    tracks = tl.get('tracks')
    if not isinstance(tracks, list):
        return False, 'timeline.tracks must be a list'
    if len(tracks) > 64:
        return False, 'too many tracks (max 64)'
    for t in tracks:
        if not isinstance(t, dict):
            return False, 'each track must be an object'
        if t.get('kind') not in _VALID_TRACK_KINDS:
            return False, f'unknown track kind {t.get("kind")!r}'
        clips = t.get('clips') or []
        if not isinstance(clips, list):
            return False, 'track.clips must be a list'
        if len(clips) > 512:
            return False, 'too many clips on one track (max 512)'
        for c in clips:
            if not isinstance(c, dict):
                return False, 'each clip must be an object'
            for f in ('start', 'end'):
                if not isinstance(c.get(f), (int, float)):
                    return False, f'clip.{f} must be a number'
            if c['end'] < c['start']:
                return False, 'clip.end must be >= clip.start'
    return True, ''


@video_editor_bp.route('/api/media/video/timelines', methods=['POST'])
def create_timeline():
    body = request.get_json(silent=True) or {}
    # Y.53: type-check string + numeric fields before unsafe ops.
    for col in ('name', 'owner', 'project_id', 'resolution', 'notes'):
        v = body.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify(ok=False, error=f'{col} must be a string'), 400
    for col in ('duration_seconds', 'fps'):
        v = body.get(col)
        if v is not None and not isinstance(v, (int, float)):
            return jsonify(ok=False, error=f'{col} must be a number'), 400
        if isinstance(v, (int, float)) and v < 0:
            return jsonify(ok=False, error=f'{col} must be >= 0'), 400
    name = (body.get('name') or '').strip()
    if not name or len(name) > 128:
        return jsonify(ok=False, error='name required (≤128)'), 400
    timeline = body.get('timeline') or {'tracks': []}
    ok, why = _validate_timeline(timeline)
    if not ok:
        return jsonify(ok=False, error=why), 400
    timeline_id = f'VTL-{uuid.uuid4().hex[:12].upper()}'
    now = _now()
    c = _conn()
    try:
        _ensure_tables(c)
        c.execute(
            '''INSERT INTO video_timelines
               (timeline_id, name, owner, project_id, timeline_json,
                duration_seconds, fps, resolution, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (
                timeline_id,
                name,
                (body.get('owner') or '').strip() or None,
                (body.get('project_id') or '').strip() or None,
                json.dumps(timeline),
                float(body['duration_seconds']) if body.get('duration_seconds') is not None else None,
                float(body['fps']) if body.get('fps') is not None else None,
                (body.get('resolution') or '').strip() or None,
                (body.get('notes') or '').strip() or None,
                now,
                now,
            ),
        )
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, timeline_id=timeline_id, created_at=now), 201


@video_editor_bp.route('/api/media/video/timelines', methods=['GET'])
def list_timelines():
    project_id = request.args.get('project_id')
    c = _conn()
    try:
        _ensure_tables(c)
        if project_id:
            rows = c.execute(
                'SELECT timeline_id, name, owner, project_id, duration_seconds, fps, '
                'resolution, updated_at FROM video_timelines '
                'WHERE project_id=? ORDER BY updated_at DESC LIMIT 200',
                (project_id,),
            ).fetchall()
        else:
            rows = c.execute(
                'SELECT timeline_id, name, owner, project_id, duration_seconds, fps, '
                'resolution, updated_at FROM video_timelines '
                'ORDER BY updated_at DESC LIMIT 200'
            ).fetchall()
    finally:
        c.close()
    return jsonify(ok=True, count=len(rows), timelines=[dict(r) for r in rows])


@video_editor_bp.route('/api/media/video/timelines/<timeline_id>', methods=['GET'])
def get_timeline(timeline_id: str):
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT * FROM video_timelines WHERE timeline_id=?', (timeline_id,)
        ).fetchone()
    finally:
        c.close()
    if not row:
        return jsonify(ok=False, error='not found'), 404
    out = dict(row)
    out['timeline'] = json.loads(out.pop('timeline_json'))
    return jsonify(ok=True, timeline=out)


@video_editor_bp.route('/api/media/video/timelines/<timeline_id>', methods=['PATCH'])
def update_timeline(timeline_id: str):
    body = request.get_json(silent=True) or {}
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT 1 FROM video_timelines WHERE timeline_id=?', (timeline_id,)
        ).fetchone()
        if not row:
            return jsonify(ok=False, error='not found'), 404
        if 'timeline' in body:
            ok, why = _validate_timeline(body['timeline'])
            if not ok:
                return jsonify(ok=False, error=why), 400
            c.execute(
                'UPDATE video_timelines SET timeline_json=?, updated_at=? WHERE timeline_id=?',
                (json.dumps(body['timeline']), _now(), timeline_id),
            )
        for col in ('name', 'duration_seconds', 'fps', 'resolution', 'notes', 'project_id'):
            if col not in body:
                continue
            value = body[col]
            if col in ('name', 'resolution', 'notes', 'project_id'):
                if value is not None and not isinstance(value, str):
                    return jsonify(ok=False, error=f'{col} must be a string'), 400
                if col == 'name' and (value is None or not value.strip()):
                    return jsonify(ok=False, error='name cannot be empty'), 400
                if isinstance(value, str) and len(value) > 128:
                    return jsonify(ok=False, error=f'{col} too long (max 128)'), 400
            elif col in ('duration_seconds', 'fps'):
                if value is not None and not isinstance(value, (int, float)):
                    return jsonify(ok=False, error=f'{col} must be a number'), 400
                if isinstance(value, (int, float)) and value < 0:
                    return jsonify(ok=False, error=f'{col} cannot be negative'), 400
            c.execute(
                f'UPDATE video_timelines SET {col}=?, updated_at=? WHERE timeline_id=?',
                (value, _now(), timeline_id),
            )
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, timeline_id=timeline_id)


@video_editor_bp.route('/api/media/video/timelines/<timeline_id>/render', methods=['POST'])
def queue_render(timeline_id: str):
    """Queue a render via the media_jobs pipeline.

    Returns the render row immediately; the underlying media job is what
    actually executes (kind='video_graph').
    """
    body = request.get_json(silent=True) or {}
    raw_agent = body.get('agent')
    if raw_agent is not None and not isinstance(raw_agent, str):
        return jsonify(ok=False, error='agent must be a string'), 400
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT timeline_json FROM video_timelines WHERE timeline_id=?',
            (timeline_id,),
        ).fetchone()
        if not row:
            return jsonify(ok=False, error='timeline not found'), 404
        render_id = f'VREN-{uuid.uuid4().hex[:12].upper()}'
        now = _now()
        media_job_id = None
        status = 'queued'
        error = None
        # Hand off to the media_jobs queue if available; otherwise just
        # record the render row so the UI can poll/retry.
        try:
            from core.pipeline.queue_manager import intake_internal
            agent = (body.get('agent') or 'ghost').strip().lower()
            title = f'Video render · {timeline_id}'
            desc = f'kind=video_graph timeline_id={timeline_id}'
            queue_id, proposal_id = intake_internal(agent, title, desc, priority=5)
            media_job_id = proposal_id
        except Exception as exc:  # noqa: BLE001 — record but don't 500
            error = f'enqueue failed: {exc}'
            status = 'failed'
        c.execute(
            '''INSERT INTO video_render_jobs (render_id, timeline_id, media_job_id, status,
                                              asset_id, error, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)''',
            (render_id, timeline_id, media_job_id, status, None, error, now, now),
        )
        c.commit()
    finally:
        c.close()
    code = 201 if status != 'failed' else 502
    return jsonify(ok=status != 'failed', render_id=render_id,
                   media_job_id=media_job_id, status=status, error=error), code


@video_editor_bp.route('/api/media/video/timelines/<timeline_id>/renders', methods=['GET'])
def list_renders(timeline_id: str):
    c = _conn()
    try:
        _ensure_tables(c)
        rows = c.execute(
            'SELECT render_id, media_job_id, status, asset_id, error, updated_at '
            'FROM video_render_jobs WHERE timeline_id=? ORDER BY updated_at DESC LIMIT 100',
            (timeline_id,),
        ).fetchall()
    finally:
        c.close()
    return jsonify(ok=True, count=len(rows), renders=[dict(r) for r in rows])
