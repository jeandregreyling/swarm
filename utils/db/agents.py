"""
db.agents — Agent registry and capability management.
"""
from ._connection import get_connection, logger


def get_agent_registry():
    """Return all active agents ordered by number. Excludes retired (number=-1)."""
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT number, name, label, model, temperature, role
                   FROM agents
                   WHERE number >= 0
                   ORDER BY number ASC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f'get_agent_registry failed: {e}')
        return []


# All capabilities an agent can be granted
AGENT_CAPABILITY_REGISTRY = {
    'ticket_create':    {'desc': 'Create tickets and proposals via agent API',           'trust': 1},
    'ticket_query':     {'desc': 'Query all tickets and proposals via agent API',         'trust': 0},
    'sandpit_read':     {'desc': 'Read any sandpit (own + shared)',                       'trust': 0},
    'sandpit_write':    {'desc': 'Write to own sandpit',                                  'trust': 1},
    'shared_write':     {'desc': 'Write to shared sandpit',                               'trust': 2},
    'skill_shell':      {'desc': 'Execute whitelisted shell commands',                    'trust': 2},
    'skill_browse':     {'desc': 'Browse URLs with headless browser',                     'trust': 1},
    'skill_search':     {'desc': 'Run DuckDuckGo web searches',                          'trust': 0},
    'skill_schedule':   {'desc': 'Create scheduled tasks',                                'trust': 2},
    'memory_write':     {'desc': 'Save to own agent memory',                              'trust': 1},
    'memory_read_all':  {'desc': 'Read memory of other agents (cross-agent awareness)',   'trust': 2},
    'git_propose':      {'desc': 'Create ALM-gated Git proposals (stage/unstage/commit)', 'trust': 1},
    'git_execute':      {'desc': 'Execute approved ALM-gated Git proposals',               'trust': 2},
    'propose_work':     {'desc': 'Self-initiate work proposals without human prompt',     'trust': 2},
    'coordinate':       {'desc': 'Send coordination messages to other local agents',      'trust': 2},
}


def get_agent_capabilities(agent_name):
    """Return all capabilities for an agent, with granted status."""
    name = (agent_name or '').strip().lower()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT capability, granted, trust_level, granted_by, granted_at, notes "
            "FROM agent_capabilities WHERE agent_name=? ORDER BY capability",
            (name,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def grant_agent_capability(agent_name, capability, granted_by='ghost', proposal_id='', notes=''):
    """Grant a capability to an agent. Idempotent."""
    name = (agent_name or '').strip().lower()
    cap = (capability or '').strip().lower()
    if not name or not cap:
        return
    meta = AGENT_CAPABILITY_REGISTRY.get(cap, {})
    trust = meta.get('trust', 0)
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO agent_capabilities
               (agent_name, capability, granted, trust_level, granted_by, proposal_id, notes, granted_at)
               VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(agent_name, capability)
               DO UPDATE SET granted=1, granted_by=excluded.granted_by,
                             proposal_id=excluded.proposal_id, notes=excluded.notes,
                             granted_at=excluded.granted_at""",
            (name, cap, trust, granted_by, proposal_id, notes)
        )
        conn.commit()
    finally:
        conn.close()


def revoke_agent_capability(agent_name, capability):
    """Revoke a capability from an agent."""
    name = (agent_name or '').strip().lower()
    cap = (capability or '').strip().lower()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE agent_capabilities SET granted=0 WHERE agent_name=? AND capability=?",
            (name, cap)
        )
        conn.commit()
    finally:
        conn.close()


def agent_has_capability(agent_name, capability):
    """Check if an agent has a specific capability granted."""
    name = (agent_name or '').strip().lower()
    cap = (capability or '').strip().lower()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT granted FROM agent_capabilities WHERE agent_name=? AND capability=?",
            (name, cap)
        ).fetchone()
        return bool(row and row['granted'])
    finally:
        conn.close()
