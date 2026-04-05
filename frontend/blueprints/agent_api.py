"""agent_api.py — Agent Self-Service API routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

agent_api_bp = Blueprint('agent_api', __name__)

@agent_api_bp.route('/api/agent/tickets', methods=['POST'])
def api_agent_create_ticket():
    """
    Allow a local agent to create a ticket/proposal directly via API.
    
    Requires headers:
    - X-Agent-Key: AGENT_API_KEY environment variable
    - X-Agent-Id: agent name (gemma, qwen, llama, etc.)
    
    JSON payload:
    - title: proposal title (required)
    - description: proposal description (proposed work)
    - priority: 1-10 (default 5, lower = more urgent)
    - tags: comma-separated tags (optional)
    
    Returns: {ok, queue_id, proposal_id, created_at}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)
    
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    
    # Use intake_internal which already handles queue + proposal creation
    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    
    created_at = datetime.now(timezone.utc).isoformat()
    log_activity(
        'terminal',
        'agent_ticket_created',
        f'agent={agent_id} proposal_id={proposal_id}'
    )
    
    return jsonify({
        'ok': True,
        'queue_id': queue_id,
        'proposal_id': proposal_id,
        'created_at': created_at
    }), 201



@agent_api_bp.route('/api/agent/tickets', methods=['GET'])
def api_agent_list_tickets():
    """
    Agent queries: what tickets have I created?
    
    Requires: X-Agent-Key, X-Agent-Id headers
    
    Query params:
    - status: filter by status (queued, processing, completed, failed)
    - limit: max results (default 50)
    
    Returns: {ok, tickets: [{queue_id, proposal_id, title, status, created_at, ...}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    status = request.args.get('status', '').strip()
    limit = int(request.args.get('limit', 50) or 50)
    
    conn = get_connection()
    try:
        query = "SELECT * FROM queue WHERE agent=?"
        params = [agent_id]
        
        if status:
            query += " AND status=?"
            params.append(status)
        
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        
        # Also fetch linked proposals
        tickets = []
        for row in rows:
            ticket_dict = dict(row)
            proposal = conn.execute(
                "SELECT proposal_id, status AS proposal_status FROM work_proposals WHERE queue_id=? LIMIT 1",
                (ticket_dict['id'],)
            ).fetchone()
            if proposal:
                ticket_dict['proposal_id'] = proposal['proposal_id']
                ticket_dict['proposal_status'] = proposal['proposal_status']
            tickets.append(ticket_dict)
        
        return jsonify({'ok': True, 'agent_id': agent_id, 'tickets': tickets})
    finally:
        conn.close()



@agent_api_bp.route('/api/agent/proposals', methods=['GET'])
def api_agent_list_proposals():
    """
    List pending proposals (for agent coordination).
    Used by Fridays orchestrator to see what work needs doing.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    
    Query params:
    - status: filter (pending, approved, rejected, executed)
    - agent: filter by target agent (optional)
    - limit: max results (default 50)
    
    Returns: {ok, proposals: [{proposal_id, agent, title, status, ticket_link, ...}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    status = request.args.get('status', 'pending').strip()  # Default to pending
    filter_agent = request.args.get('agent', '').strip()
    limit = int(request.args.get('limit', 50) or 50)
    
    conn = get_connection()
    try:
        query = "SELECT proposal_id, agent, title, description, status, queue_id, created_at, updated_at FROM work_proposals WHERE 1=1"
        params = []
        
        if status:
            query += " AND status=?"
            params.append(status)
        
        if filter_agent:
            query += " AND agent=?"
            params.append(filter_agent)
        
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        
        proposals = [dict(row) for row in rows]
        
        return jsonify({'ok': True, 'proposals': proposals})
    finally:
        conn.close()



@agent_api_bp.route('/api/agent/git/proposals', methods=['POST'])
def api_agent_git_create_proposal():
    """
    Agent creates a Git ALM proposal (stage, unstage, or commit).

    Requires: X-Agent-Key, X-Agent-Id headers
    JSON:
      - action: stage | unstage | commit
      - paths: ["file1", ...] or path: "file1" (for stage/unstage)
      - message: commit message (for commit)
      - priority: optional 1..10
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    try:
        if not agent_has_capability(agent_id, 'git_propose'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} lacks git_propose capability'}), 403
    except Exception:
        pass

    data = request.get_json() or {}
    action = str(data.get('action') or '').strip().lower()
    priority = int(data.get('priority', 4) or 4)

    if action not in ('stage', 'unstage', 'commit'):
        return jsonify({'ok': False, 'error': 'action must be stage, unstage, or commit'}), 400

    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not raw_paths and data.get('path'):
        raw_paths = [data.get('path')]
    message = str(data.get('message') or '').strip()

    try:
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if action in ('stage', 'unstage') and not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required for stage/unstage'}), 400
    if action == 'commit' and not message:
        return jsonify({'ok': False, 'error': 'message required for commit'}), 400

    title = {
        'stage': 'Git stage file',
        'unstage': 'Git unstage file',
        'commit': 'Git commit staged changes',
    }[action]
    description = _build_git_operation_description(action, rel_paths, message)

    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    log_activity('terminal', 'agent_git_proposal_created', f'agent={agent_id} proposal_id={proposal_id} action={action}')
    return jsonify({
        'ok': True,
        'agent_id': agent_id,
        'queue_id': queue_id,
        'proposal_id': proposal_id,
        'action': action,
        'paths': rel_paths,
        'message': message,
    }), 201



@agent_api_bp.route('/api/agent/git/proposals', methods=['GET'])
def api_agent_git_list_proposals():
    """List git proposals for current agent (or all agents when all_agents=1)."""
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    status = request.args.get('status', '').strip().lower()
    include_all_agents = request.args.get('all_agents', '0') == '1'
    limit = int(request.args.get('limit', 50) or 50)

    conn = get_connection()
    try:
        query = (
            "SELECT proposal_id, agent, title, description, status, queue_id, created_at, updated_at "
            "FROM work_proposals WHERE (lower(title) LIKE 'git %' OR lower(description) LIKE '%git panel:%')"
        )
        params = []
        if status:
            query += ' AND lower(status)=?'
            params.append(status)
        if not include_all_agents:
            query += ' AND lower(agent)=?'
            params.append(agent_id.lower())
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        rows = conn.execute(query, tuple(params)).fetchall()
        return jsonify({'ok': True, 'agent_id': agent_id, 'proposals': [dict(r) for r in rows]})
    finally:
        conn.close()



@agent_api_bp.route('/api/agent/git/proposals/<proposal_id>/execute', methods=['POST'])
def api_agent_git_execute_proposal(proposal_id):
    """Execute an approved git proposal created by the same agent."""
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    try:
        if not agent_has_capability(agent_id, 'git_execute'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} lacks git_execute capability'}), 403
    except Exception:
        pass

    conn = get_connection()
    row = conn.execute(
        'SELECT proposal_id, agent, title, description, status FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': f'proposal not found: {proposal_id}'}), 404

    if str(row['agent'] or '').lower() != agent_id.lower():
        return jsonify({'ok': False, 'error': 'agent can only execute its own proposals'}), 403

    gate = _alm_gate_or_response({'proposal_id': proposal_id}, 'agent_git_execute')
    if gate:
        return gate

    operation = _parse_git_operation_from_proposal(row['title'], row['description'])
    if not operation:
        return jsonify({'ok': False, 'error': 'unable to parse git operation from proposal'}), 400

    try:
        result = _execute_git_operation(operation, proposal_id=proposal_id)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if str(row['status'] or '').lower() != 'executed':
        update_proposal_status(proposal_id, 'executed')

    log_activity('terminal', 'agent_git_proposal_executed', f'agent={agent_id} proposal_id={proposal_id}')
    return jsonify({'ok': True, 'proposal_id': proposal_id, 'operation': operation, 'result': result})



@agent_api_bp.route('/api/agent/capabilities', methods=['GET'])
def api_agent_capabilities():
    """
    Tell an agent what capabilities it has been granted.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    Returns: {ok, agent_id, capabilities: [{capability, desc, granted}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    try:
        from database import get_agent_capabilities, AGENT_CAPABILITY_REGISTRY
        caps = get_agent_capabilities(agent_id)
        
        # Enrich with descriptions
        enriched = []
        for cap in caps:
            meta = AGENT_CAPABILITY_REGISTRY.get(cap['capability'], {})
            enriched.append({
                'capability': cap['capability'],
                'description': meta.get('desc', ''),
                'trust_level': cap['trust_level'],
                'granted': bool(cap['granted']),
                'granted_by': cap['granted_by'],
                'granted_at': cap['granted_at'],
            })
        
        return jsonify({'ok': True, 'agent_id': agent_id, 'capabilities': enriched})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@agent_api_bp.route('/api/agent/think', methods=['POST'])
def api_agent_push_think():
    """
    Agent pushes a self-proposed work item via API (alternative to THINK.md file).
    Fridays orchestrator processes these on the next heartbeat.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    JSON: {title, description, priority}
    Returns: {ok, proposal_id, queue_id}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    # Check agent has propose_work capability
    try:
        from database import agent_has_capability
        if not agent_has_capability(agent_id, 'propose_work'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} does not have propose_work capability'}), 403
    except Exception:
        pass  # If DB check fails, still allow (graceful degradation)
    
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)
    
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    
    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    log_activity('terminal', 'agent_self_proposed', f'agent={agent_id} proposal_id={proposal_id}')
    
    return jsonify({
        'ok': True,
        'proposal_id': proposal_id,
        'queue_id': queue_id,
        'via': 'think_api'
    }), 201



@agent_api_bp.route('/api/agent/identity', methods=['GET'])
def api_agent_identity():
    """
    Return an agent's identity card from its sandpit WHO_AM_I.md.
    Agents call this on startup to remember who they are.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    Returns: {ok, agent_id, identity_md, capabilities_count, sandpit_path}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    sandpit = Path('/home/seven/swarm/sandpits') / agent_id
    identity_file = sandpit / 'WHO_AM_I.md'
    
    identity_md = identity_file.read_text() if identity_file.exists() else None
    
    try:
        from database import get_agent_capabilities
        caps = [c for c in get_agent_capabilities(agent_id) if c.get('granted')]
        caps_count = len(caps)
        cap_names = [c['capability'] for c in caps]
    except Exception:
        caps_count = 0
        cap_names = []
    
    return jsonify({
        'ok': True,
        'agent_id': agent_id,
        'identity_md': identity_md,
        'capabilities_count': caps_count,
        'capabilities': cap_names,
        'sandpit_path': str(sandpit),
        'shared_path': '/home/seven/swarm/sandpits/shared',
    })



