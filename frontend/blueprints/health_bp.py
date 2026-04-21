"""Health digest API blueprint — one-stop-shop system visibility.

GET  /api/health/digest       — full system health digest
GET  /api/health/status       — quick overall status (healthy/degraded/error/critical)
GET  /api/health/memory       — Agent 20 memory state and patterns
"""

from flask import Blueprint, jsonify

from utils.db._connection import get_connection

health_digest_bp = Blueprint('health_digest_bp', __name__)


@health_digest_bp.route('/api/health/digest')
def health_digest():
    """Return full system health digest from the mapper."""
    from agents.twenty.mapper import build_health_digest
    try:
        digest = build_health_digest()
        return jsonify(digest)
    except Exception as exc:
        return jsonify({'error': str(exc), 'overall_status': 'error'}), 500


@health_digest_bp.route('/api/health/status')
def health_status():
    """Quick status check — returns just the overall status string."""
    from agents.twenty.mapper import build_health_digest
    try:
        digest = build_health_digest()
        return jsonify({
            'status': digest.get('overall_status', 'unknown'),
            'scanned_at': digest.get('scanned_at', ''),
        })
    except Exception as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 500


@health_digest_bp.route('/api/health/memory')
def health_memory():
    """Return Agent 20's memory and learned patterns."""
    from agents.twenty.memory import recall, recall_patterns
    try:
        conn = get_connection()
        try:
            memories = recall(min_importance=3, limit=30, conn=conn)
            patterns = recall_patterns(min_confidence=0.2, limit=30, conn=conn)
            return jsonify({
                'memories': memories,
                'patterns': patterns,
                'memory_count': len(memories),
                'pattern_count': len(patterns),
            })
        finally:
            conn.close()
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
