"""
frontend/blueprints/onboarding.py — Onboarding wizard API
═══════════════════════════════════════════════════════════════════════════════
GET  /api/onboarding/status   — aggregated setup health for each wizard step
POST /api/onboarding/test-key — validate an API key before saving
"""

import os
import platform
import shutil
import socket
import sys
import logging
import requests as _requests

from flask import Blueprint, jsonify, request

onboarding_bp = Blueprint('onboarding', __name__)
logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds

# Cloud agent definitions: (agent_name, env_var, display_label, test_url, test_method)
_CLOUD_AGENTS = [
    ('nine',    'GROQ_API_KEY',     'Groq (Agent 9)',       'https://api.groq.com/openai/v1/models'),
    ('ten',     'GEMINI_API_KEY',   'Gemini (Agent 10)',    'https://generativelanguage.googleapis.com/v1beta/models'),
    ('eleven',  'XAI_API_KEY',      'xAI / Grok (Agent 11)', 'https://api.x.ai/v1/models'),
    ('twelve',  'ANTHROPIC_API_KEY','Anthropic (Agent 12)', 'https://api.anthropic.com/v1/models'),
    ('gemini',  'GEMINI_API_KEY',   'Gemini (Agent 18)',    'https://generativelanguage.googleapis.com/v1beta/models'),
    ('scholar', 'GEMINI_API_KEY',   'Gemini (Scholar)',     'https://generativelanguage.googleapis.com/v1beta/models'),
    ('seeker',  'TAVILY_API_KEY',   'Tavily (Seeker)',      'https://api.tavily.com/search'),
]


def _key_is_set(env_var: str) -> bool:
    """Check if a key is available via env or .env.agents."""
    if os.environ.get(env_var):
        return True
    try:
        from config import _load_env_key
        return bool(_load_env_key(env_var))
    except Exception:
        return False


def _get_key(env_var: str) -> str:
    """Get key value from env or .env.agents."""
    val = os.environ.get(env_var, '')
    if val:
        return val
    try:
        from config import _load_env_key
        return _load_env_key(env_var) or ''
    except Exception:
        return ''


def _check_ollama() -> dict:
    """Check Ollama connectivity and model count."""
    try:
        r = _requests.get('http://localhost:11434/api/tags', timeout=_TIMEOUT)
        if r.status_code == 200:
            models = r.json().get('models', [])
            return {'running': True, 'model_count': len(models)}
    except Exception:
        pass
    return {'running': False, 'model_count': 0}


def _check_lmstudio() -> dict:
    """Check LM Studio connectivity."""
    try:
        r = _requests.get('http://localhost:1234/v1/models', timeout=_TIMEOUT)
        if r.status_code == 200:
            return {'running': True, 'models': len(r.json().get('data', []))}
    except Exception:
        pass
    return {'running': False, 'models': 0}


def _detect_lan_endpoint() -> str:
    """Best-effort LAN URL for this host (e.g. http://10.0.0.9:5050)."""
    port = os.environ.get('PORT', '5050').strip() or '5050'
    ip = ''
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('10.255.255.255', 1))
            ip = sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:
        ip = ''
    if not ip or ip.startswith('127.'):
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = '127.0.0.1'
    return f'http://{ip}:{port}'


def _ollama_install_hint() -> str:
    sys_os = platform.system().lower()
    if sys_os == 'windows':
        return 'winget install Ollama.Ollama  (or https://ollama.com/download/windows)'
    if sys_os == 'darwin':
        return 'brew install ollama  (or https://ollama.com/download/mac)'
    return 'curl -fsSL https://ollama.com/install.sh | sh'


def _build_packager_snapshot(force: bool = False) -> dict:
    """Build the Welcome Aboard Packager preflight + hardware + enrollment snapshot."""
    profile: dict = {}
    try:
        from core.hive.system_profile import collect_system_profile
        profile = collect_system_profile(force=force)
    except Exception as exc:
        logger.debug('packager system_profile error: %s', exc)

    enrollment = None
    try:
        from core.hive.node_enrollment import load_enrollment
        enrollment = load_enrollment()
    except Exception as exc:
        logger.debug('packager load_enrollment error: %s', exc)

    sampler_running = False
    try:
        from core.hive import self_sampler
        sampler_running = self_sampler.is_running()
    except Exception:
        pass

    hw = profile.get('hardware') or {}
    rt = profile.get('runtimes') or {}
    rec = profile.get('recommended_models') or {}
    ollama_rt = rt.get('ollama') or {}
    models = rt.get('models') or []
    git_ok = bool(shutil.which('git'))
    detected_endpoint = _detect_lan_endpoint()

    preflight = [
        {
            'id': 'python',
            'label': 'Python Runtime',
            'status': 'ok',
            'detail': f'Python {platform.python_version()} ({platform.system()})',
            'install_hint': '',
        },
        {
            'id': 'git',
            'label': 'Git CLI',
            'status': 'ok' if git_ok else 'warn',
            'detail': 'Installed' if git_ok else 'Not found in PATH (optional for updates)',
            'install_hint': 'winget install Git.Git' if platform.system().lower() == 'windows' else 'sudo apt install git',
        },
        {
            'id': 'ollama',
            'label': 'Ollama Local Runtime',
            'status': 'ok' if (ollama_rt.get('online') or ollama_rt.get('reachable') or ollama_rt.get('running')) else 'missing',
            'detail': (
                f"Running on {ollama_rt.get('url', '127.0.0.1:11434')} ({len(models)} models)"
                if (ollama_rt.get('online') or ollama_rt.get('reachable') or ollama_rt.get('running'))
                else 'Not reachable on 127.0.0.1:11434'
            ),
            'install_hint': _ollama_install_hint(),
        },
        {
            'id': 'local_models',
            'label': 'Local AI Models',
            'status': 'ok' if len(models) > 0 else 'missing',
            'detail': (
                f"{len(models)} model(s) ready — recommended APEX: {(rec.get('apex') or {}).get('model') or 'none'}"
                if models
                else 'No local models pulled yet'
            ),
            'install_hint': 'ollama pull llama3.2:latest && ollama pull qwen2.5:latest',
        },
        {
            'id': 'node_enrollment',
            'label': 'Node & Role Enrollment (APEX / FRED / HB)',
            'status': 'ok' if (enrollment and enrollment.get('enrolled')) else 'warn',
            'detail': (
                f"Enrolled as {enrollment.get('node_id')} ({enrollment.get('role')})"
                if (enrollment and enrollment.get('enrolled'))
                else 'Not enrolled yet — configure node identity and APEX/FRED/HB models below'
            ),
            'install_hint': '',
        },
        {
            'id': 'telemetry_sampler',
            'label': 'Hive Telemetry Heartbeat',
            'status': 'ok' if sampler_running else 'warn',
            'detail': (
                'Background heartbeat running (30s interval)'
                if sampler_running
                else 'Will start automatically when pipes are connected'
            ),
            'install_hint': '',
        },
    ]

    return {
        'hardware': hw,
        'runtimes': rt,
        'recommended_models': rec,
        'enrollment': enrollment,
        'enrolled': bool(enrollment and enrollment.get('enrolled')),
        'detected_endpoint_url': detected_endpoint,
        'sampler_running': sampler_running,
        'preflight': preflight,
    }


@onboarding_bp.route('/api/onboarding/status')
def onboarding_status():
    """Aggregated setup health check for the onboarding wizard.

    Returns the state of each setup step so the wizard can show
    green/amber/red indicators and skip already-completed steps.
    """
    # Step 1: Local AI
    ollama = _check_ollama()
    lmstudio = _check_lmstudio()
    local_ai = {
        'ollama': ollama,
        'lmstudio': lmstudio,
        'ready': ollama['running'] or lmstudio['running'],
    }

    # Step 2: Cloud agent keys
    cloud_agents = []
    for agent_name, env_var, label, test_url in [(a[0], a[1], a[2], a[3]) for a in _CLOUD_AGENTS]:
        cloud_agents.append({
            'agent': agent_name,
            'env_var': env_var,
            'label': label,
            'key_set': _key_is_set(env_var),
        })
    cloud_ready = sum(1 for a in cloud_agents if a['key_set'])

    # Step 3: Cloud nodes
    try:
        from utils.db.nodes import list_nodes
        nodes = list_nodes()
        remote_nodes = [n for n in nodes if n.get('role') != 'owner']
    except Exception:
        remote_nodes = []

    packager = _build_packager_snapshot(force=False)

    return jsonify({
        'local_ai': local_ai,
        'cloud_agents': cloud_agents,
        'cloud_agents_configured': cloud_ready,
        'cloud_agents_total': len(_CLOUD_AGENTS),
        'cloud_nodes': len(remote_nodes),
        'packager': packager,
        'complete': local_ai['ready'] and (packager['enrolled'] or cloud_ready >= 1),
    })


@onboarding_bp.route('/api/onboarding/packager')
def onboarding_packager():
    """Welcome Aboard Packager preflight + hardware/model recommendations."""
    force = request.args.get('refresh') in ('1', 'true', 'yes')
    return jsonify({'ok': True, **_build_packager_snapshot(force=force)})


@onboarding_bp.route('/api/onboarding/packager/connect', methods=['POST'])
def onboarding_packager_connect():
    """Connect all HB pipes: enroll node, bind APEX/FRED/HB models, start heartbeat, push to leader."""
    data = request.get_json(silent=True) or {}
    models = data.get('models') if isinstance(data.get('models'), dict) else {}
    share = data.get('share') if isinstance(data.get('share'), dict) else None
    try:
        from core.hive.node_enrollment import enroll_local_node
        models_map = {}
        for role_key in ('apex', 'fred', 'hb'):
            val = str(data.get(f'{role_key}_model') or models.get(role_key) or '').strip()
            if val:
                models_map[role_key] = val
        result = enroll_local_node(
            node_id=str(data.get('node_id') or '').strip() or None,
            label=str(data.get('label') or '').strip() or None,
            role=str(data.get('role') or 'worker').strip() or 'worker',
            leader_url=str(data.get('leader_url') or '').strip(),
            endpoint_url=str(data.get('endpoint_url') or '').strip() or _detect_lan_endpoint(),
            models=models_map or None,
            share=share,
        )
    except Exception as exc:
        logger.exception('packager connect failed')
        return jsonify({'ok': False, 'error': str(exc)}), 500

    sampler_running = False
    try:
        from core.hive import self_sampler
        self_sampler.start()
        sampler_running = self_sampler.is_running()
    except Exception:
        pass

    return jsonify({
        'ok': True,
        **result,
        'sampler_running': sampler_running,
    })


@onboarding_bp.route('/api/onboarding/test-key', methods=['POST'])
def onboarding_test_key():
    """Test an API key before saving it.

    JSON body: {env_var: "GROQ_API_KEY", value: "gsk_..."}
    Returns: {ok: true/false, message: "..."}
    """
    data = request.get_json() or {}
    env_var = (data.get('env_var') or '').strip()
    value = (data.get('value') or '').strip()

    if not env_var or not value:
        return jsonify({'ok': False, 'message': 'env_var and value required'}), 400

    # Find the matching cloud agent
    match = None
    for agent_name, var, label, test_url in [(a[0], a[1], a[2], a[3]) for a in _CLOUD_AGENTS]:
        if var == env_var:
            match = (agent_name, var, label, test_url)
            break

    if not match:
        return jsonify({'ok': False, 'message': f'Unknown key variable: {env_var}'}), 400

    agent_name, var, label, test_url = match

    # Test the key
    try:
        headers = {}
        params = {}

        if var == 'GROQ_API_KEY':
            headers = {'Authorization': f'Bearer {value}'}
        elif var == 'GITHUB_TOKEN':
            headers = {'Authorization': f'token {value}'}
        elif var == 'XAI_API_KEY':
            headers = {'Authorization': f'Bearer {value}'}
        elif var == 'ANTHROPIC_API_KEY':
            headers = {'x-api-key': value, 'anthropic-version': '2023-06-01'}
        elif var == 'GEMINI_API_KEY':
            params = {'key': value}
        elif var == 'TAVILY_API_KEY':
            # Tavily uses POST with api_key in body
            r = _requests.post(test_url, json={
                'api_key': value,
                'query': 'test',
                'max_results': 1,
            }, timeout=_TIMEOUT)
            if r.status_code == 200:
                return jsonify({'ok': True, 'message': f'{label} key is valid'})
            return jsonify({'ok': False, 'message': f'{label} key rejected (HTTP {r.status_code})'})

        r = _requests.get(test_url, headers=headers, params=params, timeout=_TIMEOUT)
        if r.status_code in (200, 201):
            return jsonify({'ok': True, 'message': f'{label} key is valid'})
        return jsonify({'ok': False, 'message': f'{label} key rejected (HTTP {r.status_code})'})

    except _requests.Timeout:
        return jsonify({'ok': False, 'message': f'Timeout connecting to {label}'})
    except Exception as e:
        return jsonify({'ok': False, 'message': f'Connection error: {str(e)}'})
