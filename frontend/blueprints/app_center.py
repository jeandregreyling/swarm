"""app_center.py — App Center for mobile/tablet/desktop/web/game projects.

Y.47. The App Center is a new pillar surface for building user-facing apps
and games. Each project is a tracked record (kind, framework, targets) with
an attached source bundle reference and a build pipeline that hands off to
the media_jobs / queue_manager infrastructure used by Media Center renders.

Tables (created idempotently):

* `app_projects` — top-level project rows: kind, framework, name, owner,
  description, repo_ref, status, optional studio_project_id linkage so the
  same record is visible in Studio/ALM.
* `app_project_targets` — per-platform target list (ios/android/windows/
  macos/linux/web/wasm/itch). Each target carries its own status + last
  build_id so the UI can show 'Android: ok 2 mins ago, iOS: failed'.
* `app_builds` — append-only build attempts per (project, target). status
  in {queued, building, succeeded, failed, cancelled}; carries
  media_job_id (proposal_id from intake_internal) + asset_id (built
  artifact uri).

Endpoints:
  POST   /api/app-center/projects
  GET    /api/app-center/projects[?kind=&framework=&status=]
  GET    /api/app-center/projects/<project_id>
  PATCH  /api/app-center/projects/<project_id>
  POST   /api/app-center/projects/<project_id>/targets
  POST   /api/app-center/projects/<project_id>/build {target}
  GET    /api/app-center/projects/<project_id>/builds
  GET    /api/app-center/registry  (kinds + frameworks + targets contract)
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid

from flask import Blueprint, jsonify, request



app_center_bp = Blueprint('app_center', __name__)

_DB_PATH = 'swarm_memory.db'

_VALID_KINDS = {'mobile', 'tablet', 'desktop', 'web', 'game'}
_VALID_FRAMEWORKS = {
    # Mobile / cross-device
    'flutter', 'react-native', 'expo', 'ionic', 'native-android', 'native-ios',
    # Desktop / cross-platform
    'electron', 'tauri', 'qt', 'gtk',
    # Web / PWA
    'next', 'sveltekit', 'astro', 'pwa',
    # Games
    'godot', 'unity', 'unreal', 'phaser', 'love2d', 'pygame',
    # Other
    'custom',
}
_VALID_TARGETS = {
    'ios', 'android', 'windows', 'macos', 'linux', 'web', 'wasm', 'itch', 'steam',
}
_VALID_PROJECT_STATUS = {'draft', 'active', 'paused', 'archived'}
_VALID_BUILD_STATUS   = {'queued', 'building', 'succeeded', 'failed', 'cancelled'}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())


def _ensure_tables(c: sqlite3.Connection) -> None:
    c.execute(
        '''CREATE TABLE IF NOT EXISTS app_projects (
            project_id        TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            kind              TEXT NOT NULL,
            framework         TEXT NOT NULL,
            owner             TEXT,
            description       TEXT,
            repo_ref          TEXT,
            status            TEXT NOT NULL,
            studio_project_id TEXT,
            tags_json         TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        )'''
    )
    c.execute(
        '''CREATE TABLE IF NOT EXISTS app_project_targets (
            target_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    TEXT NOT NULL,
            target        TEXT NOT NULL,
            status        TEXT NOT NULL,
            last_build_id TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            UNIQUE(project_id, target),
            FOREIGN KEY (project_id) REFERENCES app_projects(project_id)
        )'''
    )
    c.execute(
        '''CREATE TABLE IF NOT EXISTS app_builds (
            build_id     TEXT PRIMARY KEY,
            project_id   TEXT NOT NULL,
            target       TEXT NOT NULL,
            status       TEXT NOT NULL,
            media_job_id TEXT,
            asset_id     TEXT,
            error        TEXT,
            agent        TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES app_projects(project_id)
        )'''
    )
    c.execute('CREATE INDEX IF NOT EXISTS idx_app_builds_project ON app_builds(project_id, created_at)')
    c.commit()


def _row_to_project(row: sqlite3.Row) -> dict:
    out = dict(row)
    try:
        out['tags'] = json.loads(out.pop('tags_json') or '[]')
    except Exception:  # noqa: BLE001 — corrupt JSON shouldn't break GET
        out['tags'] = []
        out.pop('tags_json', None)
    return out


# ── projects CRUD ──────────────────────────────────────────────────────

@app_center_bp.route('/api/app-center/projects', methods=['POST'])
def create_project():
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    kind = (body.get('kind') or '').strip().lower()
    framework = (body.get('framework') or '').strip().lower()
    if not name or len(name) > 128:
        return jsonify(ok=False, error='name required (≤128)'), 400
    if kind not in _VALID_KINDS:
        return jsonify(ok=False, error=f'invalid kind; valid={sorted(_VALID_KINDS)}'), 400
    if framework not in _VALID_FRAMEWORKS:
        return jsonify(ok=False, error=f'invalid framework; valid={sorted(_VALID_FRAMEWORKS)}'), 400
    targets = body.get('targets') or []
    if not isinstance(targets, list):
        return jsonify(ok=False, error='targets must be a list'), 400
    bad = [t for t in targets if t not in _VALID_TARGETS]
    if bad:
        return jsonify(ok=False, error=f'invalid targets: {bad}'), 400
    tags = body.get('tags') or []
    if not isinstance(tags, list):
        return jsonify(ok=False, error='tags must be a list'), 400
    project_id = f'APP-{uuid.uuid4().hex[:12].upper()}'
    now = _now()
    c = _conn()
    try:
        _ensure_tables(c)
        c.execute(
            '''INSERT INTO app_projects (project_id, name, kind, framework, owner,
                description, repo_ref, status, studio_project_id, tags_json,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                project_id, name, kind, framework,
                (body.get('owner') or '').strip() or None,
                (body.get('description') or '').strip() or None,
                (body.get('repo_ref') or '').strip() or None,
                (body.get('status') or 'draft').strip().lower() if (body.get('status') or 'draft').strip().lower() in _VALID_PROJECT_STATUS else 'draft',
                (body.get('studio_project_id') or '').strip() or None,
                json.dumps([str(t)[:60] for t in tags][:32]),
                now, now,
            ),
        )
        for t in targets:
            c.execute(
                '''INSERT INTO app_project_targets (project_id, target, status, created_at, updated_at)
                   VALUES (?,?,?,?,?)''',
                (project_id, t, 'pending', now, now),
            )
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, project_id=project_id, created_at=now), 201


@app_center_bp.route('/api/app-center/projects', methods=['GET'])
def list_projects():
    kind = (request.args.get('kind') or '').strip().lower() or None
    framework = (request.args.get('framework') or '').strip().lower() or None
    status = (request.args.get('status') or '').strip().lower() or None
    where = []
    args: list = []
    if kind:
        where.append('kind=?'); args.append(kind)
    if framework:
        where.append('framework=?'); args.append(framework)
    if status:
        where.append('status=?'); args.append(status)
    sql = ('SELECT project_id, name, kind, framework, owner, status, '
           'studio_project_id, updated_at FROM app_projects')
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY updated_at DESC LIMIT 200'
    c = _conn()
    try:
        _ensure_tables(c)
        rows = c.execute(sql, args).fetchall()
        projects = [dict(r) for r in rows]
        return jsonify(ok=True, count=len(projects), projects=projects)
    finally:
        c.close()


@app_center_bp.route('/api/app-center/projects/<project_id>', methods=['GET'])
def get_project(project_id: str):
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT * FROM app_projects WHERE project_id=?', (project_id,)
        ).fetchone()
        if not row:
            return jsonify(ok=False, error="not found"), 404
        targets = c.execute(
            'SELECT target, status, last_build_id, updated_at FROM app_project_targets '
            'WHERE project_id=? ORDER BY target', (project_id,)
        ).fetchall()
    finally:
        c.close()
    out = _row_to_project(row)
    out['targets'] = [dict(t) for t in targets]
    return jsonify(ok=True, project=out)


@app_center_bp.route('/api/app-center/projects/<project_id>', methods=['PATCH'])
def update_project(project_id: str):
    body = request.get_json(silent=True) or {}
    c = _conn()
    try:
        _ensure_tables(c)
        if not c.execute('SELECT 1 FROM app_projects WHERE project_id=?', (project_id,)).fetchone():
            return jsonify(ok=False, error='not found'), 404
        # Typed validation per column.
        for col in ('name', 'description', 'repo_ref', 'owner', 'studio_project_id'):
            if col in body:
                v = body[col]
                if v is not None and not isinstance(v, str):
                    return jsonify(ok=False, error=f'{col} must be a string'), 400
                if col == 'name' and (v is None or not v.strip()):
                    return jsonify(ok=False, error='name cannot be empty'), 400
                if isinstance(v, str) and len(v) > 256:
                    return jsonify(ok=False, error=f'{col} too long (max 256)'), 400
                c.execute(
                    f'UPDATE app_projects SET {col}=?, updated_at=? WHERE project_id=?',
                    (v, _now(), project_id),
                )
        if 'kind' in body:
            if body['kind'] not in _VALID_KINDS:
                return jsonify(ok=False, error='invalid kind'), 400
            c.execute('UPDATE app_projects SET kind=?, updated_at=? WHERE project_id=?',
                      (body['kind'], _now(), project_id))
        if 'framework' in body:
            if body['framework'] not in _VALID_FRAMEWORKS:
                return jsonify(ok=False, error='invalid framework'), 400
            c.execute('UPDATE app_projects SET framework=?, updated_at=? WHERE project_id=?',
                      (body['framework'], _now(), project_id))
        if 'status' in body:
            if body['status'] not in _VALID_PROJECT_STATUS:
                return jsonify(ok=False, error='invalid status'), 400
            c.execute('UPDATE app_projects SET status=?, updated_at=? WHERE project_id=?',
                      (body['status'], _now(), project_id))
        if 'tags' in body:
            if not isinstance(body['tags'], list):
                return jsonify(ok=False, error='tags must be a list'), 400
            tags = [str(t)[:60] for t in body['tags']][:32]
            c.execute('UPDATE app_projects SET tags_json=?, updated_at=? WHERE project_id=?',
                      (json.dumps(tags), _now(), project_id))
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, project_id=project_id)


# ── targets ────────────────────────────────────────────────────────────

@app_center_bp.route('/api/app-center/projects/<project_id>/targets', methods=['POST'])
def add_target(project_id: str):
    body = request.get_json(silent=True) or {}
    target = (body.get('target') or '').strip().lower()
    if target not in _VALID_TARGETS:
        return jsonify(ok=False, error=f'invalid target; valid={sorted(_VALID_TARGETS)}'), 400
    c = _conn()
    try:
        _ensure_tables(c)
        if not c.execute('SELECT 1 FROM app_projects WHERE project_id=?', (project_id,)).fetchone():
            return jsonify(ok=False, error='project not found'), 404
        try:
            c.execute(
                '''INSERT INTO app_project_targets (project_id, target, status, created_at, updated_at)
                   VALUES (?,?,?,?,?)''',
                (project_id, target, 'pending', _now(), _now()),
            )
            c.commit()
        except sqlite3.IntegrityError:
            return jsonify(ok=False, error='target already attached'), 409
    finally:
        c.close()
    return jsonify(ok=True, project_id=project_id, target=target), 201


# ── build ──────────────────────────────────────────────────────────────

@app_center_bp.route('/api/app-center/projects/<project_id>/build', methods=['POST'])
def start_build(project_id: str):
    body = request.get_json(silent=True) or {}
    target = (body.get('target') or '').strip().lower()
    if target not in _VALID_TARGETS:
        return jsonify(ok=False, error=f'invalid target; valid={sorted(_VALID_TARGETS)}'), 400
    agent = (body.get('agent') or 'ghost_coder').strip().lower()
    c = _conn()
    try:
        _ensure_tables(c)
        proj = c.execute(
            'SELECT name, status FROM app_projects WHERE project_id=?', (project_id,)
        ).fetchone()
        if not proj:
            return jsonify(ok=False, error='project not found'), 404
        # Y.50 bug-fix: archived projects must not accept new builds. Without
        # this we'd silently queue and waste the build slot — surface a 409
        # so the UI can prompt the user to unarchive first.
        if proj['status'] == 'archived':
            return jsonify(ok=False, error='project is archived; unarchive before building'), 409
        target_row = c.execute(
            'SELECT 1 FROM app_project_targets WHERE project_id=? AND target=?',
            (project_id, target),
        ).fetchone()
        if not target_row:
            return jsonify(ok=False, error=f'target {target} not attached to project'), 400
        build_id = f'BUILD-{uuid.uuid4().hex[:12].upper()}'
        media_job_id = None
        status = 'queued'
        error = None
        try:
            from core.pipeline.queue_manager import intake_internal
            title = f'App build · {proj["name"]} → {target}'
            desc = f'kind=app_build project_id={project_id} target={target} build_id={build_id}'
            queue_id, proposal_id = intake_internal(agent, title, desc, priority=5)
            media_job_id = proposal_id
        except Exception as exc:  # noqa: BLE001 — record but don't 500
            error = f'enqueue failed: {exc}'
            status = 'failed'
        now = _now()
        c.execute(
            '''INSERT INTO app_builds (build_id, project_id, target, status, media_job_id,
                                       asset_id, error, agent, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (build_id, project_id, target, status, media_job_id, None, error, agent, now, now),
        )
        c.execute(
            'UPDATE app_project_targets SET status=?, last_build_id=?, updated_at=? '
            'WHERE project_id=? AND target=?',
            (status, build_id, now, project_id, target),
        )
        c.commit()
    finally:
        c.close()
    code = 201 if status != 'failed' else 502
    return jsonify(ok=status != 'failed', build_id=build_id, project_id=project_id,
                   target=target, status=status, media_job_id=media_job_id, error=error), code


@app_center_bp.route('/api/app-center/projects/<project_id>/builds', methods=['GET'])
def list_builds(project_id: str):
    target = (request.args.get('target') or '').strip().lower() or None
    # Y.50 bug-fix: validate the target filter so a typo returns 400 instead
    # of an empty list that looks like "no builds yet".
    if target is not None and target not in _VALID_TARGETS:
        return jsonify(ok=False, error=f'invalid target; valid={sorted(_VALID_TARGETS)}'), 400
    c = _conn()
    try:
        _ensure_tables(c)
        if target:
            rows = c.execute(
                'SELECT build_id, target, status, media_job_id, asset_id, error, agent, '
                'created_at, updated_at FROM app_builds WHERE project_id=? AND target=? '
                'ORDER BY created_at DESC LIMIT 100', (project_id, target),
            ).fetchall()
        else:
            rows = c.execute(
                'SELECT build_id, target, status, media_job_id, asset_id, error, agent, '
                'created_at, updated_at FROM app_builds WHERE project_id=? '
                'ORDER BY created_at DESC LIMIT 100', (project_id,),
            ).fetchall()
    finally:
        c.close()
    return jsonify(ok=True, count=len(rows), builds=[dict(r) for r in rows])


@app_center_bp.route('/api/app-center/builds/<build_id>', methods=['PATCH'])
def update_build(build_id: str):
    body = request.get_json(silent=True) or {}
    # Y.50 bug-fix: type-check inputs before .strip() so non-string payloads
    # (e.g. {"status": 123}) return 400 instead of crashing with AttributeError.
    raw_status = body.get('status')
    raw_asset = body.get('asset_id')
    if raw_status is not None and not isinstance(raw_status, str):
        return jsonify(ok=False, error='status must be a string'), 400
    if raw_asset is not None and not isinstance(raw_asset, str):
        return jsonify(ok=False, error='asset_id must be a string'), 400
    status = (raw_status or '').strip().lower() or None
    asset_id = (raw_asset or '').strip() or None
    if asset_id and len(asset_id) > 256:
        return jsonify(ok=False, error='asset_id too long (max 256)'), 400
    error = body.get('error')
    if error is not None and not isinstance(error, (str, int, float)):
        return jsonify(ok=False, error='error must be a string or number'), 400
    if status and status not in _VALID_BUILD_STATUS:
        return jsonify(ok=False, error=f'invalid status; valid={sorted(_VALID_BUILD_STATUS)}'), 400
    if not (status or asset_id or error is not None):
        return jsonify(ok=False, error='no fields to update'), 400
    c = _conn()
    try:
        _ensure_tables(c)
        row = c.execute(
            'SELECT project_id, target FROM app_builds WHERE build_id=?', (build_id,)
        ).fetchone()
        if not row:
            return jsonify(ok=False, error='not found'), 404
        if status:
            c.execute('UPDATE app_builds SET status=?, updated_at=? WHERE build_id=?',
                      (status, _now(), build_id))
            c.execute('UPDATE app_project_targets SET status=?, updated_at=? '
                      'WHERE project_id=? AND target=?',
                      (status, _now(), row['project_id'], row['target']))
        if asset_id:
            c.execute('UPDATE app_builds SET asset_id=?, updated_at=? WHERE build_id=?',
                      (asset_id, _now(), build_id))
        if error is not None:
            c.execute('UPDATE app_builds SET error=?, updated_at=? WHERE build_id=?',
                      (str(error)[:600], _now(), build_id))
        c.commit()
    finally:
        c.close()
    return jsonify(ok=True, build_id=build_id)


# ── registry (contract for UI) ─────────────────────────────────────────

@app_center_bp.route('/api/app-center/registry', methods=['GET'])
def registry():
    return jsonify(ok=True,
                   kinds=sorted(_VALID_KINDS),
                   frameworks=sorted(_VALID_FRAMEWORKS),
                   targets=sorted(_VALID_TARGETS),
                   project_status=sorted(_VALID_PROJECT_STATUS),
                   build_status=sorted(_VALID_BUILD_STATUS))
