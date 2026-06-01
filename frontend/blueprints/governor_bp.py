from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.system_governor import get_governor, init_governor


governor_bp = Blueprint('governor_bp', __name__)


@governor_bp.route('/api/governor/state', methods=['GET'])
def api_governor_state():
    return jsonify({'ok': True, 'governor': get_governor().state()})


@governor_bp.route('/api/governor/focus', methods=['POST'])
def api_governor_focus():
    data = request.get_json(silent=True) or {}
    surface = str(data.get('surface') or data.get('window') or '').strip()
    if not surface:
        return jsonify({'ok': False, 'error': 'surface required'}), 400
    event = get_governor().update_focus_surface(data)
    return jsonify({'ok': True, 'focus': event})


@governor_bp.route('/api/governor/enforce', methods=['POST'])
def api_governor_enforce():
    data = request.get_json(silent=True) or {}
    context = data.get('context') if isinstance(data.get('context'), dict) else {}
    verdict = get_governor().enforce(data.get('input') or {}, context=context)
    return jsonify({'ok': True, 'verdict': verdict})


def ensure_governor() -> None:
    init_governor()
