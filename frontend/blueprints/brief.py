"""brief.py — Ghost Brief routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

brief_bp = Blueprint('brief', __name__)

@brief_bp.route('/api/brief')
def api_brief_get():
    """Return the latest cached Ghost Brief from DB (read-only, no generation)."""
    from brief_engine import get_latest_brief
    try:
        brief = get_latest_brief()
        return jsonify({'brief': brief})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@brief_bp.route('/api/brief/generate', methods=['POST'])
def api_brief_generate():
    """Force-generate a new Ghost Brief immediately."""
    from brief_engine import generate_brief
    try:
        brief = generate_brief(trigger='manual')
        if not brief:
            return jsonify({'error': 'Brief generation failed — check Claude API key'}), 503
        return jsonify(brief)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@brief_bp.route('/api/brief/history')
def api_brief_history():
    """Return list of past Ghost Briefs."""
    from brief_engine import get_brief_history
    try:
        limit = int(request.args.get('limit', 10))
        return jsonify({'briefs': get_brief_history(limit=limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



