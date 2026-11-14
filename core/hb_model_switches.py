"""Owner 13 Nov: turn local models On, Off or Auto from the Live status panel.

Auto (default): HB's routing chooses as before. On: preferred whenever it is eligible and fits.
Off: never chosen by routing, and Fred (the CPU reviewer) is not called. Only models HB can actually use are
listed: the chat-routable catalogue (llama.cpp, 16k context) plus Fred. The APEX service itself (:8080) is
started and stopped by systemd, not here; switching it Off only stops HB routing work to it.
"""
import time

MODES = ('auto', 'on', 'off')
FRED = 'fred-cpu:24b'


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_model_switches(model TEXT PRIMARY KEY, mode TEXT NOT NULL, actor TEXT, updated_at REAL)')


def modes(conn):
    ensure_schema(conn)
    return {m: mode for m, mode in conn.execute('SELECT model, mode FROM hb_model_switches')}


def current_modes():
    """Routing-side read; any storage problem means Auto for everything (never blocks a turn).
    Read-only: no CREATE TABLE here. It is called inside other open transactions (peer bridge mention parsing), where a
    schema write on a second connection waited for the first one's lock (13 Nov: test_hb_local_jobs hung)."""
    try:
        from contextlib import closing
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            conn.execute('PRAGMA busy_timeout=200')
            return {m: mode for m, mode in conn.execute('SELECT model, mode FROM hb_model_switches')}
    except Exception:
        return {}


def routable(entry):
    return (entry.driver == 'llamacpp' and entry.role != 'embed' and int(entry.ctx or 0) >= 16384
            and not entry.options.get('raw_completion') and bool(entry.path)) or entry.name == FRED


def catalogue(conn, *, residents=None, served=None):
    """Models HB can use, with where they run, whether they are loaded now, and their switch."""
    from pathlib import Path
    from core.seven_llm import registry
    if residents is None:
        try:
            from core.seven_llm import llama_server
            residents = {r['model'] for r in llama_server.resource_snapshot().get('residents', [])}
        except Exception:
            residents = set()
    if served is None:
        served = _served_by_endpoints()
    switches = modes(conn)
    rows = []
    for entry in registry.list_models():
        if not routable(entry):
            continue
        where = (f"GPU service {entry.endpoint.rsplit(':', 1)[-1]}" if entry.endpoint
                 else 'CPU (RAM)' if entry.options.get('ngl') == 0 else 'GPU pool')
        present = bool(entry.endpoint) or Path(entry.path).is_file()
        loaded = (entry.options.get('api_model') or entry.name) in served if entry.endpoint else entry.name in residents
        rows.append({'model': entry.name, 'role': 'reviewer' if entry.name == FRED else entry.role, 'where': where,
                     'size_gb': float(entry.ram_gb or 0), 'loaded': bool(loaded), 'installed': present,
                     'mode': switches.get(entry.name, 'auto')})
    rows.sort(key=lambda r: (r['model'] != 'qwen2.5:14b-instruct', r['model'] == FRED, r['size_gb']))
    return rows


def _served_by_endpoints():
    import requests
    from core.seven_llm import registry
    served = set()
    for endpoint in {e.endpoint.rstrip('/') for e in registry.list_models() if e.endpoint}:
        try:
            for item in requests.get(endpoint + '/v1/models', timeout=1).json().get('data', []):
                if isinstance(item, dict):
                    served.add(item.get('id'))
                    served.update(a for a in item.get('aliases', []) if isinstance(a, str))
        except Exception:
            pass
    return served


def set_mode(conn, model, mode, actor):
    if mode not in MODES:
        raise ValueError('mode must be auto, on or off')
    names = {row['model'] for row in catalogue(conn, residents=set(), served=set())}
    if model not in names:
        raise ValueError(f'{model} is not a local model HB can route to')
    switches = modes(conn)
    switches[model] = mode
    chat_models = names - {FRED}
    if mode == 'off' and all(switches.get(m, 'auto') == 'off' for m in chat_models):
        raise ValueError('At least one local chat model must stay On or Auto, or APEX cannot answer')
    conn.execute('INSERT INTO hb_model_switches VALUES(?,?,?,?) ON CONFLICT(model) DO UPDATE SET mode=excluded.mode, '
                 'actor=excluded.actor, updated_at=excluded.updated_at', (model, mode, actor, time.time()))
    return {'model': model, 'mode': mode}


# ---- @model mentions (owner 13 Nov): call a usable local model by name from main chat -------------------
_ALIAS_CACHE = {'at': 0.0, 'map': {}}


def mention_aliases():
    """{alias: model} for every model HB can route to: the name with ':' as '-', plus 'fred' for the reviewer."""
    if time.time() - _ALIAS_CACHE['at'] < 60 and _ALIAS_CACHE['map']:
        return _ALIAS_CACHE['map']
    try:
        from core.seven_llm import registry
        aliases = {e.name.lower().replace(':', '-'): e.name for e in registry.list_models() if routable(e)}
    except Exception:
        aliases = {}
    if FRED in aliases.values():
        aliases['fred'] = FRED
    _ALIAS_CACHE.update(at=time.time(), map=aliases)
    return aliases


def model_from_mention(text, switches=None):
    """The first @model in text whose switch is not Off, else None."""
    import re
    aliases = mention_aliases()
    switches = current_modes() if switches is None else switches
    for match in re.finditer(r'(?<![\w@])@([a-z0-9][a-z0-9_.\-]{1,48})', str(text or '').lower()):
        token = match.group(1).rstrip('.-')
        model = aliases.get(token)
        if model and switches.get(model) != 'off':
            return model
    return None


def mention_menu(conn):
    """Models for the @ list: alias, label, where it runs, loaded or not; Off models are left out."""
    by_model = {}
    for alias, model in mention_aliases().items():
        if alias == 'fred' or model not in by_model:
            by_model[model] = alias
    return [{'alias': by_model[r['model']], 'model': r['model'], 'where': r['where'], 'loaded': r['loaded']}
            for r in catalogue(conn) if r['mode'] != 'off' and r['model'] in by_model]
