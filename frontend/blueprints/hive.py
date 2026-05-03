"""frontend.blueprints.hive — HTTP surface for the cross-platform Hive.

Endpoints:

    GET    /api/hive/nodes                — list all enrolled nodes + last telemetry
    GET    /api/hive/node/<node_id>       — single node detail + recent events
    POST   /api/hive/telemetry            — node uploads a contract-v0 envelope
    POST   /api/hive/policy               — executive sets policy on a node
    DELETE /api/hive/node/<node_id>       — deregister a node
    GET    /api/hive/local                — telemetry for THIS host (debug)

Auth model: enrolment tokens land in a later iteration. For now we
accept telemetry from any local-network caller so the Linux node can
talk to itself without ceremony. The validate_telemetry / validate_policy
guards make the surface safe against malformed input.
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

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

_LOG = logging.getLogger(__name__)

hive_bp = Blueprint('hive', __name__, url_prefix='/api/hive')


def _registry() -> HiveRegistry:
    return get_registry()


def _err(msg: str, status: int = 400) -> Any:
    return jsonify({'ok': False, 'error': msg}), status


@hive_bp.get('/nodes')
def list_nodes():
    max_age = request.args.get('max_age_s', type=int)
    nodes = _registry().list_nodes(max_age_s=max_age)
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
