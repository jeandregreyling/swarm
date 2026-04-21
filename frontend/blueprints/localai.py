"""
blueprints/localai.py — Local AI status and proxy API
═══════════════════════════════════════════════════════════════════════════════
Unified status and chat proxy for all local inference services:
  - Ollama         (port 11434)
  - LM Studio      (port 1234, OpenAI-compatible)
  - Picoclaw       (port 18790, gateway API)
"""
import requests
import json
from flask import Blueprint, jsonify, request

localai_bp = Blueprint('localai', __name__)

_OLLAMA_BASE  = 'http://localhost:11434'
_LMSTUDIO_BASE = 'http://localhost:1234'
_PICOCLAW_BASE = 'http://localhost:18790'

_TIMEOUT = 3   # seconds for status checks


def _ollama_status():
    try:
        r = requests.get(f'{_OLLAMA_BASE}/api/tags', timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            models = [
                {
                    'name':   m['name'],
                    'size_gb': round(m['size'] / 1e9, 1),
                    'family': m.get('details', {}).get('family', ''),
                    'params': m.get('details', {}).get('parameter_size', ''),
                    'quant':  m.get('details', {}).get('quantization_level', ''),
                }
                for m in data.get('models', [])
                if m.get('name') != 'nomic-embed-text:latest'  # embedding-only, skip
            ]
            return {'running': True, 'models': models}
    except Exception:
        pass
    return {'running': False, 'models': []}


def _lmstudio_status():
    try:
        r = requests.get(f'{_LMSTUDIO_BASE}/v1/models', timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            models = [m.get('id', '') for m in data.get('data', [])]
            return {'running': True, 'models': models, 'loaded': models[0] if models else None}
    except Exception:
        pass
    return {'running': False, 'models': [], 'loaded': None}


def _picoclaw_status():
    try:
        r = requests.get(f'{_PICOCLAW_BASE}/', timeout=_TIMEOUT, allow_redirects=False)
        # Any response (even the login redirect) means it's up
        return {'running': r.status_code in (200, 302, 301), 'url': _PICOCLAW_BASE}
    except Exception:
        pass
    return {'running': False, 'url': _PICOCLAW_BASE}


@localai_bp.route('/api/localai/status', methods=['GET'])
def localai_status():
    ollama   = _ollama_status()
    lmstudio = _lmstudio_status()
    picoclaw = _picoclaw_status()
    return jsonify({
        'ok': True,
        'ollama':   ollama,
        'lmstudio': lmstudio,
        'picoclaw': picoclaw,
    })


@localai_bp.route('/api/localai/available-models', methods=['GET'])
def localai_available_models():
    """Discover all models from Ollama + LM Studio, flag which are already registered."""
    from utils.db.registry import get_agent_models, get_agent_roster
    registered_models = get_agent_models()       # {agent_name: model_name}
    registered_set = {v.lower() for v in registered_models.values() if v}
    roster = get_agent_roster()
    registered_names = {a['name'] for a in roster}

    available = []

    # Ollama models
    ollama = _ollama_status()
    if ollama['running']:
        for m in ollama['models']:
            name = m['name']
            available.append({
                'model':      name,
                'source':     'ollama',
                'size_gb':    m.get('size_gb', 0),
                'family':     m.get('family', ''),
                'params':     m.get('params', ''),
                'quant':      m.get('quant', ''),
                'registered': name.lower() in registered_set,
            })

    # LM Studio models
    lms = _lmstudio_status()
    if lms['running']:
        for name in lms.get('models', []):
            available.append({
                'model':      name,
                'source':     'lmstudio',
                'size_gb':    0,
                'family':     '',
                'params':     '',
                'quant':      '',
                'registered': name.lower() in registered_set,
            })

    return jsonify({
        'ok': True,
        'models': available,
        'registered_agents': list(registered_names),
    })


@localai_bp.route('/api/localai/ollama/models', methods=['GET'])
def ollama_models():
    status = _ollama_status()
    return jsonify({'ok': True, 'models': status['models'], 'running': status['running']})


@localai_bp.route('/api/localai/ollama/chat', methods=['POST'])
def ollama_quick_chat():
    """Quick single-turn chat against any Ollama model."""
    data  = request.get_json(force=True) or {}
    model = (data.get('model') or 'mistral:latest').strip()
    msg   = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400
    try:
        r = requests.post(
            f'{_OLLAMA_BASE}/api/chat',
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': msg}],
                'stream': False,
                'options': {'temperature': 0.7},
            },
            timeout=120,
        )
        if r.status_code == 200:
            answer = r.json().get('message', {}).get('content', '')
            return jsonify({'ok': True, 'answer': answer, 'model': model})
        return jsonify({'ok': False, 'error': f'Ollama returned {r.status_code}'}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({'ok': False, 'error': 'Ollama not running'}), 503
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@localai_bp.route('/api/localai/lmstudio/chat', methods=['POST'])
def lmstudio_quick_chat():
    """Quick single-turn chat against LM Studio."""
    data  = request.get_json(force=True) or {}
    msg   = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400
    status = _lmstudio_status()
    if not status['running']:
        return jsonify({'ok': False, 'error': 'LM Studio not running'}), 503
    model = data.get('model') or status.get('loaded') or 'local-model'
    try:
        r = requests.post(
            f'{_LMSTUDIO_BASE}/v1/chat/completions',
            headers={'Authorization': 'Bearer lm-studio', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': msg}],
                'max_tokens': 1024,
                'temperature': 0.7,
            },
            timeout=120,
        )
        if r.status_code == 200:
            answer = r.json()['choices'][0]['message']['content']
            return jsonify({'ok': True, 'answer': answer, 'model': model})
        return jsonify({'ok': False, 'error': f'LM Studio returned {r.status_code}: {r.text[:200]}'}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({'ok': False, 'error': 'LM Studio not running'}), 503
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
