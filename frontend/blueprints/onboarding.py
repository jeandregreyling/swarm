"""
frontend/blueprints/onboarding.py — Onboarding wizard API
═══════════════════════════════════════════════════════════════════════════════
GET  /api/onboarding/status   — aggregated setup health for each wizard step
POST /api/onboarding/test-key — validate an API key before saving
"""

import os
import logging
import requests as _requests

from flask import Blueprint, jsonify, request

onboarding_bp = Blueprint('onboarding', __name__)
logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds

# Cloud agent definitions: (agent_name, env_var, display_label, test_url, test_method)
_CLOUD_AGENTS = [
    ('nine',    'GROQ_API_KEY',     'Groq (Agent 9)',       'https://api.groq.com/openai/v1/models'),
    ('ten',     'GITHUB_TOKEN',     'GitHub (Agent 10)',    'https://api.github.com/user'),
    ('eleven',  'XAI_API_KEY',      'xAI / Grok (Agent 11)', 'https://api.x.ai/v1/models'),
    ('twelve',  'ANTHROPIC_API_KEY','Anthropic (Agent 12)', 'https://api.anthropic.com/v1/models'),
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

    return jsonify({
        'local_ai': local_ai,
        'cloud_agents': cloud_agents,
        'cloud_agents_configured': cloud_ready,
        'cloud_agents_total': len(_CLOUD_AGENTS),
        'cloud_nodes': len(remote_nodes),
        'complete': local_ai['ready'] and cloud_ready >= 1,
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
