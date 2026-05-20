"""frontend.blueprints.hive — HTTP surface for the cross-platform Hive.

Endpoints:

    GET    /api/hive/nodes                — list all enrolled nodes + last telemetry
    GET    /api/hive/node/<node_id>       — single node detail + recent events
    POST   /api/hive/telemetry            — node uploads a contract-v0 envelope
    POST   /api/hive/policy               — executive sets policy on a node
    DELETE /api/hive/node/<node_id>       — deregister a node
    GET    /api/hive/local                — telemetry for THIS host (debug)
    GET    /api/hive/install/<filename>   — serve agent + installer scripts
    GET    /api/hive/install/             — JSON manifest of available installers

Auth model: enrolment tokens land in a later iteration. For now we
accept telemetry from any local-network caller so the Linux node can
talk to itself without ceremony. The validate_telemetry / validate_policy
guards make the surface safe against malformed input.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import io
import tarfile

from flask import Blueprint, Response, jsonify, request, send_from_directory, url_for

from core.hive import (
    HiveRegistry,
    build_local_telemetry,
    build_policy,
    get_registry,
    validate_policy,
    validate_telemetry,
)
from core.hive.contract import ContractError
from core.hive.enrolment import (
    list_tokens,
    mint_token,
    revoke_token,
    verify_token,
)
from utils.db.watchdog_lessons import list_open_repair_lessons

_LOG = logging.getLogger(__name__)

hive_bp = Blueprint('hive', __name__, url_prefix='/api/hive')


def _registry() -> HiveRegistry:
    return get_registry()


def _err(msg: str, status: int = 400) -> Any:
    return jsonify({'ok': False, 'error': msg}), status


_EXPECTED_FARM_NODES = (
    {
        'node_id': 'potato-1',
        'label': 'potato-1 Leader',
        'platform': 'linux',
        'capabilities': ['scheduler.coordinator', 'inference.cpu', 'inference.ollama'],
    },
    {
        'node_id': 'potato-2',
        'label': 'potato-2 Samsung S9 FE',
        'platform': 'android',
        'capabilities': ['scheduler.worker', 'inference.cpu', 'inference.gpu', 'inference.tflite'],
    },
    {
        'node_id': 'potato-3',
        'label': 'potato-3 MacBook',
        'platform': 'macos',
        'capabilities': ['scheduler.worker', 'inference.cpu'],
    },
    {
        'node_id': 'potato-4',
        'label': 'potato-4 Dell',
        'platform': 'linux/windows',
        'capabilities': ['scheduler.worker', 'inference.cpu'],
    },
)


def _with_expected_farm_nodes(nodes: list[dict]) -> list[dict]:
    """Add expected farm nodes so every client renders the same roster."""
    seen = {str(n.get('node_id') or '').lower() for n in nodes}
    merged = list(nodes)
    for expected in _EXPECTED_FARM_NODES:
        if expected['node_id'].lower() in seen:
            continue
        merged.append({
            'node_id': expected['node_id'],
            'platform': expected['platform'],
            'enrolled_ts': None,
            'last_seen_ts': None,
            'age_s': None,
            'label': expected['label'],
            'notes': 'expected potato farm node; waiting for telemetry',
            'offline': True,
            'expected': True,
            'telemetry': {
                'contract': 'node.resource/v0',
                'node_id': expected['node_id'],
                'platform': expected['platform'],
                'ts': 0,
                'capabilities': expected['capabilities'],
                'compute': {
                    'cpu_load_pct': None,
                    'cpu_peak_temp_c': None,
                    'cpu_throttled': None,
                    'gpu_present': 'inference.gpu' in expected['capabilities'],
                    'gpu_load_pct': None,
                    'gpu_temp_c': None,
                    'npu_present': 'inference.npu' in expected['capabilities'],
                },
                'thermal': {
                    'fan_rpm': None,
                    'fan_pwm': None,
                    'fan_max_rpm': None,
                    'fan_mode': 'unknown',
                    'controllable': False,
                },
                'memory': {
                    'ram_total_mb': None,
                    'ram_free_mb': None,
                    'swap_used_mb': None,
                },
                'power': {
                    'on_battery': False,
                    'battery_pct': None,
                    'thermal_pressure': 'nominal',
                },
            },
            'policy': None,
        })
    return merged


@hive_bp.get('/nodes')
def list_nodes():
    max_age = request.args.get('max_age_s', type=int)
    nodes = _registry().list_nodes(max_age_s=max_age)
    if request.args.get('expected', '1') != '0':
        nodes = _with_expected_farm_nodes(nodes)
    return jsonify({'ok': True, 'count': len(nodes), 'nodes': nodes})


@hive_bp.get('/node/<node_id>')
def get_node(node_id: str):
    reg = _registry()
    node = reg.get_node(node_id)
    if not node:
        return _err(f'unknown node {node_id!r}', 404)
    events = reg.recent_events(node_id=node_id, limit=50)
    return jsonify({'ok': True, 'node': node, 'events': events})


@hive_bp.post('/telemetry')
def post_telemetry():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _err('expected JSON object', 400)
    try:
        validate_telemetry(payload)
    except ContractError as e:
        return _err(f'contract violation: {e}', 422)
    ok, reason = _check_token_for_telemetry(payload)
    if not ok:
        return _err(reason or 'unauthorized', 401)
    reg = _registry()
    reg.record_telemetry(payload)
    return jsonify({'ok': True, 'node_id': payload['node_id'], 'ts': payload['ts']})


@hive_bp.post('/policy')
def post_policy():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _err('expected JSON object', 400)

    # Two acceptance modes:
    #   1. Already-built envelope: validate_policy.
    #   2. Convenience kwargs: build_policy(...) from individual fields.
    if payload.get('contract'):
        try:
            validate_policy(payload)
        except ContractError as e:
            return _err(f'contract violation: {e}', 422)
        envelope = payload
    else:
        node_id = payload.get('node_id')
        if not isinstance(node_id, str) or not node_id:
            return _err('node_id required', 400)
        try:
            envelope = build_policy(
                node_id,
                fan_mode=payload.get('fan_mode'),
                boost_exit_temp_c=payload.get('boost_exit_temp_c'),
                max_load_pct=payload.get('max_load_pct'),
                accept_jobs=payload.get('accept_jobs'),
            )
        except ContractError as e:
            return _err(f'contract violation: {e}', 422)

    try:
        _registry().set_policy(envelope)
    except KeyError as e:
        return _err(str(e), 404)
    return jsonify({'ok': True, 'policy': envelope})


@hive_bp.delete('/node/<node_id>')
def delete_node(node_id: str):
    reg = _registry()
    if not reg.get_node(node_id):
        return _err(f'unknown node {node_id!r}', 404)
    reg.remove(node_id)
    return jsonify({'ok': True, 'removed': node_id})


@hive_bp.get('/local')
def local_telemetry():
    """Debug endpoint — telemetry sample for the host running Fridays."""
    try:
        payload = build_local_telemetry()
    except Exception as e:
        _LOG.exception('build_local_telemetry failed')
        return _err(f'local sample failed: {e}', 500)
    return jsonify({'ok': True, 'telemetry': payload})


# ── Enrolment ────────────────────────────────────────────────────────────

@hive_bp.post('/enrol')
def enrol_node():
    """Mint a token for a node. Body: {node_id, label?, platform?}."""
    payload = request.get_json(silent=True) or {}
    node_id = payload.get('node_id')
    if not isinstance(node_id, str) or not node_id:
        return _err('node_id required', 400)
    label = payload.get('label') or ''
    platform = payload.get('platform') or 'unknown'
    reg = _registry()
    reg.enrol(node_id, platform, label=label, notes=payload.get('notes', ''))
    token = mint_token(node_id, label=label)
    return jsonify({'ok': True, 'node_id': node_id, 'token': token})


@hive_bp.post('/revoke/<node_id>')
def revoke_node(node_id: str):
    removed = revoke_token(node_id)
    return jsonify({'ok': True, 'node_id': node_id, 'revoked': removed})


@hive_bp.get('/tokens')
def tokens_list():
    return jsonify({'ok': True, 'tokens': list_tokens()})


def _check_token_for_telemetry(payload: dict) -> tuple[bool, str | None]:
    """Soft-auth: only enforce when SWARM_HIVE_REQUIRE_TOKEN=1.

    First-touch telemetry from a not-yet-enrolled node is allowed when
    auth is off; this keeps the local Linux node working out of the box
    while still letting operators enable strict mode for remote nodes.
    """
    import os as _os
    if _os.environ.get('SWARM_HIVE_REQUIRE_TOKEN') != '1':
        return True, None
    node_id = payload.get('node_id')
    token = request.headers.get('X-Hive-Token')
    if not verify_token(node_id, token):
        return False, 'invalid or missing X-Hive-Token'
    return True, None


# ---- install surface ------------------------------------------------------
#
# Lets a fresh device enrol with a single curl/irm one-liner instead of
# requiring a git clone. We serve a small, fixed set of files from the
# repo's ops/ tree — the agent itself plus the per-platform installers
# and their bootstrap shims — and reject anything else.

_INSTALL_FILES: dict[str, tuple[str, str]] = {
    # filename                  -> (path relative to repo root, mime type)
    'agent.py':                  ('ops/hive_agent.py',                       'text/x-python'),
    'hive_agent.py':             ('ops/hive_agent.py',                       'text/x-python'),
    'install_linux.sh':          ('ops/install/install_linux.sh',            'text/x-shellscript'),
    'install_macos.sh':          ('ops/install/install_macos.sh',            'text/x-shellscript'),
    'install_termux.sh':         ('ops/install/install_termux.sh',           'text/x-shellscript'),
    'install_windows.ps1':       ('ops/install/install_windows.ps1',         'text/plain'),
    'bootstrap.sh':              ('ops/install/bootstrap.sh',                'text/x-shellscript'),
    'bootstrap.ps1':             ('ops/install/bootstrap.ps1',               'text/plain'),
    'hive_installer_core.py':    ('ops/install/hive_installer_core.py',      'text/x-python'),
    'hive_installer_gui.py':     ('ops/install/hive_installer_gui.py',       'text/x-python'),
    'termux_runner.py':          ('core/hive/termux_runner.py',              'text/x-python'),
    'swarm-hive.apk':            ('ops/install/android/swarm-hive.apk',      'application/vnd.android.package-archive'),
    'seven-app.apk':             ('ops/install/android/seven-app.apk',       'application/vnd.android.package-archive'),
    'seven-app-v1.0.4.apk':      ('ops/install/android/seven-app-v1.0.4.apk','application/vnd.android.package-archive'),
    'seven-app-v1.0.0.apk':      ('ops/install/android/seven-app-v1.0.0.apk','application/vnd.android.package-archive'),
    'seven-app-v1.0.1.apk':      ('ops/install/android/seven-app-v1.0.1.apk','application/vnd.android.package-archive'),
    'seven-app-v1.0.2.apk':      ('ops/install/android/seven-app-v1.0.2.apk','application/vnd.android.package-archive'),
    'seven-app-v1.0.3.apk':      ('ops/install/android/seven-app-v1.0.3.apk','application/vnd.android.package-archive'),
    't':                         ('ops/install/termux_quick.sh',             'text/x-shellscript'),
    'README.md':                 ('ops/install/README.md',                   'text/markdown'),
}


def _repo_root() -> Path:
    # frontend/blueprints/hive.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


@hive_bp.get('/install/android')
def install_android_page():
    """HTML landing page for Android users — open in tablet browser, tap to install."""
    leader = request.host_url.rstrip('/')
    apk_url = f'{leader}/api/hive/install/seven-app.apk'
    v104_url = f'{leader}/api/hive/install/seven-app-v1.0.4.apk'
    v103_url = f'{leader}/api/hive/install/seven-app-v1.0.3.apk'
    v102_url = f'{leader}/api/hive/install/seven-app-v1.0.2.apk'
    v101_url = f'{leader}/api/hive/install/seven-app-v1.0.1.apk'
    v100_url = f'{leader}/api/hive/install/seven-app-v1.0.0.apk'
    old_url = f'{leader}/api/hive/install/swarm-hive.apk'
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seven — Android Install</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 2rem; background: #0b0f19; color: #e0e6f1; }}
  .card {{ max-width: 420px; margin: auto; background: #151b2b; border-radius: 16px; padding: 2rem; box-shadow: 0 8px 32px rgba(0,0,0,.4); }}
  h1 {{ margin: 0 0 .5rem; font-size: 1.5rem; }}
  p {{ line-height: 1.5; color: #a0aec0; }}
  .btn {{ display: block; width: 100%; padding: 1rem; margin: 1.5rem 0 0; font-size: 1.1rem; font-weight: 600; text-align: center; text-decoration: none; color: #0b0f19; background: #4fd1c5; border-radius: 10px; border: none; cursor: pointer; }}
  .btn:hover {{ background: #38b2ac; }}
  .btn-secondary {{ display: block; width: 100%; padding: .7rem; margin: .5rem 0 0; font-size: .9rem; font-weight: 500; text-align: center; text-decoration: none; color: #a0aec0; background: #0b0f19; border-radius: 8px; border: 1px solid #2d3748; cursor: pointer; }}
  .btn-secondary:hover {{ background: #1a202c; color: #e0e6f1; }}
  code {{ background: #0b0f19; padding: .15rem .4rem; border-radius: 6px; font-size: .9rem; color: #4fd1c5; }}
  .steps {{ margin-top: 1.5rem; padding-left: 1.2rem; }}
  .steps li {{ margin-bottom: .6rem; color: #a0aec0; }}
  .warn {{ color: #f6ad55; font-size: .9rem; margin-top: 1rem; }}
  .feature {{ font-size: .85rem; color: #68d391; margin-top: .8rem; }}
  .version {{ font-size: .8rem; color: #718096; margin-top: .5rem; }}
  .archive {{ margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2d3748; }}
  .archive-title {{ font-size: .85rem; color: #718096; margin-bottom: .5rem; }}
</style>
</head>
<body>
<div class="card">
  <h1>🤖 Seven for Android</h1>
  <p>Install the <strong>Seven</strong> app on your Samsung S9 FE tablet. Chat with the swarm, view Hive nodes, and manage settings.</p>
    <p class="version">Latest: v1.0.4 (5.5 MB) · signed · GPU packet handoff</p>
  <a class="btn" href="{apk_url}" download>⬇ Download Seven App</a>
  <p class="warn">⚠ You may need to allow “Install unknown apps” for your browser when prompted.</p>
  <ol class="steps">
    <li>Tap the button above to download <code>seven-app.apk</code>.</li>
    <li>Open the downloaded file and tap <strong>Install</strong>.</li>
    <li>Open the <strong>Seven</strong> app.</li>
    <li>Enter Leader URL: <code>http://100.87.66.45:5050</code></li>
    <li>Tap <strong>Save</strong>. Done!</li>
  </ol>
  <p class="feature">✅ Features: Chat · Nodes Grid · Settings · Material Design 3</p>
  <div class="archive">
    <p class="archive-title">📦 Version Archive</p>
        <a class="btn-secondary" href="{v104_url}" download>v1.0.4 — GPU packet handoff</a>
    <a class="btn-secondary" href="{v103_url}" download>v1.0.3 — sundial system status</a>
    <a class="btn-secondary" href="{v102_url}" download>v1.0.2 — potato status + resource sharing</a>
    <a class="btn-secondary" href="{v101_url}" download>v1.0.1 — launch crash fix</a>
    <a class="btn-secondary" href="{v100_url}" download>v1.0.0 — seven-app-v1.0.0.apk</a>
    <a class="btn-secondary" href="{old_url}" download>v0.2.0 — swarm-hive.apk (old agent)</a>
  </div>
</div>
</body>
</html>'''
    return Response(html, mimetype='text/html')


@hive_bp.get('/install/')
@hive_bp.get('/install')
def install_manifest():
    """List the installer artefacts the leader is willing to serve."""
    leader = request.host_url.rstrip('/')
    files = []
    root = _repo_root()
    for name, (rel, mime) in _INSTALL_FILES.items():
        p = root / rel
        files.append({
            'name': name,
            'mime': mime,
            'size': p.stat().st_size if p.exists() else None,
            'available': p.exists(),
            'url': f'{leader}/api/hive/install/{name}',
        })
    # Synthetic asset built on demand from the live core/hive/ tree.
    core_hive_dir = root / 'core' / 'hive'
    files.append({
        'name': 'core_hive.tar.gz',
        'mime': 'application/gzip',
        'size': None,
        'available': core_hive_dir.is_dir(),
        'url': f'{leader}/api/hive/install/core_hive.tar.gz',
        'note': 'built-on-demand tar.gz of core/hive runtime',
        'built_on_demand': True,
    })
    return jsonify({
        'ok': True,
        'leader': leader,
        'one_liners': {
            'linux_macos': (
                f"curl -fsSL {leader}/api/hive/install/bootstrap.sh "
                f"| SWARM_HIVE_LEADER={leader} bash"
            ),
            'windows': (
                f"$env:SWARM_HIVE_LEADER='{leader}'; "
                f"irm {leader}/api/hive/install/bootstrap.ps1 | iex"
            ),
        },
        'click_through': {
            'gui_installer': f'{leader}/api/hive/install/hive_installer_gui.py',
            'instructions': (
                'Save the file, then double-click it (Python 3.10+ required). '
                'A wizard opens — click Next, paste the leader URL above, click Install.'
            ),
        },
        'files': files,
    })


@hive_bp.get('/install/<path:filename>')
def install_file(filename: str):
    """Serve a single installer artefact from the repo's ops/ tree.

    Special case: ``core_hive.tar.gz`` is built on the fly from the live
    ``core/hive/`` tree so the bootstrap script can stage the agent's
    Python dependencies on a fresh host (Termux, Linux, macOS) without a
    git clone. The tarball strips ``__pycache__`` and contains a
    top-level ``core/hive/`` path so it extracts cleanly into a stage
    dir.
    """
    if filename == 'core_hive.tar.gz':
        return _serve_core_hive_tarball()
    entry = _INSTALL_FILES.get(filename)
    if entry is None:
        return _err(f'unknown install asset {filename!r}', 404)
    rel, mime = entry
    p = _repo_root() / rel
    if not p.exists():
        return _err(f'install asset missing on leader: {filename!r}', 503)
    return send_from_directory(
        directory=str(p.parent),
        path=p.name,
        mimetype=mime,
        as_attachment=False,
        download_name=filename,
    )


# ── Job queue -----------------------------------------------------------

@hive_bp.post('/jobs/submit')
def submit_job():
    """Submit a job to the Hive queue.

    Body: {kind, payload, capability_req?, node_id?}
    """
    payload = request.get_json(silent=True) or {}
    kind = payload.get('kind')
    if not isinstance(kind, str) or not kind:
        return _err('kind required', 400)
    body = payload.get('payload') or {}
    node_id = payload.get('node_id') or body.get('target_node')
    if node_id is not None and not isinstance(node_id, str):
        return _err('node_id must be a string', 400)
    job_id = _registry().submit_job(
        kind,
        body,
        capability_req=payload.get('capability_req'),
        node_id=node_id or None,
    )
    return jsonify({'ok': True, 'job_id': job_id, 'node_id': node_id or None})


@hive_bp.post('/jobs/next')
def claim_next_job():
    """Node claims the next available job matching its capabilities.

    Body: {node_id, capabilities[]}
    """
    payload = request.get_json(silent=True) or {}
    node_id = payload.get('node_id')
    caps = payload.get('capabilities') or []
    if not isinstance(node_id, str) or not node_id:
        return _err('node_id required', 400)
    if not isinstance(caps, list):
        return _err('capabilities must be a list', 400)
    job = _registry().claim_next_job(node_id, caps)
    if job is None:
        return jsonify({'ok': True, 'job': None})
    return jsonify({'ok': True, 'job': job})


@hive_bp.post('/jobs/report')
def report_job_result():
    """Report job completion.

    Body: {job_id, result}
    """
    payload = request.get_json(silent=True) or {}
    job_id = payload.get('job_id')
    result = payload.get('result')
    if not isinstance(job_id, str) or not job_id:
        return _err('job_id required', 400)
    ok = _registry().report_job_result(job_id, result or {})
    return jsonify({'ok': ok, 'job_id': job_id})


@hive_bp.get('/jobs')
def list_jobs():
    """List jobs in the queue. Query: ?status=pending|claimed|completed"""
    status = request.args.get('status')
    jobs = _registry().list_jobs(status=status, limit=200)
    return jsonify({'ok': True, 'count': len(jobs), 'jobs': jobs})


@hive_bp.get('/lessons')
def list_lessons():
    """Return open Watchdog repair lessons so agents can self-heal."""
    limit = request.args.get('limit', 20, type=int)
    lessons = list_open_repair_lessons(limit=limit)
    return jsonify({'ok': True, 'count': len(lessons), 'lessons': lessons})


def _serve_core_hive_tarball() -> Response:
    """Build and stream a tar.gz of the runtime ``core/hive/`` tree.

    Built fresh per request — small (<50 KB) and rare. We deliberately
    do not cache: the leader is the source of truth and node operators
    need the latest contract files.
    """
    src = _repo_root() / 'core' / 'hive'
    if not src.is_dir():
        return _err('core/hive/ not present on leader', 503)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for path in sorted(src.rglob('*')):
            if '__pycache__' in path.parts:
                continue
            if path.suffix in {'.pyc', '.pyo'}:
                continue
            arcname = 'core/hive/' + str(path.relative_to(src)).replace('\\', '/')
            tar.add(str(path), arcname=arcname, recursive=False)
    data = buf.getvalue()
    return Response(
        data,
        mimetype='application/gzip',
        headers={
            'Content-Disposition': 'attachment; filename="core_hive.tar.gz"',
            'Content-Length': str(len(data)),
        },
    )
