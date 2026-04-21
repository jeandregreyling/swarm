"""Mapper — System process scanner for Agent 20.

Scans every auditable surface of the swarm: logs, queues, agents, tasks,
tickets, decisions, memories, governance, errors.  Produces a health digest
that is the "one-stop shop" view of what the system is doing right now.

If this digest shows zero problems, either the system is perfect or the
mapper is broken — and the mapper should flag that too.

Honesty rule applies: nothing is hidden, nothing is softened.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from utils.db._connection import get_connection

logger = logging.getLogger('seven.agent20.mapper')

# ── Status constants ──────────────────────────────────────────────────

STATUS_HEALTHY = 'healthy'
STATUS_DEGRADED = 'degraded'
STATUS_ERROR = 'error'
STATUS_CRITICAL = 'critical'
STATUS_UNKNOWN = 'unknown'


def _safe_count(conn, sql, params=()):
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0
    except Exception:
        return -1  # -1 means table missing or query failed


def _safe_fetch(conn, sql, params=()):
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def scan_agents(conn):
    """Map all agent statuses."""
    agents = _safe_fetch(conn,
        "SELECT number, name, label, model, role, enabled FROM agents ORDER BY number")
    total = len(agents)
    enabled = sum(1 for a in agents if a.get('enabled'))
    disabled = total - enabled
    return {
        'total': total,
        'enabled': enabled,
        'disabled': disabled,
        'agents': agents,
        'status': STATUS_HEALTHY if enabled > 0 else STATUS_ERROR,
    }


def scan_queue(conn):
    """Map queue state: depth, aging, stuck items."""
    now = datetime.now(timezone.utc)
    depth = _safe_count(conn, "SELECT COUNT(*) FROM queue WHERE status='queued'")
    total = _safe_count(conn, "SELECT COUNT(*) FROM queue")
    processing = _safe_count(conn, "SELECT COUNT(*) FROM queue WHERE status='processing'")
    failed = _safe_count(conn, "SELECT COUNT(*) FROM queue WHERE status='failed'")

    cutoff_1h = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    stuck = _safe_count(conn,
        "SELECT COUNT(*) FROM queue WHERE status='queued' AND created_at < ?",
        (cutoff_1h,))

    status = STATUS_HEALTHY
    if stuck > 5 or failed > 3:
        status = STATUS_ERROR
    elif depth > 10 or stuck > 0:
        status = STATUS_DEGRADED

    return {
        'depth': depth,
        'total': total,
        'processing': processing,
        'failed': failed,
        'stuck_over_1h': stuck,
        'status': status,
    }


def scan_tickets(conn):
    """Map ticket state: open, aging, unresolved."""
    now = datetime.now(timezone.utc)
    open_count = _safe_count(conn, "SELECT COUNT(*) FROM tickets WHERE status='open'")
    total = _safe_count(conn, "SELECT COUNT(*) FROM tickets")

    cutoff_24h = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    aging = _safe_count(conn,
        "SELECT COUNT(*) FROM tickets WHERE status='open' AND created_at < ?",
        (cutoff_24h,))

    cutoff_72h = (now - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S')
    stale = _safe_count(conn,
        "SELECT COUNT(*) FROM tickets WHERE status='open' AND created_at < ?",
        (cutoff_72h,))

    status = STATUS_HEALTHY
    if stale > 0:
        status = STATUS_ERROR
    elif aging > 3:
        status = STATUS_DEGRADED

    return {
        'open': open_count,
        'total': total,
        'aging_over_24h': aging,
        'stale_over_72h': stale,
        'status': status,
    }


def scan_errors(conn):
    """Map recent errors across the system."""
    now = datetime.now(timezone.utc)
    cutoff_1h = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    cutoff_24h = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')

    errors_1h = _safe_fetch(conn,
        "SELECT service, event, detail, created_at FROM activity_log "
        "WHERE event LIKE '%error%' AND created_at > ? ORDER BY created_at DESC LIMIT 20",
        (cutoff_1h,))

    errors_24h_count = _safe_count(conn,
        "SELECT COUNT(*) FROM activity_log WHERE event LIKE '%error%' AND created_at > ?",
        (cutoff_24h,))

    # Group by service
    by_service = {}
    for e in errors_1h:
        svc = e.get('service', 'unknown')
        by_service[svc] = by_service.get(svc, 0) + 1

    status = STATUS_HEALTHY
    if len(errors_1h) >= 10:
        status = STATUS_CRITICAL
    elif len(errors_1h) >= 5:
        status = STATUS_ERROR
    elif len(errors_1h) >= 1:
        status = STATUS_DEGRADED

    return {
        'last_hour': len(errors_1h),
        'last_24h': errors_24h_count,
        'by_service': by_service,
        'recent': errors_1h[:5],
        'status': status,
    }


def scan_system(conn):
    """Map system resource state."""
    rows = _safe_fetch(conn,
        "SELECT cpu_percent, ram_used_gb, ram_available_gb, cpu_temp_c, recorded_at "
        "FROM system_stats ORDER BY id DESC LIMIT 1")
    if not rows:
        return {'status': STATUS_UNKNOWN, 'detail': 'No system stats recorded'}

    s = rows[0]
    cpu = s.get('cpu_percent', 0)
    ram_avail = s.get('ram_available_gb', 8)
    temp = s.get('cpu_temp_c', 0)

    status = STATUS_HEALTHY
    problems = []
    if cpu > 90:
        status = STATUS_CRITICAL
        problems.append(f'CPU {cpu:.0f}%')
    elif cpu > 70:
        status = STATUS_DEGRADED
        problems.append(f'CPU {cpu:.0f}%')
    if ram_avail < 1:
        status = STATUS_CRITICAL
        problems.append(f'RAM {ram_avail:.1f}GB free')
    elif ram_avail < 2:
        status = max(status, STATUS_DEGRADED)
        problems.append(f'RAM {ram_avail:.1f}GB free')
    if temp > 85:
        status = STATUS_CRITICAL
        problems.append(f'Temp {temp:.0f}°C')
    elif temp > 70:
        status = max(status, STATUS_DEGRADED)
        problems.append(f'Temp {temp:.0f}°C')

    return {
        'cpu_percent': cpu,
        'ram_used_gb': s.get('ram_used_gb', 0),
        'ram_available_gb': ram_avail,
        'cpu_temp_c': temp,
        'recorded_at': s.get('recorded_at', ''),
        'problems': problems,
        'status': status,
    }


def scan_proposals(conn):
    """Map proposal pipeline."""
    pending = _safe_count(conn, "SELECT COUNT(*) FROM work_proposals WHERE status='pending'")
    approved = _safe_count(conn, "SELECT COUNT(*) FROM work_proposals WHERE status='approved'")
    rejected = _safe_count(conn, "SELECT COUNT(*) FROM work_proposals WHERE status='rejected'")
    total = _safe_count(conn, "SELECT COUNT(*) FROM work_proposals")

    status = STATUS_HEALTHY
    if pending > 10:
        status = STATUS_DEGRADED

    return {
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'total': total,
        'status': status,
    }


def scan_council(conn):
    """Map Agent 20's own council output state."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    active = _safe_count(conn,
        "SELECT COUNT(*) FROM council_output WHERE dismissed=0 AND expires_at > ?",
        (now,))
    dismissed = _safe_count(conn, "SELECT COUNT(*) FROM council_output WHERE dismissed=1")
    expired = _safe_count(conn,
        "SELECT COUNT(*) FROM council_output WHERE dismissed=0 AND expires_at <= ?",
        (now,))
    total = _safe_count(conn, "SELECT COUNT(*) FROM council_output")

    # Role distribution of active thoughts
    role_dist = {}
    rows = _safe_fetch(conn,
        "SELECT orb_role, COUNT(*) as cnt FROM council_output "
        "WHERE dismissed=0 AND expires_at > ? GROUP BY orb_role",
        (now,))
    for r in rows:
        role_dist[r['orb_role']] = r['cnt']

    return {
        'active': active,
        'dismissed': dismissed,
        'expired': expired,
        'total': total,
        'role_distribution': role_dist,
        'status': STATUS_HEALTHY if active >= 0 else STATUS_UNKNOWN,
    }


def scan_memory(conn):
    """Map Agent 20's memory state."""
    active = _safe_count(conn, "SELECT COUNT(*) FROM memory_twenty WHERE archived=0")
    archived = _safe_count(conn, "SELECT COUNT(*) FROM memory_twenty WHERE archived=1")
    patterns = _safe_count(conn, "SELECT COUNT(*) FROM user_patterns")
    high_importance = _safe_count(conn,
        "SELECT COUNT(*) FROM memory_twenty WHERE archived=0 AND importance >= 7")

    return {
        'active_memories': active,
        'archived': archived,
        'patterns_tracked': patterns,
        'high_importance': high_importance,
        'status': STATUS_HEALTHY,
    }


def scan_governance(conn):
    """Map governance/audit state."""
    gov_entries = _safe_count(conn, "SELECT COUNT(*) FROM governance_log")
    recent_gov = _safe_count(conn,
        "SELECT COUNT(*) FROM governance_log WHERE created_at > datetime('now', '-24 hours')")

    decisions_total = _safe_count(conn, "SELECT COUNT(*) FROM decisions")
    decisions_pending = _safe_count(conn,
        "SELECT COUNT(*) FROM decisions WHERE test_status='PENDING'")

    return {
        'governance_entries': gov_entries,
        'governance_last_24h': recent_gov,
        'decisions_total': decisions_total,
        'decisions_pending': decisions_pending,
        'status': STATUS_HEALTHY,
    }


def scan_emails(conn):
    """Map email pipeline state."""
    backlog = _safe_count(conn, "SELECT COUNT(*) FROM pending_emails WHERE processed_at IS NULL")
    status = STATUS_HEALTHY
    if backlog > 20:
        status = STATUS_ERROR
    elif backlog > 5:
        status = STATUS_DEGRADED
    return {'backlog': backlog, 'status': status}


def scan_tasks(conn):
    """Map scheduled task state."""
    now = datetime.now(timezone.utc)
    enabled = _safe_count(conn, "SELECT COUNT(*) FROM scheduled_tasks WHERE enabled=1")
    overdue = _safe_count(conn,
        "SELECT COUNT(*) FROM scheduled_tasks WHERE enabled=1 AND next_run IS NOT NULL AND next_run < ?",
        (now.strftime('%Y-%m-%d %H:%M:%S'),))

    recent_failures = _safe_count(conn,
        "SELECT COUNT(*) FROM task_run_log WHERE status != 'ok' AND run_at > ?",
        ((now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S'),))

    status = STATUS_HEALTHY
    if recent_failures > 3:
        status = STATUS_ERROR
    elif overdue > 2 or recent_failures > 0:
        status = STATUS_DEGRADED

    return {
        'enabled': enabled,
        'overdue': overdue,
        'recent_failures_24h': recent_failures,
        'status': status,
    }


# ── Honesty check: is the mapper itself broken? ──────────────────────

def _self_check(digest):
    """If every subsystem reports healthy but there are zero data points,
    the mapper might be broken or the DB is empty.  Flag it."""
    all_healthy = all(
        v.get('status') == STATUS_HEALTHY
        for v in digest.values()
        if isinstance(v, dict) and 'status' in v
    )
    # If the system has no errors, no queue, no tickets, no proposals, check if DB is just empty
    has_data = (
        digest.get('queue', {}).get('total', 0) > 0
        or digest.get('tickets', {}).get('total', 0) > 0
        or digest.get('agents', {}).get('total', 0) > 0
        or digest.get('council', {}).get('total', 0) > 0
    )

    if all_healthy and not has_data:
        digest['_self_check'] = {
            'status': STATUS_DEGRADED,
            'warning': 'All subsystems report healthy but database appears empty — '
                       'mapper may not be reading real data',
        }
    elif all_healthy:
        digest['_self_check'] = {
            'status': STATUS_HEALTHY,
            'note': 'All subsystems healthy with live data',
        }
    else:
        problem_count = sum(
            1 for v in digest.values()
            if isinstance(v, dict) and v.get('status') not in (STATUS_HEALTHY, None)
        )
        digest['_self_check'] = {
            'status': STATUS_DEGRADED if problem_count < 3 else STATUS_ERROR,
            'problems_found': problem_count,
        }
    return digest


# ── Overall status ────────────────────────────────────────────────────

_STATUS_RANK = {STATUS_HEALTHY: 0, STATUS_UNKNOWN: 1, STATUS_DEGRADED: 2,
                STATUS_ERROR: 3, STATUS_CRITICAL: 4}


def _overall_status(digest):
    """Worst status across all subsystems."""
    worst = STATUS_HEALTHY
    for v in digest.values():
        if isinstance(v, dict) and 'status' in v:
            s = v['status']
            if _STATUS_RANK.get(s, 0) > _STATUS_RANK.get(worst, 0):
                worst = s
    return worst


# ── Main entry ────────────────────────────────────────────────────────

def build_health_digest(conn=None):
    """Scan the entire system and return a health digest dict.

    This is the one-stop-shop: everything Agent 20 can see, in one object.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        digest = {
            'agents': scan_agents(conn),
            'queue': scan_queue(conn),
            'tickets': scan_tickets(conn),
            'errors': scan_errors(conn),
            'system': scan_system(conn),
            'proposals': scan_proposals(conn),
            'council': scan_council(conn),
            'memory': scan_memory(conn),
            'governance': scan_governance(conn),
            'emails': scan_emails(conn),
            'tasks': scan_tasks(conn),
            'scanned_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
        }

        digest = _self_check(digest)
        digest['overall_status'] = _overall_status(digest)

        return digest
    finally:
        if close:
            conn.close()
