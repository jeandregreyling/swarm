"""
frontend/blueprints/research.py — Research API (B.4.1)
═══════════════════════════════════════════════════════════════════════════════
POST /api/research/start          — start a new research session
GET  /api/research/sessions       — list all sessions (paginated)
GET  /api/research/<id>           — session detail + evidence
POST /api/research/<id>/resume    — resume paused session
GET  /api/research/<id>/evidence  — evidence list
"""

from flask import Blueprint, request, jsonify
import threading

research_bp = Blueprint('research', __name__)


@research_bp.route('/api/research/start', methods=['POST'])
def api_research_start():
    """Start a new research session. Body: {topic, depth?}"""
    data = request.get_json(silent=True) or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'ok': False, 'error': 'topic is required'}), 400

    depth = data.get('depth', 'standard')
    if depth not in ('quick', 'standard', 'deep'):
        return jsonify({'ok': False, 'error': f'Invalid depth: {depth}'}), 400

    agent = data.get('agent', 'user')

    # Run research in a background thread so the request returns immediately
    from utils.db.research import create_session
    session_id = create_session(topic, depth=depth, requesting_agent=agent)

    def _run():
        try:
            from fridays.research_workflow import run_research
            run_research(topic, depth=depth, requesting_agent=agent)
        except Exception:
            pass  # Status auto-set to 'paused' on error

    # For quick depth, run synchronously (fast); otherwise background
    if depth == 'quick':
        try:
            from fridays.research_workflow import run_research
            _sid, summary = run_research(topic, depth=depth, requesting_agent=agent)
            return jsonify({'ok': True, 'session_id': _sid, 'summary': summary})
        except Exception as e:
            return jsonify({'ok': False, 'session_id': session_id,
                            'error': str(e)}), 500
    else:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return jsonify({'ok': True, 'session_id': session_id,
                        'status': 'started', 'depth': depth})


@research_bp.route('/api/research/sessions', methods=['GET'])
def api_research_sessions():
    """List research sessions. Query: ?status=done&limit=20"""
    status = request.args.get('status')
    limit = min(int(request.args.get('limit', 50)), 200)
    from utils.db.research import list_sessions
    sessions = list_sessions(status=status, limit=limit)
    return jsonify({'ok': True, 'sessions': sessions})


@research_bp.route('/api/research/<int:session_id>', methods=['GET'])
def api_research_detail(session_id):
    """Get session detail + evidence count."""
    from utils.db.research import get_session, count_evidence
    sess = get_session(session_id)
    if sess is None:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    sess['evidence_count'] = count_evidence(session_id)
    return jsonify({'ok': True, 'session': sess})


@research_bp.route('/api/research/<int:session_id>/resume', methods=['POST'])
def api_research_resume(session_id):
    """Resume a paused research session."""
    from utils.db.research import get_session
    sess = get_session(session_id)
    if sess is None:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if sess['status'] not in ('paused', 'planning', 'searching', 'analysing'):
        return jsonify({'ok': False, 'error': f'Cannot resume: status={sess["status"]}'}), 400

    def _run():
        try:
            from fridays.research_workflow import resume_research
            resume_research(session_id)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'ok': True, 'session_id': session_id, 'status': 'resuming'})


@research_bp.route('/api/research/<int:session_id>/evidence', methods=['GET'])
def api_research_evidence(session_id):
    """Get evidence for a session."""
    from utils.db.research import get_session, get_evidence_for_session
    sess = get_session(session_id)
    if sess is None:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    limit = min(int(request.args.get('limit', 100)), 500)
    evidence = get_evidence_for_session(session_id, limit=limit)
    return jsonify({'ok': True, 'session_id': session_id, 'evidence': evidence})
