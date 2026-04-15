"""
utils/node_discovery.py — Node discovery + heartbeat daemon (A.5.1)
═══════════════════════════════════════════════════════════════════
- REST-based: pings each registered node's GET /api/node/info
- Updates last_seen on success, marks stale after threshold
- Runs as a daemon thread (started from terminal.py)
"""

import json
import logging
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
        else:
            results[nid] = False
            logger.info(f'[Discovery] node {nid} ({node["name"]}) unreachable')
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
