"""
frontend/blueprints/node.py — Node registration endpoints (A.4.5)
═════════════════════════════════════════════════════════════════
GET  /api/node/info     — this node's identity, agents, capabilities
POST /api/node/register — remote node registers itself (API key required)
GET  /api/node/list     — list all registered nodes (owner only)
"""

from flask import Blueprint, jsonify, request
import json
import logging

node_bp = Blueprint('node', __name__)
logger = logging.getLogger(__name__)


@node_bp.route('/api/node/info', methods=['GET'])
def node_info():
    """Return this node's identity, agents, and capabilities."""
    try:
        from utils.db.nodes import get_local_node_id, get_node
        from utils.db._connection import DB_PATH
        from utils.db.registry import get_all_agents

        node_id = get_local_node_id()
        node = get_node(node_id)

        # Build agent list from registry
        agents = []
        try:
            for a in get_all_agents():
                agents.append({
                    'name': a.get('name', ''),
                    'label': a.get('label', ''),
                    'enabled': bool(a.get('enabled', 1)),
                })
        except Exception:
            pass

        return jsonify({
            'node_id': node_id,
            'name': node['name'] if node else 'local',
            'role': node['role'] if node else 'owner',
            'db_path': DB_PATH,
            'agents': agents,
            'registered': node is not None,
        })
    except Exception as exc:
        logger.error(f'node_info failed: {exc}')
        return jsonify({'error': str(exc)}), 500


@node_bp.route('/api/node/register', methods=['POST'])
def node_register():
    """Register a remote node. Requires name, url, api_key."""
    try:
        data = request.get_json(force=True)
        name = data.get('name', '').strip()
        url = data.get('url', '').strip()
        api_key = data.get('api_key', '').strip()
        role = data.get('role', 'contributor').strip()
        agents = data.get('agents', [])
        capabilities = data.get('capabilities', [])

        if not name or not url or not api_key:
            return jsonify({'error': 'name, url, and api_key are required'}), 400

        from utils.db.nodes import register_node
        node_id = register_node(
            name, url, api_key,
            role=role, agents=agents, capabilities=capabilities,
        )
        return jsonify({'node_id': node_id, 'status': 'registered'})
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as exc:
        logger.error(f'node_register failed: {exc}')
        return jsonify({'error': str(exc)}), 500


@node_bp.route('/api/node/list', methods=['GET'])
def node_list():
    """List all registered nodes."""
    try:
        from utils.db.nodes import list_nodes
        nodes = list_nodes()
        # Strip api_key_hash from response
        for n in nodes:
            n.pop('api_key_hash', None)
        return jsonify({'nodes': nodes})
    except Exception as exc:
        logger.error(f'node_list failed: {exc}')
        return jsonify({'error': str(exc)}), 500
