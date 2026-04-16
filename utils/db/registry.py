"""
db.registry — Cached Agent Registry: single source of truth for all agent metadata.

Every runtime dict that previously hardcoded agent definitions now reads from here.
The DB `agents` table is the canonical store; this module caches it with a 60-second TTL.

Usage:
    from utils.db.registry import (
        get_agent_roster,        # list[dict] — replaces _AGENT_ROSTER
        get_agent_aliases,       # dict str→str — replaces _CHAT_PARTICIPANT_ALIASES
        get_agent_tables,        # dict str→str — replaces _AGENT_TABLES
        get_agent_models,        # dict str→str — replaces AGENTS (orchestrator)
        get_agent_temps,         # dict str→float — replaces TEMPERATURES
        get_agent_prompts,       # dict str→str — replaces SYSTEM_PROMPTS
        get_agent_etas,          # dict str→int — replaces _CHAT_AGENT_ETA_SECONDS
        get_agent_runtime_classes,  # dict str→str — replaces _CHAT_AGENT_RUNTIME_CLASS
        get_single_task_locals,  # set[str] — replaces _CHAT_SINGLE_TASK_LOCAL_AGENTS
        get_keep_alive_map,      # dict str→int — replaces MODEL_KEEP_ALIVE
        get_display_labels,      # dict str→str — replaces _display_chat_participant labels
        get_api_key_map,         # dict str→str — replaces _agent_reachability_status key_map
        invalidate_cache,        # force refresh on next access
    )
"""

import json
import time
import threading
from ._connection import get_connection, logger

__all__ = [
    'get_agent_roster', 'get_agent_aliases', 'get_agent_tables',
    'get_agent_models', 'get_agent_temps', 'get_agent_prompts',
    'get_agent_etas', 'get_agent_runtime_classes', 'get_single_task_locals',
    'get_keep_alive_map', 'get_display_labels', 'get_api_key_map',
    'invalidate_cache', 'get_all_agents_raw',
]

# ── Cache internals ──────────────────────────────────────────────────────────
_CACHE_TTL = 60  # seconds
_cache_lock = threading.Lock()
_cache = {
    'stamp': 0.0,
    'rows': [],     # list of dicts from DB
}


def invalidate_cache():
    """Force the next accessor to reload from DB."""
    with _cache_lock:
        _cache['stamp'] = 0.0


def _load_rows():
    """Fetch all active agents from DB, refreshing cache if stale."""
    now = time.monotonic()
    with _cache_lock:
        if now - _cache['stamp'] < _CACHE_TTL and _cache['rows']:
            return _cache['rows']
    # Outside lock for the actual DB read
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT name, number, label, model, temperature, role,
                          system_prompt, api_key_var, tier, enabled,
                          memory_table, display_label, aliases,
                          eta_seconds, keep_alive
                   FROM agents
                   WHERE number >= 0 AND enabled = 1
                   ORDER BY number ASC"""
            ).fetchall()
            result = [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'registry._load_rows failed: {e}')
        with _cache_lock:
            return _cache['rows']  # return stale if DB fails
    with _cache_lock:
        _cache['rows'] = result
        _cache['stamp'] = time.monotonic()
    return result


# ── Public accessors ─────────────────────────────────────────────────────────

def get_all_agents_raw():
    """Return raw list of agent dicts from DB. Used by get_agent_registry()."""
    return _load_rows()


def get_agent_roster():
    """Replaces _AGENT_ROSTER in services.py.
    Returns list of dicts with keys matching the old format.
    `name` is the canonical DB key (lowercase); `label` is the display name."""
    out = []
    for r in _load_rows():
        entry = {
            'name': r['name'],
            'label': r.get('label') or r['name'].capitalize(),
            'model': r['model'],
            'role': r['role'] or '',
            'default_temp': r['temperature'],
        }
        tier = r.get('tier', 'local')
        if tier in ('paid', 'service') or r['name'] == 'ghost':
            entry['no_temp'] = True
        if 'Developer Agent' in (r['role'] or '') or 'developer' in (r['role'] or '').lower():
            entry['developer_agent'] = True
        if r['name'] == 'ghost':
            entry['ghost_layer'] = True
            entry['no_toggle'] = True
        out.append(entry)
    return out


def get_agent_aliases():
    """Replaces _CHAT_PARTICIPANT_ALIASES in services.py.
    Returns dict mapping every alias → canonical agent name."""
    aliases = {'user': 'user', 'ghost': 'user', 'fridays': 'fridays'}
    for r in _load_rows():
        name = r['name']
        if name == 'ghost':
            continue
        aliases[name] = name
        # Parse the JSON aliases column
        raw = r.get('aliases') or '[]'
        try:
            extra = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            extra = []
        for a in extra:
            aliases[str(a).lower().strip()] = name
    return aliases


def get_agent_tables():
    """Replaces _AGENT_TABLES in services.py and memory.py.
    Returns dict agent_name → memory table name."""
    out = {}
    for r in _load_rows():
        name = r['name']
        tbl = r.get('memory_table') or ''
        if tbl:
            out[name] = tbl
    return out


def get_agent_models(local_only=False):
    """Replaces AGENTS dict in orchestrator.py.
    If local_only=True, returns only tier='local' agents."""
    out = {}
    for r in _load_rows():
        if local_only and r.get('tier', 'local') != 'local':
            continue
        out[r['name']] = r['model']
    return out


def get_agent_temps(local_only=False):
    """Replaces TEMPERATURES dict in orchestrator.py."""
    out = {}
    for r in _load_rows():
        if local_only and r.get('tier', 'local') != 'local':
            continue
        if r['temperature'] is not None:
            out[r['name']] = r['temperature']
    return out


def get_agent_prompts():
    """Replaces SYSTEM_PROMPTS dict in orchestrator.py."""
    out = {}
    for r in _load_rows():
        prompt = r.get('system_prompt') or ''
        if prompt:
            out[r['name']] = prompt
    return out


def get_agent_etas():
    """Replaces _CHAT_AGENT_ETA_SECONDS in services.py."""
    out = {}
    for r in _load_rows():
        eta = r.get('eta_seconds')
        if eta is not None:
            out[r['name']] = int(eta)
    return out


def get_agent_runtime_classes():
    """Replaces _CHAT_AGENT_RUNTIME_CLASS in services.py."""
    _tier_map = {'local': 'local', 'paid': 'paid', 'free': 'paid', 'service': 'service', 'human': 'local'}
    out = {}
    for r in _load_rows():
        if r['name'] == 'ghost':
            continue
        out[r['name']] = _tier_map.get(r.get('tier', 'local'), 'local')
    return out


def get_single_task_locals():
    """Replaces _CHAT_SINGLE_TASK_LOCAL_AGENTS in services.py.
    Returns set of local agents that run as single-task Ollama instances."""
    skip = {'librarian', 'duck', 'sniffles'}
    out = set()
    for r in _load_rows():
        if r.get('tier', 'local') == 'local' and r['name'] not in skip and r['name'] != 'ghost':
            out.add(r['name'])
    return out


def get_keep_alive_map():
    """Replaces MODEL_KEEP_ALIVE in orchestrator.py."""
    out = {}
    for r in _load_rows():
        ka = r.get('keep_alive')
        if ka is not None:
            out[r['name']] = int(ka)
    return out


def get_display_labels():
    """Replaces the inline dict in _display_chat_participant (services.py)."""
    out = {'user': 'USER', 'fridays': 'FRIDAYS'}
    for r in _load_rows():
        name = r['name']
        dl = r.get('display_label') or ''
        if dl:
            out[name] = dl
        else:
            out[name] = name.upper()
    return out


def get_api_key_map():
    """Replaces the inline key_map in _agent_reachability_status (services.py).
    Returns dict agent_name → env var name (only for agents with API keys)."""
    out = {}
    for r in _load_rows():
        kv = r.get('api_key_var') or ''
        if kv:
            out[r['name']] = kv
    return out
