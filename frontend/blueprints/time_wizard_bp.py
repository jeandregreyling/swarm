"""time_wizard_bp.py — Time Wizard routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

time_wizard_bp = Blueprint('time_wizard_bp', __name__)

@time_wizard_bp.route('/api/time/timeline', methods=['GET'])
def api_time_timeline():
    """Get agent timeline — all recorded events."""
    agent = request.args.get('agent', None)
    start_time = request.args.get('start', None)
    end_time = request.args.get('end', None)
    limit = int(request.args.get('limit', 100))
    
    timeline = time_wizard.get_timeline(
        agent=agent,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'agent': agent,
        'count': len(timeline),
        'timeline': timeline
    })



@time_wizard_bp.route('/api/time/sessions', methods=['GET'])
def api_time_sessions():
    """Get all temporal sessions."""
    agent = request.args.get('agent', None)
    status = request.args.get('status', None)
    
    sessions = time_wizard.get_sessions(agent=agent, status=status)
    
    return jsonify({
        'agent': agent,
        'status': status,
        'count': len(sessions),
        'sessions': sessions
    })



@time_wizard_bp.route('/api/time/checkpoint/<name>', methods=['GET'])
def api_time_checkpoint(name):
    """Retrieve a specific checkpoint."""
    checkpoint = time_wizard.get_checkpoint(name)
    
    if not checkpoint:
        return jsonify({'error': f'Checkpoint "{name}" not found'}), 404
    
    return jsonify(checkpoint)



@time_wizard_bp.route('/api/time/checkpoints', methods=['GET'])
def api_time_checkpoints():
    """List all checkpoints."""
    before = request.args.get('before', None)
    after = request.args.get('after', None)
    limit = int(request.args.get('limit', 100))
    
    checkpoints = time_wizard.list_checkpoints(before_time=before, after_time=after, limit=limit)
    
    return jsonify({
        'count': len(checkpoints),
        'checkpoints': checkpoints
    })



@time_wizard_bp.route('/api/time/checkpoints', methods=['POST'])
def api_time_create_checkpoint():
    """Capture a Swarm-facing Vortex checkpoint from current workflow state."""
    data = request.get_json() or {}
    label = (data.get('label') or 'manual-checkpoint').strip()
    description = (data.get('description') or '').strip()
    agent = (data.get('agent') or 'terminal_ui').strip()

    try:
        checkpoint = time_wizard.create_workflow_checkpoint(label=label, agent=agent, description=description)
        return jsonify({'ok': True, 'checkpoint': checkpoint}), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@time_wizard_bp.route('/api/time/restore', methods=['POST'])
def api_time_restore():
    """Preview or apply a workflow state step-back to a named Vortex checkpoint."""
    data = request.get_json() or {}
    checkpoint_name = (data.get('checkpoint_name') or '').strip()
    actor = (data.get('actor') or 'terminal_ui').strip()
    dry_run = bool(data.get('dry_run', True))

    if not checkpoint_name:
        return jsonify({'ok': False, 'error': 'checkpoint_name required'}), 400

    # Non-dry-run state restore is irreversible — require an approved proposal.
    if not dry_run:
        gate = _alm_gate_or_response(data, 'time_restore')
        if gate:
            return gate

    try:
        result = time_wizard.restore_workflow_state(checkpoint_name=checkpoint_name, actor=actor, dry_run=dry_run)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@time_wizard_bp.route('/api/time/stats/<agent>', methods=['GET'])
def api_time_stats(agent):
    """Get temporal statistics for an agent."""
    stats = time_wizard.get_temporal_stats(agent)
    return jsonify(stats)



@time_wizard_bp.route('/api/time/bootstrap', methods=['POST'])
def api_time_bootstrap():
    """Initialize a new Time Wizard session."""
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            return jsonify({'ok': True, 'session_id': session_id}), 201
        else:
            return jsonify({'ok': False, 'error': 'Bootstrap failed'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@time_wizard_bp.route('/api/time/log-decision', methods=['POST'])
def api_time_log_decision():
    """Log a decision execution event."""
    data = request.get_json() or {}
    decision_id = data.get('decision_id')
    agent = data.get('agent', 'twelve')
    status = data.get('status', 'executed')
    details = data.get('details', {})
    
    if not decision_id:
        return jsonify({'ok': False, 'error': 'decision_id required'}), 400
    
    try:
        event_id = time_wizard.log_decision_execution(
            decision_id, agent, status, details
        )
        return jsonify({
            'ok': True,
            'event_id': event_id,
            'decision_id': decision_id
        }), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@time_wizard_bp.route('/api/time/decision-history/<decision_id>', methods=['GET'])
def api_time_decision_history(decision_id):
    """Get execution history for a decision."""
    try:
        history = time_wizard.get_decision_history(decision_id)
        return jsonify({
            'ok': True,
            'decision_id': decision_id,
            'events': history,
            'total': len(history)
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



