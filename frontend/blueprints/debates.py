"""debates.py — Debates routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

debates_bp = Blueprint('debates', __name__)

@debates_bp.route('/api/debates')
def api_debates_list():
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT id, topic, initiator, status, rounds, consensus, created_at FROM debates ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'topic': r[1], 'initiator': r[2],
        'status': r[3], 'rounds': r[4], 'consensus': r[5], 'ts': str(r[6] or '')[:16]
    } for r in rows])



@debates_bp.route('/api/debates', methods=['POST'])
def api_debates_create():
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    conn = get_connection()
    conn.execute("INSERT INTO debates (topic, initiator) VALUES (?, ?)", (topic, 'nine'))
    conn.commit()
    debate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    from database import log_activity
    log_activity('terminal', 'debate_opened', topic[:80])
    return jsonify({'id': debate_id, 'ok': True})



@debates_bp.route('/api/debates/<int:debate_id>/turns')
def api_debate_turns(debate_id):
    conn  = get_connection()
    turns = conn.execute(
        "SELECT agent, position, round, created_at FROM debate_turns WHERE debate_id=? ORDER BY round, created_at",
        (debate_id,)
    ).fetchall()
    conn.close()
    return jsonify([{'agent': t[0], 'position': t[1], 'round': t[2], 'ts': str(t[3] or '')[:16]} for t in turns])



@debates_bp.route('/api/debates/<int:debate_id>/run', methods=['POST'])
def api_debate_run(debate_id):
    """Run a debate asynchronously — returns immediately, debate runs in background thread."""
    import threading
    def _run():
        try:
            from debate import run_debate
            result = run_debate(debate_id)
            print(f'[Terminal] Debate #{debate_id} finished: {result["status"]}')
        except Exception as e:
            print(f'[Terminal] Debate #{debate_id} error: {e}')
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True, 'message': f'Debate #{debate_id} started in background'})



@debates_bp.route('/api/debates/quick', methods=['POST'])
def api_debate_quick():
    """Open + run a debate from VS tab. Topic in request body."""
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    import threading
    results = {}
    def _run():
        try:
            from debate import run_and_resolve
            results['result'] = run_and_resolve(topic, initiator='nine')
        except Exception as e:
            results['error'] = str(e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=0)  # Fire and forget — VS tab polls for result
    conn = get_connection()
    debate_id = conn.execute("SELECT id FROM debates WHERE topic=? ORDER BY id DESC LIMIT 1", (topic,)).fetchone()
    conn.close()
    return jsonify({'ok': True, 'debate_id': debate_id[0] if debate_id else None,
                    'message': f'Debate started: {topic[:60]}'})



