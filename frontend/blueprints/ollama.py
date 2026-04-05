"""ollama.py — Ollama Models routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

ollama_bp = Blueprint('ollama', __name__)

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



