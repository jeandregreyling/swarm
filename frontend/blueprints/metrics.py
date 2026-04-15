"""
frontend/blueprints/metrics.py — Observability metrics endpoint (E.3.2)
═══════════════════════════════════════════════════════════════════════════════
GET /api/metrics — returns operational counters and gauges
"""

import logging
from flask import Blueprint, jsonify

metrics_bp = Blueprint('metrics', __name__)
logger = logging.getLogger(__name__)


@metrics_bp.route('/api/metrics', methods=['GET'])
def get_metrics():
    """Return operational metrics as JSON."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            metrics = {}

            # Agent counts
            row = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) as active "
                "FROM agents"
            ).fetchone()
            metrics['agents_total'] = row[0]
            metrics['agents_active'] = row[1]

            # Proposals by status
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM work_proposals GROUP BY status"
            ).fetchall()
            metrics['proposals_by_status'] = {r[0]: r[1] for r in rows}

            # Bus events in last 24h
            row = conn.execute(
                "SELECT COUNT(*) FROM swarm_bus "
                "WHERE created_at > datetime('now', '-1 day')"
            ).fetchone()
            metrics['bus_events_24h'] = row[0]

            # Bus unconsumed
            row = conn.execute(
                "SELECT COUNT(*) FROM swarm_bus WHERE consumed_at IS NULL"
            ).fetchone()
            metrics['bus_unconsumed'] = row[0]

            # Research sessions
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM research_sessions "
                "GROUP BY status"
            ).fetchall()
            metrics['research_by_status'] = {r[0]: r[1] for r in rows}

            # Node count
            row = conn.execute("SELECT COUNT(*) FROM swarm_nodes").fetchone()
            metrics['node_count'] = row[0]

            # Knowledge entries
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM shared_knowledge"
                ).fetchone()
                metrics['knowledge_entries'] = row[0]
            except Exception:
                metrics['knowledge_entries'] = 0

            # Tool builds by status
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM tool_builds "
                    "GROUP BY status"
                ).fetchall()
                metrics['tool_builds_by_status'] = {r[0]: r[1] for r in rows}
            except Exception:
                metrics['tool_builds_by_status'] = {}

            # Ticket counts
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM tickets GROUP BY status"
                ).fetchall()
                metrics['tickets_by_status'] = {r[0]: r[1] for r in rows}
            except Exception:
                metrics['tickets_by_status'] = {}

            return jsonify(metrics)
        finally:
            conn.close()
    except Exception as exc:
        logger.error(f'metrics endpoint failed: {exc}')
        return jsonify({'error': str(exc)}), 500
