"""
frontend/blueprints/node.py — Node registration + federation endpoints (A.4.5 + A.5)
═════════════════════════════════════════════════════════════════════════════════════
GET  /api/node/info         — this node's identity, agents, capabilities
POST /api/node/register     — remote node registers itself (API key required)
GET  /api/node/list         — list all registered nodes
POST /api/node/discover     — discover + register a remote node by URL
POST /api/node/heartbeat    — trigger one heartbeat cycle
GET  /api/node/proposals    — this node's proposals (for remote consumption)
GET  /api/federation/proposals — aggregated proposals from all connected nodes
GET  /api/federation/roster — aggregated agent roster from all connected nodes
"""

from flask import Blueprint, jsonify, request
import json
import logging
import urllib.request
import urllib.error
import functools

node_bp = Blueprint('node', __name__)
logger = logging.getLogger(__name__)


# ── A.5.4: Node Authentication ───────────────────────────────────────────────

def require_node_api_key(f):
    """Decorator: require valid X-Node-API-Key header.

    Looks up the node by X-Node-ID header, verifies the key hash matches.
    Skips auth if no nodes are registered yet (bootstrap mode).
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        node_id = request.headers.get('X-Node-ID', '').strip()
        api_key = request.headers.get('X-Node-API-Key', '').strip()
        if not node_id or not api_key:
            return jsonify({'error': 'X-Node-ID and X-Node-API-Key headers required'}), 401
        from utils.db.nodes import verify_api_key, get_node
        node = get_node(node_id)
        if not node:
            return jsonify({'error': f'Unknown node: {node_id}'}), 403
        if not verify_api_key(node_id, api_key):
            return jsonify({'error': 'Invalid API key'}), 403
        return f(*args, **kwargs)
    return decorated


@node_bp.route('/api/node/info', methods=['GET'])
def node_info():
    """Return this node's identity, agents, and capabilities."""
    try:
        from utils.db.nodes import get_local_node_id, get_node
        from utils.db._connection import DB_PATH
        from utils.db.registry import get_all_agents_raw

        node_id = get_local_node_id()
        node = get_node(node_id)

        # Build agent list from registry
        agents = []
        try:
            for a in get_all_agents_raw():
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


@node_bp.route('/api/node/discover', methods=['POST'])
def node_discover():
    """Discover and register a remote node by URL. Requires url + api_key."""
    try:
        data = request.get_json(force=True)
        url = data.get('url', '').strip()
        api_key = data.get('api_key', '').strip()
        name = data.get('name', '').strip() or None

        if not url or not api_key:
            return jsonify({'error': 'url and api_key are required'}), 400

        from utils.node_discovery import discover_node
        result = discover_node(url, api_key, name=name)
        if result is None:
            return jsonify({'error': f'Node at {url} is unreachable'}), 502
        return jsonify(result)
    except Exception as exc:
        logger.error(f'node_discover failed: {exc}')
        return jsonify({'error': str(exc)}), 500


@node_bp.route('/api/node/heartbeat', methods=['POST'])
def node_heartbeat():
    """Run one heartbeat cycle immediately (admin trigger)."""
    try:
        from utils.node_discovery import run_heartbeat_once
        results = run_heartbeat_once()
        return jsonify({'results': results})
    except Exception as exc:
        logger.error(f'node_heartbeat failed: {exc}')
        return jsonify({'error': str(exc)}), 500


# ── A.5.2: Cross-Node Proposal Visibility ────────────────────────────────────

@node_bp.route('/api/node/proposals', methods=['GET'])
@require_node_api_key
def node_proposals():
    """Return this node's proposals (for remote nodes to consume)."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT proposal_id, title, description, agent, status, "
                "created_at, updated_at FROM work_proposals "
                "ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
            proposals = [dict(r) for r in rows]
        finally:
            conn.close()
        from utils.db.nodes import get_local_node_id
        return jsonify({
            'node_id': get_local_node_id(),
            'proposals': proposals,
        })
    except Exception as exc:
        logger.error(f'node_proposals failed: {exc}')
        return jsonify({'error': str(exc)}), 500


def _fetch_remote_json(url, path, *, timeout=10):
    """GET a JSON endpoint from a remote node."""
    target = url.rstrip('/') + path
    try:
        req = urllib.request.Request(target, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.debug(f'[Federation] fetch {target} failed: {exc}')
        return None


@node_bp.route('/api/federation/proposals', methods=['GET'])
def federation_proposals():
    """Aggregate proposals from this node + all connected remote nodes."""
    try:
        from utils.db._connection import get_connection
        from utils.db.nodes import list_nodes, get_local_node_id

        local_id = get_local_node_id()
        all_proposals = []

        # Local proposals
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT proposal_id, title, description, agent, status, "
                "created_at, updated_at FROM work_proposals "
                "ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
            for r in rows:
                p = dict(r)
                p['_node_id'] = local_id
                p['_node_name'] = 'local'
                all_proposals.append(p)
        finally:
            conn.close()

        # Remote proposals
        for node in list_nodes():
            if node['node_id'] == local_id:
                continue
            url = node.get('url', '')
            if not url:
                continue
            data = _fetch_remote_json(url, '/api/node/proposals')
            if data and 'proposals' in data:
                for p in data['proposals']:
                    p['_node_id'] = node['node_id']
                    p['_node_name'] = node.get('name', 'unknown')
                    all_proposals.append(p)

        return jsonify({'proposals': all_proposals})
    except Exception as exc:
        logger.error(f'federation_proposals failed: {exc}')
        return jsonify({'error': str(exc)}), 500


# ── A.5.3: Federated Agent Roster + Skill Registry ───────────────────────────

@node_bp.route('/api/federation/roster', methods=['GET'])
def federation_roster():
    """Aggregate agent roster from this node + all connected remote nodes."""
    try:
        from utils.db.nodes import list_nodes, get_local_node_id

        local_id = get_local_node_id()
        roster = []

        # Local agents
        try:
            from utils.db.registry import get_all_agents_raw
            for a in get_all_agents_raw():
                roster.append({
                    'name': a.get('name', ''),
                    'label': a.get('label', ''),
                    'enabled': bool(a.get('enabled', 1)),
                    'model': a.get('model', ''),
                    '_node_id': local_id,
                    '_node_name': 'local',
                    '_remote': False,
                })
        except Exception:
            pass

        # Remote agents via /api/node/info
        for node in list_nodes():
            if node['node_id'] == local_id:
                continue
            url = node.get('url', '')
            if not url:
                continue
            data = _fetch_remote_json(url, '/api/node/info')
            if data and 'agents' in data:
                for a in data['agents']:
                    a['_node_id'] = node['node_id']
                    a['_node_name'] = node.get('name', 'unknown')
                    a['_remote'] = True
                    roster.append(a)

        return jsonify({'roster': roster})
    except Exception as exc:
        logger.error(f'federation_roster failed: {exc}')
        return jsonify({'error': str(exc)}), 500
