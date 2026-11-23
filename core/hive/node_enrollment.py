"""core.hive.node_enrollment — First-boot & cross-platform potato-node enrollment.

When Hummingbird is deployed on a new host (e.g., Dell OptiPlex potato node,
MacBook, Linux box, or AMD rig), enrollment binds:
  1. Persistent node identity (``node_id``, ``label``, ``role``)
  2. Hardware fingerprint + probed runtimes
  3. Local model assignments for ``apex``, ``fred`` (deep/counsel/review), and
     ``hb`` (fast coordinator/homework)
  4. Shareable peer manifest (what this node can share with other potato nodes)
  5. Optional leader URL for joining an existing Hive mesh

Also provides ``discover_peer_capabilities`` and ``find_peer_for_model`` so
nodes can see what every enrolled potato node can run and share.
"""
from __future__ import annotations

import json
import logging
import os
import platform as _platform
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from .system_profile import (
    build_shareable_manifest,
    collect_system_profile,
)

_LOG = logging.getLogger(__name__)

VALID_ROLES = ('leader', 'worker', 'standalone')


def enrollment_path() -> Path:
    """Resolve the persistent node enrollment JSON path."""
    override = os.environ.get('SWARM_NODE_ENROLLMENT', '').strip()
    if override:
        return Path(override)
    if _platform.system().lower() == 'windows':
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('SWARM_ROOT') or str(Path(__file__).resolve().parents[2])
        return Path(base) / 'Fridays' / 'node_enrollment.json'
    root = os.environ.get('SWARM_ROOT') or str(Path(__file__).resolve().parents[2])
    return Path(root) / 'runtime' / 'node_enrollment.json'


def load_enrollment(path: Path | str | None = None) -> dict[str, Any] | None:
    """Load the saved node enrollment dict, or None if not yet enrolled."""
    target = Path(path) if path else enrollment_path()
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except Exception:
        _LOG.debug('Failed to read node enrollment at %s', target, exc_info=True)
        return None


def save_enrollment(record: dict[str, Any], path: Path | str | None = None) -> Path:
    """Atomically persist the node enrollment record."""
    target = Path(path) if path else enrollment_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(tmp, target)
    return target


def enrolled_node_id(path: Path | str | None = None) -> str | None:
    rec = load_enrollment(path)
    if rec and isinstance(rec.get('node_id'), str) and rec['node_id'].strip():
        return rec['node_id'].strip()
    return None


def enrolled_role_models(path: Path | str | None = None) -> dict[str, str]:
    """Return {role: model} from enrollment, mapping fred->deep/counsel/review and hb->homework."""
    rec = load_enrollment(path)
    if not rec or not isinstance(rec.get('models'), dict):
        return {}
    raw = rec['models']
    out: dict[str, str] = {}
    apex = str(raw.get('apex') or '').strip()
    fred = str(raw.get('fred') or '').strip()
    hb = str(raw.get('hb') or '').strip()
    if apex:
        out['apex'] = apex
    if fred:
        out['fred'] = fred
        out['deep'] = fred
        out['counsel'] = fred
        out['review'] = fred
    if hb:
        out['hb'] = hb
        out['homework'] = hb
    return out


def _sync_hb_roles_db(models: dict[str, str | None], actor: str = 'node-enrollment') -> dict[str, str]:
    """Persist APEX/FRED/HB role selections into the hb_roles SQLite table."""
    applied: dict[str, str] = {}
    mapping = {
        'apex': models.get('apex'),
        'deep': models.get('fred'),
        'counsel': models.get('fred'),
        'review': models.get('fred'),
        'homework': models.get('hb'),
        'hb': models.get('hb'),
    }
    try:
        from utils.db._connection import get_connection
        from core import hb_roles
        with closing(get_connection()) as conn, conn:
            hb_roles.ensure_schema(conn)
            now = time.time()
            for role, model in mapping.items():
                if not model:
                    continue
                conn.execute(
                    'INSERT INTO hb_roles(role, model, set_by, updated_at) VALUES (?,?,?,?) '
                    'ON CONFLICT(role) DO UPDATE SET model=excluded.model, '
                    'set_by=excluded.set_by, updated_at=excluded.updated_at',
                    (role, str(model).strip(), actor[:80], now),
                )
                applied[role] = str(model).strip()
    except Exception:
        _LOG.debug('Could not sync hb_roles DB during node enrollment', exc_info=True)
    return applied


def enroll_local_node(
    *,
    node_id: str | None = None,
    label: str | None = None,
    role: str = 'worker',
    leader_url: str = '',
    endpoint_url: str = '',
    models: dict[str, str | None] | None = None,
    share: dict[str, Any] | None = None,
    path: Path | str | None = None,
    sync_db: bool = True,
    record_registry: bool = True,
) -> dict[str, Any]:
    """Enroll (or re-enroll) THIS host with hardware awareness + APEX/FRED/HB models."""
    role_clean = str(role or 'worker').strip().lower()
    if role_clean not in VALID_ROLES:
        raise ValueError(f'role must be one of {VALID_ROLES}, got {role!r}')

    profile = collect_system_profile(force=True)
    hw = profile['hardware']
    rt = profile['runtimes']
    rec_models = profile['recommended_models']

    existing = load_enrollment(path) or {}
    from .local_node import _default_node_id, reset_local_node

    chosen_node_id = (
        str(node_id or '').strip()
        or str(existing.get('node_id') or '').strip()
        or _default_node_id(hw.get('os') or 'generic')
    )
    default_label = ' '.join(p for p in (hw.get('manufacturer'), hw.get('model')) if p).strip() or hw.get('hostname') or chosen_node_id
    chosen_label = str(label or '').strip() or str(existing.get('label') or '').strip() or default_label

    in_models = models if isinstance(models, dict) else {}
    ex_models = existing.get('models') if isinstance(existing.get('models'), dict) else {}
    resolved_models = {
        'apex': (str(in_models.get('apex') or '').strip()
                 or str(ex_models.get('apex') or '').strip()
                 or (rec_models.get('apex') or {}).get('model')),
        'fred': (str(in_models.get('fred') or '').strip()
                 or str(ex_models.get('fred') or '').strip()
                 or (rec_models.get('fred') or {}).get('model')),
        'hb': (str(in_models.get('hb') or '').strip()
               or str(ex_models.get('hb') or '').strip()
               or (rec_models.get('hb') or {}).get('model')),
    }

    in_share = share if isinstance(share, dict) else {}
    ex_share = existing.get('share') if isinstance(existing.get('share'), dict) else {}
    share_cfg = {
        'accept_remote_jobs': bool(in_share.get('accept_remote_jobs', ex_share.get('accept_remote_jobs', True))),
        'max_concurrent_jobs': int(in_share.get('max_concurrent_jobs', ex_share.get('max_concurrent_jobs', 1 if not hw.get('has_discrete_gpu') else 2))),
        'ram_reserve_mb': int(in_share.get('ram_reserve_mb', ex_share.get('ram_reserve_mb', 4096))),
        'shared_models': in_share.get('shared_models', ex_share.get('shared_models')),
    }

    port = os.environ.get('PORT', '5050')
    chosen_endpoint = (
        str(endpoint_url or '').strip()
        or str(existing.get('endpoint_url') or '').strip()
        or f'http://127.0.0.1:{port}'
    )
    chosen_leader = (
        str(leader_url or '').strip()
        or str(existing.get('leader_url') or '').strip()
    )

    record = {
        'enrolled': True,
        'enrolled_at': int(time.time()),
        'node_id': chosen_node_id,
        'label': chosen_label,
        'role': role_clean,
        'leader_url': chosen_leader,
        'endpoint_url': chosen_endpoint,
        'models': resolved_models,
        'share': share_cfg,
        'hardware': {
            'hostname': hw.get('hostname'),
            'os': hw.get('os'),
            'manufacturer': hw.get('manufacturer'),
            'model': hw.get('model'),
            'cpu_model': hw.get('cpu_model'),
            'cpu_cores': hw.get('cpu_cores'),
            'cpu_threads': hw.get('cpu_threads'),
            'ram_total_mb': hw.get('ram_total_mb'),
            'has_discrete_gpu': hw.get('has_discrete_gpu'),
            'primary_backend': hw.get('primary_backend'),
            'tier': hw.get('tier'),
            'gpus': hw.get('gpus'),
        },
    }
    record['shareable'] = build_shareable_manifest(hw, rt, record)
    saved_to = save_enrollment(record, path=path)

    # Refresh LocalNode singleton so it immediately adopts the enrolled node_id
    reset_local_node()

    synced_roles: dict[str, str] = {}
    if sync_db:
        synced_roles = _sync_hb_roles_db(resolved_models, actor=f'enroll:{chosen_node_id}')

    if record_registry:
        try:
            from .local_node import build_local_telemetry
            from .registry import get_registry
            payload = build_local_telemetry(node_id=chosen_node_id)
            reg = get_registry()
            reg.record_telemetry(payload, label=chosen_label, notes=f"{hw.get('tier')} ({hw.get('primary_backend')})")
        except Exception:
            _LOG.debug('Could not update HiveRegistry during enrollment', exc_info=True)

    leader_push: dict[str, Any] | None = None
    if chosen_leader and role_clean != 'leader':
        leader_push = push_telemetry_to_leader(
            leader_url=chosen_leader,
            node_id=chosen_node_id,
            label=chosen_label,
            notes=f"{hw.get('tier')} ({hw.get('primary_backend')})",
        )

    return {
        'enrollment': record,
        'saved_to': str(saved_to),
        'synced_roles': synced_roles,
        'recommended_models': rec_models,
        'leader_push': leader_push,
    }


def push_telemetry_to_leader(
    *,
    leader_url: str = '',
    node_id: str | None = None,
    label: str | None = None,
    notes: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Push this node's full telemetry (including system_profile + shareable) to a Hive leader."""
    import urllib.request
    import urllib.error

    enr = load_enrollment() or {}
    target = (str(leader_url or '').strip() or str(enr.get('leader_url') or '').strip()).rstrip('/')
    if not target:
        return {'ok': False, 'error': 'no leader_url configured'}

    from .local_node import build_local_telemetry
    payload = build_local_telemetry(node_id=node_id or enr.get('node_id'))
    if label or enr.get('label'):
        payload['label'] = label or enr.get('label')
    if notes:
        payload['notes'] = notes

    url = f'{target}/api/hive/telemetry'
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {'raw': raw[:200]}
            return {'ok': 200 <= resp.status < 300, 'status': resp.status, 'leader_url': target, 'response': parsed}
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'status': exc.code, 'leader_url': target, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'leader_url': target, 'error': str(exc)}


def discover_peer_capabilities(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize what each enrolled Hive node can run and share across the mesh."""
    peers: list[dict[str, Any]] = []
    for node in nodes:
        tel = node.get('telemetry') if isinstance(node.get('telemetry'), dict) else {}
        sp = tel.get('system_profile') if isinstance(tel.get('system_profile'), dict) else {}
        sh = tel.get('shareable') if isinstance(tel.get('shareable'), dict) else {}
        hw = sp.get('hardware') if isinstance(sp.get('hardware'), dict) else {}
        mem = tel.get('memory') if isinstance(tel.get('memory'), dict) else {}
        shared_models = sh.get('shared_models') if isinstance(sh.get('shared_models'), list) else []
        peers.append({
            'node_id': node.get('node_id'),
            'label': node.get('label') or node.get('node_id'),
            'platform': node.get('platform'),
            'offline': bool(node.get('offline', True)),
            'expected': bool(node.get('expected', False)),
            'tier': sh.get('tier') or hw.get('tier') or 'unknown',
            'primary_backend': sh.get('primary_backend') or hw.get('primary_backend') or 'cpu',
            'endpoint_url': sh.get('endpoint_url') or '',
            'accept_remote_jobs': bool(sh.get('accept_remote_jobs', False)),
            'ram_total_mb': mem.get('ram_total_mb') or hw.get('ram_total_mb'),
            'ram_free_mb': mem.get('ram_free_mb') or hw.get('ram_free_mb'),
            'capabilities': list(tel.get('capabilities') or []),
            'role_models': sh.get('role_models') or {},
            'shared_models': shared_models,
        })
    return peers


def find_peer_for_model(model_name: str, nodes: list[dict[str, Any]], *, exclude_node_id: str | None = None) -> dict[str, Any] | None:
    """Find the best online peer node that advertises ``model_name`` and accepts remote jobs."""
    wanted = str(model_name or '').strip().lower()
    if not wanted:
        return None
    fit_order = {'fast': 0, 'tight': 1, 'too-large': 2}
    tier_order = {'gpu-workstation': 0, 'gpu-node': 1, 'cpu-workstation': 2, 'potato-node': 3, 'edge-potato': 4, 'unknown': 5}
    matches = []
    for peer in discover_peer_capabilities(nodes):
        if peer['offline'] or not peer['accept_remote_jobs']:
            continue
        if exclude_node_id and peer['node_id'] == exclude_node_id:
            continue
        for m in peer['shared_models']:
            if str(m.get('name') or '').strip().lower() == wanted:
                score = (
                    fit_order.get(str(m.get('fit') or 'tight'), 2),
                    0 if m.get('loaded') else 1,
                    tier_order.get(str(peer.get('tier') or 'unknown'), 5),
                    -(int(peer.get('ram_free_mb') or 0)),
                )
                matches.append((score, peer, m))
                break
    if not matches:
        return None
    _, best_peer, best_model = min(matches, key=lambda x: x[0])
    return {
        'node_id': best_peer['node_id'],
        'label': best_peer['label'],
        'endpoint_url': best_peer['endpoint_url'],
        'tier': best_peer['tier'],
        'primary_backend': best_peer['primary_backend'],
        'model': best_model,
    }
