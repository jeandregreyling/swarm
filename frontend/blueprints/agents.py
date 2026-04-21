# ── Roles–Skills Mapping Endpoints ─────────────────────────────────────────

import json as _json
from flask import Blueprint, request, Response, jsonify, send_file
from services import *
from utils.db.registry import get_agent_roster as _reg_roster_bp, invalidate_cache as _invalidate_reg_cache

agents_bp = Blueprint('agents', __name__)
ROLES_SKILLS_PATH = os.path.join(os.path.dirname(__file__), '..', 'roles_skills.json')

@agents_bp.route('/api/roles-skills', methods=['GET'])
def api_roles_skills_get():
    """Get the mapping of roles to skills (meta, for Access tile)."""
    try:
        with open(ROLES_SKILLS_PATH, 'r') as f:
            mapping = _json.load(f)
    except Exception:
        mapping = {}
    return jsonify({'ok': True, 'mapping': mapping})

@agents_bp.route('/api/roles-skills', methods=['POST'])
def api_roles_skills_post():
    """Set the mapping of roles to skills (meta, for Access tile)."""
    data = request.get_json() or {}
    mapping = data.get('mapping')
    if not isinstance(mapping, dict):
        return jsonify({'ok': False, 'error': 'mapping must be a dict'}), 400
    try:
        with open(ROLES_SKILLS_PATH, 'w') as f:
            _json.dump(mapping, f, indent=2)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

"""agents.py — Agents Config routes

WARNING: This file is critical for Flask API routes. Indentation or syntax errors will prevent the web server from starting.
After editing, ALWAYS run: python3 frontend/terminal.py
to check for errors before committing or deploying.

ALSO: This file is cross-linked with:
    - frontend/static/js/views/access.js (Access tile logic)
    - frontend/static/js/views/agents-config.js (Agents tile logic)
    - frontend/static/js/views/skills.js (Skills/capabilities logic)
If you change anything about roles, skills, or their mapping, you MUST update and test all three views and their APIs. Always ensure all endpoints return valid JSON, even on error, to prevent frontend breakage.
"""

@agents_bp.route('/api/agents')
def api_agents():
    from database import get_agent_registry
    # Build a lookup of number + label from the DB registry (keyed by internal name)
    registry_map = {}
    try:
        for row in get_agent_registry():
            registry_map[row['name'].lower()] = {'number': row['number'], 'label': row['label']}
    except Exception:
        pass  # registry unavailable — fall back gracefully, UI gets empty number/label

    result = []
    for a in _reg_roster_bp():
        entry = dict(a)
        entry['enabled']     = a['name'] not in DISABLED_AGENTS
        entry['temperature'] = orchestrator.TEMPERATURES.get(a['name'], a['default_temp'])
        entry['status']      = _agent_reachability_status(a['name'])
        entry['ghost_layer'] = a.get('ghost_layer', False)
        reg = registry_map.get((a.get('name') or '').lower(), {})
        entry['number'] = reg.get('number', None)
        entry['label']  = reg.get('label', a.get('name', ''))
        result.append(entry)
    return jsonify(result)


# ── A.2.2: Agent Status API ────────────────────────────────────────────────
@agents_bp.route('/api/agents/status')
def api_agents_status():
    """Per-agent operational status derived from chat_jobs + circuit breaker + registry.

    Returns JSON list of {name, tier, status, active_jobs, circuit_breaker, last_seen}.
    status: idle | busy | down | disabled
    """
    try:
        conn = get_connection()
        try:
            # All registered agents
            agents_rows = conn.execute(
                "SELECT name, tier, enabled FROM agents WHERE number >= 0 ORDER BY number ASC"
            ).fetchall()
            # Running chat_jobs grouped by agent
            running_rows = conn.execute(
                "SELECT agent, COUNT(*) as cnt FROM chat_jobs WHERE status='running' GROUP BY agent"
            ).fetchall()
            # Last activity per agent
            last_seen_rows = conn.execute(
                "SELECT agent, MAX(updated_at) as last_seen FROM chat_jobs GROUP BY agent"
            ).fetchall()
        finally:
            conn.close()

        running_map = {r['agent'].lower(): r['cnt'] for r in running_rows}
        last_seen_map = {r['agent'].lower(): r['last_seen'] for r in last_seen_rows}

        # Circuit breaker state
        try:
            from utils.circuit_breaker import status_for as _cb_status_for
            _cb_available = True
        except ImportError:
            _cb_available = False

        result = []
        for row in agents_rows:
            name = row['name'].lower()
            enabled = bool(row['enabled']) if row['enabled'] is not None else True
            active = running_map.get(name, 0)

            cb_state = 'closed'
            if _cb_available:
                try:
                    cb_info = _cb_status_for(name)
                    cb_state = cb_info.get('state', 'closed')
                except Exception:
                    pass

            # Derive status: disabled > down > busy > idle
            if not enabled or name in DISABLED_AGENTS:
                status = 'disabled'
            elif cb_state == 'open':
                status = 'down'
            elif active > 0:
                status = 'busy'
            else:
                status = 'idle'

            result.append({
                'name': name,
                'tier': row['tier'] or 'local',
                'status': status,
                'active_jobs': active,
                'circuit_breaker': cb_state,
                'last_seen': last_seen_map.get(name),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@agents_bp.route('/api/agents/config')
# WARNING: Indentation or syntax errors here will break the web server. Always test with:
#   python3 frontend/terminal.py
def api_agents_config_get():
    """Full agent config for the Agents tile — includes system_prompt, api_key_var, tier."""
    try:
        conn = get_connection()
        rows = conn.execute(
             """SELECT number, name, label, model, role, roles, temperature,
                    system_prompt, api_key_var, tier, enabled
                FROM agents WHERE number >= 0 ORDER BY number ASC"""
            ).fetchall()
        conn.close()
        result = []
        import json
        for r in rows:
            d = dict(r)
            # Parse roles as array, fallback to single role if needed
            roles_val = d.get('roles')
            if roles_val:
                try:
                    d['roles'] = json.loads(roles_val)
                except Exception:
                    d['roles'] = []
            elif d.get('role'):
                d['roles'] = [d['role']]
            else:
                d['roles'] = []
            # Never send the actual key — send presence flag only
            key_var = d.get('api_key_var') or ''
            if key_var:
                import os
                raw = os.environ.get(key_var, '')
                if not raw:
                    try:
                        from config import _load_env_key
                        raw = _load_env_key(key_var)
                    except Exception:
                        raw = ''
                d['api_key_set'] = bool(raw)
            else:
                d['api_key_set'] = None  # not applicable
            d['status'] = _agent_reachability_status(d['name'])
            result.append(d)
        return jsonify(result)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500



@agents_bp.route('/api/agents/config/<name>', methods=['PUT'])
def api_agents_config_put(name):
    """Update an agent's config fields."""
    data  = request.get_json() or {}
    conn  = get_connection()
    row   = conn.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': f'Agent {name} not found'}), 404

    import json
    allowed = ['label', 'model', 'role', 'roles', 'temperature', 'system_prompt', 'tier', 'enabled', 'api_key_var', 'number']
    updates = {k: v for k, v in data.items() if k in allowed}
    if 'number' in updates:
        try:
            updates['number'] = int(updates['number'])
        except Exception:
            conn.close()
            return jsonify({'error': 'number must be an integer'}), 400
        if updates['number'] < -1:
            conn.close()
            return jsonify({'error': 'number must be >= -1'}), 400

        # Keep agent numbers unique in practice: if target number is occupied,
        # swap the two numbers so edits from the UI are automatic.
        conflict = conn.execute(
            "SELECT name, number FROM agents WHERE number=? AND name<>? LIMIT 1",
            (updates['number'], name)
        ).fetchone()
        if conflict:
            current = conn.execute("SELECT number FROM agents WHERE name=?", (name,)).fetchone()
            current_number = int(current['number'] or 0) if current else 0
            conn.execute("UPDATE agents SET number=? WHERE name=?", (current_number, conflict['name']))
    # If roles is present and is a list, store as JSON
    if 'roles' in updates and isinstance(updates['roles'], list):
        updates['roles'] = json.dumps(updates['roles'])
        # Optionally, update 'role' to first role for legacy compatibility
        if updates['roles'] and not data.get('role'):
            try:
                updates['role'] = updates['roles'][0]
            except Exception:
                pass
    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400

    set_clause = ', '.join(f'{k}=?' for k in updates)
    conn.execute(f"UPDATE agents SET {set_clause} WHERE name=?", (*updates.values(), name))
    # If disabling, archive memory rows for this agent (don't delete).
    # Memory table mapping comes from the DB registry (single source of truth).
    if 'enabled' in updates and not updates['enabled']:
        from utils.db.registry import get_agent_tables
        agent_tables = get_agent_tables()
        agent_key = name.strip().lower()
        table = agent_tables.get(agent_key)
        try:
            if table and table != 'memory':
                conn.execute(f"UPDATE {table} SET archived=1 WHERE archived=0")
                conn.commit()
            elif table == 'memory':
                conn.execute("UPDATE memory SET archived=1 WHERE agent=? AND archived=0", (agent_key,))
                conn.commit()
        except Exception as e:
            print(f"[WARN] Could not archive memory for {name}: {e}")
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@agents_bp.route('/api/agents/config', methods=['POST'])
def api_agents_config_post():
    """Add a new agent."""
    data  = request.get_json() or {}
    name  = (data.get('name') or '').strip().lower()
    label = (data.get('label') or '').strip()
    model = (data.get('model') or '').strip()
    if not name or not model:
        return jsonify({'error': 'name and model required'}), 400

    conn = get_connection()
    existing = conn.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': f'Agent {name} already exists'}), 409

    max_num = conn.execute("SELECT MAX(number) FROM agents WHERE number >= 0").fetchone()[0] or 0
    conn.execute(
        """INSERT INTO agents (name, label, model, role, temperature, system_prompt, api_key_var, tier, number, enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (name, label or name, model,
         data.get('role', ''), float(data.get('temperature', 0.5) or 0.5),
         data.get('system_prompt', ''), data.get('api_key_var', ''),
         data.get('tier', 'local'), max_num + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@agents_bp.route('/api/agents/key/<name>', methods=['PUT'])
def api_agents_key_put(name):
    """Write an API key to .env.agents for the named agent."""
    import re as _re
    data    = request.get_json() or {}
    key_var = (data.get('key_var') or '').strip()
    value   = (data.get('value')   or '').strip()

    if not key_var or not _re.match(r'^[A-Z][A-Z0-9_]{2,60}$', key_var):
        return jsonify({'error': 'Invalid key variable name'}), 400
    if not value:
        return jsonify({'error': 'Key value required'}), 400

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.agents')
    try:
        try:
            with open(env_path, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        new_lines = [l for l in lines if not l.startswith(f'{key_var}=')]
        new_lines.append(f'{key_var}={value}\n')

        with open(env_path, 'w') as f:
            f.writelines(new_lines)

        # Also update api_key_var in agents table
        conn = get_connection()
        conn.execute("UPDATE agents SET api_key_var=? WHERE name=?", (key_var, name))
        conn.commit()
        conn.close()

        from database import log_activity
        log_activity('terminal', 'agent_key_updated', f'{name}: {key_var} set')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@agents_bp.route('/api/agents/capability-matrix')
def api_agents_capability_matrix():
    """Read-only matrix of granted capabilities per agent for governance UI."""
    include_inactive = request.args.get('include_inactive', '0') == '1'
    try:
        from database import get_agent_capabilities, AGENT_CAPABILITY_REGISTRY

        roster_agents = sorted({str(a.get('name', '')).strip().lower() for a in _reg_roster_bp() if a.get('name')})
        if include_inactive:
            extras = {'fridays', 'ghost'}
            roster_agents = sorted(set(roster_agents) | extras)

        matrix = []
        for agent_name in roster_agents:
            caps = get_agent_capabilities(agent_name)
            granted = []
            for cap in caps:
                if not bool(cap.get('granted')):
                    continue
                cname = str(cap.get('capability') or '').strip().lower()
                meta = AGENT_CAPABILITY_REGISTRY.get(cname, {})
                granted.append({
                    'capability': cname,
                    'description': meta.get('desc', ''),
                    'trust_level': int(cap.get('trust_level') or meta.get('trust', 0) or 0),
                    'granted_by': cap.get('granted_by', ''),
                    'granted_at': cap.get('granted_at', ''),
                })

            granted.sort(key=lambda item: (item.get('trust_level', 0), item.get('capability', '')))
            matrix.append({
                'agent': agent_name,
                'granted_count': len(granted),
                'capabilities': granted,
            })

        return jsonify({'ok': True, 'agents': matrix})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500



@agents_bp.route('/api/agents/capabilities', methods=['POST'])
def api_agents_capabilities_update():
    """Grant or revoke one or more capabilities for a target agent."""
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['effective_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update agent capabilities'}), 403

    target_agent = str(data.get('agent') or '').strip().lower()
    if not target_agent:
        return jsonify({'ok': False, 'error': 'agent required'}), 400

    known_agents = {str(a.get('name') or '').strip().lower() for a in _reg_roster_bp() if a.get('name')}
    if target_agent not in known_agents:
        return jsonify({'ok': False, 'error': f'unknown agent: {target_agent}'}), 404

    raw_caps = data.get('capabilities', data.get('capability', []))
    if isinstance(raw_caps, str):
        raw_caps = [raw_caps]
    capabilities = []
    for cap in (raw_caps or []):
        cname = str(cap or '').strip().lower()
        if cname and cname not in capabilities:
            capabilities.append(cname)
    if not capabilities:
        return jsonify({'ok': False, 'error': 'capability or capabilities required'}), 400

    invalid = [c for c in capabilities if c not in AGENT_CAPABILITY_REGISTRY]
    if invalid:
        return jsonify({'ok': False, 'error': f'unknown capabilities: {", ".join(invalid)}'}), 400

    enabled = bool(data.get('enabled', True))
    proposal_id = str(data.get('proposal_id') or '').strip()
    notes = str(data.get('notes') or '').strip()
    granted_by = str(identity.get('effective_user') or 'ghost').strip().lower() or 'ghost'

    changed = []
    for cap in capabilities:
        if enabled:
            grant_agent_capability(
                target_agent,
                cap,
                granted_by=granted_by,
                proposal_id=proposal_id,
                notes=notes,
            )
        else:
            revoke_agent_capability(target_agent, cap)
        changed.append({'capability': cap, 'enabled': enabled})

    granted_rows = [
        row for row in get_agent_capabilities(target_agent)
        if bool(row.get('granted'))
    ]
    granted_rows.sort(key=lambda item: (int(item.get('trust_level') or 0), str(item.get('capability') or '')))

    action_label = 'grant' if enabled else 'revoke'
    log_activity(
        'terminal',
        'agent_capabilities_updated',
        f'{target_agent}:{action_label}:{",".join(capabilities)} by {granted_by}'
    )

    return jsonify({
        'ok': True,
        'agent': target_agent,
        'changed': changed,
        'granted_count': len(granted_rows),
        'capabilities': granted_rows,
    })



@agents_bp.route('/api/agents/<name>/toggle', methods=['POST'])
def toggle_agent(name):
    if name in DISABLED_AGENTS:
        DISABLED_AGENTS.discard(name)
        enabled = True
    else:
        DISABLED_AGENTS.add(name)
        enabled = False
    print(f'[Terminal] {name} {"enabled" if enabled else "disabled"}')
    return jsonify({'name': name, 'enabled': enabled})



@agents_bp.route('/api/agents/<name>/temperature', methods=['POST'])
def set_agent_temperature(name):
    data = request.get_json() or {}
    try:
        temp = float(data.get('temperature', 0.5))
        temp = round(max(0.0, min(1.0, temp)), 2)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid temperature'}), 400
    orchestrator.TEMPERATURES[name] = temp
    print(f'[Terminal] {name} temperature → {temp}')
    return jsonify({'name': name, 'temperature': temp})



@agents_bp.route('/api/agents/<agent>/memory')
def api_agent_memory(agent):
    """Browse an agent's persistent memory pool. Query params: ?query=... &limit=10 &importance=5+"""
    query = request.args.get('query', '').strip()
    limit = int(request.args.get('limit', 10))
    min_importance = int(request.args.get('min_importance', 0))
    
    conn = get_connection()
    
    # Map agent name to memory table (from DB registry)
    from utils.db.registry import get_agent_tables
    agent_key = agent.lower()
    table = get_agent_tables().get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    # Check what columns exist in this table
    try:
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        # Build query based on available columns
        if 'subject' in columns:
            # Schema: memory_gemma, memory_eight, memory_nine style
            search_clause = "(subject LIKE ? OR content LIKE ?)" if query else "1=1"
            search_params = (f'%{query}%', f'%{query}%') if query else ()
            
            rows = conn.execute(f"""
                SELECT id, subject, content, tags, importance, created_at 
                FROM {table}
                WHERE {search_clause}
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, search_params + (min_importance, limit)).fetchall()
        else:
            # Schema: memory_twelve style (no subject)
            rows = conn.execute(f"""
                SELECT id, content, tags, type, importance, created_at 
                FROM {table}
                WHERE content LIKE ?
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, (f'%{query}%', min_importance, limit)).fetchall()
        
        conn.close()
        return jsonify({
            'agent': agent,
            'table': table,
            'query': query,
            'limit': limit,
            'entries': [dict(r) for r in rows]
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500



@agents_bp.route('/api/agents/<agent>/memory/write', methods=['POST'])
def api_agent_memory_write(agent):
    """Write to an agent's memory pool. Body: {content, tags?, importance?} for memory_twelve style"""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    tags = (data.get('tags') or '').strip()
    importance = int(data.get('importance', 5))
    memo_type = (data.get('type') or 'observation').strip()  # For memory_twelve
    subject = (data.get('subject') or '').strip()  # For memory_gemma/eight/nine
    
    if not content:
        return jsonify({'error': 'content required'}), 400
    
    if not 1 <= importance <= 10:
        return jsonify({'error': 'importance must be 1-10'}), 400
    
    conn = get_connection()
    
    from utils.db.registry import get_agent_tables
    agent_key = agent.lower()
    table = get_agent_tables().get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    try:
        now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        
        # Detect schema
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        if 'subject' in columns:
            # memory_gemma/eight/nine style
            source = data.get('source', 'api')
            conn.execute(f"""
                INSERT INTO {table} (agent, subject, content, tags, importance, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (agent_key, (subject or content[:100])[:200], content, tags, importance, source, now))
        else:
            # memory_twelve style  
            conn.execute(f"""
                INSERT INTO {table} (agent, content, tags, importance, type, created_at, updated_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (agent_key, content, tags, importance, memo_type, now, now))
        
        conn.commit()
        
        entry_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        conn.close()
        
        return jsonify({
            'ok': True,
            'agent': agent,
            'table': table,
            'entry_id': entry_id,
            'importance': importance
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500



@agents_bp.route('/api/agents/memories/query')
def api_agents_memories_query():
    """Cross-agent memory search. Find what any agent knows about a topic."""
    q = request.args.get('q', '').strip()
    agents_filter = [a.strip().lower() for a in request.args.get('agents', '').split(',') if a.strip()]  # Handle empty strings
    limit = int(request.args.get('limit', 5))
    min_importance = int(request.args.get('min_importance', 1))  # Changed default to 1 for broader search
    
    if not q:
        return jsonify({'error': 'q (query) required'}), 400
    
    from utils.db.registry import get_agent_tables
    memory_tables = get_agent_tables()
    
    conn = get_connection()
    results = {}
    
    # If agents specified, search only those; otherwise search all
    tables_to_search = {k: v for k, v in memory_tables.items() 
                       if not agents_filter or k in agents_filter}
    
    for agent_key, table in tables_to_search.items():
        try:
            # Detect schema for this table
            c = conn.cursor()
            c.execute(f"PRAGMA table_info({table})")
            columns = {col[1] for col in c.fetchall()}
            
            if 'subject' in columns:
                # memory_gemma/eight/nine style
                rows = conn.execute(f"""
                    SELECT id, subject, content, tags, importance, created_at 
                    FROM {table}
                    WHERE (subject LIKE ? OR content LIKE ?) 
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', f'%{q}%', min_importance, limit)).fetchall()
            else:
                # memory_twelve style
                rows = conn.execute(f"""
                    SELECT id, content, tags, type, importance, created_at 
                    FROM {table}
                    WHERE content LIKE ?
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', min_importance, limit)).fetchall()
            
            if rows:
                results[agent_key] = [dict(r) for r in rows]
        except:
            pass  # Table might not exist, skip
    
    conn.close()
    
    return jsonify({
        'query': q,
        'agents': list(results.keys()),
        'results': results
    })



@agents_bp.route('/api/agents/bootstrap', methods=['POST'])
def api_agents_bootstrap():
    """Bootstrap a newly added agent across all hardcoded registries."""
    import os, re, textwrap
    from datetime import datetime, timezone

    data = request.get_json() or {}
    name = (data.get('name') or '').strip().lower()
    if not name:
        return jsonify({'error': 'name required'}), 400

    conn = get_connection()
    row = conn.execute(
        "SELECT name, label, model, role, tier, system_prompt, api_key_var FROM agents WHERE name=?", (name,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': f'Agent {name} not found in DB'}), 404

    agent     = dict(row)
    label     = agent.get('label') or name.capitalize()
    model     = agent.get('model') or ''
    role      = agent.get('role') or ''
    tier      = agent.get('tier') or 'local'
    api_key_var   = agent.get('api_key_var') or ''
    system_prompt = (agent.get('system_prompt') or '').strip()
    mem_table = f'memory_{name}'

    steps  = []
    errors = []
    is_service = (tier == 'service')

    # Derive swarm root reliably from this file's absolute path
    # __file__ = /home/seven/swarm/frontend/blueprints/agents.py  → 3x dirname = swarm root
    swarm_root   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    frontend_dir = os.path.join(swarm_root, 'frontend')

    # ── 1. Sandpit directory ─────────────────────────────────────────────────
    sandpit_path  = os.path.join(swarm_root, 'sandpits', name)
    who_am_i_path = os.path.join(sandpit_path, 'WHO_AM_I.md')

    if is_service:
        steps.append('sandpit: skipped (service tier)')
        steps.append('WHO_AM_I.md: skipped (service tier)')
        steps.append(f'memory table: skipped (service tier)')
    else:
        # ── 1. Sandpit directory ──────────────────────────────────────────────
        try:
            os.makedirs(sandpit_path, exist_ok=True)
            steps.append(f'sandpit: {sandpit_path}')
        except Exception as e:
            errors.append(f'sandpit: {e}')

        # ── 2. WHO_AM_I.md ────────────────────────────────────────────────────
        if not os.path.exists(who_am_i_path):
            try:
                now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
                content = textwrap.dedent(f"""\
                    # WHO AM I — {name.upper()}

                    Generated: {now}

                    ## Identity
                    - **Name**: {name}
                    - **Label**: {label}
                    - **Role**: {role}
                    - **Model**: {model}
                    - **Tier**: {tier}
                    - **Reports To**: ghost

                    ## Purpose
                    {role}

                    ## My Sandpit
                    - **Path**: sandpits/{name}/
                    - **Shared**: sandpits/shared/
                    - **Agent API Key**: Load from `/home/seven/swarm/.env.agents`

                    ## How I Work With Others
                    - I query `GET /api/agent/proposals?status=pending` to see what needs doing
                    - I create tickets via `POST /api/agent/tickets` when I find work
                    - I read `shared/` sandpit for cross-agent notes
                    - I write my working notes to `{name}/` sandpit
                    - I check this file when I wake up to remember who I am
                """)
                with open(who_am_i_path, 'w') as f:
                    f.write(content)
                steps.append('WHO_AM_I.md written')
            except Exception as e:
                errors.append(f'WHO_AM_I.md: {e}')
        else:
            steps.append('WHO_AM_I.md already exists — skipped')

        # ── 3. Memory table ───────────────────────────────────────────────────
        try:
            conn = get_connection()
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {mem_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT DEFAULT '{name}',
                    subject TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    importance INTEGER DEFAULT 7,
                    source TEXT DEFAULT 'session',
                    ticket_ref TEXT DEFAULT '',
                    archived INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)
            conn.commit()
            conn.close()
            steps.append(f'memory table: {mem_table}')
        except Exception as e:
            errors.append(f'memory table: {e}')

    # ── 3b. Agent module (agents/<name>/<name>_agent.py) ─────────────────────
    agent_dir    = os.path.join(swarm_root, 'agents', name)
    agent_module = os.path.join(agent_dir, f'{name}_agent.py')
    agent_init   = os.path.join(agent_dir, '__init__.py')
    try:
        os.makedirs(agent_dir, exist_ok=True)
        if not os.path.exists(agent_init):
            open(agent_init, 'w').close()
        if os.path.exists(agent_module):
            steps.append(f'agents/{name}/{name}_agent.py: already exists — skipped')
        else:
            # Pick template by api_key_var
            hf_vars   = {'HF_API_TOKEN', 'HUGGINGFACE_API_TOKEN'}
            groq_vars = {'GROQ_API_KEY'}
            oai_vars  = {'OPENAI_API_KEY'}
            ant_vars  = {'ANTHROPIC_API_KEY'}
            key_var   = (api_key_var or '').upper()

            if key_var in hf_vars:
                base_url   = 'https://router.huggingface.co/v1'
                import_key = 'HF_API_TOKEN'
                api_cfg    = f"    client = OpenAI(api_key=api_key, base_url='{base_url}')"
                timeout    = 120
            elif key_var in groq_vars:
                import_key = 'GROQ_API_KEY'
                api_cfg    = "    from groq import Groq\n    client = Groq(api_key=api_key)"
                timeout    = 60
            elif key_var in ant_vars:
                import_key = 'ANTHROPIC_API_KEY'
                api_cfg    = "    from anthropic import Anthropic\n    client_raw = Anthropic(api_key=api_key)\n    # Wrap as OpenAI-compatible\n    client = OpenAI(api_key=api_key, base_url='https://api.anthropic.com/v1')"
                timeout    = 60
            else:
                import_key = key_var or 'OPENAI_API_KEY'
                api_cfg    = "    client = OpenAI(api_key=api_key)"
                timeout    = 60

            const_key = f'{name.upper()}_SYSTEM_PROMPT'
            template = f'''"""
agents/{name}/{name}_agent.py — {label}
Generated by Swarm bootstrap. Customise as needed.
"""
import logging, sys, os
_swarm_root = os.environ.get('SWARM_ROOT', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_swarm_root, 'utils'))
sys.path.insert(0, os.path.join(_swarm_root, 'frontend'))
logger = logging.getLogger('seven.{name}')
AGENT_NAME = '{name}'

def _build_context(message):
    from database import get_connection, get_agent_memory
    lines = ['=== Governance rules (ALM) ===',
             'Mutating changes require approved work proposals.',]
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status=\'queued\'").fetchone()[0]
        lines.append(f'Queue: {{queued}} queued')
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5)
    if mems:
        lines.append(f"\\n=== {{AGENT_NAME.capitalize()}}\'s memory ===")
        for m in mems:
            m = dict(m)
            lines.append(f"[{{str(m.get(\'created_at\',\'\'))[:16]}}] {{m.get(\'subject\',\'\')}}: {{str(m.get(\'content\',\'\'))[:200]}}")
    return \'\\n\'.join(lines)

def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try: stage_cb(t, None)
            except Exception: pass
    try:
        from openai import OpenAI
    except ImportError:
        return \'[{name}] openai package not installed\', 0
    from config import {import_key}
    const_mod = __import__(\'config\', fromlist=[\'{const_key}\'])
    system_prompt = getattr(const_mod, \'{const_key}\', \'{label} — Ghost Layer agent.\')
    api_key = {import_key}
    if not api_key:
        return \'[{name}] {import_key} not configured\', 0
    _emit(\'loading memory\')
    context = _build_context(message)
    messages = [{{"role": "system", "content": system_prompt + \'\\n\\n\' + context}}]
    if conversation_history:
        messages.extend(conversation_history[-10:])
    messages.append({{"role": "user", "content": message}})
    try:
        _emit(\'sending request\')
{api_cfg}
        response = client.chat.completions.create(
            model=\'{model}\', messages=messages, max_tokens=2048)
        answer = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        _emit(\'persisting memory\')
        try:
            from database import save_agent_memory
            save_agent_memory(agent_name=AGENT_NAME, subject=str(message or \'\')[:100],
                              content=answer, tags=\'chat,shared-thread\', importance=7, source=\'terminal_chat\')
        except Exception: pass
        logger.info(f\'[{label}] tokens={{tokens}}\')
        return answer, tokens
    except Exception as e:
        msg = str(e)
        logger.error(f\'[{label}] error: {{msg}}\')
        if \'401\' in msg or \'auth\' in msg.lower(): return \'[{name}] API key invalid.\', 0
        if \'429\' in msg or \'rate\' in msg.lower(): return f\'[{name}] Rate limit hit.\', 0
        return f\'[{name}] error: {{msg}}\', 0
'''
            with open(agent_module, 'w') as f:
                f.write(template)
            steps.append(f'agents/{name}/{name}_agent.py: created')
    except Exception as e:
        errors.append(f'agent module: {e}')

    def _patch_file(path, label_, check, find, replace):
        try:
            with open(path, 'r') as f:
                src = f.read()
            if check in src:
                steps.append(f'{label_} already present — skipped')
                return
            patched = src.replace(find, replace)
            if patched == src:
                errors.append(f'{label_}: anchor not found in {os.path.basename(path)}')
                return
            with open(path, 'w') as f:
                f.write(patched)
            steps.append(f'{label_} patched')
        except Exception as e:
            errors.append(f'{label_}: {e}')

    is_service = tier == 'service'

    # ── 4. DB registry — roster metadata (replaces old services.py file patching) ──
    services_path = os.path.join(frontend_dir, 'services.py')
    try:
        conn = get_connection()
        conn.execute("""
            UPDATE agents SET memory_table=?, display_label=?, eta_seconds=COALESCE(eta_seconds, 60)
            WHERE name=?
        """, (mem_table, f'{name.upper()} ({label.upper()})', name))
        conn.commit()
        conn.close()
        _invalidate_reg_cache()
        steps.append('DB registry: roster metadata updated')
    except Exception as e:
        errors.append(f'DB registry update: {e}')
    agents_bp_path = os.path.abspath(__file__)
    memory_bp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory.py')
    if is_service:
        steps.append('agents.py memory_tables: skipped (service tier)')
        steps.append('memory._AGENT_TABLES: skipped (service tier)')
        steps.append('memory._SUBJECT_TABLES: skipped (service tier)')
    else:
        entry_line = f"        '{name}': '{mem_table}',"
        try:
            with open(agents_bp_path, 'r') as f:
                agents_src = f.read()
            if f"'{name}': '{mem_table}'" in agents_src:
                steps.append('agents.py memory_tables already present — skipped')
            else:
                patched = re.sub(
                    r"(memory_tables\s*=\s*\{[^}]*?)(\s*\})",
                    lambda m: m.group(1) + f"\n{entry_line}" + m.group(2),
                    agents_src
                )
                with open(agents_bp_path, 'w') as f:
                    f.write(patched)
                steps.append(f'agents.py memory_tables patched ({patched.count(entry_line)} locations)')
        except Exception as e:
            errors.append(f'agents.py memory_tables: {e}')

        _patch_file(memory_bp_path, 'memory._AGENT_TABLES',
                    f"'{name}':",
                    "    'scholar':   'memory',",
                    f"    '{name}':  '{mem_table}',\n    'scholar':   'memory',")
        _patch_file(memory_bp_path, 'memory._SUBJECT_TABLES',
                    f"'{mem_table}'",
                    "    'memory_grok',",
                    f"    'memory_grok',\n    '{mem_table}',")

    # ── 10. file_agent.py — AGENT_SANDPITS (skip for services) ──────────────
    file_agent_path = os.path.join(swarm_root, 'fridays', 'file_agent.py')
    if is_service:
        steps.append('file_agent.AGENT_SANDPITS: skipped (service tier)')
    else:
        _patch_file(file_agent_path, 'file_agent.AGENT_SANDPITS',
                    f"'{name}'",
                    "'nine', 'ten', 'eleven', 'twelve',",
                    f"'nine', 'ten', 'eleven', 'twelve', '{name}',")

    # ── 11. chat.js — CHAT_AGENT_OPTIONS (skip for services) ────────────────
    chat_js_path = os.path.join(swarm_root, 'frontend', 'static', 'js', 'views', 'chat.js')
    if is_service:
        steps.append('chat.js CHAT_AGENT_OPTIONS: skipped (service tier — not a chat agent)')
    else:
        number = name
        try:
            conn = get_connection()
            num_row = conn.execute("SELECT number FROM agents WHERE name=?", (name,)).fetchone()
            conn.close()
            number = num_row['number'] if num_row else 'null'
        except Exception:
            number = 'null'
        chat_js_entry = f"  {{ value: '{name}', label: '{number} · {label}', number: {number}, tier: '{tier}', hasTemp: false }},\n"
        _patch_file(chat_js_path, 'chat.js CHAT_AGENT_OPTIONS',
                    f"value: '{name}'",
                    "  { value: 'scholar',",
                    chat_js_entry + "  { value: 'scholar',")

    # ── 12. chat.py — now fully dynamic (DB-driven); no file patching needed ──
    steps.append('chat.py routing: dynamic (no patch required)')

    # ── 13. config.py — system prompt constant ───────────────────────────────
    config_path = os.path.join(swarm_root, 'utils', 'config.py')
    const_name  = f'{name.upper()}_SYSTEM_PROMPT'
    try:
        with open(config_path, 'r') as f:
            cfg = f.read()
        if const_name in cfg:
            steps.append(f'config.py {const_name} already present — skipped')
        elif system_prompt:
            escaped = system_prompt.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
            with open(config_path, 'a') as f:
                f.write(f'\n\n{const_name} = """{escaped}"""\n')
            steps.append(f'config.py {const_name} appended')
        else:
            steps.append(f'config.py: no system_prompt in DB — skipped')
    except Exception as e:
        errors.append(f'config.py: {e}')

    # ── 14. utils/db/_connection.py — AGENT_POOL_MAP (skip for services) ─────
    pool_map_path = os.path.join(swarm_root, 'utils', 'db', '_connection.py')
    if is_service:
        steps.append('db._connection.AGENT_POOL_MAP: skipped (service tier)')
    else:
        _patch_file(pool_map_path, 'db._connection.AGENT_POOL_MAP',
                    f"'{name}': '{mem_table}'",
                    "    'scholar': 'memory', 'seeker': 'memory'",
                    f"    '{name}': '{mem_table}',\n    'scholar': 'memory', 'seeker': 'memory'")

    # ── 15. terminal_base.html — memory agent tab (skip for services) ────────
    terminal_path = os.path.join(swarm_root, 'frontend', 'templates', 'terminal_base.html')
    if is_service:
        steps.append('terminal_base.html memory tab: skipped (service tier)')
    else:
        tab_entry  = f"        <button class=\"mem-tab\" data-agent=\"{name}\"  onclick=\"_memTab(this,'{name}')\">{number} · {label}</button>"
        tab_anchor = "      </div>\n      <div id=\"memory-source-tabs\""
        _patch_file(terminal_path, 'terminal_base.html memory tab',
                    f"data-agent=\"{name}\"",
                    tab_anchor,
                    f"{tab_entry}\n{tab_anchor}")

    # ── Verification ─────────────────────────────────────────────────────────
    checks = {}
    try:
        conn = get_connection()
        tbl_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (mem_table,)
        ).fetchone()
        conn.close()
        checks['memory_table_exists'] = bool(tbl_exists)
    except Exception:
        checks['memory_table_exists'] = False

    checks['sandpit_dir_exists']  = os.path.isdir(sandpit_path)
    checks['who_am_i_exists']     = os.path.isfile(who_am_i_path)

    try:
        conn = get_connection()
        db_agent = conn.execute("SELECT name, display_label FROM agents WHERE name=?", (name,)).fetchone()
        conn.close()
        checks['in_agent_roster']    = bool(db_agent)
        checks['in_display_labels']  = bool(db_agent and db_agent['display_label'])
    except Exception:
        checks['in_agent_roster'] = checks['in_display_labels'] = False

    try:
        with open(agents_bp_path) as f: abp = f.read()
        checks['in_memory_tables']   = f"'{name}': '{mem_table}'" in abp
    except Exception:
        checks['in_memory_tables'] = False

    try:
        with open(memory_bp_path) as f: mbp = f.read()
        checks['in_memory_agent_tables']   = f"'{name}':" in mbp
        checks['in_memory_allowed_tables'] = f"'{mem_table}'" in mbp
        # Dynamic memory.py builds UNION from _AGENT_TABLES at runtime — check dict entry, not literal SQL
        checks['in_memory_tables_dict']    = f"'{name}':" in mbp and f"'{mem_table}'" in mbp
    except Exception:
        checks['in_memory_agent_tables'] = checks['in_memory_allowed_tables'] = checks['in_memory_tables_dict'] = False

    if is_service:
        checks['in_chat_agent_options'] = True   # N/A for services
        checks['in_file_agent_sandpits'] = True  # N/A for services
        checks['in_memory_agent_tab'] = True     # N/A for services
    else:
        try:
            with open(chat_js_path) as f: cjs = f.read()
            checks['in_chat_agent_options'] = f"value: '{name}'" in cjs
        except Exception:
            checks['in_chat_agent_options'] = False

        try:
            with open(file_agent_path) as f: fap = f.read()
            checks['in_file_agent_sandpits'] = f"'{name}'" in fap
        except Exception:
            checks['in_file_agent_sandpits'] = False

        try:
            with open(terminal_path) as f: tmpl = f.read()
            checks['in_memory_agent_tab'] = f"data-agent=\"{name}\"" in tmpl
        except Exception:
            checks['in_memory_agent_tab'] = False

    try:
        with open(config_path) as f: cfg = f.read()
        checks['system_prompt_in_config'] = const_name in cfg
    except Exception:
        checks['system_prompt_in_config'] = False

    try:
        with open(pool_map_path) as f: pmp = f.read()
        checks['in_agent_pool_map'] = f"'{name}': '{mem_table}'" in pmp
    except Exception:
        checks['in_agent_pool_map'] = False

    checks['agent_module_exists'] = os.path.isfile(agent_module)

    failed_checks = [k for k, v in checks.items() if not v]

    from database import log_activity
    log_activity('terminal', 'agent_bootstrapped',
                 f'{name}: {len(steps)} steps, {len(errors)} errors, {len(failed_checks)} check failures')

    return jsonify({
        'ok':     len(errors) == 0 and len(failed_checks) == 0,
        'agent':  name,
        'steps':  steps,
        'errors': errors,
        'checks': checks,
        'failed_checks': failed_checks,
    })



@agents_bp.route('/api/agents/<name>/decommission', methods=['POST'])
def api_agents_decommission(name):
    """
    Decommission an agent: set enabled=0, strip from runtime registries.
    Keeps DB row, memory table, sandpit, agent module — fully reversible via /reactivate.
    """
    import os, re

    name = name.strip().lower()
    protected = {'gemma', 'llama', 'mistral', 'qwen', 'eight', 'nine', 'ten',
                 'eleven', 'twelve', 'scholar', 'seeker', 'ghost', 'librarian', 'duck', 'sniffles'}
    if name in protected:
        return jsonify({'ok': False, 'error': f'{name} is a core agent and cannot be decommissioned'}), 403

    conn = get_connection()
    row = conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': f'Agent {name} not found'}), 404
    conn.execute("UPDATE agents SET enabled=0 WHERE name=?", (name,))
    conn.commit()
    conn.close()

    steps = [f'DB: {name} set enabled=0']
    errors = []

    swarm_root   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    services_path  = os.path.join(swarm_root, 'frontend', 'services.py')
    agents_bp_path = os.path.abspath(__file__)
    memory_bp_path = os.path.join(swarm_root, 'frontend', 'blueprints', 'memory.py')
    file_agent_path = os.path.join(swarm_root, 'fridays', 'file_agent.py')
    chat_js_path   = os.path.join(swarm_root, 'frontend', 'static', 'js', 'views', 'chat.js')
    pool_map_path  = os.path.join(swarm_root, 'utils', 'db', '_connection.py')
    terminal_path  = os.path.join(swarm_root, 'frontend', 'templates', 'terminal_base.html')
    mem_table = f'memory_{name}'

    def _strip(path, label_, pattern):
        try:
            with open(path) as f:
                lines = f.readlines()
            filtered = [l for l in lines if not re.search(pattern, l)]
            if len(filtered) < len(lines):
                with open(path, 'w') as f:
                    f.writelines(filtered)
                steps.append(f'{label_}: removed {len(lines)-len(filtered)} line(s)')
            else:
                steps.append(f'{label_}: not found — skipped')
        except Exception as e:
            errors.append(f'{label_}: {e}')

    def _replace(path, label_, old, new):
        try:
            src = open(path).read()
            if old not in src:
                steps.append(f'{label_}: not found — skipped')
                return
            open(path, 'w').write(src.replace(old, new, 1))
            steps.append(f'{label_}: updated')
        except Exception as e:
            errors.append(f'{label_}: {e}')

    # Registry cache invalidation (roster now lives in DB; enabled=0 already set above)
    _invalidate_reg_cache()
    steps.append('DB registry: cache invalidated (agent disabled)')

    # Strip from non-DB registries (files that still hold hardcoded entries)
    _strip(agents_bp_path,  'agents.py memory_tables',      rf"'{re.escape(name)}':\s*'{re.escape(mem_table)}'")
    _strip(memory_bp_path,  'memory._AGENT_TABLES',         rf"'{re.escape(name)}':\s*'{re.escape(mem_table)}'")
    _strip(memory_bp_path,  'memory._SUBJECT_TABLES',       rf"'{re.escape(mem_table)}',")
    _replace(file_agent_path, 'file_agent.AGENT_SANDPITS',  f", '{name}'", '')
    _strip(chat_js_path,    'chat.js CHAT_AGENT_OPTIONS',   rf"value:\s*'{re.escape(name)}'")
    _strip(pool_map_path,   'db._connection.AGENT_POOL_MAP', rf"'{re.escape(name)}':\s*'{re.escape(mem_table)}'")
    _strip(terminal_path,   'terminal_base.html memory tab', rf'data-agent="{re.escape(name)}"')

    from database import log_activity
    log_activity('terminal', 'agent_decommissioned',
                 f'{name}: {len(steps)} steps, {len(errors)} errors')

    return jsonify({
        'ok':     len(errors) == 0,
        'agent':  name,
        'steps':  steps,
        'errors': errors,
        'note':   'Agent decommissioned. Data preserved. Use /reactivate to restore.',
    })


@agents_bp.route('/api/agents/<name>/reactivate', methods=['POST'])
def api_agents_reactivate(name):
    """Re-enable a decommissioned agent and re-run bootstrap to restore all registries."""
    import os, re, textwrap
    from datetime import datetime, timezone

    name = name.strip().lower()
    conn = get_connection()
    row = conn.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': f'Agent {name} not found in DB'}), 404
    conn.execute("UPDATE agents SET enabled=1 WHERE name=?", (name,))
    conn.commit()
    conn.close()

    # Run bootstrap logic directly — inject name into the request context-free path
    # by building a minimal fake request object
    class _FakeRequest:
        def get_json(self, **kw): return {'name': name}
    _orig_req = None
    try:
        import frontend.blueprints.agents as _self_mod
        _orig_req = getattr(_self_mod, 'request', None)
    except Exception:
        pass

    # Actually — just call the inner logic via a sub-import approach.
    # The cleanest: re-use the bootstrap endpoint but call it via internal POST.
    # Since we can't easily fake Flask's request, we reconstruct the bootstrap
    # payload using the same shared pattern as api_agents_bootstrap.
    # Import the current module and call _run_bootstrap(name) — but we haven't
    # extracted that yet. For now, use werkzeug test client which is always available:
    from flask import current_app
    with current_app.test_client() as client:
        import json
        resp = client.post(
            '/api/agents/bootstrap',
            data=json.dumps({'name': name}),
            content_type='application/json'
        )
        data = resp.get_json() or {}

    data['note'] = 'Agent reactivated. Restart server to go fully live.'
    return jsonify(data)


@agents_bp.route('/api/agents/<name>/reset', methods=['POST'])
def api_agents_reset(name):
    """
    Reset an agent: wipe all memory rows, clear sandpit files (keep folder),
    then re-run bootstrap to ensure all registry entries are fresh.
    Config (DB row, API key, system prompt) is preserved.
    """
    import os, shutil
    from flask import current_app

    name = name.strip().lower()
    if name == 'ghost':
        return jsonify({'ok': False, 'error': 'ghost cannot be reset'}), 403

    conn = get_connection()
    row = conn.execute("SELECT name, tier FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': f'Agent {name} not found'}), 404
    conn.close()

    steps = []
    errors = []
    swarm_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.db._connection import AGENT_POOL_MAP
    mem_table = AGENT_POOL_MAP.get(name, f'memory_{name}')
    shared_table = mem_table == 'memory'  # shared table — scope by agent column

    # ── 1. Wipe memory rows ───────────────────────────────────────────────────
    try:
        conn = get_connection()
        if shared_table:
            count = conn.execute("SELECT COUNT(*) FROM memory WHERE agent=?", (name,)).fetchone()[0]
            conn.execute("DELETE FROM memory WHERE agent=?", (name,))
        else:
            count = conn.execute(f"SELECT COUNT(*) FROM {mem_table}").fetchone()[0]
            conn.execute(f"DELETE FROM {mem_table}")
        conn.commit()
        conn.close()
        steps.append(f'memory cleared: {count} rows deleted from {mem_table}')
    except Exception as e:
        steps.append(f'memory: {mem_table} not found or empty — skipped')

    # ── 2. Clear sandpit files (keep folder, regenerate WHO_AM_I.md) ─────────
    sandpit_path = os.path.join(swarm_root, 'sandpits', name)
    if os.path.isdir(sandpit_path):
        cleared = 0
        for item in os.listdir(sandpit_path):
            item_path = os.path.join(sandpit_path, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    cleared += 1
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    cleared += 1
            except Exception as e:
                errors.append(f'sandpit/{item}: {e}')
        steps.append(f'sandpit cleared: {cleared} item(s) removed from sandpits/{name}/')
    else:
        steps.append(f'sandpit: not found — will be created by bootstrap')

    # ── 3. Re-run bootstrap (idempotent — fills any gaps, writes fresh WHO_AM_I)
    steps.append('running bootstrap…')
    with current_app.test_client() as client:
        import json
        resp = client.post(
            '/api/agents/bootstrap',
            data=json.dumps({'name': name}),
            content_type='application/json'
        )
        bs = resp.get_json() or {}

    steps.extend(bs.get('steps', []))
    errors.extend(bs.get('errors', []))

    from database import log_activity
    log_activity('terminal', 'agent_reset',
                 f'{name}: {len(steps)} steps, {len(errors)} errors')

    return jsonify({
        'ok':     len(errors) == 0,
        'agent':  name,
        'steps':  steps,
        'errors': errors,
        'checks': bs.get('checks', {}),
        'failed_checks': bs.get('failed_checks', []),
        'note':   'Agent reset complete. Restart server to apply.',
    })


@agents_bp.route('/api/agents/<name>', methods=['DELETE'])
def api_agents_delete(name):
    """Permanently remove an agent from DB and all registries. Irreversible."""
    import os, re, shutil

    name = name.strip().lower()
    # Protect core agents
    protected = {'gemma', 'llama', 'mistral', 'qwen', 'eight', 'nine', 'ten',
                 'eleven', 'twelve', 'ghost', 'librarian', 'duck', 'sniffles'}
    if name in protected:
        return jsonify({'ok': False, 'error': f'{name} is a protected agent and cannot be deleted'}), 403

    conn = get_connection()
    row = conn.execute("SELECT name, tier FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': f'Agent {name} not found'}), 404

    mem_table = f'memory_{name}'

    swarm_root    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    frontend_dir  = os.path.join(swarm_root, 'frontend')

    steps  = []
    errors = []

    def _strip_line(path, label_, pattern):
        """Remove all lines matching a regex pattern from a file."""
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            before = len(lines)
            lines = [l for l in lines if not re.search(pattern, l)]
            if len(lines) < before:
                with open(path, 'w') as f:
                    f.writelines(lines)
                steps.append(f'{label_} removed ({before - len(lines)} line(s))')
            else:
                steps.append(f'{label_} not found — skipped')
        except Exception as e:
            errors.append(f'{label_}: {e}')

    def _replace_in_file(path, label_, find, replace):
        try:
            with open(path, 'r') as f:
                src = f.read()
            if find not in src:
                steps.append(f'{label_} not found — skipped')
                return
            with open(path, 'w') as f:
                f.write(src.replace(find, replace))
            steps.append(f'{label_} removed')
        except Exception as e:
            errors.append(f'{label_}: {e}')

    # ── 1. DB: remove agent row ───────────────────────────────────────────────
    try:
        conn.execute("DELETE FROM agents WHERE name=?", (name,))
        conn.commit()
        steps.append(f'DB: agents row deleted')
    except Exception as e:
        errors.append(f'DB delete: {e}')

    # ── 2. DB: drop memory table ──────────────────────────────────────────────
    try:
        conn.execute(f"DROP TABLE IF EXISTS {mem_table}")
        conn.commit()
        steps.append(f'DB: {mem_table} dropped')
    except Exception as e:
        errors.append(f'DB drop table: {e}')
    conn.close()

    # ── 3. Sandpit directory — always removed on full delete ──────────────────
    sandpit_path = os.path.join(swarm_root, 'sandpits', name)
    if os.path.isdir(sandpit_path):
        try:
            shutil.rmtree(sandpit_path)
            steps.append('sandpit directory deleted')
        except Exception as e:
            errors.append(f'sandpit delete: {e}')
    else:
        steps.append('sandpit: not found — skipped')

    # ── 4. DB registry: cache invalidated (agent row already deleted above) ──
    _invalidate_reg_cache()
    steps.append('DB registry: cache invalidated (agent deleted)')

    # ── 5. agents.py — memory_tables (3 dicts) ────────────────────────────────
    agents_bp_path = os.path.abspath(__file__)
    _strip_line(agents_bp_path, 'agents.py memory_tables',
                rf"'{re.escape(name)}':\s*'{re.escape(mem_table)}'")

    # ── 6. memory.py — _AGENT_TABLES + _SUBJECT_TABLES ─────────────────────
    memory_bp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory.py')
    _strip_line(memory_bp_path, 'memory._AGENT_TABLES',
                rf"'{re.escape(name)}':\s*'{re.escape(mem_table)}'")
    _strip_line(memory_bp_path, 'memory._SUBJECT_TABLES',
                rf"'{re.escape(mem_table)}',")

    # ── 7. file_agent.py — AGENT_SANDPITS ────────────────────────────────────
    file_agent_path = os.path.join(swarm_root, 'fridays', 'file_agent.py')
    _replace_in_file(file_agent_path, 'file_agent.AGENT_SANDPITS',
                     f", '{name}'", '')

    # ── 8. chat.js — CHAT_AGENT_OPTIONS ──────────────────────────────────────
    chat_js_path = os.path.join(swarm_root, 'frontend', 'static', 'js', 'views', 'chat.js')
    _strip_line(chat_js_path, 'chat.js CHAT_AGENT_OPTIONS',
                rf"value:\s*'{re.escape(name)}'")

    # ── 9. chat.py — now fully dynamic (DB-driven); no file changes needed ──
    steps.append('chat.py: dynamic dispatch — no patch needed')

    # ── 10. config.py — system prompt constant ────────────────────────────────
    config_path = os.path.join(swarm_root, 'utils', 'config.py')
    const_name  = f'{name.upper()}_SYSTEM_PROMPT'
    try:
        with open(config_path, 'r') as f:
            cfg = f.read()
        # Remove the constant and its value (multi-line triple-quoted string)
        cleaned = re.sub(
            rf'\n\n{re.escape(const_name)}\s*=\s*""".*?"""\n',
            '', cfg, flags=re.DOTALL
        )
        if cleaned != cfg:
            with open(config_path, 'w') as f:
                f.write(cleaned)
            steps.append(f'config.py {const_name} removed')
        else:
            steps.append(f'config.py {const_name} not found — skipped')
    except Exception as e:
        errors.append(f'config.py: {e}')

    # ── utils/db/_connection.py — remove from AGENT_POOL_MAP ───────────────────────────
    pool_map_path = os.path.join(swarm_root, 'utils', 'db', '_connection.py')
    _strip_line(pool_map_path, 'db._connection.AGENT_POOL_MAP', f"'{name}': '{mem_table}'")

    # ── terminal_base.html — remove memory agent tab ───────────────────────────
    terminal_path = os.path.join(swarm_root, 'frontend', 'templates', 'terminal_base.html')
    _strip_line(terminal_path, 'terminal_base.html memory tab', f'data-agent="{name}"')

    # ── Verification: confirm nothing remains ─────────────────────────────────
    checks = {}
    try:
        c = get_connection()
        checks['db_row_gone']    = not c.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
        checks['mem_table_gone'] = not c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (mem_table,)
        ).fetchone()
        c.close()
    except Exception:
        checks['db_row_gone'] = checks['mem_table_gone'] = False

    def _absent(path, needle):
        try:
            return needle not in open(path).read()
        except Exception:
            return False

    checks['roster_clean']       = True  # roster now DB-driven; row already deleted above
    checks['memory_tables_clean'] = _absent(agents_bp_path,  f"'{name}': '{mem_table}'")
    checks['memory_py_clean']    = _absent(memory_bp_path,   f"'{name}':")
    checks['chat_js_clean']      = _absent(chat_js_path,     f"value: '{name}'")
    checks['config_clean']       = _absent(config_path,      const_name)
    checks['pool_map_clean']     = _absent(pool_map_path,    f"'{name}': '{mem_table}'")
    checks['memory_tab_clean']   = _absent(terminal_path,    f'data-agent="{name}"')

    failed = [k for k, v in checks.items() if not v]

    from database import log_activity
    log_activity('terminal', 'agent_deleted',
                 f'{name}: {len(steps)} steps, {len(errors)} errors, {len(failed)} check failures')

    return jsonify({
        'ok':            len(errors) == 0 and len(failed) == 0,
        'agent':         name,
        'steps':         steps,
        'errors':        errors,
        'checks':        checks,
        'failed_checks': failed,
    })


@agents_bp.route('/api/skills', methods=['GET'])
def api_skills():
    """List all skills in the system."""
    conn = get_connection()
    rows = conn.execute('SELECT id, name, description FROM skills ORDER BY name ASC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@agents_bp.route('/api/agents/<agent>/skills', methods=['GET'])
def api_agent_skills(agent):
    """List all skills assigned to a given agent."""
    conn = get_connection()
    agent_row = conn.execute('SELECT id FROM agents WHERE name=?', (agent.lower(),)).fetchone()
    if not agent_row:
        conn.close()
        return jsonify({'error': f'Agent {agent} not found'}), 404
    agent_id = agent_row['id']
    rows = conn.execute('''
        SELECT s.id, s.name, s.description
        FROM agent_skills AS a
        JOIN skills AS s ON a.skill_id = s.id
        WHERE a.agent_id = ?
        ORDER BY s.name ASC
    ''', (agent_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@agents_bp.route('/api/agents/<agent>/skills', methods=['POST'])
def api_agent_skills_update(agent):
    """Update skills for a given agent (replace all). Payload: {skills: [skill_name, ...]}"""
    data = request.get_json() or {}
    skills = data.get('skills', [])
    if not isinstance(skills, list):
        return jsonify({'error': 'skills must be a list'}), 400
    conn = get_connection()
    agent_row = conn.execute('SELECT id FROM agents WHERE name=?', (agent.lower(),)).fetchone()
    if not agent_row:
        conn.close()
        return jsonify({'error': f'Agent {agent} not found'}), 404
    agent_id = agent_row['id']
    # Get skill ids for provided names
    skill_rows = conn.execute('SELECT id, name FROM skills WHERE name IN (%s)' % (','.join(['?']*len(skills))), skills).fetchall() if skills else []
    skill_name_to_id = {r['name']: r['id'] for r in skill_rows}
    # Remove all current skills
    conn.execute('DELETE FROM agent_skills WHERE agent_id=?', (agent_id,))
    # Insert new skills
    for name in skills:
        skill_id = skill_name_to_id.get(name)
        if skill_id:
            conn.execute('INSERT OR IGNORE INTO agent_skills (agent_id, skill_id) VALUES (?, ?)', (agent_id, skill_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'skills': skills})


# ── 5.2 Hot-Swap ────────────────────────────────────────────────────────────

@agents_bp.route('/api/agents/hot-swap', methods=['POST'])
def api_agents_hot_swap():
    """Disable agent A, reassign its role + in-flight proposals to agent B.

    Payload: {from_agent: "gemma", to_agent: "qwen"}
    Proposals are re-assigned but remain tied to their original ticket/request.
    """
    data = request.get_json() or {}
    from_name = (data.get('from_agent') or '').strip().lower()
    to_name   = (data.get('to_agent') or '').strip().lower()
    if not from_name or not to_name:
        return jsonify({'error': 'from_agent and to_agent required'}), 400
    if from_name == to_name:
        return jsonify({'error': 'Cannot swap an agent with itself'}), 400

    conn = get_connection()
    src = conn.execute('SELECT id, role, roles FROM agents WHERE name=?', (from_name,)).fetchone()
    dst = conn.execute('SELECT id FROM agents WHERE name=?', (to_name,)).fetchone()
    if not src:
        conn.close()
        return jsonify({'error': f'Agent {from_name} not found'}), 404
    if not dst:
        conn.close()
        return jsonify({'error': f'Agent {to_name} not found'}), 404

    swapped = {'proposals': 0, 'queue': 0}

    # Reassign open proposals
    cur = conn.execute(
        """UPDATE work_proposals SET agent=?, updated_at=datetime('now')
           WHERE agent=? AND status IN ('pending', 'in_progress', 'review')""",
        (to_name, from_name)
    )
    swapped['proposals'] = cur.rowcount

    # Reassign queued items
    cur2 = conn.execute(
        """UPDATE queue SET agent=?
           WHERE agent=? AND status IN ('queued', 'processing')""",
        (to_name, from_name)
    )
    swapped['queue'] = cur2.rowcount

    # Disable source agent
    conn.execute("UPDATE agents SET enabled=0 WHERE name=?", (from_name,))

    # Copy role to target if it has none
    dst_row = conn.execute('SELECT role FROM agents WHERE name=?', (to_name,)).fetchone()
    if not (dst_row and dst_row['role']):
        conn.execute('UPDATE agents SET role=? WHERE name=?', (src['role'] or '', to_name))

    conn.commit()
    conn.close()
    _invalidate_reg_cache()
    return jsonify({'ok': True, 'from': from_name, 'to': to_name, 'swapped': swapped})


# ── 5.3 Import / Export ─────────────────────────────────────────────────────

@agents_bp.route('/api/agents/<name>/export', methods=['GET'])
def api_agent_export(name):
    """Export a single agent as JSON (config, capabilities, skills)."""
    name = name.strip().lower()
    conn = get_connection()
    row = conn.execute(
        """SELECT name, model, label, role, roles, temperature,
                  system_prompt, api_key_var, tier, enabled,
                  memory_table, display_label, aliases, eta_seconds, keep_alive
           FROM agents WHERE name=?""", (name,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': f'Agent {name} not found'}), 404
    agent = dict(row)

    # Capabilities
    caps = [dict(r) for r in conn.execute(
        "SELECT capability, granted, trust_level FROM agent_capabilities WHERE agent_name=?", (name,)
    ).fetchall()]

    # Skills
    skills = [r[0] for r in conn.execute(
        """SELECT s.name FROM skills s
           JOIN agent_skills a ON a.skill_id = s.id
           JOIN agents ag ON ag.id = a.agent_id
           WHERE ag.name=?""", (name,)
    ).fetchall()]

    conn.close()
    return jsonify({
        'ok': True,
        'export_version': 1,
        'agent': agent,
        'capabilities': caps,
        'skills': skills,
    })


@agents_bp.route('/api/agents/export-all', methods=['GET'])
def api_agents_export_all():
    """Export the full agent registry as JSON (all agents + capabilities + skills)."""
    conn = get_connection()
    agents = [dict(r) for r in conn.execute(
        """SELECT name, model, label, role, roles, temperature,
                  system_prompt, api_key_var, tier, enabled,
                  memory_table, display_label, aliases, eta_seconds, keep_alive
           FROM agents ORDER BY number ASC"""
    ).fetchall()]
    caps = [dict(r) for r in conn.execute(
        "SELECT agent_name, capability, granted, trust_level FROM agent_capabilities"
    ).fetchall()]
    skills = [{'agent': r[0], 'skill': r[1]} for r in conn.execute(
        """SELECT ag.name, s.name FROM skills s
           JOIN agent_skills a ON a.skill_id = s.id
           JOIN agents ag ON ag.id = a.agent_id"""
    ).fetchall()]
    conn.close()
    return jsonify({
        'ok': True,
        'export_version': 1,
        'agents': agents,
        'capabilities': caps,
        'skills': skills,
    })


@agents_bp.route('/api/agents/import', methods=['POST'])
def api_agents_import():
    """Import one or more agents from exported JSON.

    Accepts either a single-agent export ({agent: {...}}) or
    a multi-agent export ({agents: [...]}).
    Existing agents are updated, new ones created.
    """
    data = request.get_json() or {}
    if 'agent' in data:
        agent_list = [data['agent']]
        caps_list = data.get('capabilities', [])
        skills_list = data.get('skills', [])
    elif 'agents' in data:
        agent_list = data['agents']
        caps_list = data.get('capabilities', [])
        skills_list = data.get('skills', [])
    else:
        return jsonify({'error': 'Expected agent or agents in payload'}), 400

    conn = get_connection()
    imported = []
    for ag in agent_list:
        name = (ag.get('name') or '').strip().lower()
        model = (ag.get('model') or '').strip()
        if not name or not model:
            continue
        existing = conn.execute('SELECT id FROM agents WHERE name=?', (name,)).fetchone()
        if existing:
            # Update
            conn.execute(
                """UPDATE agents SET model=?, label=?, role=?, roles=?, temperature=?,
                          system_prompt=?, api_key_var=?, tier=?, enabled=?,
                          memory_table=?, display_label=?, aliases=?, eta_seconds=?, keep_alive=?
                   WHERE name=?""",
                (model, ag.get('label', name), ag.get('role', ''), ag.get('roles', ''),
                 float(ag.get('temperature', 0.5) or 0.5),
                 ag.get('system_prompt', ''), ag.get('api_key_var', ''),
                 ag.get('tier', 'local'), 1 if ag.get('enabled', True) else 0,
                 ag.get('memory_table', ''), ag.get('display_label', ''),
                 ag.get('aliases', ''), int(ag.get('eta_seconds', 0) or 0),
                 int(ag.get('keep_alive', 300) if ag.get('keep_alive') is not None else 300),
                 name)
            )
        else:
            # Insert
            max_num = conn.execute("SELECT MAX(number) FROM agents WHERE number >= 0").fetchone()[0] or 0
            conn.execute(
                """INSERT INTO agents (name, model, label, role, roles, temperature,
                       system_prompt, api_key_var, tier, enabled, number,
                       memory_table, display_label, aliases, eta_seconds, keep_alive)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name, model, ag.get('label', name), ag.get('role', ''), ag.get('roles', ''),
                 float(ag.get('temperature', 0.5) or 0.5),
                 ag.get('system_prompt', ''), ag.get('api_key_var', ''),
                 ag.get('tier', 'local'), 1 if ag.get('enabled', True) else 0, max_num + 1,
                 ag.get('memory_table', ''), ag.get('display_label', ''),
                 ag.get('aliases', ''), int(ag.get('eta_seconds', 0) or 0),
                 int(ag.get('keep_alive', 300) if ag.get('keep_alive') is not None else 300))
            )
        imported.append(name)

        # Import capabilities
        for c in caps_list:
            if isinstance(c, dict) and c.get('agent_name', name) == name:
                conn.execute(
                    """INSERT OR REPLACE INTO agent_capabilities (agent_name, capability, granted, trust_level)
                       VALUES (?, ?, ?, ?)""",
                    (name, c['capability'], c.get('granted', 1), c.get('trust_level', 'standard'))
                )

    conn.commit()
    conn.close()
    _invalidate_reg_cache()
    return jsonify({'ok': True, 'imported': imported})


@agents_bp.route('/api/agents/<name>/self', methods=['GET'])
def api_agent_self(name):
    """Agent awareness endpoint — full self-description for an agent (Tier 4.6).
    Returns config, capabilities, recent activity, personality excerpt, queue status."""
    from pathlib import Path
    swarm_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    safe_name = str(name or '').strip().lower()
    if not safe_name:
        return jsonify({'ok': False, 'error': 'agent name required'}), 400

    conn = get_connection()
    # Agent config
    agent = conn.execute("SELECT * FROM agents WHERE name=?", (safe_name,)).fetchone()
    if not agent:
        conn.close()
        return jsonify({'ok': False, 'error': f'agent {safe_name} not found'}), 404
    agent_dict = dict(agent)

    # Capabilities
    caps = conn.execute(
        "SELECT capability, granted, trust_level FROM agent_capabilities WHERE agent_name=? AND granted=1",
        (safe_name,)
    ).fetchall()

    # Recent activity
    activity = conn.execute(
        "SELECT service, event, detail, created_at FROM activity_log WHERE detail LIKE ? ORDER BY id DESC LIMIT 10",
        (f'%{safe_name}%',)
    ).fetchall()

    # Pending work
    try:
        pending = conn.execute(
            "SELECT COUNT(*) FROM work_proposals WHERE agent=? AND status='pending'",
            (safe_name,)
        ).fetchone()[0]
    except Exception:
        pending = 0

    # Skills
    try:
        skills = conn.execute(
            "SELECT capability FROM agent_capabilities WHERE agent_name=? AND granted=1",
            (safe_name,)
        ).fetchall()
        skills_list = [r['capability'] for r in skills]
    except Exception:
        skills_list = []

    # Recent memory entries
    try:
        mem_rows = conn.execute(
            f"SELECT content, importance, created_at FROM memory_{safe_name} ORDER BY id DESC LIMIT 5"
        ).fetchall()
        memories = [dict(r) for r in mem_rows]
    except Exception:
        memories = []

    # Recent diary entries
    try:
        diary_rows = conn.execute(
            "SELECT entry, mood, created_at FROM agent_diary WHERE agent_name=? ORDER BY id DESC LIMIT 5",
            (safe_name,)
        ).fetchall()
        diary = [dict(r) for r in diary_rows]
    except Exception:
        diary = []

    # System prompt
    system_prompt = agent_dict.get('system_prompt', '') or ''

    conn.close()

    # Personality excerpt
    personality_path = Path(swarm_root) / 'agents' / safe_name / 'personality.md'
    personality = ''
    if personality_path.is_file():
        personality = personality_path.read_text(encoding='utf-8', errors='replace')[:500]

    return jsonify({
        'ok': True,
        'agent': safe_name,
        'config': {k: agent_dict[k] for k in agent_dict if k != 'api_key'},
        'capabilities': [dict(c) for c in caps],
        'skills': skills_list,
        'recent_activity': [dict(a) for a in activity],
        'pending_proposals': pending,
        'personality_excerpt': personality,
        'recent_memory': memories,
        'recent_diary': diary,
        'system_prompt': system_prompt[:1000] if system_prompt else '',
    })

