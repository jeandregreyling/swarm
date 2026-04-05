"""agents.py — Agents Config routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

agents_bp = Blueprint('agents', __name__)

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
    for a in _AGENT_ROSTER:
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



@agents_bp.route('/api/agents/config')
def api_agents_config_get():
    """Full agent config for the Agents tile — includes system_prompt, api_key_var, tier."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT number, name, label, model, role, temperature,
                  system_prompt, api_key_var, tier, enabled
           FROM agents WHERE number >= 0 ORDER BY number ASC"""
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
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



@agents_bp.route('/api/agents/config/<name>', methods=['PUT'])
def api_agents_config_put(name):
    """Update an agent's config fields."""
    data  = request.get_json() or {}
    conn  = get_connection()
    row   = conn.execute("SELECT id FROM agents WHERE name=?", (name,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': f'Agent {name} not found'}), 404

    allowed = ['label', 'model', 'role', 'temperature', 'system_prompt', 'tier', 'enabled']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400

    set_clause = ', '.join(f'{k}=?' for k in updates)
    conn.execute(f"UPDATE agents SET {set_clause} WHERE name=?", (*updates.values(), name))
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

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.agents')
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

        roster_agents = sorted({str(a.get('name', '')).strip().lower() for a in _AGENT_ROSTER if a.get('name')})
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

    known_agents = {str(a.get('name') or '').strip().lower() for a in _AGENT_ROSTER if a.get('name')}
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
    
    # Map agent name to memory table
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'mistral': 'memory_mistral', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
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
    
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'mistral': 'memory_mistral', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
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
    
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'mistral': 'memory_mistral', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
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



