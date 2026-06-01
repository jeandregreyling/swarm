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
import os
import threading
import time
from datetime import datetime, timezone

import requests
from ._connection import get_connection, logger


def _resolve_ollama_host() -> str:
    env = os.environ.get('OLLAMA_HOST', '').strip()
    if env:
        return env if env.startswith('http') else f'http://{env}'

    try:
        release = open('/proc/sys/kernel/osrelease', 'r', encoding='utf-8').read().lower()
        if 'microsoft' in release or 'wsl' in release:
            resolv = open('/etc/resolv.conf', 'r', encoding='utf-8').read()
            match = __import__('re').search(r'^nameserver\s+([\d.]+)', resolv, __import__('re').MULTILINE)
            if match:
                return f'http://{match.group(1)}:11434'
    except OSError:
        pass

    return 'http://127.0.0.1:11434'


OLLAMA_BASE_URL = _resolve_ollama_host()

__all__ = [
    'get_agent_roster', 'get_agent_aliases', 'get_agent_tables',
    'get_agent_models', 'get_agent_temps', 'get_agent_prompts',
    'get_agent_etas', 'get_agent_runtime_classes', 'get_single_task_locals',
    'get_keep_alive_map', 'get_display_labels', 'get_api_key_map',
    'invalidate_cache', 'get_all_agents_raw',
    'full_zoo_ping', 'get_zoo_ping_snapshot',
    # Routing view — used by chat/relay/queue to decide who's addressable.
    'get_routable_agents', 'is_agent_routable',
    'SILENT_API_TIERS', 'ROUTABLE_EXCLUDED_TIERS',
    'set_runtime_disabled_provider',
]

# Tiers that are NEVER in the routable (user-facing) view.
#   service = silent APIs (Scholar=Gemini, Seeker=Tavily) used by local agents
#             for internet/vision access. They are not chat participants.
#   human   = Ghost — the operator, not an agent to be routed to.
SILENT_API_TIERS = frozenset({'service'})
ROUTABLE_EXCLUDED_TIERS = frozenset({'service', 'human'})

# ── Cache internals ──────────────────────────────────────────────────────────
_CACHE_TTL = 60  # seconds
_cache_lock = threading.Lock()
_cache = {
    'stamp': 0.0,
    'rows': [],     # list of dicts from DB
}

_NON_OLLAMA_MODELS = frozenset({'', 'external', 'local-algorithm'})
_API_PING_TIMEOUT_S = 6
_PROVIDER_META = {
    'GROQ_API_KEY': {
        'provider': 'groq',
        'fault_domain': 'EXTERNAL_API',
        'method': 'GET',
        'url': 'https://api.groq.com/openai/v1/models',
        'headers': lambda key: {'Authorization': f'Bearer {key}'},
    },
    'GITHUB_TOKEN': {
        'provider': 'github',
        'fault_domain': 'EXTERNAL_API',
        'method': 'GET',
        'url': 'https://api.github.com/user',
        'headers': lambda key: {'Authorization': f'token {key}'},
    },
    'XAI_API_KEY': {
        'provider': 'xai',
        'fault_domain': 'EXTERNAL_API',
        'method': 'GET',
        'url': 'https://api.x.ai/v1/models',
        'headers': lambda key: {'Authorization': f'Bearer {key}'},
    },
    'ANTHROPIC_API_KEY': {
        'provider': 'anthropic',
        'fault_domain': 'EXTERNAL_API',
        'method': 'GET',
        'url': 'https://api.anthropic.com/v1/models',
        'headers': lambda key: {
            'x-api-key': key,
            'anthropic-version': '2023-06-01',
        },
    },
    'HF_API_TOKEN': {
        'provider': 'huggingface',
        'fault_domain': 'EXTERNAL_API',
        'method': 'GET',
        'url': 'https://huggingface.co/api/whoami-v2',
        'headers': lambda key: {'Authorization': f'Bearer {key}'},
    },
}
_NAME_PROVIDER_META = {
    'nine': ('groq', 'EXTERNAL_API'),
    'ten': ('github', 'EXTERNAL_API'),
    'eleven': ('xai', 'EXTERNAL_API'),
    'twelve': ('anthropic', 'EXTERNAL_API'),
    'thirteen': ('huggingface', 'EXTERNAL_API'),
}

_RUNTIME_TRUTH_COLUMNS = [
    "ALTER TABLE agents ADD COLUMN provider TEXT DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN fault_domain TEXT DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN runtime_status TEXT DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN runtime_reason TEXT DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN registry_status TEXT DEFAULT ''",
    "ALTER TABLE agents ADD COLUMN runtime_checked_at TEXT DEFAULT ''",
]


def invalidate_cache():
    """Force the next accessor to reload from DB."""
    with _cache_lock:
        _cache['stamp'] = 0.0


def _ensure_runtime_truth_columns():
    try:
        conn = get_connection()
        try:
            for ddl in _RUNTIME_TRUTH_COLUMNS:
                try:
                    conn.execute(ddl)
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'registry._ensure_runtime_truth_columns failed: {e}')


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


def _load_rows_all():
    """Fetch all non-retired agents, including disabled rows, for census work."""
    _ensure_runtime_truth_columns()
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT name, number, label, model, temperature, role,
                          system_prompt, api_key_var, tier, enabled,
                          memory_table, display_label, aliases,
                          eta_seconds, keep_alive, provider, fault_domain,
                          runtime_status, runtime_reason, registry_status,
                          runtime_checked_at
                   FROM agents
                   WHERE number >= 0
                   ORDER BY number ASC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'registry._load_rows_all failed: {e}')
        return []


def _utc_now_text():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _resolve_provider_meta(row):
    name = str(row.get('name') or '').strip().lower()
    tier = str(row.get('tier') or 'local').strip().lower()
    model = str(row.get('model') or '').strip().lower()
    env_var = str(row.get('api_key_var') or '').strip()
    meta = _PROVIDER_META.get(env_var)
    if meta:
        return meta['provider'], meta['fault_domain']
    if name in _NAME_PROVIDER_META:
        return _NAME_PROVIDER_META[name]
    if tier == 'local':
        if model in _NON_OLLAMA_MODELS:
            return 'local', 'LOCAL_RUNTIME'
        return 'ollama', 'OLLAMA_RUNTIME'
    if name == 'ghost':
        return 'human', 'OPERATOR_SURFACE'
    return '', 'EXTERNAL_API' if tier == 'paid' else ''


def _resolve_api_key(env_var):
    if not env_var:
        return ''
    val = os.environ.get(env_var, '')
    if val:
        return val
    try:
        import config as _cfg
        cfg_val = getattr(_cfg, env_var, '')
        if cfg_val:
            return str(cfg_val)
        loader = getattr(_cfg, '_load_env_key', None)
        if callable(loader):
            return str(loader(env_var) or '')
    except Exception:
        pass
    return ''


def _probe_paid_row(row):
    provider, fault_domain = _resolve_provider_meta(row)
    env_var = str(row.get('api_key_var') or '').strip()
    meta = _PROVIDER_META.get(env_var)
    if not meta and str(row.get('name') or '').strip().lower() == 'nine':
        meta = _PROVIDER_META.get('GROQ_API_KEY')
    elif not meta and str(row.get('name') or '').strip().lower() == 'ten':
        meta = _PROVIDER_META.get('GITHUB_TOKEN')
    elif not meta and str(row.get('name') or '').strip().lower() == 'eleven':
        meta = _PROVIDER_META.get('XAI_API_KEY')
    elif not meta and str(row.get('name') or '').strip().lower() == 'twelve':
        meta = _PROVIDER_META.get('ANTHROPIC_API_KEY')
    elif not meta and str(row.get('name') or '').strip().lower() == 'thirteen':
        meta = _PROVIDER_META.get('HF_API_TOKEN')
    if not meta:
        return {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'FAULT',
            'runtime_reason': 'identity ping unsupported',
            'registry_status': 'STATUS_ORPHANED',
        }
    key = _resolve_api_key(env_var)
    if not key:
        return {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'FAULT',
            'runtime_reason': f'missing_key:{env_var}',
            'registry_status': 'STATUS_ORPHANED',
        }

    method = meta.get('method', 'GET').upper()
    headers = dict(meta['headers'](key))
    url = meta['url']
    try:
        if method == 'POST':
            resp = requests.post(url, headers=headers, timeout=_API_PING_TIMEOUT_S)
        else:
            resp = requests.get(url, headers=headers, timeout=_API_PING_TIMEOUT_S)
        if 200 <= resp.status_code < 300:
            return {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'READY',
                'runtime_reason': f'identity_ping:{resp.status_code}',
                'registry_status': 'ACTIVE',
            }
        detail = resp.text[:180].strip().replace('\n', ' ')
        return {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'FAULT',
            'runtime_reason': f'identity_ping:{resp.status_code}:{detail}',
            'registry_status': 'STATUS_ORPHANED',
        }
    except Exception as exc:
        return {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'FAULT',
            'runtime_reason': f'identity_ping_error:{type(exc).__name__}:{exc}',
            'registry_status': 'STATUS_ORPHANED',
        }


def _probe_local_rows(rows):
    from core.model_runtime_gateway import ollama_health

    snap = ollama_health()
    if not snap.get('ok'):
        reason = str(snap.get('error_code') or 'RUNTIME_OFFLINE')
        detail = '; '.join(str(item) for item in (snap.get('warnings') or []) if item) or reason
        results = {}
        for row in rows:
            name = str(row.get('name') or '').lower()
            model = str(row.get('model') or '').strip().lower()
            provider, fault_domain = _resolve_provider_meta(row)
            if model in _NON_OLLAMA_MODELS:
                results[name] = {
                    'provider': provider,
                    'fault_domain': fault_domain,
                    'runtime_status': 'READY',
                    'runtime_reason': 'non_ollama_local',
                    'registry_status': 'ACTIVE',
                }
            else:
                results[name] = {
                    'provider': provider,
                    'fault_domain': fault_domain,
                    'runtime_status': 'FAULT',
                    'runtime_reason': detail,
                    'registry_status': 'STATUS_ORPHANED',
                }
        return results

    loaded_models = {
        str(item.get('name') or '').strip().lower()
        for item in (snap.get('models') or [])
        if str(item.get('name') or '').strip()
    }
    installed_models = set()
    try:
        resp = requests.get(f'{OLLAMA_BASE_URL}/api/tags', timeout=_API_PING_TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json() or {}
        for item in (payload.get('models') or []):
            name = str(item.get('model') or item.get('name') or '').strip().lower()
            if name:
                installed_models.add(name)
    except Exception as exc:
        detail = f'library_probe_error:{type(exc).__name__}:{exc}'
        return {
            str(row.get('name') or '').lower(): {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'FAULT',
                'runtime_reason': detail,
                'registry_status': 'STATUS_ORPHANED',
            }
            for row in rows
        }

    results = {}
    for row in rows:
        name = str(row.get('name') or '').lower()
        model = str(row.get('model') or '').strip().lower()
        provider, fault_domain = _resolve_provider_meta(row)
        if model in _NON_OLLAMA_MODELS:
            results[name] = {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'READY',
                'runtime_reason': 'non_ollama_local',
                'registry_status': 'ACTIVE',
            }
        elif model in loaded_models:
            results[name] = {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'LOADED',
                'runtime_reason': f'model_loaded:{model}',
                'registry_status': 'ACTIVE',
            }
        elif model in installed_models:
            results[name] = {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'READY',
                'runtime_reason': f'model_installed:{model}',
                'registry_status': 'ACTIVE',
            }
        else:
            results[name] = {
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': 'FAULT',
                'runtime_reason': f'model_missing:{model}',
                'registry_status': 'STATUS_ORPHANED',
            }
    return results


def _persist_zoo_ping(results):
    checked_at = _utc_now_text()
    conn = get_connection()
    try:
        for name, result in results.items():
            conn.execute(
                """UPDATE agents
                   SET provider = ?,
                       fault_domain = ?,
                       runtime_status = ?,
                       runtime_reason = ?,
                       registry_status = ?,
                       runtime_checked_at = ?
                   WHERE lower(name) = lower(?)""",
                (
                    str(result.get('provider') or ''),
                    str(result.get('fault_domain') or ''),
                    str(result.get('runtime_status') or ''),
                    str(result.get('runtime_reason') or ''),
                    str(result.get('registry_status') or ''),
                    checked_at,
                    name,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    invalidate_cache()
    return checked_at


def _emit_zoo_ping_story(results, checked_at):
    orphaned = sorted(name for name, result in results.items() if result.get('registry_status') == 'STATUS_ORPHANED')
    local_faults = sorted(
        name for name, result in results.items()
        if result.get('fault_domain') == 'OLLAMA_RUNTIME' and result.get('runtime_status') == 'FAULT'
    )
    paid_faults = sorted(
        name for name, result in results.items()
        if result.get('fault_domain') == 'EXTERNAL_API' and result.get('runtime_status') == 'FAULT'
    )
    payload = {
        'kind': 'zoo_ping',
        'checked_at': checked_at,
        'summary': {
            'agents_checked': len(results),
            'orphaned': len(orphaned),
            'local_faults': len(local_faults),
            'paid_faults': len(paid_faults),
        },
        'orphaned': orphaned,
        'local_faults': local_faults,
        'paid_faults': paid_faults,
    }
    try:
        from utils.swarm_bus import publish as bus_publish
        bus_publish('registry.zoo_ping', payload, source_service='db.registry')
    except Exception:
        pass
    try:
        from core import spine
        severity = spine.Severity.WARN if orphaned else spine.Severity.INFO
        spine.log(
            spine.EventKind.SYSTEM,
            f'full-zoo ping complete: {len(orphaned)} orphaned',
            severity=severity,
            source='db.registry',
            payload=payload,
        )
    except Exception:
        pass


def full_zoo_ping():
    """Probe local and paid agent tiers, then persist runtime truth to DB.

    Persisted fields on `agents`:
      - provider
      - fault_domain
      - runtime_status   (READY / LOADED / FAULT)
      - runtime_reason
      - registry_status  (ACTIVE / DISABLED / STATUS_ORPHANED)
      - runtime_checked_at

    Intent routing still uses enabled/tier/runtime soft-disable filters; this
    census is operational truth, not a replacement router.
    """
    _ensure_runtime_truth_columns()
    rows = _load_rows_all()
    local_rows = [
        row for row in rows
        if str(row.get('tier') or '').lower() == 'local'
        and str(row.get('name') or '').lower() not in _NAME_PROVIDER_META
        and not _PROVIDER_META.get(str(row.get('api_key_var') or '').strip())
    ]
    paid_rows = [
        row for row in rows
        if str(row.get('tier') or '').lower() == 'paid'
        or (
            str(row.get('name') or '').lower() in _NAME_PROVIDER_META
            and str(row.get('tier') or '').lower() not in {'service', 'human'}
        )
        or _PROVIDER_META.get(str(row.get('api_key_var') or '').strip())
    ]
    results = {}
    results.update(_probe_local_rows(local_rows))
    for row in paid_rows:
        name = str(row.get('name') or '').lower()
        results[name] = _probe_paid_row(row)

    for row in rows:
        name = str(row.get('name') or '').lower()
        tier = str(row.get('tier') or '').lower()
        if tier not in {'local', 'paid', 'free'} and name not in _NAME_PROVIDER_META:
            continue
        enabled = int(row.get('enabled') or 0)
        provider, fault_domain = _resolve_provider_meta(row)
        result = results.get(name, {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'FAULT',
            'runtime_reason': 'no probe result',
            'registry_status': 'STATUS_ORPHANED',
        })
        result.setdefault('provider', provider)
        result.setdefault('fault_domain', fault_domain)
        if not enabled:
            result['registry_status'] = 'DISABLED'
        results[name] = result

    persisted = dict(results)
    for row in rows:
        name = str(row.get('name') or '').lower()
        tier = str(row.get('tier') or '').lower()
        if name in persisted:
            continue
        provider, fault_domain = _resolve_provider_meta(row)
        persisted[name] = {
            'provider': provider,
            'fault_domain': fault_domain,
            'runtime_status': 'OUT_OF_SCOPE',
            'runtime_reason': f'tier_excluded:{tier or "unknown"}',
            'registry_status': 'OUT_OF_SCOPE',
        }

    checked_at = _persist_zoo_ping(persisted)
    _emit_zoo_ping_story(results, checked_at)
    return {
        'ok': True,
        'checked_at': checked_at,
        'results': results,
        'summary': {
            'agents_checked': len(results),
            'active': sum(1 for item in results.values() if item.get('registry_status') == 'ACTIVE'),
            'disabled': sum(1 for item in results.values() if item.get('registry_status') == 'DISABLED'),
            'orphaned': sum(1 for item in results.values() if item.get('registry_status') == 'STATUS_ORPHANED'),
        },
    }


def get_zoo_ping_snapshot():
    """Return the persisted zoo census snapshot from the agents table."""
    _ensure_runtime_truth_columns()
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT number, name, label, tier, enabled, model,
                          provider, fault_domain, runtime_status,
                          runtime_reason, registry_status, runtime_checked_at
                   FROM agents
                   WHERE number >= 0
                   ORDER BY number ASC"""
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'registry.get_zoo_ping_snapshot failed: {e}')
        return {'ok': False, 'error': str(e), 'items': [], 'summary': {}}

    items = [dict(r) for r in rows]
    audited = [row for row in items if str(row.get('registry_status') or '') != 'OUT_OF_SCOPE']
    checked_values = [str(row.get('runtime_checked_at') or '') for row in items if row.get('runtime_checked_at')]
    checked_at = max(checked_values) if checked_values else ''
    active_names = [
        str(row.get('name') or '')
        for row in audited
        if row.get('registry_status') == 'ACTIVE'
    ]
    summary = {
        'agents_checked': sum(1 for row in audited if str(row.get('runtime_status') or '') not in {'', 'OUT_OF_SCOPE'}),
        'active': sum(1 for row in audited if row.get('registry_status') == 'ACTIVE'),
        'disabled': sum(1 for row in audited if row.get('registry_status') == 'DISABLED'),
        'orphaned': sum(1 for row in audited if row.get('registry_status') == 'STATUS_ORPHANED'),
        'out_of_scope': sum(1 for row in items if row.get('registry_status') == 'OUT_OF_SCOPE'),
    }
    orphaned_names = [
        str(row.get('name') or '')
        for row in audited
        if row.get('registry_status') == 'STATUS_ORPHANED'
    ]
    breakdown = {
        'local_faults': [],
        'paid_faults': [],
        'disabled': [],
        'active': active_names,
    }
    reasons = {}
    for row in audited:
        name = str(row.get('name') or '')
        registry_status = str(row.get('registry_status') or '')
        runtime_status = str(row.get('runtime_status') or '')
        provider = str(row.get('provider') or '')
        fault_domain = str(row.get('fault_domain') or '')
        reason = str(row.get('runtime_reason') or '')
        if registry_status == 'STATUS_ORPHANED':
            entry = {
                'name': name,
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': runtime_status,
                'runtime_reason': reason,
            }
            if fault_domain == 'OLLAMA_RUNTIME':
                breakdown['local_faults'].append(entry)
            else:
                breakdown['paid_faults'].append(entry)
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        elif registry_status == 'DISABLED':
            breakdown['disabled'].append({
                'name': name,
                'provider': provider,
                'fault_domain': fault_domain,
                'runtime_status': runtime_status,
                'runtime_reason': reason,
            })
    top_reasons = sorted(
        (
            {'reason': reason, 'count': count}
            for reason, count in reasons.items()
        ),
        key=lambda item: (-item['count'], item['reason'])
    )[:5]
    return {
        'ok': True,
        'checked_at': checked_at,
        'items': items,
        'summary': summary,
        'orphaned_names': orphaned_names,
        'breakdown': breakdown,
        'top_reasons': top_reasons,
    }


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
    Returns set of local agents that run as single-task Ollama instances.
    Excludes shared-memory runners (librarian/duck/sniffles) and non-Ollama
    agents (seven uses local-algorithm, ghost is human)."""
    skip = {'librarian', 'duck', 'sniffles'}
    non_ollama_models = {'external', 'local-algorithm', ''}
    out = set()
    for r in _load_rows():
        if r.get('tier', 'local') != 'local':
            continue
        if r['name'] in skip or r['name'] == 'ghost':
            continue
        model = str(r.get('model') or '').strip().lower()
        if model in non_ollama_models:
            continue
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


# ── Routing view ─────────────────────────────────────────────────────────────
# A single accessor that chat, relay, queue dispatch, and agent-awareness all
# consult to decide "who can this message go to right now". Consolidates:
#   - DB `enabled` column (persisted truth)
#   - tier filter (service/human tiers never user-facing)
#   - runtime soft-disable set (late-bound to avoid circular import)
# Callers should NEVER reimplement their own "routable" logic; this is the view.

_runtime_disabled_provider = None  # late-bound; set by services layer at boot.


def set_runtime_disabled_provider(provider):
    """Register a zero-arg callable that returns an iterable of disabled agent names.

    The registry cannot import from `frontend.services` (circular); the services
    layer registers its `DISABLED_AGENTS` set here at boot, so runtime soft
    disables are honored without a restart.
    """
    global _runtime_disabled_provider
    _runtime_disabled_provider = provider


def _current_runtime_disabled():
    if _runtime_disabled_provider is None:
        return frozenset()
    try:
        return frozenset(str(n).lower() for n in _runtime_disabled_provider())
    except Exception:
        return frozenset()


def get_routable_agents():
    """Return the list of agents addressable for chat/relay/queue routing.

    Filters applied (in order):
      1. DB `enabled = 1` (already enforced by _load_rows).
      2. Tier not in ROUTABLE_EXCLUDED_TIERS (service, human).
      3. Name not in runtime disabled set (soft-toggle without restart).

    Scholar and Seeker (tier='service') are silent-API services used by local
    agents for internet access; they never appear here.
    Ghost (tier='human') is the operator; never a routing target.
    """
    disabled = _current_runtime_disabled()
    out = []
    for r in _load_rows():
        tier = r.get('tier') or 'local'
        if tier in ROUTABLE_EXCLUDED_TIERS:
            continue
        name = r['name']
        if name.lower() in disabled:
            continue
        out.append(dict(r))
    return out


def is_agent_routable(name):
    """Convenience: True if `name` is currently in the routable set."""
    if not name:
        return False
    wanted = str(name).strip().lower()
    return any(r['name'].lower() == wanted for r in get_routable_agents())
