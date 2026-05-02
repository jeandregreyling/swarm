"""Knowledge Center blueprint.

Session 29.2 — the Knowledge Center is the emerging home for test-lab
scripts, change-run history, and (later) skill + agent knowledge.

Endpoints:
    GET  /api/knowledge/testlab/scripts              — same shape as
                                                       /api/studio/testlab/scripts
    GET  /api/knowledge/change-runs                  — recent change runs
    GET  /api/knowledge/change-runs/<change_id>      — runs for a change
"""
from __future__ import annotations

import os
import sqlite3

from flask import Blueprint, jsonify, request

from core.knowledge import scripts as _kc_scripts
from core.knowledge import test_runs as _kc_runs
from core.knowledge import projects as _kc_projects
from core.knowledge import context_packs as _kc_context_packs
from core.knowledge import close_out as _kc_closeout

knowledge_bp = Blueprint('knowledge_bp', __name__)


def _group_scripts(scripts):
    groups = {}
    order = []
    for s in scripts:
        g = s.get('group') or 'misc'
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(s)
    return [{'name': g, 'scripts': groups[g]} for g in order]


@knowledge_bp.route('/api/knowledge/testlab/scripts', methods=['GET'])
def api_knowledge_testlab_scripts():
    """Mirror of /api/studio/testlab/scripts under the Knowledge Center API."""
    scripts = _kc_scripts.get_registry()
    return jsonify({
        'ok': True,
        'count': len(scripts),
        'groups': _group_scripts(scripts),
        'env': {
            'repo_root': os.environ.get('SWARM_ROOT') or os.getcwd(),
            'venv': os.environ.get('VIRTUAL_ENV') or '',
        },
    })


@knowledge_bp.route('/api/knowledge/change-runs', methods=['GET'])
def api_knowledge_change_runs_recent():
    """List the most recent change runs across all changes."""
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    return jsonify({
        'ok': True,
        'items': _kc_scripts.list_change_runs(limit=limit),
    })


@knowledge_bp.route('/api/knowledge/change-runs/<change_id>', methods=['GET'])
def api_knowledge_change_runs_for_change(change_id: str):
    """List change runs for a specific change_id, most-recent first."""
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    return jsonify({
        'ok': True,
        'change_id': change_id,
        'items': _kc_scripts.list_change_runs(change_id=change_id, limit=limit),
    })


# ── Session 30 — Step-through timeline (MD-SESSION30-CB0CE94C6B60) ────────


@knowledge_bp.route('/api/knowledge/changes/<change_id>/timeline', methods=['GET'])
def api_knowledge_change_timeline(change_id: str):
    """Stitch change_runs + test_runs for a change into a single timeline."""
    try:
        limit = max(1, min(int(request.args.get('limit', 200)), 1000))
    except (TypeError, ValueError):
        limit = 200
    return jsonify({
        'ok': True,
        'change_id': change_id,
        'items': _kc_scripts.timeline_for_change(change_id, limit=limit),
    })


# ── Session 30 — Knowledge Center tile feed (MD-SESSION30-FF20242F3F3D) ──


@knowledge_bp.route('/api/knowledge/runs/feed', methods=['GET'])
def api_knowledge_runs_feed():
    """Combined feed of recent change_runs + test_runs for the KC tile.

    Optional ?limit (default 50, max 200). Items are ordered newest-first
    and tagged with ``kind`` so the tile can render heterogeneously.
    """
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    items = []
    try:
        for cr in _kc_scripts.list_change_runs(limit=limit):
            items.append({
                'kind': 'change_run',
                'ts': cr.get('created_at'),
                'change_run_id': cr.get('id'),
                'change_id': cr.get('change_id'),
                'script_ids': cr.get('script_ids') or [],
            })
    except Exception:
        pass
    try:
        for tr in _kc_runs.list_runs(limit=limit) or []:
            items.append({
                'kind': 'test_run',
                'ts': tr.get('started_at') or tr.get('created_at') or 0,
                'run_id': tr.get('id') or tr.get('run_id'),
                'script_id': tr.get('script_id'),
                'change_id': tr.get('change_id'),
                'status': tr.get('status'),
                'finished_at': tr.get('finished_at'),
                'exit_code': tr.get('exit_code'),
                'triggered_by': tr.get('triggered_by'),
            })
    except Exception:
        pass
    items.sort(key=lambda x: (x.get('ts') or 0), reverse=True)
    return jsonify({'ok': True, 'count': len(items[:limit]), 'items': items[:limit]})


# ── Session 30 — Test Run history (ALM-style) ─────────────────────────────

@knowledge_bp.route('/api/knowledge/test-runs', methods=['POST'])
def api_knowledge_test_run_start():
    """Start recording a test run.

    Body: {script_id, change_id?, command?, triggered_by?}
    Returns: {ok, run_id}
    """
    body = request.get_json(silent=True) or {}
    script_id = str(body.get('script_id') or '').strip()
    if not script_id:
        return jsonify({'ok': False, 'error': 'script_id required'}), 400
    # Session 30 — auto-tag triggered_by=change:<id> when a change_id is
    # supplied but no explicit triggered_by was passed. (MD-SESSION30-ECA581250AF5)
    raw_change_id = body.get('change_id') or None
    raw_triggered_by = body.get('triggered_by')
    if raw_triggered_by is None or str(raw_triggered_by).strip() == '':
        if raw_change_id:
            triggered_by = f'change:{str(raw_change_id).strip()}'
        else:
            triggered_by = 'manual'
    else:
        triggered_by = str(raw_triggered_by)
    try:
        run_id = _kc_runs.start_run(
            script_id,
            change_id=raw_change_id,
            command=body.get('command') or None,
            triggered_by=triggered_by,
            project_id=body.get('project_id') or None,
            step_id=body.get('step_id') or None,
            case_id=body.get('case_id') or None,
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not run_id:
        return jsonify({'ok': False, 'error': 'could not create run'}), 500
    return jsonify({'ok': True, 'run_id': run_id})


@knowledge_bp.route('/api/knowledge/test-runs/<run_id>', methods=['PATCH'])
def api_knowledge_test_run_finish(run_id: str):
    """Finish a run.

    Body: {status, exit_code?, stdout_tail?}
    """
    body = request.get_json(silent=True) or {}
    status = str(body.get('status') or '').strip() or _kc_runs.STATUS_FAIL
    ok = _kc_runs.finish_run(
        run_id,
        status=status,
        exit_code=body.get('exit_code'),
        stdout_tail=str(body.get('stdout_tail') or ''),
    )
    if not ok:
        return jsonify({'ok': False, 'error': 'run not found or DB failure'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/test-runs/<run_id>/artifacts', methods=['POST'])
def api_knowledge_test_run_add_artifact(run_id: str):
    """Add a note/log/screenshot/link to a run.

    Body: {kind, body}
    kind: 'note' | 'screenshot' | 'log' | 'link'
    body: free-form text (screenshots can be data-URL strings)
    """
    body = request.get_json(silent=True) or {}
    kind = str(body.get('kind') or '').strip() or 'note'
    text = str(body.get('body') or '').strip()
    if not text:
        return jsonify({'ok': False, 'error': 'body required'}), 400
    ok = _kc_runs.add_artifact(run_id, kind, text)
    if not ok:
        return jsonify({'ok': False, 'error': 'could not attach artifact'}), 500
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/test-runs', methods=['GET'])
def api_knowledge_test_runs_list():
    """List recent test runs. Filters: script_id, change_id, status, limit."""
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    include_artifacts = request.args.get('artifacts') in ('1', 'true', 'yes')
    return jsonify({
        'ok': True,
        'items': _kc_runs.list_runs(
            script_id=request.args.get('script_id') or None,
            change_id=request.args.get('change_id') or None,
            status=request.args.get('status') or None,
            project_id=request.args.get('project_id') or None,
            step_id=request.args.get('step_id') or None,
            case_id=request.args.get('case_id') or None,
            limit=limit,
            include_artifacts=include_artifacts,
        ),
    })


@knowledge_bp.route('/api/knowledge/test-runs/<run_id>', methods=['GET'])
def api_knowledge_test_run_detail(run_id: str):
    """Return a single run with its artifacts."""
    run = _kc_runs.get_run(run_id)
    if not run:
        return jsonify({'ok': False, 'error': 'run not found'}), 404
    return jsonify({'ok': True, 'run': run})


# ── Session 30.1 — Projects (Agile / Waterfall / Prince2 / Mixed) ────────

@knowledge_bp.route('/api/knowledge/projects', methods=['GET'])
def api_projects_list():
    try:
        limit = max(1, min(int(request.args.get('limit', 100)), 500))
    except (TypeError, ValueError):
        limit = 100
    return jsonify({
        'ok': True,
        'items': _kc_projects.list_projects(
            status=request.args.get('status') or None,
            tag=request.args.get('tag') or None,
            limit=limit,
        ),
    })


@knowledge_bp.route('/api/knowledge/projects', methods=['POST'])
def api_projects_create():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'}), 400
    methodology = str(body.get('methodology') or 'mixed').lower()
    try:
        project_id = _kc_projects.create_project(
            name,
            description=str(body.get('description') or ''),
            methodology=methodology,
            owner=str(body.get('owner') or 'seven'),
            tags=body.get('tags'),
        )
    except ValueError as ve:
        return jsonify({'ok': False, 'error': str(ve)}), 400
    if not project_id:
        return jsonify({'ok': False, 'error': 'could not create project'}), 500
    return jsonify({'ok': True, 'project_id': project_id})


@knowledge_bp.route('/api/knowledge/projects/<project_id>', methods=['GET'])
def api_projects_detail(project_id: str):
    proj = _kc_projects.get_project(project_id)
    if not proj:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    # Flatten for UI: merge project row with its steps/test_cases/proposals lists.
    flat = dict(proj.get('project') or {})
    flat['steps'] = proj.get('steps') or []
    flat['test_cases'] = proj.get('test_cases') or []
    flat['blackboard_notes'] = proj.get('blackboard_notes') or []
    flat['proposals'] = proj.get('proposals') or []
    return jsonify({'ok': True, 'project': flat})


@knowledge_bp.route('/api/knowledge/projects/<project_id>', methods=['PATCH'])
def api_projects_update(project_id: str):
    body = request.get_json(silent=True) or {}
    # Strip reserved / server-owned keys so a caller can never overwrite them
    # and never collide with the positional project_id argument below.
    for reserved in ('project_id', 'created_at', 'updated_at'):
        body.pop(reserved, None)
    try:
        ok = _kc_projects.update_project(project_id, **body)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except TypeError as e:
        return jsonify({'ok': False, 'error': f'bad field: {e}'}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'update failed or no valid fields'}), 400
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/steps', methods=['POST'])
def api_project_add_step(project_id: str):
    body = request.get_json(silent=True) or {}
    title = str(body.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    try:
        step_id = _kc_projects.add_step(
            project_id,
            title,
            description=str(body.get('description') or ''),
            owner=str(body.get('owner') or 'seven'),
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    if not step_id:
        return jsonify({'ok': False, 'error': 'could not add step'}), 500
    return jsonify({'ok': True, 'step_id': step_id})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/steps', methods=['GET'])
def api_project_list_steps(project_id: str):
    return jsonify({'ok': True, 'items': _kc_projects.list_steps(project_id)})


# ── Session 28 — bulk import + search (S-0F9BA7EF34, S-1DC62BD77B) ────────

@knowledge_bp.route('/api/knowledge/projects/<project_id>/steps/bulk', methods=['POST'])
def api_project_steps_bulk_import(project_id: str):
    """Bulk-create backlog steps under one project.

    Body: ``{"steps": [{"title": "...", "description": "...", "owner": "..."},
                       ...]}``
    The endpoint is idempotent on title within the same project: an existing
    step with a matching title is reused and reported as ``skipped``.
    Returns ``{"ok": true, "created": [...], "skipped": [...]}``.
    """
    body = request.get_json(silent=True) or {}
    raw = body.get('steps')
    if not isinstance(raw, list) or not raw:
        return jsonify({'ok': False, 'error': 'steps array required'}), 400
    if len(raw) > 500:
        return jsonify({'ok': False, 'error': 'max 500 steps per request'}), 400
    if not _kc_projects.get_project(project_id):
        return jsonify({'ok': False, 'error': 'project not found'}), 404

    existing_titles = {
        (s.get('title') or '').strip().lower()
        for s in _kc_projects.list_steps(project_id) or []
    }
    created, skipped = [], []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            skipped.append({'index': i, 'reason': 'not an object'})
            continue
        title = str(item.get('title') or '').strip()
        if not title:
            skipped.append({'index': i, 'reason': 'title required'})
            continue
        if title.lower() in existing_titles:
            skipped.append({'index': i, 'title': title, 'reason': 'duplicate title'})
            continue
        try:
            step_id = _kc_projects.add_step(
                project_id, title,
                description=str(item.get('description') or ''),
                owner=str(item.get('owner') or 'seven'),
            )
        except ValueError as e:
            skipped.append({'index': i, 'title': title, 'reason': str(e)})
            continue
        if step_id:
            existing_titles.add(title.lower())
            created.append({'index': i, 'step_id': step_id, 'title': title})
        else:
            skipped.append({'index': i, 'title': title, 'reason': 'add_step returned None'})

    return jsonify({'ok': True, 'created': created, 'skipped': skipped,
                    'created_count': len(created), 'skipped_count': len(skipped)})


@knowledge_bp.route('/api/knowledge/projects/search', methods=['GET'])
def api_projects_search():
    """Search projects by name/description substring (case-insensitive).

    Query params: ``q`` (required, min 2 chars), ``limit`` (default 25, max 100).
    """
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'ok': False, 'error': 'q must be >= 2 chars'}), 400
    try:
        limit = max(1, min(int(request.args.get('limit', 25)), 100))
    except (TypeError, ValueError):
        limit = 25
    try:
        from utils.db._connection import get_connection as _get_conn
        with _get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT project_id, name, description, status, methodology, owner, "
                "COALESCE(priority, 0) AS priority, created_at, updated_at "
                "FROM projects "
                "WHERE LOWER(name) LIKE ? OR LOWER(IFNULL(description,'')) LIKE ? "
                "ORDER BY priority DESC, updated_at DESC LIMIT ?",
                (f'%{q.lower()}%', f'%{q.lower()}%', limit),
            ).fetchall()
        items = [dict(r) for r in rows]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({'ok': True, 'q': q, 'items': items, 'count': len(items)})


@knowledge_bp.route('/api/knowledge/steps/<step_id>', methods=['PATCH'])
def api_step_update_status(step_id: str):
    body = request.get_json(silent=True) or {}
    status = str(body.get('status') or '').strip()
    if status not in _kc_projects.STEP_STATUSES:
        return jsonify({'ok': False, 'error': f'status must be one of {list(_kc_projects.STEP_STATUSES)}'}), 400
    ok = _kc_projects.update_step_status(step_id, status, owner=body.get('owner') or None)
    if not ok:
        return jsonify({'ok': False, 'error': 'step not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/steps/<step_id>', methods=['GET'])
def api_step_detail(step_id: str):
    """ALM detail surface (PACKET-03): full step record with linked
    test cases and recent test runs so the UI can open it."""
    step = _kc_projects.get_step(step_id)
    if not step:
        return jsonify({'ok': False, 'error': 'step not found'}), 404
    return jsonify({'ok': True, 'step': step})


# ── Platinum layer record endpoints ────────────────────────────────────
# (kind, id) is the universal address for every Studio record.

@knowledge_bp.route('/api/records/_kinds', methods=['GET'])
def api_records_kinds():
    from core.records import KINDS
    return jsonify({'ok': True, 'kinds': [k for k, *_ in KINDS]})


@knowledge_bp.route('/api/records/<kind>', methods=['GET'])
def api_records_list(kind: str):
    from core.records import RECORDS_ROOT, KINDS
    import json as _json
    valid = {k for k, *_ in KINDS}
    if kind not in valid:
        return jsonify({'ok': False, 'error': f'unknown kind: {kind}'}), 404
    base = RECORDS_ROOT / kind
    items = []
    if base.exists():
        for path in base.rglob('*.json'):
            try:
                d = _json.loads(path.read_text(encoding='utf-8'))
                data = d.get('data', {})
                items.append({
                    'id': d.get('id'),
                    'title': data.get('title') or data.get('name') or data.get('subject') or data.get('doc_name'),
                    'status': data.get('status'),
                    'project_id': data.get('project_id'),
                    'updated_at': data.get('updated_at') or data.get('created_at'),
                    'path': str(path.relative_to(RECORDS_ROOT.parent.parent)),
                })
            except Exception:
                continue
    items.sort(key=lambda r: (r.get('updated_at') or 0), reverse=True)
    q = (request.args.get('q') or '').lower()
    if q:
        items = [i for i in items if q in (i.get('title') or '').lower() or q in (i.get('id') or '').lower()]
    return jsonify({'ok': True, 'kind': kind, 'count': len(items), 'items': items[:500]})


@knowledge_bp.route('/api/records/<kind>/<rid>', methods=['GET'])
def api_record_detail(kind: str, rid: str):
    from core.records import load_record, record_path, record_md_path, RECORDS_ROOT
    from core.records.links import neighbours
    from core.records.promote import promotion_chain
    payload = load_record(kind, rid)
    if not payload:
        return jsonify({'ok': False, 'error': 'record not found'}), 404
    # Find the on-disk paths so the UI can show 'Open file' links.
    json_path = None
    md = None
    base = RECORDS_ROOT / kind
    if base.exists():
        for p in base.rglob(f'{rid}.json'):
            json_path = str(p.relative_to(RECORDS_ROOT.parent.parent))
            md_p = p.with_suffix('.md')
            if md_p.exists():
                try:
                    md = md_p.read_text(encoding='utf-8')
                except Exception:
                    md = None
            break
    return jsonify({
        'ok': True,
        'record': payload,
        'json_path': json_path,
        'markdown': md,
        'links': neighbours(kind, rid),
        'chain': [{'kind': k, 'id': i} for k, i in promotion_chain(kind, rid)],
    })


@knowledge_bp.route('/api/records/<kind>/<rid>/links', methods=['POST'])
def api_record_link(kind: str, rid: str):
    from core.records.links import link as _link
    body = request.get_json(silent=True) or {}
    rel = (body.get('rel') or '').strip()
    dst_kind = (body.get('dst_kind') or '').strip()
    dst_id = (body.get('dst_id') or '').strip()
    if not (rel and dst_kind and dst_id):
        return jsonify({'ok': False, 'error': 'rel, dst_kind, dst_id required'}), 400
    _link((kind, rid), rel, (dst_kind, dst_id), actor=str(body.get('actor') or 'ui'))
    return jsonify({'ok': True})


@knowledge_bp.route('/api/records/<kind>/<rid>/promote', methods=['POST'])
def api_record_promote(kind: str, rid: str):
    from core.records.promote import promote as _promote
    body = request.get_json(silent=True) or {}
    dst_kind = (body.get('dst_kind') or '').strip()
    if not dst_kind:
        return jsonify({'ok': False, 'error': 'dst_kind required'}), 400
    try:
        new_kind, new_id = _promote(kind, rid, dst_kind,
                                    overrides=body.get('overrides'),
                                    actor=str(body.get('actor') or 'ui'))
    except KeyError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'kind': new_kind, 'id': new_id})


# ── Platinum: content-addressed attachments ────────────────────────────

@knowledge_bp.route('/api/records/attachments', methods=['POST'])
def api_attachments_upload():
    """Accept either multipart form-data ('file') or raw bytes; return sha256."""
    from core.records import attachments as _attach
    blob = None
    ext = None
    f = request.files.get('file') if request.files else None
    if f is not None:
        blob = f.read()
        fname = f.filename or ''
        if '.' in fname:
            ext = fname.rsplit('.', 1)[-1]
    else:
        blob = request.get_data() or b''
        ext = (request.args.get('ext') or '').lstrip('.')
    if not blob:
        return jsonify({'ok': False, 'error': 'empty payload'}), 400
    digest = _attach.put(blob, ext=ext or 'bin')
    p = _attach.find(digest)
    return jsonify({
        'ok': True,
        'sha256': digest,
        'bytes': len(blob),
        'path': str(p.relative_to(p.parents[2])) if p else None,
    })


@knowledge_bp.route('/api/records/attachments/<sha256>', methods=['GET'])
def api_attachments_get(sha256: str):
    """Stream the binary back. 404 if unknown."""
    from core.records import attachments as _attach
    from flask import send_file
    import re as _re
    if not _re.fullmatch(r'[0-9a-fA-F]{64}', sha256):
        return jsonify({'ok': False, 'error': 'bad sha256'}), 400
    p = _attach.find(sha256.lower())
    if not p or not p.exists():
        return jsonify({'ok': False, 'error': 'attachment not found'}), 404
    return send_file(str(p),
                     as_attachment=False,
                     download_name=p.name,
                     mimetype='application/octet-stream')


@knowledge_bp.route('/api/records/_browse', methods=['GET'])
def api_records_browse():
    """Browser-style directory listing under runtime/records/ ONLY.

    Used by the Files tile (Platinum slice 4). Hardened against path
    traversal: any resolved path escaping RECORDS_ROOT is rejected.
    """
    from core.records import RECORDS_ROOT
    from pathlib import Path as _P
    rel = (request.args.get('path') or '').lstrip('/').strip()
    base = RECORDS_ROOT
    try:
        target = (base / rel).resolve()
        base_resolved = base.resolve()
        if not str(target).startswith(str(base_resolved)):
            return jsonify({'ok': False, 'error': 'path escapes runtime/records/'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'bad path: {e}'}), 400
    if not target.exists():
        return jsonify({'ok': False, 'error': 'path not found'}), 404
    if not target.is_dir():
        return jsonify({'ok': False, 'error': 'not a directory'}), 400
    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            stat = child.stat()
            entries.append({
                'name': child.name,
                'is_dir': child.is_dir(),
                'size': stat.st_size if child.is_file() else None,
                'mtime': stat.st_mtime,
                'rel': str(child.relative_to(base_resolved)),
            })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    parent = None
    if rel:
        parent_path = _P(rel).parent
        parent = '' if str(parent_path) == '.' else str(parent_path)
    return jsonify({
        'ok': True,
        'path': rel,
        'parent': parent,
        'count': len(entries),
        'entries': entries,
    })


@knowledge_bp.route('/api/knowledge/projects/<project_id>/test-cases', methods=['POST'])
def api_project_add_case(project_id: str):
    body = request.get_json(silent=True) or {}
    title = str(body.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    try:
        case_id = _kc_projects.add_test_case(
            project_id,
            title,
            step_id=body.get('step_id') or None,
            script_id=body.get('script_id') or None,
            owner=str(body.get('owner') or 'seven'),
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    if not case_id:
        return jsonify({'ok': False, 'error': 'could not add test case'}), 500
    return jsonify({'ok': True, 'case_id': case_id})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/test-cases', methods=['GET'])
def api_project_list_cases(project_id: str):
    return jsonify({'ok': True, 'items': _kc_projects.list_test_cases(
        project_id,
        step_id=request.args.get('step_id') or None,
    )})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/blackboard', methods=['GET'])
def api_project_blackboard_list(project_id: str):
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 100))
        status = request.args.get('status')
        if status == 'all':
            status = None
        elif not status:
            status = 'active'
        items = _kc_projects.list_blackboard_notes(project_id, status=status, limit=limit)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    return jsonify({'ok': True, 'items': items})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/context-preview', methods=['GET'])
def api_project_context_preview(project_id: str):
    context = _kc_context_packs.build_project_context_block(project_id=project_id)
    if not context:
        return jsonify({'ok': False, 'error': 'project not found or no context available'}), 404
    return jsonify({
        'ok': True,
        'project_id': project_id,
        'context': context.strip(),
    })


@knowledge_bp.route('/api/knowledge/projects/<project_id>/blackboard', methods=['POST'])
def api_project_blackboard_add(project_id: str):
    body = request.get_json(silent=True) or {}
    content = str(body.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    try:
        note_id = _kc_projects.add_blackboard_note(
            project_id,
            content,
            author=str(body.get('author') or 'seven'),
            kind=str(body.get('kind') or 'note'),
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not note_id:
        return jsonify({'ok': False, 'error': 'could not add note'}), 500
    return jsonify({'ok': True, 'note_id': note_id})


@knowledge_bp.route('/api/knowledge/blackboard/<note_id>', methods=['PATCH'])
def api_project_blackboard_status(note_id: str):
    body = request.get_json(silent=True) or {}
    status = str(body.get('status') or '').strip().lower()
    try:
        ok = _kc_projects.update_blackboard_note_status(note_id, status)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'note not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/projects/<project_id>/link-proposal', methods=['POST'])
def api_project_link_proposal(project_id: str):
    body = request.get_json(silent=True) or {}
    proposal_id = str(body.get('proposal_id') or '').strip()
    if not proposal_id:
        return jsonify({'ok': False, 'error': 'proposal_id required'}), 400
    ok = _kc_projects.link_proposal(project_id, proposal_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'link failed'}), 500
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/cases/<case_id>', methods=['PATCH'])
def api_case_update_status(case_id: str):
    """Transition a test case status (draft/ready/passed/failed/blocked/obsolete)."""
    body = request.get_json(silent=True) or {}
    status = str(body.get('status') or '').strip()
    if status not in _kc_projects.CASE_STATUSES:
        return jsonify({'ok': False, 'error': f'status must be one of {list(_kc_projects.CASE_STATUSES)}'}), 400
    try:
        ok = _kc_projects.update_case_status(case_id, status, owner=body.get('owner') or None)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'case not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/cases/<case_id>', methods=['GET'])
def api_case_detail(case_id: str):
    """ALM detail surface (PACKET-03): full test-case record with parent
    step and recent test runs so the UI can open it."""
    case = _kc_projects.get_test_case(case_id)
    if not case:
        return jsonify({'ok': False, 'error': 'case not found'}), 404
    return jsonify({'ok': True, 'case': case})


# ── Phase 3 — Project / Step / Case edit + delete + per-step test scoping ─

@knowledge_bp.route('/api/knowledge/projects/<project_id>', methods=['DELETE'])
def api_projects_delete(project_id: str):
    ok = _kc_projects.delete_project(project_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'project not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/steps/<step_id>', methods=['DELETE'])
def api_step_delete(step_id: str):
    ok = _kc_projects.delete_step(step_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'step not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/steps/<step_id>/edit', methods=['PATCH'])
def api_step_edit(step_id: str):
    """Edit a step's title/description/owner (separate from status PATCH)."""
    body = request.get_json(silent=True) or {}
    try:
        ok = _kc_projects.update_step(
            step_id,
            title=body.get('title'),
            description=body.get('description'),
            owner=body.get('owner'),
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'step not found or no fields'}), 404
    return jsonify({'ok': True})


# ── Step dependencies (S-98FA0FAEFE) ────────────────────────────────────────

@knowledge_bp.route('/api/knowledge/steps/<step_id>/dependencies', methods=['GET'])
def api_step_deps_list(step_id: str):
    return jsonify({
        'ok': True,
        'depends_on': _kc_projects.list_step_dependencies(step_id),
        'blocks':     _kc_projects.list_step_blockers(step_id),
    })


@knowledge_bp.route('/api/knowledge/steps/<step_id>/dependencies', methods=['POST'])
def api_step_deps_add(step_id: str):
    body = request.get_json(silent=True) or {}
    dep = str(body.get('depends_on') or '').strip()
    if not dep:
        return jsonify({'ok': False, 'error': 'depends_on required'}), 400
    try:
        ok = _kc_projects.add_step_dependency(step_id, dep)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'could not add dependency'}), 500
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/steps/<step_id>/dependencies/<depends_on>', methods=['DELETE'])
def api_step_deps_remove(step_id: str, depends_on: str):
    if _kc_projects.remove_step_dependency(step_id, depends_on):
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'dependency not found'}), 404


@knowledge_bp.route('/api/knowledge/cases/<case_id>', methods=['DELETE'])
def api_case_delete(case_id: str):
    ok = _kc_projects.delete_test_case(case_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'case not found'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/cases/<case_id>/edit', methods=['PATCH'])
def api_case_edit(case_id: str):
    body = request.get_json(silent=True) or {}
    try:
        ok = _kc_projects.update_test_case(
            case_id,
            title=body.get('title'),
            script_id=body.get('script_id'),
            step_id=body.get('step_id'),
            owner=body.get('owner'),
        )
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'case not found or no fields'}), 404
    return jsonify({'ok': True})


@knowledge_bp.route('/api/knowledge/steps/<step_id>/test-scripts', methods=['GET'])
def api_step_test_scripts(step_id: str):
    """Return the Test Lab script_ids tied to this step's cases.

    This is the "only run relevant tests after each step" primitive — the
    UI posts the returned ``script_ids`` to ``/api/studio/testlab/resolve``
    to obtain shell commands, then executes them through the existing
    Test Lab runner.
    """
    cases = _kc_projects.scripts_for_step(step_id)
    return jsonify({
        'ok': True,
        'step_id': step_id,
        'cases': cases,
        'script_ids': [c['script_id'] for c in cases if c.get('script_id')],
    })


@knowledge_bp.route('/api/knowledge/steps/<step_id>/complete', methods=['POST'])
def api_step_complete(step_id: str):
    """Mark a step done AND auto-write a Knowledge Center doc summarising it.

    Body (optional): {summary, files_changed: [..], tests_run: [..]}

    The KB doc is tagged ``auto,step,<project_id>`` so Seven's KC reader
    picks it up next chat turn.
    """
    body = request.get_json(silent=True) or {}
    try:
        ok = _kc_projects.update_step_status(step_id, 'done', owner=body.get('owner') or None)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if not ok:
        return jsonify({'ok': False, 'error': 'step not found'}), 404

    # Best-effort auto-doc into project_docs (Knowledge Center).
    doc_id = None
    try:
        import time as _t
        from utils.db._connection import get_connection as _gc
        # Find the project that owns this step (for tags + title context).
        conn = _gc()
        try:
            row = conn.execute(
                "SELECT s.title AS step_title, s.project_id, p.name AS proj_name "
                "FROM project_steps s LEFT JOIN projects p ON p.project_id=s.project_id "
                "WHERE s.step_id=?",
                (step_id,),
            ).fetchone()
            if row:
                step_title = row['step_title'] or step_id
                project_id = row['project_id'] or ''
                proj_name = row['proj_name'] or project_id
                summary = str(body.get('summary') or '').strip() or \
                    f"Step '{step_title}' completed."
                files = body.get('files_changed') or []
                tests = body.get('tests_run') or []
                lines = [
                    f"# {step_title}",
                    "",
                    f"**Project:** {proj_name} (`{project_id}`)  ",
                    f"**Step:** `{step_id}`  ",
                    f"**Completed:** {_t.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "## Summary",
                    summary,
                ]
                if files:
                    lines += ["", "## Files changed", *[f"- `{f}`" for f in files]]
                if tests:
                    lines += ["", "## Tests run", *[f"- `{t}`" for t in tests]]
                content = "\n".join(lines)
                doc_name = f"auto:step:{step_id}"
                tags = ",".join(filter(None, ['auto', 'step', project_id]))
                conn.execute(
                    "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                    (doc_name, content, tags),
                )
                conn.commit()
                got = conn.execute(
                    "SELECT id FROM project_docs WHERE doc_name=? ORDER BY id DESC LIMIT 1",
                    (doc_name,),
                ).fetchone()
                if got:
                    doc_id = got['id']
        finally:
            conn.close()
    except Exception:
        pass

    return jsonify({'ok': True, 'kb_doc_id': doc_id})


# ── V7C-R17 / A16 — Close-out report + live step probe ─────────────────

@knowledge_bp.route('/api/knowledge/projects/<project_id>/close-out', methods=['GET'])
def api_project_close_out(project_id: str):
    """Return a close-out report: every step, its locked test file(s),
    its latest test-run verdict, and a rolled-up verdict per step.

    Query string: ``format=md`` returns text/markdown instead of JSON
    (S-4DB57C3A23 — closeout markdown export).
    """
    rep = _kc_closeout.build_report(project_id)
    fmt = (request.args.get('format') or '').strip().lower()
    if fmt in ('md', 'markdown'):
        body = _kc_closeout.render_markdown(rep)
        status = 200 if rep.get('ok') else 404
        return body, status, {'Content-Type': 'text/markdown; charset=utf-8'}
    if not rep.get('ok'):
        return jsonify(rep), 404
    return jsonify(rep)


@knowledge_bp.route('/api/knowledge/steps/<step_id>/probe', methods=['POST'])
def api_step_probe(step_id: str):
    """V7C-A16 — replay a step's locked pytest file(s) on demand.

    Body (optional): {"timeout": seconds}. Default 60s, capped at 180.
    Returns parsed pass/fail counts and a short tail of output.
    """
    body = request.get_json(silent=True) or {}
    try:
        timeout = float(body.get('timeout') or 60.0)
    except (TypeError, ValueError):
        timeout = 60.0
    timeout = max(5.0, min(timeout, 180.0))
    rep = _kc_closeout.run_step_probe(step_id, timeout=timeout)
    return jsonify(rep)
