"""
utils/agent_coordination.py — Agent self-coordination (A.2.3)
═══════════════════════════════════════════════════════════════
Pre-dispatch availability checks and idle proposal claiming.

Usage:
    from utils.agent_coordination import check_agent_available, find_alternative, claim_pending_proposal

    ok, info = check_agent_available('gemma')
    if not ok:
        alt = find_alternative('gemma')  # returns best idle agent with matching role
"""

import logging

logger = logging.getLogger('seven.agent_coordination')


def get_agent_status_map():
    """Build a dict of agent_name → {status, tier, active_jobs, circuit_breaker, role}.

    Derives status from: chat_jobs (running=busy), circuit breaker (open=down),
    agents table (enabled field).
    """
    try:
        from database import get_connection
        conn = get_connection()
        try:
            agents_rows = conn.execute(
                "SELECT name, tier, role, enabled FROM agents WHERE number >= 0"
            ).fetchall()
            running_rows = conn.execute(
                "SELECT agent, COUNT(*) as cnt FROM chat_jobs WHERE status='running' GROUP BY agent"
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'get_agent_status_map failed: {e}')
        return {}

    running_map = {r['agent'].lower(): r['cnt'] for r in running_rows}

    try:
        from utils.circuit_breaker import status_for as _cb_status_for
        _cb_ok = True
    except ImportError:
        _cb_ok = False

    result = {}
    # Import DISABLED_AGENTS if available
    try:
        from services import DISABLED_AGENTS
    except ImportError:
        DISABLED_AGENTS = set()

    for row in agents_rows:
        name = row['name'].lower()
        enabled = bool(row['enabled']) if row['enabled'] is not None else True
        active = running_map.get(name, 0)

        cb_state = 'closed'
        if _cb_ok:
            try:
                cb_state = _cb_status_for(name).get('state', 'closed')
            except Exception:
                pass

        if not enabled or name in DISABLED_AGENTS:
            status = 'disabled'
        elif cb_state == 'open':
            status = 'down'
        elif active > 0:
            status = 'busy'
        else:
            status = 'idle'

        result[name] = {
            'status': status,
            'tier': row['tier'] or 'local',
            'role': row['role'] or '',
            'active_jobs': active,
            'circuit_breaker': cb_state,
        }
    return result


def check_agent_available(agent_name):
    """Check if an agent is available for dispatch.

    Returns (available: bool, info: dict).
    info keys: status, reason (if unavailable).
    """
    name = (agent_name or '').strip().lower()
    if not name:
        return False, {'status': 'unknown', 'reason': 'empty agent name'}

    status_map = get_agent_status_map()
    info = status_map.get(name)
    if not info:
        return False, {'status': 'unknown', 'reason': f'agent {name!r} not in registry'}

    if info['status'] == 'idle':
        return True, info
    if info['status'] == 'busy':
        return False, {**info, 'reason': f'{name} has {info["active_jobs"]} active job(s)'}
    if info['status'] == 'down':
        return False, {**info, 'reason': f'{name} circuit breaker is open'}
    if info['status'] == 'disabled':
        return False, {**info, 'reason': f'{name} is disabled'}

    return True, info   # fallback: assume available


def find_alternative(target_agent, exclude=None):
    """Find the best idle agent with the same role as target_agent.

    Returns agent name (str) or None if no alternative found.
    Prefers agents of the same tier, then higher tier.
    """
    name = (target_agent or '').strip().lower()
    exclude = set(exclude or [])
    exclude.add(name)

    status_map = get_agent_status_map()
    target_info = status_map.get(name, {})
    target_role = target_info.get('role', '')

    tier_rank = {'local': 0, 'paid': 1, 'service': 2, 'human': 3}

    candidates = []
    for agent, info in status_map.items():
        if agent in exclude:
            continue
        if info['status'] != 'idle':
            continue
        # Role match: same role, or if target has no role, any agent
        if target_role and info.get('role') != target_role:
            continue
        candidates.append((agent, info))

    if not candidates:
        # Fallback: any idle agent (no role match required)
        for agent, info in status_map.items():
            if agent in exclude or info['status'] != 'idle':
                continue
            if agent in ('ghost', 'duck', 'sniffles', 'librarian'):
                continue  # skip utility/system agents
            candidates.append((agent, info))

    if not candidates:
        return None

    # Sort: prefer same tier as target, then by tier rank ascending
    target_tier = target_info.get('tier', 'local')
    def _sort_key(item):
        a_tier = item[1].get('tier', 'local')
        same = 0 if a_tier == target_tier else 1
        rank = tier_rank.get(a_tier, 0)
        return (same, rank, item[0])

    candidates.sort(key=_sort_key)
    return candidates[0][0]


def check_and_reroute(target_agent, exclude=None):
    """Check target availability; if unavailable, find alternative.

    Returns (final_agent: str, rerouted: bool, reason: str).
    """
    available, info = check_agent_available(target_agent)
    if available:
        return target_agent, False, ''

    reason = info.get('reason', f'{target_agent} unavailable')
    alt = find_alternative(target_agent, exclude=exclude)
    if alt:
        logger.info(f'[coordination] reroute {target_agent} → {alt}: {reason}')
        return alt, True, f'{reason}; rerouted to {alt}'

    logger.warning(f'[coordination] no alternative for {target_agent}: {reason}')
    return target_agent, False, reason  # no alternative — try anyway


def claim_pending_proposal(agent_name):
    """Attempt to atomically claim a pending proposal matching agent's role.

    Uses atomic UPDATE ... WHERE status='pending' AND agent IS NULL.
    Returns proposal_id (int) or None.
    """
    name = (agent_name or '').strip().lower()
    if not name:
        return None

    try:
        from database import get_connection
        conn = get_connection()
        try:
            # Get agent's role for matching
            agent_row = conn.execute(
                "SELECT role FROM agents WHERE name=?", (name,)
            ).fetchone()
            role = (agent_row['role'] if agent_row else '') or ''

            # Atomic claim: grab oldest pending proposal with no assigned agent
            # If agent has a role, prefer proposals tagged with that role
            if role:
                row = conn.execute(
                    """UPDATE work_proposals
                       SET agent = ?, status = 'approved', updated_at = datetime('now')
                       WHERE id = (
                           SELECT id FROM work_proposals
                           WHERE status = 'pending'
                             AND (agent IS NULL OR agent = '')
                             AND (tags LIKE ? OR tags LIKE '%general%' OR tags IS NULL)
                           ORDER BY priority ASC, created_at ASC
                           LIMIT 1
                       )
                       RETURNING id""",
                    (name, f'%{role}%')
                ).fetchone()
            else:
                row = conn.execute(
                    """UPDATE work_proposals
                       SET agent = ?, status = 'approved', updated_at = datetime('now')
                       WHERE id = (
                           SELECT id FROM work_proposals
                           WHERE status = 'pending'
                             AND (agent IS NULL OR agent = '')
                           ORDER BY priority ASC, created_at ASC
                           LIMIT 1
                       )
                       RETURNING id""",
                    (name,)
                ).fetchone()

            if row:
                conn.commit()
                proposal_id = row['id'] if isinstance(row, dict) else row[0]
                logger.info(f'[coordination] {name} claimed proposal {proposal_id}')
                return proposal_id
            return None
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'claim_pending_proposal failed for {name}: {e}')
        return None
