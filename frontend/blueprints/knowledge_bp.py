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
    its latest test-run verdict, and a rolled-up verdict per step."""
    rep = _kc_closeout.build_report(project_id)
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
