"""media_jobs.py — queued execution for MusicGen / Stable Audio / ffmpeg / video graph.

MD-FEATURE-70E4913A6059 — "wire MusicGen / Stable Audio / ffmpeg / video
graph execution into the queued job system." Provides a thin HTTP surface
that records media generation/render requests and routes them through the
existing core.pipeline.queue_manager.intake_internal pipeline so they share
the same priority/visibility/proposal infrastructure as the rest of the
swarm's internal work.

Each enqueue also writes a row to `media_jobs` so the UI can list status,
parameters, and the linked queue entry without re-parsing description text.
"""

from __future__ import annotations

import json
import time
import uuid

from flask import Blueprint, request, jsonify

from services import get_connection

media_jobs_bp = Blueprint('media_jobs', __name__)

_VALID_KINDS = {'musicgen', 'stable_audio', 'ffmpeg', 'video_graph'}
_DEFAULT_AGENT_FOR_KIND = {
    'musicgen':     'mistral',
    'stable_audio': 'mistral',
    'ffmpeg':       'ghost',
    'video_graph':  'ghost',
}


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS media_jobs (
            job_id      TEXT PRIMARY KEY,
            kind        TEXT NOT NULL,
            params_json TEXT NOT NULL,
            agent       TEXT,
            status      TEXT NOT NULL DEFAULT 'queued',
            queue_id    INTEGER,
            proposal_id TEXT,
            asset_id    TEXT,
            error       TEXT,
            created_at  REAL NOT NULL,
            updated_at  REAL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_jobs_status ON media_jobs(status, created_at)"
    )


@media_jobs_bp.route('/api/media/jobs', methods=['POST'])
def submit_job():
    data   = request.get_json(silent=True) or {}
    # Y.54: type-check before .strip()/lower/int (same class as Y.50/Y.53).
    raw_kind = data.get('kind')
    if raw_kind is not None and not isinstance(raw_kind, str):
        return jsonify({'ok': False, 'error': 'kind must be a string'}), 400
    raw_agent = data.get('agent')
    if raw_agent is not None and not isinstance(raw_agent, str):
        return jsonify({'ok': False, 'error': 'agent must be a string'}), 400
    raw_prio = data.get('priority')
    if raw_prio is not None and not isinstance(raw_prio, (int, float)):
        return jsonify({'ok': False, 'error': 'priority must be a number'}), 400
    kind   = (raw_kind or '').strip().lower()
    params = data.get('params') or {}
    agent  = (raw_agent or '').strip().lower() or _DEFAULT_AGENT_FOR_KIND.get(kind, 'mistral')
    priority = int(raw_prio if raw_prio is not None else 5)
    if priority < 0 or priority > 10:
        return jsonify({'ok': False, 'error': 'priority must be in 0..10'}), 400
    if kind not in _VALID_KINDS:
        return jsonify({'ok': False, 'error': f'invalid kind: {kind}',
                        'valid': sorted(_VALID_KINDS)}), 400
    if not isinstance(params, dict):
        return jsonify({'ok': False, 'error': 'params must be an object'}), 400
    # Bound params payload to keep DB rows reasonable.
    try:
        params_json = json.dumps(params)[:4000]
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'params not JSON-serialisable'}), 400

    job_id = f'MJOB-{uuid.uuid4().hex[:12].upper()}'
    title  = f'Media job · {kind}'
    description = f'kind={kind} job_id={job_id} params={params_json}'

    queue_id   = None
    proposal_id = None
    try:
        from core.pipeline.queue_manager import intake_internal
        queue_id, proposal_id = intake_internal(agent, title, description, priority=priority)
    except Exception as exc:
        # Queue dispatch failed — still record the job so the UI can
        # see the failure and the user can retry, instead of swallowing it.
        conn = get_connection()
        try:
            _ensure_schema(conn)
            now = time.time()
            conn.execute(
                "INSERT INTO media_jobs (job_id, kind, params_json, agent, status, error, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (job_id, kind, params_json, agent, 'failed', f'queue_intake: {exc}'[:400], now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': False, 'job_id': job_id, 'error': str(exc)}), 500

    conn = get_connection()
    try:
        _ensure_schema(conn)
        now = time.time()
        conn.execute(
            "INSERT INTO media_jobs (job_id, kind, params_json, agent, status, queue_id, proposal_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, kind, params_json, agent, 'queued', queue_id, proposal_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True, 'job_id': job_id, 'kind': kind, 'agent': agent,
                    'queue_id': queue_id, 'proposal_id': proposal_id, 'status': 'queued'})


@media_jobs_bp.route('/api/media/jobs', methods=['GET'])
def list_jobs():
    status = (request.args.get('status') or '').strip().lower() or None
    kind   = (request.args.get('kind')   or '').strip().lower() or None
    if kind and kind not in _VALID_KINDS:
        return jsonify({'ok': False, 'error': f'invalid kind: {kind}'}), 400
    conn = get_connection()
    try:
        _ensure_schema(conn)
        sql  = ("SELECT job_id, kind, params_json, agent, status, queue_id, proposal_id, "
                "asset_id, error, created_at, updated_at FROM media_jobs")
        clauses = []
        args = []
        if status:
            clauses.append("status=?")
            args.append(status)
        if kind:
            clauses.append("kind=?")
            args.append(kind)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 100"
        rows = conn.execute(sql, args).fetchall()
        items = []
        for r in rows:
            try:
                params = json.loads(r['params_json'] if hasattr(r, 'keys') else r[2])
            except Exception:
                params = {}
            items.append({
                'job_id':      r['job_id']      if hasattr(r, 'keys') else r[0],
                'kind':        r['kind']        if hasattr(r, 'keys') else r[1],
                'params':      params,
                'agent':       r['agent']       if hasattr(r, 'keys') else r[3],
                'status':      r['status']      if hasattr(r, 'keys') else r[4],
                'queue_id':    r['queue_id']    if hasattr(r, 'keys') else r[5],
                'proposal_id': r['proposal_id'] if hasattr(r, 'keys') else r[6],
                'asset_id':    r['asset_id']    if hasattr(r, 'keys') else r[7],
                'error':       r['error']       if hasattr(r, 'keys') else r[8],
                'created_at':  r['created_at']  if hasattr(r, 'keys') else r[9],
                'updated_at':  r['updated_at']  if hasattr(r, 'keys') else r[10],
            })
        return jsonify({'ok': True, 'items': items, 'count': len(items)})
    finally:
        conn.close()


@media_jobs_bp.route('/api/media/jobs/<job_id>', methods=['PATCH'])
def update_job(job_id):
    """Update job status / asset_id / error. Used by workers + the UI."""
    data = request.get_json(silent=True) or {}
    # Y.54: type-check before .strip() to avoid 500 on non-string input.
    for col in ('status', 'asset_id', 'error'):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({'ok': False, 'error': f'{col} must be a string'}), 400
    status = (data.get('status') or '').strip().lower() or None
    asset_id = (data.get('asset_id') or '').strip()[:256] or None
    error = (data.get('error') or '').strip() or None
    if status and status not in {'queued', 'running', 'done', 'failed', 'cancelled'}:
        return jsonify({'ok': False, 'error': f'invalid status: {status}'}), 400
    if not (status or asset_id or error):
        return jsonify({'ok': False, 'error': 'no fields to update'}), 400
    fields = []
    args = []
    if status:
        fields.append('status=?')
        args.append(status)
    if asset_id:
        fields.append('asset_id=?')
        args.append(asset_id)
    if error is not None:
        fields.append('error=?')
        args.append(error[:400])
    fields.append('updated_at=?')
    args.append(time.time())
    args.append(job_id)
    conn = get_connection()
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            f"UPDATE media_jobs SET {', '.join(fields)} WHERE job_id=?", args,
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'ok': False, 'error': 'job not found'}), 404
        return jsonify({'ok': True, 'job_id': job_id})
    finally:
        conn.close()
