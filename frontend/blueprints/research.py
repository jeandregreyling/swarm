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
    """Start a new research session. Body: {topic, depth?, idempotency_key?}

    2026-05-02 (S-12E202F189) — ``idempotency_key`` lets callers retry safely;
    a duplicate key returns the existing session_id instead of starting again.
    2026-05-02 (S-A43BF83EB7) — background failures now write to
    ``research_sessions.last_error`` instead of silently swallowing.
    """
    data = request.get_json(silent=True) or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'ok': False, 'error': 'topic is required'}), 400

    depth = data.get('depth', 'standard')
    if depth not in ('quick', 'standard', 'deep'):
        return jsonify({'ok': False, 'error': f'Invalid depth: {depth}'}), 400

    agent = data.get('agent', 'user')
    idem = (data.get('idempotency_key') or '').strip()
    project_id = (data.get('project_id') or '').strip()  # S-BFEE738F64

    def _run_bg(sid):
        try:
            from fridays.research_workflow import resume_research
            resume_research(sid)
        except Exception as e:
            import logging, traceback
            logging.getLogger('research').exception('research session %s failed', sid)
            try:
                from utils.db.research import update_session
                update_session(sid, status='paused',
                               last_error=f'{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}')
            except Exception:
                pass

    # For quick depth, run synchronously (fast); otherwise background
    if depth == 'quick':
        try:
            from fridays.research_workflow import run_research
            from utils.db.research import create_session
            # Honour idempotency for quick mode too — reuse the existing row.
            if idem:
                _existing = create_session(topic, depth=depth, requesting_agent=agent,
                                           idempotency_key=idem,
                                           project_id=project_id)
                from utils.db.research import get_session
                _row = get_session(_existing)
                if _row and _row.get('status') == 'done':
                    return jsonify({'ok': True, 'session_id': _existing,
                                    'reused': True, 'summary': _row.get('summary', '')})
            _sid, summary = run_research(topic, depth=depth, requesting_agent=agent)
            return jsonify({'ok': True, 'session_id': _sid, 'summary': summary})
        except Exception as e:
            import logging
            logging.getLogger('research').exception('quick research failed')
            return jsonify({'ok': False, 'error': str(e)}), 500
    else:
        from utils.db.research import create_session, get_session
        session_id = create_session(topic, depth=depth, requesting_agent=agent,
                                    idempotency_key=idem,
                                    project_id=project_id)
        # If idempotency hit returned an existing in-flight or finished session, don't relaunch.
        existing = get_session(session_id) if idem else None
        reused = bool(existing and existing.get('status') in ('done', 'searching', 'analysing', 'synthesising'))
        if not reused:
            t = threading.Thread(target=_run_bg, args=(session_id,), daemon=True)
            t.start()
        return jsonify({'ok': True, 'session_id': session_id,
                        'status': 'started' if not reused else (existing or {}).get('status', 'reused'),
                        'depth': depth, 'reused': reused})


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
        except Exception as e:
            import logging, traceback
            logging.getLogger('research').exception('resume failed for %s', session_id)
            try:
                from utils.db.research import update_session
                update_session(session_id, status='paused',
                               last_error=f'{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}')
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
