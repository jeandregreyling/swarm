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


@metrics_bp.route('/api/metrics/prometheus', methods=['GET'])
def get_metrics_prometheus():
    """Return metrics in Prometheus text exposition format."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            lines = []

            # Agent counts
            row = conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) as active "
                "FROM agents"
            ).fetchone()
            lines.append(f'# HELP swarm_agents_total Total number of agents')
            lines.append(f'# TYPE swarm_agents_total gauge')
            lines.append(f'swarm_agents_total {row[0]}')
            lines.append(f'# HELP swarm_agents_active Number of enabled agents')
            lines.append(f'# TYPE swarm_agents_active gauge')
            lines.append(f'swarm_agents_active {row[1]}')

            # Proposals by status
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM work_proposals GROUP BY status"
            ).fetchall()
            lines.append(f'# HELP swarm_proposals Proposals by status')
            lines.append(f'# TYPE swarm_proposals gauge')
            for r in rows:
                lines.append(f'swarm_proposals{{status="{r[0]}"}} {r[1]}')

            # Bus events 24h
            row = conn.execute(
                "SELECT COUNT(*) FROM swarm_bus "
                "WHERE created_at > datetime('now', '-1 day')"
            ).fetchone()
            lines.append(f'# HELP swarm_bus_events_24h Bus events in last 24 hours')
            lines.append(f'# TYPE swarm_bus_events_24h gauge')
            lines.append(f'swarm_bus_events_24h {row[0]}')

            # Bus unconsumed
            row = conn.execute(
                "SELECT COUNT(*) FROM swarm_bus WHERE consumed_at IS NULL"
            ).fetchone()
            lines.append(f'# HELP swarm_bus_unconsumed Unconsumed bus messages')
            lines.append(f'# TYPE swarm_bus_unconsumed gauge')
            lines.append(f'swarm_bus_unconsumed {row[0]}')

            # Node count
            row = conn.execute("SELECT COUNT(*) FROM swarm_nodes").fetchone()
            lines.append(f'# HELP swarm_nodes_total Registered federation nodes')
            lines.append(f'# TYPE swarm_nodes_total gauge')
            lines.append(f'swarm_nodes_total {row[0]}')

            # Tickets by status
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM tickets GROUP BY status"
                ).fetchall()
                lines.append(f'# HELP swarm_tickets Tickets by status')
                lines.append(f'# TYPE swarm_tickets gauge')
                for r in rows:
                    lines.append(f'swarm_tickets{{status="{r[0]}"}} {r[1]}')
            except Exception:
                pass

            from flask import Response
            return Response(
                '\n'.join(lines) + '\n',
                mimetype='text/plain; version=0.0.4; charset=utf-8',
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.error(f'prometheus metrics failed: {exc}')
        return Response(f'# error: {exc}\n', mimetype='text/plain', status=500)
