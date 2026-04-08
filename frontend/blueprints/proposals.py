from flask import Blueprint, jsonify, request
from services import get_connection, log_activity, update_proposal_status
from datetime import datetime
import sqlite3

proposals_bp = Blueprint('proposals', __name__)

VALID_STAGES = {
    'proposed', 'approved', 'in_progress', 'done', 'executed', 'rejected'
}

ALLOWED_NEXT = {
    'proposed': ['approved', 'rejected'],
    'approved': ['in_progress', 'rejected'],
    'in_progress': ['done', 'rejected'],
    'done': ['executed', 'rejected'],
    'executed': [],
    'rejected': []
}

@proposals_bp.route('/api/work-proposals', methods=['GET'])
def api_work_proposals_list():
    status_filter = request.args.get('status')
    limit = int(request.args.get('limit', 200))

    conn = get_connection()
    try:
        query = "SELECT * FROM work_proposals ORDER BY created_at DESC LIMIT ?"
        params = [limit]
        if status_filter:
            query = "SELECT * FROM work_proposals WHERE status = ? ORDER BY created_at DESC LIMIT ?"
            params = [status_filter, limit]

        rows = conn.execute(query, params).fetchall()
        proposals = [dict(row) for row in rows]
        return jsonify({'ok': True, 'proposals': proposals})
    finally:
        conn.close()


@proposals_bp.route('/api/work-proposals/<int:proposal_id>/promote', methods=['POST'])
def api_work_proposals_promote(proposal_id):
    try:
        data = request.get_json(silent=True) or {}
        next_stage = str(data.get('stage', 'in_progress')).lower().strip()

        if next_stage not in VALID_STAGES:
            return jsonify({'ok': False, 'error': f'Invalid stage: {next_stage}'}), 400

        conn = get_connection()
        try:
            row = conn.execute("SELECT status FROM work_proposals WHERE id = ?", (proposal_id,)).fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'Proposal not found'}), 404

            current = str(row['status']).lower()
            if next_stage not in ALLOWED_NEXT.get(current, []):
                return jsonify({'ok': False, 'error': f'Cannot promote from {current} to {next_stage}'}), 400

            conn.execute(
                "UPDATE work_proposals SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (next_stage, proposal_id)
            )
            conn.commit()

            log_activity('studio', 'proposal_promoted', 
                        f'Proposal {proposal_id} moved from {current} to {next_stage}')

            return jsonify({
                'ok': True, 
                'new_status': next_stage, 
                'proposal_id': proposal_id,
                'message': f'Successfully promoted to {next_stage}'
            })
        finally:
            conn.close()

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[PROMOTE ERROR] Proposal {proposal_id}: {str(e)}")
        print(error_detail)
        return jsonify({'ok': False, 'error': str(e)}), 500

# Legacy compatibility
@proposals_bp.route('/proposals', methods=['GET'])
def legacy_list():
    return api_work_proposals_list()

# Stub for detail view actions (Approve / Reject / Complete)
@proposals_bp.route('/api/work-proposals/<int:proposal_id>/action', methods=['POST'])
def proposal_action(proposal_id):
    data = request.get_json(silent=True) or {}
    action = data.get('action')  # 'approve', 'reject', 'complete'

    if action == 'complete':
        # Friday final gate - trigger GIT commit + deploy logic here later
        log_activity('studio', 'proposal_completed', f'Proposal {proposal_id} completed by user')
        return jsonify({'ok': True, 'message': 'Changes completed and deployed'})

    return jsonify({'ok': False, 'error': 'Action not implemented yet'}), 501
from flask import Blueprint, jsonify, request

proposals_bp = Blueprint('proposals', __name__)

proposals = [
    {"id": 1, "title": "Sample Proposal 1", "status": "pending"},
    {"id": 2, "title": "Sample Proposal 2", "status": "pending"}
]

@proposals_bp.route('/proposals', methods=['GET'])
def list_proposals():
    return jsonify(proposals)

@proposals_bp.route('/proposals/<int:prop_id>/approve', methods=['POST'])
def approve_proposal(prop_id):
    for p in proposals:
        if p['id'] == prop_id:
            p['status'] = 'approved'
            return jsonify({"message": f"Proposal {prop_id} approved", "status": "success"})
    return jsonify({"error": "Proposal not found"}), 404

@proposals_bp.route('/proposals/<int:prop_id>/reject', methods=['POST'])
def reject_proposal(prop_id):
    for p in proposals:
        if p['id'] == prop_id:
            p['status'] = 'rejected'
            return jsonify({"message": f"Proposal {prop_id} rejected", "status": "success"})
    return jsonify({"error": "Proposal not found"}), 404



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
        f"SELECT id, proposal_id, agent, title, description, notes, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at "
        f"FROM work_proposals {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [max(1, min(limit, 500))])
    ).fetchall()
    conn.close()

    payload = [dict(r) for r in rows]
    return jsonify({'ok': True, 'proposals': payload, 'count': len(payload)})



@proposals_bp.route('/api/work-proposals/<proposal_id>', methods=['GET'])
def api_work_proposals_get(proposal_id):
    """Fetch a single work proposal by proposal_id."""
    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, notes, status, proposal_file, '
        'ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404
    return jsonify({'ok': True, 'proposal': dict(row)})



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

    developer_agents = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'duck', 'sniffles'}
    proposal_agent = str(row['agent'] or '').strip().lower()
    effective_user = identity['effective_user']

    if proposal_agent not in developer_agents and status in {'in_progress', 'done', 'executed'}:
        if effective_user not in developer_agents:
            return jsonify({
                'ok': False,
                'error': 'non-developer proposals must be implemented by a developer agent or Ghost One',
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



@proposals_bp.route('/api/work-proposals/<proposal_id>/agent-advance', methods=['POST'])
def api_work_proposals_agent_advance(proposal_id):
    """
    Agent self-service workflow advancement — no Ghost approval required.

    Allows any agent to advance their OWN proposal through the full lifecycle:
      pending → in_progress  (approve + start in one step, Vortex checkpoint created)
      in_progress → done     (mark implementation complete, awaiting Ghost confirmation)

    Ghost closes the ticket; agents cannot self-close.
    Duck review is skipped — the calling agent is accountable for their own work.
    """
    data = request.get_json() or {}
    requesting_agent = (data.get('agent') or '').strip().lower()
    action = (data.get('action') or '').strip().lower()   # 'start' | 'complete'
    vortex_label = (data.get('vortex_label') or '').strip()

    if not requesting_agent:
        return jsonify({'ok': False, 'error': 'agent required'}), 400
    if action not in ('start', 'complete'):
        return jsonify({'ok': False, 'error': 'action must be "start" or "complete"'}), 400

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, queue_id, ticket_number, ticket_id '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    proposal_agent = str(row['agent'] or '').strip().lower()
    current_status = str(row['status'] or '').strip().lower()

    # Only the owning agent may self-advance (ghost can always advance)
    if requesting_agent not in ('ghost', proposal_agent):
        return jsonify({
            'ok': False,
            'error': f'only the owning agent ({proposal_agent}) or ghost may self-advance this proposal',
        }), 403

    # Map action to target status
    if action == 'start':
        if current_status not in ('pending', 'approved'):
            return jsonify({'ok': False, 'error': f'cannot start from status: {current_status}'}), 400
        new_status = 'in_progress'
    else:  # complete
        if current_status != 'in_progress':
            return jsonify({'ok': False, 'error': f'cannot complete from status: {current_status}'}), 400
        new_status = 'done'

    # Create Vortex checkpoint before making the transition
    checkpoint_label = vortex_label or f'{proposal_id}-{new_status}'
    _safe_workflow_checkpoint(
        label=checkpoint_label,
        agent=proposal_agent,
        description=f'Agent self-advance: {proposal_id} → {new_status}. Title: {row["title"]}'
    )

    update_proposal_status(proposal_id, new_status)

    # If starting, also record the approved transition in time events
    if action == 'start':
        _safe_time_event(
            agent=proposal_agent,
            action='proposal_self_approved',
            event_type='proposal',
            target=proposal_id,
            details={'title': row['title'], 'new_status': new_status, 'vortex_checkpoint': checkpoint_label}
        )

    log_activity('terminal', 'proposal_agent_advance',
                 f'{proposal_id} → {new_status} by {requesting_agent}')

    # Notify agent memory
    try:
        from database import save_agent_memory
        note = (
            f'Your proposal "{row["title"]}" is now IN PROGRESS. '
            'Proceed with implementation using SKILL fs_patch/fs_write. '
            'When done, call SKILL alm_complete to mark it complete for Ghost review.'
        ) if action == 'start' else (
            f'Your proposal "{row["title"]}" is marked DONE. '
            'Awaiting Ghost confirmation to close. Do not reopen unless asked.'
        )
        save_agent_memory(
            agent_name=proposal_agent,
            subject=f'Proposal {proposal_id} → {new_status}',
            content=note,
            tags='proposal,alm,self-advance',
            importance=8,
            source='alm_pipeline'
        )
    except Exception:
        pass

    conn = get_connection()
    updated = conn.execute(
        'SELECT id, proposal_id, agent, title, status, queue_id, ticket_number, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?', (proposal_id,)
    ).fetchone()
    conn.close()

    return jsonify({
        'ok': True,
        'proposal': dict(updated) if updated else {},
        'vortex_checkpoint': checkpoint_label,
    })


@proposals_bp.route('/api/work-proposals/<proposal_id>/edit', methods=['PATCH'])
def api_work_proposals_edit(proposal_id):
    """Edit proposal title, description, and notes fields."""
    data = request.get_json() or {}
    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, status FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    updates, params = [], []
    for field in ('title', 'description', 'notes'):
        if field in data and data[field] is not None:
            updates.append(f'{field}=?')
            params.append(str(data[field]).strip())
    if not updates:
        conn.close()
        return jsonify({'ok': False, 'error': 'no editable fields provided'}), 400

    updates.append("updated_at=datetime('now')")
    params.append(proposal_id)
    conn.execute(f"UPDATE work_proposals SET {', '.join(updates)} WHERE proposal_id=?", tuple(params))
    conn.commit()
    updated = conn.execute(
        'SELECT id, proposal_id, agent, title, description, notes, status, ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()
    log_activity('terminal', 'proposal_edited', proposal_id)
    return jsonify({'ok': True, 'proposal': dict(updated)})



@proposals_bp.route('/api/work-proposals/<proposal_id>/attachments', methods=['GET'])
def api_work_proposals_attachments_list(proposal_id):
    """List file attachments for a proposal."""
    conn = get_connection()
    rows = conn.execute(
        'SELECT id, filename, original_name, mime_type, size_bytes, uploaded_by, created_at '
        'FROM proposal_attachments WHERE proposal_id=? ORDER BY created_at DESC',
        (proposal_id,)
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'attachments': [dict(r) for r in rows]})



@proposals_bp.route('/api/work-proposals/<proposal_id>/attachments', methods=['POST'])
def api_work_proposals_attachments_upload(proposal_id):
    """Upload a file attachment for a proposal."""
    conn = get_connection()
    row = conn.execute('SELECT id FROM work_proposals WHERE proposal_id=?', (proposal_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'file field required'}), 400

    f = request.files['file']
    original_name = f.filename or 'attachment'
    ext = os.path.splitext(original_name)[1]
    stored_name = f'{uuid.uuid4().hex}{ext}'
    dest = os.path.join(_ATTACHMENTS_DIR, stored_name)
    f.save(dest)
    size = os.path.getsize(dest)
    mime = mimetypes.guess_type(original_name)[0] or 'application/octet-stream'
    uploaded_by = (request.form.get('uploaded_by') or 'ghost').strip()

    conn = get_connection()
    cur = conn.execute(
        'INSERT INTO proposal_attachments (proposal_id, filename, original_name, mime_type, size_bytes, uploaded_by) '
        'VALUES (?,?,?,?,?,?)',
        (proposal_id, stored_name, original_name, mime, size, uploaded_by)
    )
    att_id = cur.lastrowid
    conn.commit()
    conn.close()

    log_activity('terminal', 'proposal_attachment_added', f'{proposal_id} / {original_name}')
    return jsonify({
        'ok': True,
        'attachment': {
            'id': att_id, 'filename': stored_name, 'original_name': original_name,
            'mime_type': mime, 'size_bytes': size, 'uploaded_by': uploaded_by,
        }
    }), 201



@proposals_bp.route('/api/work-proposals/<proposal_id>/attachments/<int:att_id>', methods=['GET'])
def api_work_proposals_attachment_download(proposal_id, att_id):
    """Download / serve a specific attachment."""
    conn = get_connection()
    row = conn.execute(
        'SELECT filename, original_name, mime_type FROM proposal_attachments WHERE id=? AND proposal_id=?',
        (att_id, proposal_id)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'ok': False, 'error': 'attachment not found'}), 404

    path = os.path.join(_ATTACHMENTS_DIR, row['filename'])
    if not os.path.exists(path):
        return jsonify({'ok': False, 'error': 'file missing on disk'}), 404

    return send_file(path, mimetype=row['mime_type'],
                     download_name=row['original_name'], as_attachment=True)



@proposals_bp.route('/api/work-proposals/<proposal_id>/attachments/<int:att_id>', methods=['DELETE'])
def api_work_proposals_attachment_delete(proposal_id, att_id):
    """Delete an attachment record and its file."""
    conn = get_connection()
    row = conn.execute(
        'SELECT filename FROM proposal_attachments WHERE id=? AND proposal_id=?',
        (att_id, proposal_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'attachment not found'}), 404
    conn.execute('DELETE FROM proposal_attachments WHERE id=?', (att_id,))
    conn.commit()
    conn.close()

    path = os.path.join(_ATTACHMENTS_DIR, row['filename'])
    try:
        os.remove(path)
    except OSError:
        pass
    log_activity('terminal', 'proposal_attachment_deleted', f'{proposal_id}/{att_id}')
    return jsonify({'ok': True})



@proposals_bp.route('/api/work-proposals/<proposal_id>', methods=['DELETE'])
def api_work_proposals_delete(proposal_id):
    """Delete proposal records (Ghost-layer only)."""
    data = request.get_json(silent=True) or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    effective_user = identity['effective_user']
    developer_agents = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'duck', 'sniffles'}
    if effective_user not in developer_agents:
        return jsonify({
            'ok': False,
            'error': 'proposal deletion requires developer agent or Ghost One identity',
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



