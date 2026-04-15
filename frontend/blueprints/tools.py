"""
frontend/blueprints/tools.py — Tool Build API (C.4.1)
═══════════════════════════════════════════════════════════════════════════════
Endpoints for viewing and managing tool builds from the frontend.
"""

import threading
from flask import Blueprint, jsonify, request

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/api/tools/builds', methods=['GET'])
def list_builds():
    """List tool builds with optional filters."""
    from utils.db.tools import list_builds as db_list
    status = request.args.get('status')
    agent = request.args.get('agent')
    limit = min(int(request.args.get('limit', 50)), 200)
    builds = db_list(status=status, building_agent=agent, limit=limit)
    return jsonify({'builds': builds})


@tools_bp.route('/api/tools/builds/<int:build_id>', methods=['GET'])
def get_build(build_id):
    """Get detail for a single build."""
    from utils.db.tools import get_build as db_get
    build = db_get(build_id)
    if build is None:
        return jsonify({'error': 'Build not found'}), 404
    return jsonify(build)


@tools_bp.route('/api/tools/builds', methods=['POST'])
def start_build():
    """Start a new tool build (scaffold from template)."""
    from fridays.tool_builder import build_tool
    data = request.get_json(silent=True) or {}
    tool_type = data.get('type', 'script')
    name = data.get('name', '').strip()
    description = data.get('description', name)
    agent = data.get('agent', 'user')

    if not name:
        return jsonify({'error': 'name is required'}), 400

    try:
        bid, path = build_tool(tool_type, name, description, agent)
        return jsonify({'build_id': bid, 'entry_path': path, 'status': 'scaffolded'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/api/tools/builds/<int:build_id>/validate', methods=['POST'])
def validate_build(build_id):
    """Trigger syntax validation for a build."""
    from fridays.tool_builder import validate_tool
    ok, msg = validate_tool(build_id)
    return jsonify({'ok': ok, 'message': msg})


@tools_bp.route('/api/tools/builds/<int:build_id>/test', methods=['POST'])
def test_build(build_id):
    """Trigger test run for a build."""
    from fridays.tool_builder import test_tool
    ok, output = test_tool(build_id)
    return jsonify({'ok': ok, 'output': output})


@tools_bp.route('/api/tools/builds/<int:build_id>/register', methods=['POST'])
def register_build(build_id):
    """Register a passing build (publishes to knowledge + bus)."""
    from fridays.tool_builder import register_tool
    ok, msg = register_tool(build_id)
    status_code = 200 if ok else 400
    return jsonify({'ok': ok, 'message': msg}), status_code


@tools_bp.route('/api/tools/templates', methods=['GET'])
def list_templates():
    """List available scaffold templates."""
    from fridays.tool_builder import list_templates
    return jsonify({'templates': list_templates()})
