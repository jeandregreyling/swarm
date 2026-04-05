"""proposals.py — Proposals & Queue routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

proposals_bp = Blueprint('proposals', __name__)

@proposals_bp.route('/api/proposals')
def api_proposals_list():
    """List all pending agent proposals with preview."""
    from sandpits import list_proposals, read_proposal
    proposals = list_proposals()
    result = []
    for p in proposals:
        content = read_proposal(p['filename']) or ''
        result.append({**p, 'preview': content[:600]})
    return jsonify({'proposals': result})



@proposals_bp.route('/api/proposals/approve', methods=['POST'])
def api_proposals_approve():
    """
    Approve a proposal:
    - Import it as a KB doc
    - Write approval to agent's memory
    - Delete the proposal file
    """
    from sandpits import read_proposal, delete_proposal
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    content = read_proposal(filename)
    if content is None:
        return jsonify({'error': 'proposal not found'}), 404

    # Import as KB doc
    conn = get_connection()
    doc_name = f'Proposal: {filename.replace(".md", "")}'
    existing = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
    if existing:
        conn.execute("UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                     (content, agent, existing[0]))
    else:
        conn.execute("INSERT INTO project_docs (doc_name, content, tags) VALUES (?, ?, ?)",
                     (doc_name, content, agent))

    # Write approval note to agent's memory using unified helper
    from database import save_agent_memory
    save_agent_memory(
        agent_name=agent,
        subject='Proposal Approved',
        content=f'My proposal "{filename}" was approved by Ghost and added to the KB.',
        importance=7,
        source='proposal_approved'
    )

    conn.commit()
    conn.close()

    # Delete the proposal file
    delete_proposal(filename)

    from database import log_activity
    log_activity('terminal', 'proposal_approved', filename)

    return jsonify({'ok': True})



@proposals_bp.route('/api/proposals/reject', methods=['POST'])
def api_proposals_reject():
    """
    Reject a proposal:
    - Optionally write feedback to agent's sandpit
    - Delete the proposal file
    """
    from sandpits import delete_proposal, write_file
    from database import log_activity
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()
    feedback = (data.get('feedback') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    # Write feedback to agent's sandpit if provided
    if feedback and agent:
        try:
            from datetime import datetime
            fb_filename = f'rejection_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            write_file(agent, fb_filename,
                       f'Proposal rejected: {filename}\n\nGhost feedback:\n{feedback}')
        except Exception:
            pass

    delete_proposal(filename)
    log_activity('terminal', 'proposal_rejected', filename)

    return jsonify({'ok': True})



@proposals_bp.route('/api/queue', methods=['GET'])
def api_queue_list():
    """List queue entries, optionally filtered by source_type and status."""
    source_type = (request.args.get('source_type') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    try:
        limit = int(request.args.get('limit', 50))
    except Exception:
        limit = 50

    rows = get_queue_entries(source_type=source_type, status=status, limit=max(1, min(limit, 500)))
    return jsonify({'ok': True, 'queue': rows, 'count': len(rows)})



@proposals_bp.route('/api/queue', methods=['POST'])
def api_queue_create_internal():
    """Create an internal queue entry and matching work proposal."""
    data = request.get_json() or {}
    agent = (data.get('agent') or '').strip().lower()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)

    if not agent or not title:
        return jsonify({'ok': False, 'error': 'agent and title required'}), 400

    queue_id, proposal_id = intake_internal(agent, title, description, priority=priority)
    log_activity('terminal', 'queue_internal_created', f'{proposal_id} ({agent})')
    return jsonify({'ok': True, 'queue_id': queue_id, 'proposal_id': proposal_id}), 201



@proposals_bp.route('/api/queue/<int:queue_id>', methods=['GET'])
def api_queue_get(queue_id):
    """Return one queue entry and linked proposal if present."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    proposal = conn.execute(
        'SELECT proposal_id, agent, title, status, queue_id, created_at, updated_at '
        'FROM work_proposals WHERE queue_id=?',
        (queue_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    return jsonify({
        'ok': True,
        'queue': dict(row),
        'proposal': dict(proposal) if proposal else None
    })



@proposals_bp.route('/api/queue/<int:queue_id>', methods=['PATCH'])
def api_queue_patch(queue_id):
    """Patch queue status and priority for manual workflow control."""
    data = request.get_json() or {}
    status = (data.get('status') or '').strip()
    priority = data.get('priority', None)

    updates = []
    params = []
    if status:
        updates.append('status=?')
        params.append(status)
    if priority is not None:
        updates.append('priority=?')
        params.append(int(priority))

    if not updates:
        return jsonify({'ok': False, 'error': 'no fields to update'}), 400

    params.append(queue_id)
    conn = get_connection()
    conn.execute(f"UPDATE queue SET {', '.join(updates)} WHERE id=?", tuple(params))
    conn.commit()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    log_activity('terminal', 'queue_updated', f'queue_id={queue_id}')
    return jsonify({'ok': True, 'queue': dict(row)})



@proposals_bp.route('/api/work-proposals', methods=['GET'])
def api_work_proposals_list():
    """List work proposals from DB with optional status/agent filters."""
    statuses = request.args.getlist('status')
    statuses = [s.strip() for s in statuses if s.strip()]
    agent = (request.args.get('agent') or '').strip()
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100

    clauses = []
    params = []
    if statuses:
        placeholders = ','.join(['?' for _ in statuses])
        clauses.append(f'status IN ({placeholders})')
        params.extend(statuses)
    if agent:
        clauses.append('agent=?')
        params.append(agent)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    conn = get_connection()
    rows = conn.execute(
        f"SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at "
        f"FROM work_proposals {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [max(1, min(limit, 500))])
    ).fetchall()
    conn.close()

    payload = [dict(r) for r in rows]
    return jsonify({'ok': True, 'proposals': payload, 'count': len(payload)})



@proposals_bp.route('/api/work-proposals/<proposal_id>', methods=['PATCH'])
def api_work_proposals_patch(proposal_id):
    """Update proposal status for approval/execution workflows."""
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    status = (data.get('status') or '').strip().lower()
    ticket_number = (data.get('ticket_number') or '').strip()
    ticket_id     = data.get('ticket_id')
    valid = {'pending', 'approved', 'rejected', 'in_progress', 'done', 'executed'}

    if status not in valid:
        return jsonify({'ok': False, 'error': f'invalid status: {status}'}), 400

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    ghost_layer_users = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'duck', 'sniffles'}
    proposal_agent = str(row['agent'] or '').strip().lower()
    effective_user = identity['effective_user']

    if proposal_agent not in ghost_layer_users and status in {'in_progress', 'done', 'executed'}:
        if effective_user not in ghost_layer_users:
            return jsonify({
                'ok': False,
                'error': 'non-ghost proposals must be implemented by a ghost-layer user',
                'proposal_id': proposal_id,
                'proposal_agent': proposal_agent,
                'effective_user': effective_user,
            }), 403

    current_status = (row['status'] or '').lower()
    allowed_transitions = {
        'pending':     {'pending', 'approved', 'rejected'},
        'approved':    {'approved', 'in_progress', 'executed', 'rejected'},
        'in_progress': {'in_progress', 'done', 'rejected'},
        'done':        {'done', 'executed', 'in_progress'},
        'executed':    {'executed'},
        'rejected':    {'rejected'},
    }
    if status not in allowed_transitions.get(current_status, {current_status}):
        _safe_time_event(
            agent=row['agent'] or 'terminal_ui',
            action='proposal_transition_blocked',
            event_type='proposal_guard',
            target=proposal_id,
            details={'from_status': current_status, 'to_status': status}
        )
        return jsonify({
            'ok': False,
            'error': f'invalid transition: {current_status} -> {status}',
            'proposal_id': proposal_id,
        }), 403

    duck_review = None
    if status == 'approved':
        duck_review = _run_proposal_duck_review(row)
        _log_proposal_duck_review(
            proposal_id,
            row['title'] or proposal_id,
            row['description'] or '',
            duck_review['result'],
            duck_review['reason']
        )
        if duck_review['result'] != 'YES':
            log_activity('terminal', 'proposal_duck_review_blocked', f'{proposal_id} -> {duck_review["reason"]}')
            _safe_time_event(
                agent=row['agent'] or 'terminal_ui',
                action='proposal_duck_review_blocked',
                event_type='proposal_review',
                target=proposal_id,
                details=duck_review
            )
            return jsonify({
                'ok': False,
                'error': 'duck review blocked approval',
                'proposal_id': proposal_id,
                'duck_review': duck_review,
            }), 403

    update_proposal_status(proposal_id, status, ticket_number=ticket_number)
    if ticket_id is not None:
        conn = get_connection()
        conn.execute('UPDATE work_proposals SET ticket_id=?, updated_at=datetime("now") WHERE proposal_id=?',
                     (ticket_id, proposal_id))
        conn.commit()
        conn.close()

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    log_activity('terminal', 'proposal_status_updated', f'{proposal_id} -> {status} by {effective_user}')
    _safe_time_event(
        agent=row['agent'] or 'terminal_ui',
        action='proposal_status_updated',
        event_type='proposal',
        target=proposal_id,
        details={'from_status': current_status, 'to_status': status, 'queue_id': row['queue_id'], 'duck_review': duck_review}
    )
    if status in ('approved', 'executed', 'rejected'):
        _safe_workflow_checkpoint(
            label=f'{proposal_id}-{status}',
            agent=row['agent'] or 'terminal_ui',
            description=f'Automatic Vortex checkpoint after {proposal_id} moved to {status}'
        )

    # Notify the originating agent via memory so it can act on the outcome
    agent_name = (row['agent'] or '').lower().strip()
    _NOTIFIABLE_AGENTS = {'nine', 'gemma', 'grok', 'llama', 'eight', 'twelve'}
    if agent_name in _NOTIFIABLE_AGENTS and status in ('approved', 'rejected', 'in_progress', 'done', 'executed'):
        try:
            from database import save_agent_memory
            status_labels = {
                'approved':   'Your proposal has been approved by Ghost. Begin planning implementation.',
                'rejected':   'Your proposal was rejected by Ghost. Review and consider revising.',
                'in_progress':'Your proposal is now in progress. Proceed with implementation.',
                'done':       'Your proposal is marked done. Awaiting final execution sign-off.',
                'executed':   'Your proposal has been executed and closed.',
            }
            note = status_labels.get(status, f'Proposal status changed to {status}.')
            save_agent_memory(
                agent_name=agent_name,
                subject=f'Proposal {proposal_id} → {status}',
                content=f'{note} Proposal: "{row["title"]}". Ticket ref: {row["ticket_number"] or "none"}.',
                tags='proposal,alm,status_change',
                importance=8,
                source='alm_pipeline'
            )
        except Exception:
            pass

    payload = {'ok': True, 'proposal': dict(row)}
    if duck_review:
        payload['duck_review'] = duck_review
    return jsonify(payload)



@proposals_bp.route('/api/work-proposals/<proposal_id>', methods=['DELETE'])
def api_work_proposals_delete(proposal_id):
    """Delete proposal records (Ghost-layer only)."""
    data = request.get_json(silent=True) or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    effective_user = identity['effective_user']
    ghost_layer_users = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'duck', 'sniffles'}
    if effective_user not in ghost_layer_users:
        return jsonify({
            'ok': False,
            'error': 'proposal deletion requires ghost-layer identity',
            'effective_user': effective_user,
        }), 403

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, queue_id, ticket_number '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    conn.execute('DELETE FROM work_proposals WHERE proposal_id=?', (proposal_id,))
    conn.commit()
    conn.close()

    deleted = dict(row)
    log_activity('terminal', 'proposal_deleted', f"{proposal_id} by {effective_user}")
    _safe_time_event(
        agent=deleted.get('agent') or 'terminal_ui',
        action='proposal_deleted',
        event_type='proposal',
        target=proposal_id,
        details={'status': deleted.get('status'), 'effective_user': effective_user}
    )

    return jsonify({'ok': True, 'deleted': deleted})



@proposals_bp.route('/api/deferred', methods=['GET'])
def api_deferred_list():
    """List unresolved deferred / pinned items."""
    include_resolved = request.args.get('resolved', '0') == '1'
    conn = get_connection()
    where = '' if include_resolved else 'WHERE resolved=0'
    rows = conn.execute(
        f'SELECT id, content, source, source_id, pinned_by, resolved, created_at, resolved_at '
        f'FROM deferred_items {where} ORDER BY created_at DESC LIMIT 200'
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'items': [dict(r) for r in rows]})



@proposals_bp.route('/api/deferred', methods=['POST'])
def api_deferred_create():
    """Pin a new deferred item."""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    source    = (data.get('source') or 'manual').strip()
    source_id = (data.get('source_id') or '').strip()
    pinned_by = (data.get('pinned_by') or 'ghost').strip()
    conn = get_connection()
    cur = conn.execute(
        'INSERT INTO deferred_items (content, source, source_id, pinned_by) VALUES (?,?,?,?)',
        (content, source, source_id, pinned_by)
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity('terminal', 'deferred_pinned', content[:80])
    return jsonify({'ok': True, 'id': item_id})



@proposals_bp.route('/api/deferred/<int:item_id>', methods=['PATCH'])
def api_deferred_patch(item_id):
    """Resolve or edit a deferred item."""
    data = request.get_json() or {}
    conn = get_connection()
    row = conn.execute('SELECT id FROM deferred_items WHERE id=?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404
    if 'resolved' in data:
        resolved = 1 if data['resolved'] else 0
        resolved_at = 'datetime("now")' if resolved else 'NULL'
        conn.execute(f'UPDATE deferred_items SET resolved=?, resolved_at={resolved_at} WHERE id=?',
                     (resolved, item_id))
    if 'content' in data:
        conn.execute('UPDATE deferred_items SET content=? WHERE id=?',
                     (data['content'].strip(), item_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@proposals_bp.route('/api/deferred/<int:item_id>', methods=['DELETE'])
def api_deferred_delete(item_id):
    """Hard-delete a deferred item."""
    conn = get_connection()
    conn.execute('DELETE FROM deferred_items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



