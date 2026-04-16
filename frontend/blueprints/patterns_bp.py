"""patterns_bp.py — Pattern learning API (Tier 4.2).
Exposes sniffer_memory patterns: top patterns, by agent, trending.
"""
from flask import Blueprint, jsonify, request
from database import get_connection

patterns_bp = Blueprint('patterns', __name__)


@patterns_bp.route('/api/patterns', methods=['GET'])
def api_patterns():
    """Return learned patterns from sniffer_memory, sorted by frequency."""
    limit = min(int(request.args.get('limit', 50)), 200)
    agent = request.args.get('agent', '')
    pattern_type = request.args.get('type', '')

    conn = get_connection()
    clauses = []
    params = []
    if agent:
        clauses.append('agent_name = ?')
        params.append(agent)
    if pattern_type:
        clauses.append('pattern_type = ?')
        params.append(pattern_type)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    params.append(limit)

    try:
        rows = conn.execute(f"""
            SELECT id, pattern_type, agent_name, description, occurrence_count,
                   escalation_level, last_seen, created_at
            FROM sniffer_memory
            {where}
            ORDER BY occurrence_count DESC
            LIMIT ?
        """, params).fetchall()
    except Exception:
        # Table might not exist yet
        conn.close()
        return jsonify({'ok': True, 'patterns': [], 'count': 0})

    conn.close()
    return jsonify({
        'ok': True,
        'patterns': [dict(r) for r in rows],
        'count': len(rows),
    })


@patterns_bp.route('/api/patterns/summary', methods=['GET'])
def api_patterns_summary():
    """Aggregated pattern stats: top types, top agents, escalation distribution."""
    conn = get_connection()
    try:
        by_type = conn.execute("""
            SELECT pattern_type, COUNT(*) as cnt, SUM(occurrence_count) as total_occ
            FROM sniffer_memory GROUP BY pattern_type ORDER BY total_occ DESC
        """).fetchall()

        by_agent = conn.execute("""
            SELECT agent_name, COUNT(*) as cnt, SUM(occurrence_count) as total_occ
            FROM sniffer_memory GROUP BY agent_name ORDER BY total_occ DESC
        """).fetchall()

        by_escalation = conn.execute("""
            SELECT escalation_level, COUNT(*) as cnt
            FROM sniffer_memory GROUP BY escalation_level ORDER BY escalation_level DESC
        """).fetchall()

        total = conn.execute("SELECT COUNT(*), SUM(occurrence_count) FROM sniffer_memory").fetchone()
    except Exception:
        conn.close()
        return jsonify({'ok': True, 'by_type': [], 'by_agent': [], 'by_escalation': [], 'total_patterns': 0, 'total_occurrences': 0})

    conn.close()
    return jsonify({
        'ok': True,
        'by_type': [dict(r) for r in by_type],
        'by_agent': [dict(r) for r in by_agent],
        'by_escalation': [dict(r) for r in by_escalation],
        'total_patterns': total[0] or 0,
        'total_occurrences': total[1] or 0,
    })
