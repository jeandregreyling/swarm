"""ollama.py — Ollama Models routes"""
import os
import re
import time
import requests
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

ollama_bp = Blueprint('ollama', __name__)

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

@ollama_bp.route('/api/ollama/models')
def api_ollama_models():
    """List all locally installed Ollama models."""
    import ollama as _ollama
    try:
        result = _ollama.list()
        models = []
        for m in (result.models if hasattr(result, 'models') else []):
            models.append({
                'name':        getattr(m, 'model', '') or '',
                'size':        int(getattr(m, 'size', 0) or 0),
                'modified_at': str(getattr(m, 'modified_at', '') or ''),
                'family':      (getattr(m, 'details', None) and getattr(m.details, 'family', '')) or '',
                'parameters':  (getattr(m, 'details', None) and getattr(m.details, 'parameter_size', '')) or '',
            })
        models.sort(key=lambda x: x['name'])
        return jsonify({'models': models})
    except Exception as e:
        return jsonify({'error': str(e), 'models': []}), 500


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
    """Load (warm) a model into memory permanently."""
    import requests as _requests
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        resp = _requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model, 'prompt': ' ', 'keep_alive': -1},
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
def api_ollama_unload():
    """Unload a model from memory immediately."""
    import requests as _requests
    data = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        resp = _requests.post(
            'http://localhost:11434/api/generate',
            json={'model': model, 'prompt': ' ', 'keep_alive': 0},
            timeout=30,
        )
        return jsonify({'ok': True, 'model': model})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@ollama_bp.route('/api/ollama/ps')
def api_ollama_ps():
    """Show models currently loaded (resident in RAM or being actively used)."""
    import ollama as _ollama
    try:
        result = _ollama.ps()
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



@ollama_bp.route('/api/ollama/show/<path:model>')
def api_ollama_show(model):
    """Return rich model metadata: family, quantisation, capabilities, parameters.
    Cached for 5 minutes to prevent UI polling from storming the ollama runner."""
    import ollama as _ollama
    now = time.time()
    cached = _SHOW_CACHE.get(model)
    if cached and (now - cached[0]) < _SHOW_TTL:
        return jsonify(cached[1])
    try:
        result = _ollama.show(model)
        details = getattr(result, 'details', None)
        payload = {
            'ok': True,
            'model': model,
            'modelfile':    getattr(result, 'modelfile', '') or '',
            'parameters':   getattr(result, 'parameters', '') or '',
            'template':     getattr(result, 'template', '') or '',
            'capabilities': list(getattr(result, 'capabilities', None) or []),
            'details': {
                'family':              getattr(details, 'family', '') or '' if details else '',
                'format':              getattr(details, 'format', '') or '' if details else '',
                'parameter_size':      getattr(details, 'parameter_size', '') or '' if details else '',
                'quantization_level':  getattr(details, 'quantization_level', '') or '' if details else '',
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
    import ollama as _ollama
    data  = request.get_json(silent=True) or {}
    model = (data.get('model') or '').strip()
    if not model:
        return jsonify({'ok': False, 'error': 'model required'}), 400
    try:
        # Guard: refuse if model is resident in RAM
        loaded_names = []
        try:
            ps = _ollama.ps()
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



