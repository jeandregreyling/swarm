"""
utils/node_discovery.py — Node discovery + heartbeat + event relay (A.5.1, D.2, D.3)
═══════════════════════════════════════════════════════════════════════════════════════
- REST-based: pings each registered node's GET /api/node/info
- Updates last_seen on success, marks stale after threshold
- Fetches remote skills and updates node_skills table (D.2)
- Relays unconsumed bus events to reachable nodes (D.3)
- Runs as a daemon thread (started from terminal.py)
"""

import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error

from utils.db.nodes import list_nodes, touch_node, get_local_node_id

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds (default: 60s)
HEARTBEAT_INTERVAL = 60
# Node considered stale if no response for this many seconds
STALE_THRESHOLD = 300

# D.3: Event relay configuration
RELAY_TOPICS = os.environ.get('SWARM_RELAY_TOPICS',
    'proposal.created,proposal.status_changed,knowledge.new,tool.registered'
).split(',')
RELAY_BATCH_SIZE = 50
RELAY_MAX_AGE = 3600  # Ignore events older than 1 hour

_heartbeat_thread = None
_stop_event = threading.Event()


def ping_node(url, *, timeout=10):
    """GET /api/node/info on a remote node. Returns parsed JSON or None."""
    target = url.rstrip('/') + '/api/node/info'
    try:
        req = urllib.request.Request(target, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as exc:
        logger.debug(f'[Discovery] ping failed for {url}: {exc}')
        return None


def run_heartbeat_once():
    """Ping all registered nodes once. Updates last_seen for live ones.
    Returns dict of {node_id: True/False} for reachable/unreachable.
    """
    local_id = get_local_node_id()
    nodes = list_nodes()
    results = {}
    for node in nodes:
        nid = node['node_id']
        if nid == local_id:
            # Don't ping ourselves
            touch_node(nid)
            results[nid] = True
            continue
        url = node.get('url', '')
        if not url:
            results[nid] = False
            continue
        info = ping_node(url)
        if info:
            touch_node(nid)
            results[nid] = True
            logger.debug(f'[Discovery] node {nid} ({node["name"]}) alive')
            # D.2: Fetch and store remote skills
            _sync_remote_skills(url, nid)
        else:
            results[nid] = False
            logger.info(f'[Discovery] node {nid} ({node["name"]}) unreachable')
            # D.2: Mark skills stale for unreachable node
            try:
                from utils.db.node_skills import mark_stale
                mark_stale(nid)
            except Exception:
                pass

    # D.3: Relay events to all reachable nodes
    reachable = [n for n in nodes if results.get(n['node_id']) and n['node_id'] != local_id]
    if reachable:
        _relay_events(reachable)

    return results


def _heartbeat_loop():
    """Background loop that runs heartbeat at HEARTBEAT_INTERVAL."""
    while not _stop_event.is_set():
        try:
            run_heartbeat_once()
        except Exception:
            logger.exception('[Discovery] heartbeat cycle failed')
        _stop_event.wait(HEARTBEAT_INTERVAL)


def start_heartbeat():
    """Start the background heartbeat daemon thread."""
    global _heartbeat_thread
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        return  # Already running
    _stop_event.clear()
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop, daemon=True, name='node-heartbeat'
    )
    _heartbeat_thread.start()
    logger.info('[Discovery] heartbeat daemon started')


def stop_heartbeat():
    """Signal the heartbeat daemon to stop."""
    _stop_event.set()
    if _heartbeat_thread:
        _heartbeat_thread.join(timeout=5)


def discover_node(url, api_key, *, name=None):
    """Discover a remote node by URL, register it if reachable."""
    info = ping_node(url)
    if not info:
        return None
    remote_name = name or info.get('name', 'unknown')
    agents = [a.get('name', '') for a in info.get('agents', [])]
    from utils.db.nodes import register_node
    node_id = register_node(
        remote_name, url, api_key,
        role='contributor', agents=agents,
    )
    return {'node_id': node_id, 'name': remote_name, 'agents': agents}


# ── D.2: Remote Skill Sync ───────────────────────────────────────────────────

def _sync_remote_skills(url, node_id):
    """Fetch skills from a remote node and update local node_skills table."""
    target = url.rstrip('/') + '/api/node/skills'
    try:
        req = urllib.request.Request(target, method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        skills = data.get('skills', [])
        if skills:
            from utils.db.node_skills import upsert_node_skills
            upsert_node_skills(node_id, skills)
            logger.debug(f'[Discovery] synced {len(skills)} skills from {node_id}')
    except Exception as exc:
        logger.debug(f'[Discovery] skill sync failed for {node_id}: {exc}')


# ── D.3: Outbound Event Relay ────────────────────────────────────────────────

def _relay_events(reachable_nodes):
    """Relay unconsumed bus events to all reachable remote nodes."""
    try:
        from utils.db._connection import get_connection
        from datetime import datetime, timedelta

        conn = get_connection()
        try:
            # Get unconsumed events matching relay topics, within max age
            cutoff = (datetime.now() - timedelta(seconds=RELAY_MAX_AGE)).strftime('%Y-%m-%d %H:%M:%S')
            placeholders = ','.join('?' * len(RELAY_TOPICS))
            rows = conn.execute(
                f"SELECT id, topic, payload_json, source_service, created_at "
                f"FROM swarm_bus "
                f"WHERE consumed_at IS NULL AND topic IN ({placeholders}) "
                f"AND created_at > ? AND source_service NOT LIKE 'remote:%' "
                f"ORDER BY created_at ASC LIMIT ?",
                (*RELAY_TOPICS, cutoff, RELAY_BATCH_SIZE)
            ).fetchall()

            if not rows:
                return

            events = []
            event_ids = []
            for r in rows:
                events.append({
                    'topic': r[1] if isinstance(r, tuple) else r['topic'],
                    'payload': json.loads(r[2] if isinstance(r, tuple) else r['payload_json']),
                    'created_at': r[4] if isinstance(r, tuple) else r['created_at'],
                })
                event_ids.append(r[0] if isinstance(r, tuple) else r['id'])

            local_id = get_local_node_id()
            payload = json.dumps({
                'source_node': local_id,
                'events': events,
            }).encode('utf-8')

            # POST to each reachable node
            for node in reachable_nodes:
                nurl = node.get('url', '')
                if not nurl:
                    continue
                target = nurl.rstrip('/') + '/api/node/events'
                try:
                    req = urllib.request.Request(target, data=payload, method='POST')
                    req.add_header('Content-Type', 'application/json')
                    req.add_header('X-Node-ID', local_id)
                    # Note: api_key not available in node dict from list_nodes
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        resp.read()
                except Exception as exc:
                    logger.debug(f'[Relay] event relay to {node["node_id"]} failed: {exc}')

            # Mark relayed events as consumed
            if event_ids:
                id_placeholders = ','.join('?' * len(event_ids))
                conn.execute(
                    f"UPDATE swarm_bus SET consumed_at = datetime('now') "
                    f"WHERE id IN ({id_placeholders})",
                    event_ids
                )
                conn.commit()
                logger.debug(f'[Relay] relayed {len(events)} events to {len(reachable_nodes)} nodes')
        finally:
            conn.close()
    except Exception as exc:
        logger.debug(f'[Relay] event relay failed: {exc}')
