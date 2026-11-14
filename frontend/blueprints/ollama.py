"""ollama.py — Ollama Models routes"""
import os
import re
import time
import json
import logging
import queue
import threading
import requests
from flask import Blueprint, request, Response, jsonify, send_file
from services import *
from services.auth import require_owner

ollama_bp = Blueprint('ollama', __name__)
_LOAD_LOG = logging.getLogger(__name__)


@ollama_bp.post('/api/agents/<agent>/load')
@require_owner
def api_agent_load(agent, current_user):
    """Warm an enabled local agent with streamed, factual runtime stages."""
    from utils.db.registry import get_agent_models
    from core import llm
    from core.seven_llm import llama_server
    from urllib.parse import urlparse

    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (
        origin and urlparse(origin).netloc != request.host
    ):
        return jsonify(ok=False, error='Cross-site model loading is not allowed'), 403
    model = get_agent_models(local_only=True).get(agent)
    if not model:
        return jsonify(ok=False, error='Enabled local agent not found'), 404
    direct = llm._direct_model(model)
    if not direct:
        return jsonify(ok=False, error='No local llama.cpp model is installed for this agent'), 409
    events = queue.Queue()

    def load():
        try:
            llama_server.ensure(direct, progress=events.put)
        except Exception as exc:
            _LOAD_LOG.exception('Agent model load failed: %s', agent)
            events.put({'stage': 'error', 'error': str(exc), 'model': direct})
        finally:
            events.put(None)

    def stream():
        threading.Thread(target=load, daemon=True).start()
        yield json.dumps({'stage': 'requested', 'agent': agent, 'model': direct}) + '\n'
        while True:
            try:
                event = events.get(timeout=2)
            except queue.Empty:
                yield json.dumps({'stage': 'waiting', 'model': direct}) + '\n'
                continue
            if event is None:
                break
            yield json.dumps(event) + '\n'

    return Response(stream(), mimetype='application/x-ndjson', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
    })

# Cache /api/ollama/show responses for 5 minutes.
# Model metadata (family, quantisation, capabilities) is static at runtime, and
# repeated /api/show calls wake/block the loaded runner, burning CPU.
_SHOW_CACHE = {}
_SHOW_TTL = 300

_OLLAMA_LIBRARY_FALLBACK = [
    'gemma3:latest',
    'gemma3:4b',
    'llama3.2:3b',
    'llama3.1:8b',
    'mistral:7b',
    'qwen2.5:7b',
    'phi3:mini',
    'deepseek-r1:7b',
    'nomic-embed-text:latest',
    'snowflake-arctic-embed2:latest',
]


def _classify_ollama_runtime_error(exc: Exception) -> tuple[str, str]:
    raw = str(exc or '').strip()
    lowered = raw.lower()
    if isinstance(exc, ConnectionRefusedError) or 'connection refused' in lowered or 'unreachable' in lowered:
        return 'RUNTIME_OFFLINE', raw or 'ollama backend unreachable'
    return 'RUNTIME_ERROR', raw or 'ollama backend error'

@ollama_bp.route('/api/ollama/models')
def api_ollama_models():
    """List all locally installed Ollama models."""
    from core import llm as _llm
    try:
        result = _llm.list_models()
        models = []
        for m in (result.models if hasattr(result, 'models') else []):
            models.append({
                'name':        getattr(m, 'model', '') or getattr(m, 'name', '') or '',
                'size':        int(getattr(m, 'size', 0) or 0),
                'modified_at': str(getattr(m, 'modified_at', '') or ''),
                'family':      (getattr(m, 'details', None) and getattr(m.details, 'family', '')) or '',
                'parameters':  (getattr(m, 'details', None) and getattr(m.details, 'parameter_size', '')) or '',
            })
        models.sort(key=lambda x: x['name'])
        return jsonify({'ok': True, 'running': True, 'models': models})
    except Exception as e:
        error_code, detail = _classify_ollama_runtime_error(e)
        return jsonify({
            'ok': False,
            'running': False,
            'error_code': error_code,
            'error': detail,
            'models': [],
        })


@ollama_bp.route('/api/ollama/library')
def api_ollama_library():
    """Best-effort Ollama registry model list for pull dropdowns.

    Ollama does not currently expose a guaranteed public JSON catalog API;
    this endpoint scrapes the library page and falls back to a curated list.
    """
    models = set(_OLLAMA_LIBRARY_FALLBACK)
    try:
        r = requests.get('https://ollama.com/library', timeout=6)
        if r.status_code == 200:
            matches = re.findall(r'href="/library/([a-z0-9._:-]+)"', r.text, flags=re.IGNORECASE)
            for name in matches:
                if name and name.lower() != 'library':
                    models.add(name)
    except Exception:
        pass
    return jsonify({'ok': True, 'models': sorted(models)})



@ollama_bp.route('/api/ollama/load', methods=['POST'])
def api_ollama_load():
    """Load (warm) a model into the configured local runtime."""
    import requests as _requests
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        from core import llm as _llm
        direct = _llm._direct_model(model)
        if direct:
            from core.seven_llm import llama_server
            handle = llama_server.ensure(direct)
            return jsonify({'ok': True, 'model': direct, 'runtime': 'llamacpp', 'pid': handle.pid})
        resp = _requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model, 'prompt': ' ', 'keep_alive': 300},
            timeout=180,
            stream=True,
        )
        # Drain the streaming response so Ollama finishes loading
        for _ in resp.iter_lines():
            pass
        return jsonify({'ok': True, 'model': model})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/unload', methods=['POST'])
@require_owner
def api_ollama_unload(current_user=None):
    """Unload a model from memory immediately."""
    import requests as _requests
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        from core import llm as _llm
        direct = _llm._direct_model(model)
        if direct:
            from core.seven_llm import llama_server
            stopped = llama_server.stop(direct)
            return jsonify({'ok': True, 'model': direct, 'runtime': 'llamacpp', 'stopped': stopped})
        resp = _requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model, 'prompt': ' ', 'keep_alive': 0},
            timeout=30,
        )
        return jsonify({'ok': True, 'model': model})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@ollama_bp.route('/api/ollama/keepalive', methods=['POST'])
def api_ollama_keepalive():
    """Set per-model idle lifetime (seconds), or refresh its current runtime lease."""
    import requests as _requests
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    try:
        seconds = int(data.get('seconds', 300))
    except (TypeError, ValueError):
        seconds = 300
    seconds = max(0, min(seconds, 86400))  # clamp 0..24h
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        from core import llm as _llm
        direct = _llm._direct_model(model)
        if direct:
            from core.seven_llm import llama_server
            if seconds == 0:
                llama_server.stop(direct)
                effective_seconds = 0
            else:
                effective_seconds = llama_server.set_ttl(direct, seconds)
                llama_server.ensure(direct)
            return jsonify({
                'ok': True,
                'model': direct,
                'runtime': 'llamacpp',
                'seconds': effective_seconds,
            })
        _requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model, 'prompt': ' ', 'keep_alive': seconds},
            timeout=30,
        )
        return jsonify({'ok': True, 'model': model, 'seconds': seconds})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/ps')
def api_ollama_ps():
    """Show models currently loaded (resident in RAM or being actively used)."""
    from core import llm as _llm
    try:
        result = _llm.ps()
        models = []
        for m in (result.models if hasattr(result, 'models') else []):
            size_bytes  = int(getattr(m, 'size', 0) or 0)
            vram_bytes  = int(getattr(m, 'size_vram', 0) or 0)
            models.append({
                'name':       getattr(m, 'model', '') or getattr(m, 'name', '') or '',
                'size_gb':    round(size_bytes / (1024 ** 3), 2),
                'size_vram_gb': round(vram_bytes / (1024 ** 3), 2),
                'expires_at': str(getattr(m, 'expires_at', '') or ''),
            })
        return jsonify({'ok': True, 'models': models, 'count': len(models)})
    except Exception as e:
        return jsonify({'ok': True, 'models': [], 'count': 0, 'error': str(e)})


@ollama_bp.route('/api/ollama/runtime/health')
def api_ollama_runtime_health():
    """Report the local inference runtime, preferring registered llama.cpp models."""
    from core.model_runtime_gateway import ollama_health
    snapshot = ollama_health()
    if snapshot.get('ok'):
        return jsonify(snapshot)
    try:
        from core.seven_llm import llama_server, registry
        from core.seven_llm.llama_server import default_binary

        direct_models = [
            entry for entry in registry.list_models()
            if entry.driver == 'llamacpp' and entry.path and os.path.isfile(entry.path)
        ]
        if direct_models and os.path.isfile(default_binary()):
            models = [
                {
                    'name': str(item.get('model') or ''),
                    'state': 'loaded',
                    'runtime': 'llamacpp',
                    'pid': item.get('pid'),
                }
                for item in llama_server.resource_snapshot().get('residents') or []
                if item.get('model')
            ]
            return jsonify({
                'ok': True,
                'status': 'healthy',
                'models': models,
                'warnings': [],
                'provider': 'llamacpp',
            })
    except Exception as exc:
        snapshot.setdefault('warnings', []).append(f'llama.cpp health check failed: {exc}')
    return jsonify(snapshot)


@ollama_bp.route('/api/ollama/runtime/json-normalize', methods=['POST'])
def api_ollama_runtime_json_normalize():
    """Normalize model JSON-ish text for downstream Studio/Media consumers."""
    from core.model_runtime_gateway import normalize_model_json
    data = request.get_json(silent=True) or {}
    return jsonify(normalize_model_json(str(data.get('text') or '')))


@ollama_bp.route('/api/ollama/runtime/force-unload', methods=['POST'])
def api_ollama_runtime_force_unload():
    """Best-effort recovery for an Ollama runner stuck in 'Stopping'.

    Tries a polite unload, polls /api/ps, and escalates to systemctl restart
    only if the runner is still stuck. Returns a structured snapshot so the
    UI can show what was attempted and the next operator action if needed.
    """
    from core.model_runtime_gateway import force_unload
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    snap = force_unload(model)
    status_code = 200 if snap.get('ok') else 409
    return jsonify(snap), status_code



@ollama_bp.route('/api/ollama/show/<path:model>')
def api_ollama_show(model):
    """Return rich model metadata: family, quantisation, capabilities, parameters.
    Cached for 5 minutes to prevent UI polling from storming the ollama runner."""
    now = time.time()
    cached = _SHOW_CACHE.get(model)
    if cached and (now - cached[0]) < _SHOW_TTL:
        return jsonify(cached[1])
    try:
        from core import llm as _llm
        result = _llm.show(model)
        details = getattr(result, 'details', None)
        details = details if isinstance(details, dict) else {
            'family': getattr(details, 'family', '') or '',
            'format': getattr(details, 'format', '') or '',
            'parameter_size': getattr(details, 'parameter_size', '') or '',
            'quantization_level': getattr(details, 'quantization_level', '') or '',
        }
        payload = {
            'ok': True,
            'model': model,
            'modelfile':    getattr(result, 'modelfile', '') or '',
            'parameters':   getattr(result, 'parameters', '') or '',
            'template':     getattr(result, 'template', '') or '',
            'capabilities': list(getattr(result, 'capabilities', None) or []),
            'details': {
                'family':              details.get('family') or '',
                'format':              details.get('format') or '',
                'parameter_size':      details.get('parameter_size') or '',
                'quantization_level':  details.get('quantization_level') or '',
            },
        }
        _SHOW_CACHE[model] = (now, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/pull', methods=['POST'])
def api_ollama_pull():
    """Pull a model from the Ollama registry. Streams NDJSON progress."""
    import ollama as _ollama, json as _json
    data  = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400

    def _generate():
        try:
            for progress in _ollama.pull(model, stream=True):
                yield _json.dumps({
                    'status':    getattr(progress, 'status', '') or '',
                    'completed': int(getattr(progress, 'completed', 0) or 0),
                    'total':     int(getattr(progress, 'total', 0) or 0),
                }) + '\n'
            yield _json.dumps({'status': 'done', 'ok': True}) + '\n'
        except Exception as e:
            yield _json.dumps({'ok': False, 'error': str(e)}) + '\n'

    return Response(_generate(), mimetype='application/x-ndjson')



@ollama_bp.route('/api/ollama/delete', methods=['POST'])
def api_ollama_delete():
    """Delete a locally installed model. Refuses if the model is currently loaded."""
    from core import llm as _llm
    data  = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        if _llm._direct_model(model):
            return jsonify({
                'ok': False,
                'error': 'This model is registered with the local llama.cpp runtime; deleting it here could remove shared model files.',
            }), 409
        import ollama as _ollama
        # Guard: refuse if model is resident in RAM
        loaded_names = []
        try:
            ps = _llm.ps()
            loaded_names = [
                getattr(m, 'model', '') or ''
                for m in (ps.models if hasattr(ps, 'models') else [])
            ]
        except Exception:
            pass
        if any(model in n or n in model for n in loaded_names if n):
            return jsonify({
                'ok': False,
                'error': f'{model} is currently loaded in RAM — unload it first',
            }), 409
        _ollama.delete(model)
        return jsonify({'ok': True, 'model': model})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/create', methods=['POST'])
def api_ollama_create():
    """Create a named model variant by baking in a custom system prompt."""
    import ollama as _ollama
    data   = request.get_json(silent=True) or {}
    name   = (data.get('name') or '').strip()
    base   = (data.get('base') or '').strip()
    system = (data.get('system') or '').strip()
    if not name or not base:
        return jsonify({'ok': False, 'error': 'name and base are required'}), 400
    try:
        _ollama.create(model=name, from_=base, system=system or None)
        return jsonify({'ok': True, 'name': name, 'base': base})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/web_search', methods=['POST'])
def api_ollama_web_search():
    """Web search via Ollama cloud API. Requires OLLAMA_API_KEY environment variable."""
    import ollama as _ollama
    data       = request.get_json(silent=True) or {}
    query      = (data.get('query') or '').strip()
    max_results = int(data.get('max_results', 3))
    if not query:
        return jsonify({'ok': False, 'error': 'query required'}), 400
    api_key = os.environ.get('OLLAMA_API_KEY', '').strip()
    if not api_key:
        return jsonify({
            'ok': False,
            'error': 'OLLAMA_API_KEY not set — Ollama web_search is a cloud feature; set the env var to enable it',
        }), 503
    try:
        client  = _ollama.Client(headers={'Authorization': f'Bearer {api_key}'})
        result  = client.web_search(query, max_results=max_results)
        results = [
            {'title': r.title, 'url': r.url, 'content': r.content}
            for r in (result.results or [])
        ]
        return jsonify({'ok': True, 'query': query, 'results': results})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/web_fetch', methods=['POST'])
def api_ollama_web_fetch():
    """Fetch URL content via Ollama cloud API. Requires OLLAMA_API_KEY environment variable."""
    import ollama as _ollama
    data    = request.get_json(silent=True) or {}
    url     = (data.get('url') or '').strip()
    if not url:
        return jsonify({'ok': False, 'error': 'url required'}), 400
    api_key = os.environ.get('OLLAMA_API_KEY', '').strip()
    if not api_key:
        return jsonify({
            'ok': False,
            'error': 'OLLAMA_API_KEY not set — Ollama web_fetch is a cloud feature; set the env var to enable it',
        }), 503
    try:
        client = _ollama.Client(headers={'Authorization': f'Bearer {api_key}'})
        result = client.web_fetch(url)
        return jsonify({
            'ok':      True,
            'url':     url,
            'title':   result.title,
            'content': result.content,
            'links':   list(result.links or []),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
