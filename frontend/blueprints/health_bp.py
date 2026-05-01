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


@health_digest_bp.route('/api/health/services')
def health_services():
    """Return per-service heartbeat + warnings.

    2026-05-02 (S-E056DBAD19, S-B1279A66EB) — surfaces stale heartbeats and
    frequent restarts so the operator can see when a daemon is flapping."""
    try:
        from utils.service_heartbeat import warnings as hb_warnings
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT service_name, code_version, started_at, last_beat_at, "
                "pid, restart_count, last_restart_at FROM service_heartbeat"
            ).fetchall()
        services = [
            {
                'service': r[0], 'code_version': r[1], 'started_at': r[2],
                'last_beat_at': r[3], 'pid': r[4],
                'restart_count': r[5], 'last_restart_at': r[6],
            }
            for r in rows
        ]
        return jsonify({'services': services, 'warnings': hb_warnings()})
    except Exception as exc:
        return jsonify({'error': str(exc), 'services': [], 'warnings': []}), 500
