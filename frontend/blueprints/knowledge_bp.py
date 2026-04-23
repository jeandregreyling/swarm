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

from flask import Blueprint, jsonify, request

from core.knowledge import scripts as _kc_scripts
from core.knowledge import test_runs as _kc_runs
from core.knowledge import projects as _kc_projects

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
    try:
        run_id = _kc_runs.start_run(
            script_id,
            change_id=body.get('change_id') or None,
            command=body.get('command') or None,
            triggered_by=str(body.get('triggered_by') or 'manual'),
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
