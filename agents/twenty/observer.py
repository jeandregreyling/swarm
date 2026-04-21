"""Observer — collects signals from existing swarm tables.

No new data capture; reads what already exists.
Returns a signal dict consumed by the council.
"""

import logging
from datetime import datetime, timedelta, timezone

from utils.db._connection import get_connection

logger = logging.getLogger('seven.agent20.observer')


def _safe_fetchone(conn, sql, params=(), default=0):
    """Execute and return a single scalar, swallowing missing-table errors."""
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else default
    except Exception as exc:
        logger.debug("observer query skipped (%s): %s", sql[:40], exc)
        return default


def _safe_fetchall(conn, sql, params=()):
    """Execute and return all rows as dicts, swallowing errors."""
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception as exc:
        logger.debug("observer query skipped (%s): %s", sql[:40], exc)
        return []


def collect_signals():
    """Read existing swarm tables and return a signal snapshot.

    Returns dict with keys matching §4b.6 design spec:
        queue_depth, queue_aging, pending_proposals, open_tickets_aging,
        agent_health, user_topics, recent_decisions, scheduled_due,
        sniffer_findings, email_backlog, agent_roster.
    """
    conn = get_connection()
    now = datetime.now(timezone.utc)
    try:
        signals = {}

        # 1. Queue depth & aging
        signals['queue_depth'] = _safe_fetchone(
            conn,
            "SELECT COUNT(*) FROM queue WHERE status='queued'"
        )
        signals['queue_aging'] = _safe_fetchall(
            conn,
            "SELECT id, subject, created_at FROM queue WHERE status='queued' ORDER BY created_at ASC LIMIT 10"
        )

        # 2. Pending proposals
        signals['pending_proposals'] = _safe_fetchall(
            conn,
            "SELECT proposal_id, agent, title, created_at FROM work_proposals WHERE status='pending' ORDER BY created_at ASC LIMIT 10"
        )

        # 3. Open tickets aging > 24h
        cutoff_24h = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        signals['open_tickets_aging'] = _safe_fetchall(
            conn,
            "SELECT ticket_number, question, created_at FROM tickets WHERE status='open' AND created_at < ? ORDER BY created_at ASC LIMIT 10",
            (cutoff_24h,)
        )

        # 4. Agent health — recent errors in activity_log (last 30 min)
        cutoff_30m = (now - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        signals['agent_errors'] = _safe_fetchall(
            conn,
            "SELECT service, event, detail, created_at FROM activity_log WHERE event LIKE '%error%' AND created_at > ? ORDER BY created_at DESC LIMIT 10",
            (cutoff_30m,)
        )

        # 5. System stats (latest reading)
        latest_stats = _safe_fetchall(
            conn,
            "SELECT cpu_percent, ram_used_gb, ram_available_gb, cpu_temp_c, recorded_at FROM system_stats ORDER BY id DESC LIMIT 1"
        )
        signals['system_stats'] = latest_stats[0] if latest_stats else {}

        # 6. User topics (active interests)
        signals['user_topics'] = _safe_fetchall(
            conn,
            "SELECT topic, category, score FROM user_interests WHERE active=1 ORDER BY score DESC LIMIT 15"
        )

        # 7. Recent decisions (last 7 days)
        cutoff_7d = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        signals['recent_decisions'] = _safe_fetchall(
            conn,
            "SELECT agent, decision, reasoning, created_at FROM decisions WHERE created_at > ? ORDER BY created_at DESC LIMIT 10",
            (cutoff_7d,)
        )

        # 8. Scheduled tasks due soon (next 1 hour)
        cutoff_1h = (now + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        signals['scheduled_due'] = _safe_fetchall(
            conn,
            "SELECT name, schedule, next_run FROM scheduled_tasks WHERE enabled=1 AND next_run IS NOT NULL AND next_run < ? ORDER BY next_run ASC LIMIT 10",
            (cutoff_1h,)
        )

        # 9. Sniffer findings (unresolved)
        signals['sniffer_findings'] = _safe_fetchall(
            conn,
            "SELECT id, detail, created_at FROM sniffer_log ORDER BY created_at DESC LIMIT 5"
        )

        # 10. Email backlog
        signals['email_backlog'] = _safe_fetchone(
            conn,
            "SELECT COUNT(*) FROM pending_emails WHERE processed_at IS NULL"
        )

        # 11. Agent roster (who's alive, what they do)
        signals['agent_roster'] = _safe_fetchall(
            conn,
            "SELECT number, name, label, model, role, enabled FROM agents WHERE enabled=1 ORDER BY number"
        )

        # 12. Past council dismissals (last 7 days) — for Keeper's value scoring
        signals['recent_dismissals'] = _safe_fetchall(
            conn,
            "SELECT orb_role, thought, created_at FROM council_output WHERE dismissed=1 AND created_at > ? ORDER BY created_at DESC LIMIT 20",
            (cutoff_7d,)
        )

        # 13. Own memory (last 10 entries) — self-reasoning
        signals['own_memory'] = _safe_fetchall(
            conn,
            "SELECT subject, content, importance, created_at FROM memory_twenty WHERE archived=0 ORDER BY importance DESC, created_at DESC LIMIT 10"
        )

        signals['collected_at'] = now.strftime('%Y-%m-%d %H:%M:%S')
        return signals

    finally:
        conn.close()
