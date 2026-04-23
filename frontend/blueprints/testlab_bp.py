"""
blueprints/testlab_bp.py — Studio Test Lab API (Session 28)
═══════════════════════════════════════════════════════════════════════════════
Thin API over ``core.testlab_registry``. The Studio "Test Lab" tab lists
registered scripts, the user ticks which ones to run for a given change, and
the frontend streams each script through the existing `/api/terminal/run`
infrastructure (so ANSI/semantic rendering + hard-kill are reused for free).

Endpoints
---------
GET  /api/studio/testlab/scripts
     Returns the script registry grouped by section, plus some environment
     hints the UI can show (repo root, active virtualenv).

POST /api/studio/testlab/resolve
     Given a list of script ids, returns the concrete shell commands the UI
     should run. Keeps the registry server-side so the UI can't inject
     arbitrary commands.

The actual execution uses `/api/terminal/run` — this blueprint deliberately
does **not** run commands itself, to avoid duplicating the stream / kill /
formatting surface the terminal tile already owns.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

from core.testlab_registry import get_registry, get_entry


testlab_bp = Blueprint('testlab_bp', __name__)


def _group_scripts(scripts):
    """Group scripts by their ``group`` field, preserving registry order."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for entry in scripts:
        g = str(entry.get('group') or 'Other')
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(entry)
    return [{'group': g, 'scripts': groups[g]} for g in order]


@testlab_bp.route('/api/studio/testlab/scripts', methods=['GET'])
def api_testlab_scripts():
    """List all registered Test Lab scripts, grouped by section."""
    scripts = get_registry()
    return jsonify({
        'ok': True,
        'count': len(scripts),
        'groups': _group_scripts(scripts),
        'env': {
            'repo_root': os.environ.get('SWARM_ROOT') or os.getcwd(),
            'venv': os.environ.get('VIRTUAL_ENV') or '',
        },
    })


@testlab_bp.route('/api/studio/testlab/resolve', methods=['POST'])
def api_testlab_resolve():
    """Resolve a list of script ids to concrete shell commands.

    Request body: ``{"script_ids": ["smoke-endpoints", "pytest-full"],
                     "change_id": "1306"}``

    Response: ``{"ok": True, "items": [{"id": ..., "label": ...,
                                        "command": "..."}]}``

    ``change_id`` is passed through verbatim as the ``SWARM_CHANGE_ID`` env
    prefix so change-aware scripts can pick it up if needed.
    """
    body = request.get_json(force=True, silent=True) or {}
    raw_ids = body.get('script_ids') or []
    change_id = str(body.get('change_id') or '').strip()

    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({'ok': False, 'error': 'script_ids must be a non-empty list'}), 400

    items = []
    missing = []
    for sid in raw_ids:
        entry = get_entry(str(sid))
        if not entry:
            missing.append(sid)
            continue
        command = str(entry.get('command') or '')
        # Change-aware scripts get a SWARM_CHANGE_ID prefix so they can opt
        # into per-change behaviour later without breaking current runs.
        if change_id and entry.get('change_aware'):
            command = f'SWARM_CHANGE_ID={change_id!s} ' + command
        items.append({
            'id': entry.get('id'),
            'label': entry.get('label'),
            'description': entry.get('description'),
            'group': entry.get('group'),
            'command': command,
        })

    # Session 29 — spine emit. Best-effort run-marker.
    try:
        from core import spine as _spine
        _spine.log(
            _spine.EventKind.TESTLAB,
            f'Resolved {len(items)} script(s)' + (f' for change {change_id}' if change_id else ''),
            severity=_spine.Severity.INFO,
            source='testlab',
            change_id=(change_id or None),
            payload={
                'ids': [i['id'] for i in items],
                'missing': missing,
            },
        )
    except Exception:
        pass

    # Session 29.2 — persist the selection into Knowledge Center so the UI
    # can recall "what did I run last time for change X?". Best-effort.
    if change_id and items:
        try:
            from core.knowledge import scripts as _kc_scripts
            _kc_scripts.record_change_run(change_id, [i['id'] for i in items])
        except Exception:
            pass

    return jsonify({
        'ok': True,
        'change_id': change_id or None,
        'items': items,
        'missing': missing,
    })
