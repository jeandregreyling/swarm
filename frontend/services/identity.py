"""
services.identity — Caller identity resolution, agent auth, reachability.

Extracted from services/__init__.py as part of Phase B.
"""
import os
import time

from flask import request, jsonify

from database import get_user_profile, log_activity

from utils.db.registry import (
    get_agent_roster      as _reg_roster,
    get_agent_runtime_classes as _reg_runtime,
    get_agent_models      as _reg_models,
    get_api_key_map       as _reg_api_keys,
)

_LOCAL_RUNTIME_CACHE = {
    'ollama_ts': 0.0,
    'ollama_running': True,
    'seven_runtime_ts': 0.0,
    'seven_runtime_running': True,
}
_LOCAL_RUNTIME_TTL_SECONDS = 2.0


def _resolve_identity_or_response(data):
    """
    Resolve caller identity and optional proxy context.
    Returns (identity_dict, None) or (None, flask_response).
    """
    payload = data or {}
    acting = (payload.get('acting_user') or payload.get('user') or 'ghost').strip().lower()
    proxy_as = (payload.get('proxy_as') or '').strip().lower()

    actor_profile = get_user_profile(acting)
    if not actor_profile:
        return None, (jsonify({'ok': False, 'error': f'unknown acting_user: {acting}'}), 404)
    if not bool(actor_profile.get('is_active')):
        return None, (jsonify({'ok': False, 'error': f'user is inactive: {acting}'}), 403)

    effective_profile = actor_profile
    if proxy_as and proxy_as != acting:
        if not bool(actor_profile.get('can_proxy')):
            return None, (jsonify({'ok': False, 'error': f'user cannot proxy: {acting}'}), 403)
        target_profile = get_user_profile(proxy_as)
        if not target_profile:
            return None, (jsonify({'ok': False, 'error': f'unknown proxy target: {proxy_as}'}), 404)
        if not bool(target_profile.get('is_active')):
            return None, (jsonify({'ok': False, 'error': f'proxy target is inactive: {proxy_as}'}), 403)
        effective_profile = target_profile

    identity = {
        'acting_user': actor_profile['username'],
        'proxy_as': proxy_as or '',
        'effective_user': effective_profile['username'],
        'can_proxy': bool(actor_profile.get('can_proxy')),
        'actor': actor_profile,
        'effective': effective_profile,
    }
    return identity, None


def _validate_agent_request():
    """
    Validate that request is from a local agent with valid AGENT_API_KEY.
    Returns (agent_id, error_response) tuple.
    - On success: (agent_id_string, None)
    - On failure: (None, Flask error response tuple)
    """
    agent_key = request.headers.get('X-Agent-Key', '').strip()
    agent_id = request.headers.get('X-Agent-Id', '').strip()

    if not agent_key or not agent_id:
        return None, (jsonify({'ok': False, 'error': 'X-Agent-Key and X-Agent-Id headers required'}), 401)

    expected_key = os.environ.get('AGENT_API_KEY', '').strip()
    if not expected_key:
        return None, (jsonify({'ok': False, 'error': 'agent API not enabled (AGENT_API_KEY not set)'}), 503)

    if agent_key != expected_key:
        log_activity('terminal', 'agent_auth_failed', f'invalid key attempt from agent {agent_id}')
        return None, (jsonify({'ok': False, 'error': 'invalid agent API key'}), 403)

    # Valid agent_id should match known local agents
    valid_agents = {a['name'].lower() for a in _reg_roster()}
    if agent_id.lower() not in valid_agents:
        log_activity('terminal', 'agent_auth_unknown', f'unknown agent_id: {agent_id}')
        # Still allow it; agents can register themselves

    return agent_id, None


def _ollama_runtime_running():
    now = time.time()
    cached_ts = float(_LOCAL_RUNTIME_CACHE.get('ollama_ts') or 0.0)
    if (now - cached_ts) <= _LOCAL_RUNTIME_TTL_SECONDS:
        return bool(_LOCAL_RUNTIME_CACHE.get('ollama_running', True))
    running = True
    try:
        from frontend.blueprints.localai import _ollama_status
        running = bool((_ollama_status() or {}).get('running'))
    except ImportError:
        running = True
    _LOCAL_RUNTIME_CACHE['ollama_ts'] = now
    _LOCAL_RUNTIME_CACHE['ollama_running'] = running
    return running


def _seven_runtime_running():
    now = time.time()
    cached_ts = float(_LOCAL_RUNTIME_CACHE.get('seven_runtime_ts') or 0.0)
    if (now - cached_ts) <= _LOCAL_RUNTIME_TTL_SECONDS:
        return bool(_LOCAL_RUNTIME_CACHE.get('seven_runtime_running', True))
    running = True
    try:
        from frontend.blueprints.localai import _seven_runtime_status
        running = bool((_seven_runtime_status() or {}).get('running'))
    except ImportError:
        running = True
    _LOCAL_RUNTIME_CACHE['seven_runtime_ts'] = now
    _LOCAL_RUNTIME_CACHE['seven_runtime_running'] = running
    return running


def _local_agent_model(agent_name):
    try:
        return str((_reg_models() or {}).get((agent_name or '').strip().lower()) or '').strip()
    except Exception:
        return ''


def _local_agent_runtime_state(agent_name):
    model = _local_agent_model(agent_name)
    if model.startswith('seven-direct:'):
        return _seven_runtime_running(), 'Seven Runtime offline'
    from core.seven_llm import registry
    entry = registry.get(model)
    if entry and entry.driver == 'llamacpp':
        from core.seven_llm.llama_server import default_binary
        if not entry.path or not os.path.isfile(entry.path):
            return False, 'Direct GGUF missing'
        binary = (entry.options or {}).get('server') or default_binary()
        return os.path.isfile(binary), 'Direct llama-server missing'
    if model in {'', 'external', 'local-algorithm'}:
        return True, ''
    return _ollama_runtime_running(), 'Ollama offline'


def _agent_reachability_status(agent_name):
    """Return 'online', 'degraded', or 'offline' based on real API key / service availability."""
    # Late import — DISABLED_AGENTS lives in services/__init__.py and is mutated by agents.py
    from . import DISABLED_AGENTS

    name = (agent_name or '').strip().lower()
    if name in DISABLED_AGENTS:
        return 'offline'
    if name == 'ghost':
        return 'online'
    # Determine tier from registry
    rt = _reg_runtime()
    tier = rt.get(name, '')
    if tier == 'local':
        running, _reason = _local_agent_runtime_state(name)
        return 'online' if running else 'offline'
    # API-backed agents — check key presence via env var from registry
    api_keys = _reg_api_keys()
    env_var = api_keys.get(name) or ''
    if not env_var:
        return 'online'  # unknown agent or no key configured
    return 'online' if os.environ.get(env_var, '') else 'offline'


def _agent_availability_reason(agent_name):
    """Return a human-readable reason when an agent is not available.

    Empty string means the agent is available enough for the UI to present it
    as ready. The status field still carries the coarse online/offline state.
    """
    from . import DISABLED_AGENTS

    name = (agent_name or '').strip().lower()
    if not name:
        return 'unknown agent'
    if name in DISABLED_AGENTS:
        return 'disabled'
    if name == 'ghost':
        return ''

    rt = _reg_runtime()
    tier = rt.get(name, '')
    if tier == 'local':
        running, reason = _local_agent_runtime_state(name)
        return '' if running else reason

    api_keys = _reg_api_keys()
    env_var = api_keys.get(name) or ''
    if not env_var:
        return ''
    return '' if os.environ.get(env_var, '') else f'missing {env_var}'
