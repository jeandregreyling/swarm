"""
blueprints/localai.py — Local AI status and proxy API
═══════════════════════════════════════════════════════════════════════════════
Unified status and chat proxy for all local inference services:
  - Ollama         (port 11434)
  - LM Studio      (port 1234, OpenAI-compatible)
  - Picoclaw       (port 18790, gateway API)
"""
import os
import re
import requests
import json
import signal
import subprocess
import sys
import time
from flask import Blueprint, jsonify, request
from database import get_connection, log_message, new_conversation

localai_bp = Blueprint('localai', __name__)


def _resolve_ollama_host() -> str:
    """Return the Ollama base URL, honouring OLLAMA_HOST env var.

    Under WSL2 the Flask process runs in Linux while Ollama may run on the
    Windows host.  We detect WSL2 by reading /proc/sys/kernel/osrelease and,
    if found, derive the Windows host IP from /etc/resolv.conf (WSL2 always
    writes the host gateway there as 'nameserver <ip>').  OLLAMA_HOST always
    takes priority so the caller can override everything.
    """
    env = os.environ.get('OLLAMA_HOST', '').strip()
    if env:
        # If the env var doesn't include a scheme, add one.
        return env if env.startswith('http') else f'http://{env}'

    try:
        release = open('/proc/sys/kernel/osrelease').read().lower()
        if 'microsoft' in release or 'wsl' in release:
            # Running inside WSL2 — Ollama likely runs on the Windows host.
            resolv = open('/etc/resolv.conf').read()
            m = re.search(r'^nameserver\s+([\d.]+)', resolv, re.MULTILINE)
            if m:
                return f'http://{m.group(1)}:11434'
    except OSError:
        pass  # Not Linux or files not present — fall through to localhost.

    return 'http://localhost:11434'


_OLLAMA_BASE  = _resolve_ollama_host()
_LMSTUDIO_BASE = 'http://localhost:1234'
_PICOCLAW_BASE = 'http://localhost:18790'
_SEVEN_RUNTIME_HOST = os.environ.get('SEVEN_RUNTIME_HOST', '127.0.0.1')
_SEVEN_RUNTIME_PORT = int(os.environ.get('SEVEN_RUNTIME_PORT', '17777'))
_SEVEN_RUNTIME_BASE = f'http://{_SEVEN_RUNTIME_HOST}:{_SEVEN_RUNTIME_PORT}'

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


def _direct_status():
    try:
        from core.seven_llm import registry
        from core.seven_llm.inventory import scan_gguf
        from core.seven_llm import llama_server
        entries = [
            {
                'name': m.name,
                'path': m.path,
                'role': m.role,
                'size_gb': round(os.path.getsize(m.path) / 1e9, 2) if m.path and os.path.isfile(m.path) else 0,
                'ctx': m.ctx,
                'quant': m.quant,
            }
            for m in registry.list_models()
            if m.driver == 'llamacpp' and m.path
        ]
        inventory = scan_gguf(limit=100)
        cli = os.environ.get('SEVEN_LLAMA_CLI') or os.path.join(
            os.getcwd(), 'agents', 'seven', 'llama.cpp', 'build', 'bin', 'llama-cli'
        )
        return {
            'running': bool(entries) and os.path.isfile(cli),
            'models': entries,
            'inventory': inventory,
            'servers': llama_server.snapshot(),
            'resources': llama_server.resource_snapshot(),
            'cli': cli,
            'cli_exists': os.path.isfile(cli),
        }
    except Exception as exc:
        return {'running': False, 'models': [], 'inventory': {'models': []}, 'error': str(exc)}


def _seven_runtime_status():
    try:
        r = requests.get(f'{_SEVEN_RUNTIME_BASE}/health', timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return {
                'running': True,
                'url': _SEVEN_RUNTIME_BASE,
                'pid': data.get('pid'),
                'ok': bool(data.get('ok')),
                'service': data.get('service') or 'seven-runtime',
                'model': data.get('model') or '',
                'flask_required': bool(data.get('flask_required')),
                'ollama_required': bool(data.get('ollama_required')),
                'chat_timeout_s': data.get('chat_timeout_s'),
                'direct_registered': bool((data.get('direct') or {}).get('registered')),
                'direct_model_count': len((data.get('direct') or {}).get('models') or []),
                'warning': data.get('warning') or '',
            }
    except Exception:
        pass
    return {
        'running': False,
        'url': _SEVEN_RUNTIME_BASE,
        'ok': False,
        'service': 'seven-runtime',
        'model': os.environ.get('SEVEN_MODEL', 'seven-direct:daily'),
        'flask_required': False,
        'ollama_required': False,
        'direct_registered': False,
        'direct_model_count': 0,
    }


def _mobile_model_list():
    """Return model choices suitable for Android/Hive clients.

    This is deliberately runtime-neutral: Android should not need to know
    whether the selected model is served by Seven Runtime, direct GGUF, or
    legacy Ollama.
    """
    models = []
    seen = set()

    seven_runtime = _seven_runtime_status()
    runtime_model = str(seven_runtime.get('model') or '').strip()
    if runtime_model:
        seen.add(runtime_model.lower())
        models.append({
            'id': runtime_model,
            'name': runtime_model,
            'label': 'Seven Runtime daily',
            'source': 'seven-runtime',
            'runtime': 'seven-runtime',
            'recommended': True,
            'running': bool(seven_runtime.get('running')),
            'chat_endpoint': '/api/localai/shared-chat',
        })

    direct = _direct_status()
    for m in direct.get('models', []):
        name = str(m.get('name') or '').strip()
        if str(m.get('role') or '').strip().lower() == 'embed':
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        models.append({
            'id': name,
            'name': name,
            'label': name,
            'source': 'direct-gguf',
            'runtime': 'direct-gguf',
            'recommended': False,
            'running': bool(direct.get('running')),
            'chat_endpoint': '/api/localai/shared-chat',
            'role': m.get('role') or '',
            'quant': m.get('quant') or '',
            'size_gb': m.get('size_gb') or 0,
        })

    ollama = _ollama_status()
    for m in ollama.get('models', []):
        name = str(m.get('name') or '').strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        models.append({
            'id': name,
            'name': name,
            'label': name,
            'source': 'ollama',
            'runtime': 'ollama',
            'recommended': False,
            'running': bool(ollama.get('running')),
            'chat_endpoint': '/api/localai/shared-chat',
            'size_gb': m.get('size_gb') or 0,
            'family': m.get('family') or '',
            'params': m.get('params') or '',
            'quant': m.get('quant') or '',
        })

    return {
        'ok': True,
        'default_model': runtime_model or (models[0]['id'] if models else ''),
        'models': models,
        'seven_runtime': seven_runtime,
    }


def _start_seven_runtime():
    status = _seven_runtime_status()
    if status.get('running'):
        return status
    root = os.environ.get('SWARM_ROOT') or os.getcwd()
    env = dict(os.environ)
    env.setdefault('PYTHONPATH', '.:frontend:utils')
    env.setdefault('SEVEN_MODEL', 'seven-direct:daily')
    env.setdefault('SEVEN_RUNTIME_PORT', str(_SEVEN_RUNTIME_PORT))
    env.setdefault('SEVEN_RUNTIME_CHAT_TIMEOUT_S', '90')
    env.setdefault('SEVEN_DIRECT_TIMEOUT_S', '30')
    env.setdefault('SEVEN_NUM_PREDICT', '256')
    log_path = '/tmp/seven-runtime-service.log'
    with open(log_path, 'a', encoding='utf-8') as log:
        subprocess.Popen(
            [
                sys.executable,
                os.path.join(root, 'scripts', 'seven_runtime_service.py'),
                '--host',
                _SEVEN_RUNTIME_HOST,
                '--port',
                str(_SEVEN_RUNTIME_PORT),
            ],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    deadline = time.time() + 8
    while time.time() < deadline:
        status = _seven_runtime_status()
        if status.get('running'):
            status['log'] = log_path
            return status
        time.sleep(0.25)
    status = _seven_runtime_status()
    status['log'] = log_path
    return status


def _stop_seven_runtime():
    status = _seven_runtime_status()
    pid = status.get('pid')
    stopped = False
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
            stopped = True
        except Exception:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _seven_runtime_status().get('running'):
            return {'running': False, 'stopped': stopped, 'url': _SEVEN_RUNTIME_BASE}
        time.sleep(0.25)
    if pid:
        try:
            os.kill(int(pid), signal.SIGKILL)
            stopped = True
        except Exception:
            pass
    time.sleep(0.5)
    return {'running': _seven_runtime_status().get('running'), 'stopped': stopped, 'url': _SEVEN_RUNTIME_BASE}


@localai_bp.route('/api/localai/status', methods=['GET'])
def localai_status():
    ollama   = _ollama_status()
    lmstudio = _lmstudio_status()
    picoclaw = _picoclaw_status()
    direct   = _direct_status()
    seven_runtime = _seven_runtime_status()
    return jsonify({
        'ok': True,
        'ollama':   ollama,
        'lmstudio': lmstudio,
        'picoclaw': picoclaw,
        'direct':   direct,
        'seven_runtime': seven_runtime,
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

    # Seven direct GGUF models
    direct = _direct_status()
    for m in direct.get('models', []):
        name = m['name']
        available.append({
            'model':      name,
            'source':     'direct-gguf',
            'size_gb':    m.get('size_gb', 0),
            'family':     'gguf',
            'params':     '',
            'quant':      m.get('quant', ''),
            'registered': name.lower() in registered_set,
        })

    return jsonify({
        'ok': True,
        'models': available,
        'registered_agents': list(registered_names),
    })


@localai_bp.route('/api/localai/mobile/models', methods=['GET'])
def mobile_models():
    return jsonify(_mobile_model_list())


@localai_bp.route('/api/localai/ollama/models', methods=['GET'])
def ollama_models():
    status = _ollama_status()
    return jsonify({'ok': True, 'models': status['models'], 'running': status['running']})


@localai_bp.route('/api/localai/direct/models', methods=['GET'])
def direct_models():
    status = _direct_status()
    return jsonify({'ok': True, 'models': status['models'], 'running': status['running'], 'inventory': status.get('inventory'), 'servers': status.get('servers', [])})


@localai_bp.route('/api/localai/direct/servers', methods=['GET'])
def direct_servers():
    try:
        from core.seven_llm import llama_server
        return jsonify({'ok': True, 'servers': llama_server.snapshot(), 'resources': llama_server.resource_snapshot()})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'servers': []}), 500


@localai_bp.route('/api/localai/direct/servers/stop', methods=['POST'])
def direct_servers_stop():
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip() or None
    try:
        from core.seven_llm import llama_server
        stopped = llama_server.stop(model)
        return jsonify({'ok': True, 'stopped': stopped, 'model': model, 'servers': llama_server.snapshot()})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'model': model}), 500


@localai_bp.route('/api/localai/seven-runtime/status', methods=['GET'])
def seven_runtime_status():
    return jsonify({'ok': True, 'runtime': _seven_runtime_status()})


@localai_bp.route('/api/localai/seven-runtime/start', methods=['POST'])
def seven_runtime_start():
    try:
        status = _start_seven_runtime()
        return jsonify({'ok': bool(status.get('running')), 'runtime': status})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'runtime': _seven_runtime_status()}), 500


@localai_bp.route('/api/localai/seven-runtime/stop', methods=['POST'])
def seven_runtime_stop():
    try:
        result = _stop_seven_runtime()
        return jsonify({'ok': not result.get('running'), **result})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'runtime': _seven_runtime_status()}), 500


@localai_bp.route('/api/localai/seven-runtime/chat', methods=['POST'])
def seven_runtime_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or data.get('prompt') or '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400
    status = _seven_runtime_status()
    if not status.get('running'):
        status = _start_seven_runtime()
    if not status.get('running'):
        return jsonify({'ok': False, 'error': 'seven runtime is not running', 'runtime': status}), 503
    try:
        r = requests.post(
            f'{_SEVEN_RUNTIME_BASE}/chat',
            json={
                'message': msg,
                'history': data.get('history') or [],
                'timeout_seconds': int(data.get('timeout_seconds') or 90),
            },
            timeout=int(data.get('timeout_seconds') or 90) + 10,
        )
        payload = r.json()
        payload.setdefault('runtime', _seven_runtime_status())
        return jsonify(payload), (200 if r.status_code < 400 else r.status_code)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'runtime': _seven_runtime_status()}), 500


@localai_bp.route('/api/localai/direct/chat', methods=['POST'])
def direct_quick_chat():
    """Quick single-turn chat against a Seven-owned direct GGUF model."""
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or 'seven-direct:daily').strip()
    msg = (data.get('message') or '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400
    try:
        from core import model_runtime_gateway as _gw
        res = _gw.chat(
            model,
            [{'role': 'user', 'content': msg}],
            absolute_timeout_s=int(data.get('timeout_s') or 180),
            idle_timeout_s=int(data.get('timeout_s') or 180),
            options={
                'num_predict': int(data.get('num_predict') or 256),
                'ctx': int(data.get('ctx') or 2048),
                'temperature': float(data.get('temperature') if data.get('temperature') is not None else 0.7),
            },
        )
        if not res.ok:
            return jsonify({'ok': False, 'error': res.error or 'direct runtime failed', 'model': model, 'events': [e.as_dict() for e in res.events]}), 502
        return jsonify({'ok': True, 'answer': res.content, 'model': model, 'events': [e.as_dict() for e in res.events]})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc), 'model': model}), 500


@localai_bp.route('/api/localai/ollama/chat', methods=['POST'])
def ollama_quick_chat():
    """Quick single-turn chat against any Ollama model."""
    data  = request.get_json(silent=True) or {}
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


def _shared_chat_messages(conv_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, from_agent AS sender, content, to_agent, message_type, tokens_used, created_at
               FROM messages
               WHERE conversation_id=?
               ORDER BY id ASC""",
            (int(conv_id),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _valid_conversation_id(raw_conv_id):
    if raw_conv_id in (None, ''):
        return None
    try:
        candidate = int(raw_conv_id)
        conn = get_connection()
        try:
            exists = conn.execute("SELECT id FROM conversations WHERE id=?", (candidate,)).fetchone()
        finally:
            conn.close()
        if exists:
            return candidate
    except Exception:
        return None
    return None


def _history_from_shared_rows(rows, node_id):
    history = []
    for row in rows:
        sender = str(row.get('sender') or '').strip().lower()
        content = str(row.get('content') or '')
        if not content:
            continue
        role = 'user' if sender in {'user', node_id.lower(), 'android'} else 'assistant'
        history.append({'role': role, 'content': content})
    return history


def _chat_with_seven_runtime(model, history, msg, timeout_seconds):
    status = _seven_runtime_status()
    if not status.get('running'):
        status = _start_seven_runtime()
    if not status.get('running'):
        return None, {'ok': False, 'error': 'seven runtime is not running', 'runtime': status}, 503
    r = requests.post(
        f'{_SEVEN_RUNTIME_BASE}/chat',
        json={
            'model': model,
            'message': msg,
            'history': history,
            'timeout_seconds': timeout_seconds,
        },
        timeout=timeout_seconds + 10,
    )
    try:
        payload = r.json()
    except Exception:
        payload = {'ok': False, 'error': r.text[:240]}
    if r.status_code >= 400 or not payload.get('ok'):
        payload.setdefault('runtime', _seven_runtime_status())
        return None, payload, r.status_code if r.status_code >= 400 else 502
    answer = str(payload.get('content') or payload.get('answer') or '').strip() or 'No response'
    payload.setdefault('runtime', _seven_runtime_status())
    return answer, payload, 200


def _chat_with_ollama(model, history, msg):
    if not history or history[-1].get('role') != 'user':
        history.append({'role': 'user', 'content': msg})
    r = requests.post(
        f'{_OLLAMA_BASE}/api/chat',
        json={
            'model': model,
            'messages': history,
            'stream': False,
            'options': {'temperature': 0.7},
        },
        timeout=120,
    )
    if r.status_code != 200:
        return None, {'ok': False, 'error': f'Ollama returned {r.status_code}'}, 502
    answer = r.json().get('message', {}).get('content', '').strip() or 'No response'
    return answer, {'ok': True, 'answer': answer, 'model': model}, 200


@localai_bp.route('/api/localai/shared-chat', methods=['POST'])
@localai_bp.route('/api/localai/ollama/shared-chat', methods=['POST'])
def shared_chat():
    """Android/remote chat entrypoint backed by the normal Fridays conversation store."""
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or data.get('model_id') or 'seven-direct:daily').strip()
    msg = (data.get('message') or '').strip()
    node_id = (data.get('node_id') or 'android').strip()[:80]
    if not msg:
        return jsonify({'ok': False, 'error': 'message required'}), 400

    conv_id = _valid_conversation_id(data.get('conversation_id'))

    if conv_id is None:
        conv_id = new_conversation(f'Fridays Android: {msg[:80]}', source='terminal-ui:ANDROID', sender=node_id)

    log_message(conv_id, 'user', msg, to_agent=model, message_type='chat')

    try:
        rows = _shared_chat_messages(conv_id)[-16:]
        history = _history_from_shared_rows(rows, node_id)
        if model.startswith('seven-direct:'):
            answer, runtime_payload, status_code = _chat_with_seven_runtime(
                model,
                history,
                msg,
                int(data.get('timeout_seconds') or 90),
            )
        else:
            answer, runtime_payload, status_code = _chat_with_ollama(model, history, msg)
        if not answer:
            runtime_payload['conversation_id'] = conv_id
            return jsonify(runtime_payload), status_code
        log_message(conv_id, model, answer, to_agent='user', message_type='response')
        return jsonify({
            'ok': True,
            'answer': answer,
            'content': answer,
            'model': model,
            'conversation_id': conv_id,
            'messages': _shared_chat_messages(conv_id),
            'runtime': runtime_payload.get('runtime'),
            'stages': runtime_payload.get('stages') or [],
            'tokens': runtime_payload.get('tokens'),
        })
    except requests.exceptions.ConnectionError:
        return jsonify({'ok': False, 'error': 'selected local runtime not reachable', 'conversation_id': conv_id}), 503
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'conversation_id': conv_id}), 500


@localai_bp.route('/api/localai/lmstudio/chat', methods=['POST'])
def lmstudio_quick_chat():
    """Quick single-turn chat against LM Studio."""
    data  = request.get_json(silent=True) or {}
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
