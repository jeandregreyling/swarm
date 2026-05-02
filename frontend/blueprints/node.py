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

from utils.response_cache import cached_json

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
        data = request.get_json(silent=True) or {}
        # S-B6F548DCDD: surgical coercion — reject non-string scalar fields
        # outright instead of stringifying lists/dicts (which would silently
        # register nodes with junk names like "[1, 2, 3]").
        for field in ('name', 'url', 'api_key', 'role'):
            v = data.get(field)
            if v is not None and not isinstance(v, str):
                return jsonify({'error': f'{field} must be a string'}), 400
        name = (data.get('name') or '').strip()
        url = (data.get('url') or '').strip()
        api_key = (data.get('api_key') or '').strip()
        role = (data.get('role') or 'contributor').strip()
        agents = data.get('agents', [])
        capabilities = data.get('capabilities', [])
        if not isinstance(agents, list) or not isinstance(capabilities, list):
            return jsonify({'error': 'agents and capabilities must be arrays'}), 400

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
        data = request.get_json(silent=True) or {}
        # S-B6F548DCDD: reject non-string fields rather than coerce.
        for field in ('url', 'api_key', 'name'):
            v = data.get(field)
            if v is not None and not isinstance(v, str):
                return jsonify({'error': f'{field} must be a string'}), 400
        url = (data.get('url') or '').strip()
        api_key = (data.get('api_key') or '').strip()
        name = (data.get('name') or '').strip() or None

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


def _fetch_remote_json(url, path, *, timeout=5, node=None):
    """GET a JSON endpoint from a remote node. Forwards auth if node provided."""
    target = url.rstrip('/') + path
    try:
        req = urllib.request.Request(target, method='GET')
        if node:
            # D.1.2: Forward auth headers using stored credentials
            req.add_header('X-Node-ID', node.get('node_id', ''))
            # Use the node's registered API key for auth
            from utils.db.nodes import get_local_node_id
            local_id = get_local_node_id()
            req.add_header('X-Node-ID', local_id)
            # If node has an api_key stored, use it; otherwise skip auth
            api_key = node.get('_api_key', '')
            if api_key:
                req.add_header('X-Node-API-Key', api_key)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.debug(f'[Federation] fetch {target} failed: {exc}')
        return None


def _post_remote_json(url, path, payload, *, timeout=5, node=None):
    """POST JSON to a remote node endpoint. Forwards auth if node provided."""
    target = url.rstrip('/') + path
    try:
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(target, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        if node:
            from utils.db.nodes import get_local_node_id
            local_id = get_local_node_id()
            req.add_header('X-Node-ID', local_id)
            api_key = node.get('_api_key', '')
            if api_key:
                req.add_header('X-Node-API-Key', api_key)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.debug(f'[Federation] post {target} failed: {exc}')
        return None


@node_bp.route('/api/federation/proposals', methods=['GET'])
@cached_json(ttl_seconds=30)
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
@cached_json(ttl_seconds=30)
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


# ── D.1.3: Cross-Node Proposal Sync ──────────────────────────────────────────

@node_bp.route('/api/node/sync/proposals', methods=['POST'])
@require_node_api_key
def node_sync_proposals():
    """Accept a batch of proposals from a remote node. Last-writer-wins merge."""
    try:
        data = request.get_json(silent=True) or {}
        proposals = data.get('proposals', [])
        source_node = data.get('source_node', '').strip()
        if not proposals or not source_node:
            return jsonify({'error': 'proposals[] and source_node required'}), 400

        from utils.db._connection import get_connection
        conn = get_connection()
        synced, skipped = 0, 0
        try:
            for p in proposals[:100]:  # Cap at 100 per batch
                pid = p.get('proposal_id', '')
                if not pid:
                    skipped += 1
                    continue
                existing = conn.execute(
                    "SELECT updated_at FROM work_proposals WHERE proposal_id = ?",
                    (pid,)
                ).fetchone()

                if existing:
                    # Last-writer-wins: update only if remote is newer
                    remote_updated = p.get('updated_at', '')
                    local_updated = existing['updated_at'] or ''
                    if remote_updated > local_updated:
                        conn.execute(
                            "UPDATE work_proposals SET title=?, description=?, "
                            "status=?, agent=?, source_node=?, updated_at=? "
                            "WHERE proposal_id=?",
                            (p.get('title', ''), p.get('description', ''),
                             p.get('status', 'pending'), p.get('agent', ''),
                             source_node, remote_updated, pid)
                        )
                        synced += 1
                    else:
                        skipped += 1
                else:
                    # New proposal — insert
                    conn.execute(
                        "INSERT INTO work_proposals "
                        "(proposal_id, agent, title, description, status, source_node, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (pid, p.get('agent', ''), p.get('title', ''),
                         p.get('description', ''), p.get('status', 'pending'),
                         source_node,
                         p.get('created_at', ''), p.get('updated_at', ''))
                    )
                    synced += 1
            conn.commit()
        finally:
            conn.close()

        # Publish bus event
        try:
            from utils.swarm_bus import publish as bus_publish
            bus_publish('proposal.synced', {
                'source_node': source_node,
                'synced': synced, 'skipped': skipped,
            }, source_service='federation')
        except Exception:
            pass

        return jsonify({'synced': synced, 'skipped': skipped})
    except Exception as exc:
        logger.error(f'node_sync_proposals failed: {exc}')
        return jsonify({'error': str(exc)}), 500


# ── D.2.2: Skill Advertisement ───────────────────────────────────────────────

@node_bp.route('/api/node/skills', methods=['GET'])
def node_skills():
    """Return this node's available skills with trust levels."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
        from fridays.skills import REGISTRY
        skills = []
        for name, meta in REGISTRY.items():
            skills.append({
                'skill_name': name,
                'trust_level': meta.get('trust_level', 0),
                'description': meta.get('description', ''),
            })
        return jsonify({'skills': skills})
    except Exception as exc:
        logger.error(f'node_skills failed: {exc}')
        return jsonify({'error': str(exc)}), 500


# ── D.3.1: Event Relay Endpoint ──────────────────────────────────────────────

@node_bp.route('/api/node/events', methods=['POST'])
@require_node_api_key
def node_events():
    """Receive relayed events from a remote node. Dedup by topic+payload hash."""
    try:
        import hashlib
        data = request.get_json(silent=True) or {}
        events = data.get('events', [])
        source_node = data.get('source_node', '').strip()
        if not events or not source_node:
            return jsonify({'error': 'events[] and source_node required'}), 400

        from utils.db._connection import get_connection
        conn = get_connection()
        inserted, duped = 0, 0
        try:
            for evt in events[:50]:  # Cap at RELAY_BATCH_SIZE
                topic = evt.get('topic', '')
                payload = evt.get('payload', {})
                created_at = evt.get('created_at', '')
                if not topic:
                    continue

                # Dedup: hash of topic + payload + 1-minute time window
                dedup_key = hashlib.sha256(
                    f"{topic}:{json.dumps(payload, sort_keys=True)}:{created_at[:16]}".encode()
                ).hexdigest()[:32]

                existing = conn.execute(
                    "SELECT id FROM swarm_bus WHERE topic = ? AND "
                    "source_service = ? AND created_at = ?",
                    (topic, f'remote:{source_node}', created_at)
                ).fetchone()

                if existing:
                    duped += 1
                    continue

                conn.execute(
                    "INSERT INTO swarm_bus (topic, payload_json, source_service, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (topic, json.dumps(payload), f'remote:{source_node}', created_at)
                )
                inserted += 1
            conn.commit()
        finally:
            conn.close()

        return jsonify({'inserted': inserted, 'duplicates': duped})
    except Exception as exc:
        logger.error(f'node_events failed: {exc}')
        return jsonify({'error': str(exc)}), 500
