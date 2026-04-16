"""idle_mgmt_bp.py — Idle-time self-management (Tier 4.5).
Allows agents to claim pending proposals/queue items when idle.
Exposes API for idle detection and auto-claim.
"""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from database import get_connection, log_activity

idle_bp = Blueprint('idle_mgmt', __name__)


@idle_bp.route('/api/agents/idle', methods=['GET'])
def api_idle_agents():
    """Return agents that haven't had activity in the last N minutes."""
    minutes = min(int(request.args.get('minutes', 10)), 60)
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_connection()
    try:
        # Agents with recent heartbeats/registry entries
        active = conn.execute("""
            SELECT DISTINCT agent_name FROM agent_registry
            WHERE last_seen > ?
        """, (cutoff,)).fetchall()
        active_names = {r[0] for r in active}

        # All known agents
        all_agents = conn.execute("SELECT name FROM agents WHERE active=1").fetchall()
        all_names = {r[0] for r in all_agents}
    except Exception:
        conn.close()
        return jsonify({'ok': True, 'idle_agents': [], 'active_agents': []})

    conn.close()
    idle = sorted(all_names - active_names)
    return jsonify({
        'ok': True,
        'idle_agents': idle,
        'active_agents': sorted(active_names),
        'idle_threshold_minutes': minutes,
    })


@idle_bp.route('/api/agents/idle/claim', methods=['POST'])
def api_idle_claim():
    """An idle agent claims a pending proposal or queue item."""
    data = request.get_json(force=True, silent=True) or {}
    agent = str(data.get('agent', '')).strip().lower()
    if not agent:
        return jsonify({'ok': False, 'error': 'agent name required'}), 400

    conn = get_connection()
    try:
        # Find oldest unclaimed pending proposal
        row = conn.execute("""
            SELECT proposal_id, title FROM work_proposals
            WHERE status='pending' AND (claimed_by IS NULL OR claimed_by='')
            ORDER BY id ASC LIMIT 1
        """).fetchone()

        if row:
            conn.execute(
                "UPDATE work_proposals SET claimed_by=?, status='in_progress' WHERE proposal_id=?",
                (agent, row['proposal_id'])
            )
            conn.commit()
            conn.close()
            log_activity('idle_mgmt', 'claim', f'{agent} claimed proposal {row["proposal_id"]}')
            return jsonify({'ok': True, 'claimed': 'proposal', 'proposal_id': row['proposal_id'], 'title': row['title']})

        # Fallback: claim oldest queued item
        q_row = conn.execute("""
            SELECT id, subject FROM queue
            WHERE status='queued'
            ORDER BY id ASC LIMIT 1
        """).fetchone()

        if q_row:
            conn.execute(
                "UPDATE queue SET status='processing' WHERE id=?",
                (q_row['id'],)
            )
            conn.commit()
            conn.close()
            log_activity('idle_mgmt', 'claim', f'{agent} claimed queue #{q_row["id"]}')
            return jsonify({'ok': True, 'claimed': 'queue', 'queue_id': q_row['id'], 'subject': q_row['subject']})
    except Exception as exc:
        conn.close()
        return jsonify({'ok': False, 'error': str(exc)[:200]}), 500

    conn.close()
    return jsonify({'ok': True, 'claimed': None, 'message': 'Nothing to claim'})


@idle_bp.route('/api/queue/depth', methods=['GET'])
def api_queue_depth():
    """Quick queue depth check."""
    conn = get_connection()
    try:
        queued = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        pending_proposals = conn.execute("SELECT COUNT(*) FROM work_proposals WHERE status='pending'").fetchone()[0]
    except Exception:
        conn.close()
        return jsonify({'ok': True, 'queued': 0, 'processing': 0, 'pending_proposals': 0})
    conn.close()
    return jsonify({'ok': True, 'queued': queued, 'processing': processing, 'pending_proposals': pending_proposals})
