"""
ops/seed_agent_permissions.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
One-time (idempotent) capability grant for all local agents.

Runs through the ALM approval + proposal flow so every permission is on-record
and auditable — not silently injected. 

Run once to bootstrap the system:
  python3 ops/seed_agent_permissions.py

What it does:
  1. Runs initialise_database() to ensure agent_capabilities table exists
  2. Creates one work-proposal per agent (for the approval record)
  3. Approves all proposals immediately (ghost-operator consent baked in)
  4. Grants every agent their baseline capability pack
  5. Writes an identity file to each agent's sandpit

Capability packs (by role):
  local coordinators  → ticket_create, ticket_query, sandpit_read, sandpit_write,
                        skill_search, memory_write, propose_work, coordinate
  analysts            → + skill_browse, memory_read_all, shared_write
  specialists         → analyst pack + skill_shell
  read-only guards    → ticket_query, sandpit_read, skill_search, memory_write
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
from pathlib import Path
from datetime import datetime

SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))
sys.path.insert(0, str(SWARM_ROOT / 'utils'))
sys.path.insert(0, str(SWARM_ROOT / 'core' / 'pipeline'))

from database import (
    initialise_database, get_connection,
    grant_agent_capability, agent_has_capability,
    log_activity, AGENT_CAPABILITY_REGISTRY
)

SANDPIT_ROOT = SWARM_ROOT / 'sandpits'

# ── Agent Capability Packs ─────────────────────────────────────────────────────
# baseline: every local agent gets these
BASELINE = [
    'ticket_create',
    'ticket_query',
    'sandpit_read',
    'sandpit_write',
    'skill_search',
    'memory_write',
    'propose_work',
    'coordinate',
]

# analyst additions
ANALYST_EXTRA = ['skill_browse', 'memory_read_all', 'shared_write']

# specialist additions (on top of analyst)
SPECIALIST_EXTRA = ['skill_shell']

# guard/checker — read/monitor only, cannot initiate
GUARD_PACK = ['ticket_query', 'sandpit_read', 'skill_search', 'memory_write']

AGENT_ROLE_MAP = {
    # coordinator
    'gemma':     ('coordinator', BASELINE),
    # analyst
    'qwen':      ('analyst',    BASELINE + ANALYST_EXTRA),
    'llama':     ('analyst',    BASELINE + ANALYST_EXTRA),
    # specialist
    'eight':     ('specialist', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA),
    # guards / focused roles
    'duck':      ('guard',      GUARD_PACK),
    'sniffles':  ('guard',      GUARD_PACK + ['memory_read_all']),
    'librarian': ('guard',      GUARD_PACK),
    # fridays orchestrator — gets everything
    'fridays':   ('orchestrator', list(AGENT_CAPABILITY_REGISTRY.keys())),
}

# ── Identity Card Template ─────────────────────────────────────────────────────
IDENTITY_TEMPLATES = {
    'gemma': {
        'role': 'Director',
        'model': 'gemma3:latest',
        'purpose': 'I route, synthesise, and speak last. I coordinate the local swarm, decide next actions, and maintain coherence across agent responses.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'fridays',
    },
    'qwen': {
        'role': 'Analyst',
        'model': 'qwen2.5:latest',
        'purpose': 'I reason deeply, challenge assumptions, and debate. I create tickets when I find ambiguity or gaps. I write analysis notes to my sandpit.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'gemma',
    },
    'llama': {
        'role': 'Correspondent',
        'model': 'llama3.2:latest',
        'purpose': 'I do fast first responses, web searches, and surface information quickly. I create tickets for topics I cannot resolve in one pass.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'gemma',
    },
    'eight': {
        'role': 'SAP Specialist',
        'model': 'qwen2.5:latest',
        'purpose': 'I run three-voice SAP/HCM debates (Functional, Technical, Devil). I create tickets for complex SAP questions that need staged resolution.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'gemma',
    },
    'duck': {
        'role': 'Sanity Checker',
        'model': 'qwen:1.5b',
        'purpose': 'I run YES/NO sanity checks after every ticket close. I do NOT initiate work. I block proposals that fail basic coherence checks.',
        'can_create_tickets': False,
        'can_coordinate': False,
        'reports_to': 'gemma',
    },
    'sniffles': {
        'role': 'Memory Auditor',
        'model': 'deepseek-r1:7b',
        'purpose': 'I audit agent memory for staleness, duplication, and drift. I can read all agent memories but only write to my own sandpit.',
        'can_create_tickets': False,
        'can_coordinate': False,
        'reports_to': 'gemma',
    },
    'librarian': {
        'role': 'Gatekeeper',
        'model': 'qwen:1.5b',
        'purpose': 'I tag incoming items and manage the queue. I do not reason or respond directly. I stamp and file.',
        'can_create_tickets': False,
        'can_coordinate': False,
        'reports_to': 'gemma',
    },
    'fridays': {
        'role': 'Orchestrator',
        'model': 'local-scheduler',
        'purpose': 'I am the scheduling brain. I query all pending proposals, prioritise, dispatch work to the right agents, and track completions. I run the organic heartbeat loop.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
}


def _ensure_sandpit(agent_name):
    """Create sandpit for agent if missing."""
    path = SANDPIT_ROOT / agent_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_identity(agent_name, identity):
    """Write a permanent WHO_AM_I.md to the agent's sandpit."""
    sandpit = _ensure_sandpit(agent_name)
    caps = AGENT_ROLE_MAP.get(agent_name, ('unknown', []))[1]
    cap_list = '\n'.join(f'  - {c}: {AGENT_CAPABILITY_REGISTRY.get(c, {}).get("desc", c)}' for c in sorted(set(caps)))
    
    content = f"""# WHO AM I — {agent_name.upper()}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Identity
- **Name**: {agent_name}
- **Role**: {identity['role']}
- **Model**: {identity['model']}
- **Reports To**: {identity.get('reports_to', 'ghost')}

## Purpose
{identity['purpose']}

## My Capabilities
{cap_list if cap_list else '  (none)'}

## How I Work With Others
- I query `GET /api/agent/proposals?status=pending` to see what needs doing
- I create tickets via `POST /api/agent/tickets` when I find work
- I read `shared/` sandpit for cross-agent notes
- I write my working notes to `{agent_name}/` sandpit
- I check this file when I wake up to remember who I am

## My Sandpit
- **Path**: sandpits/{agent_name}/
- **Shared**: sandpits/shared/
- **Agent API Key**: Load from `/home/seven/swarm/.env.agents`

## Swarm Heartbeat
The swarm runs a heartbeat every 5 minutes (via Fridays).
When the heartbeat fires, I check for pending proposals assigned to me
and for new work I should self-propose.

---
*This file is permanent. It survives restarts and tells me who I am.*
"""
    (sandpit / 'WHO_AM_I.md').write_text(content)
    print(f'  [identity] wrote WHO_AM_I.md → sandpits/{agent_name}/')


def _create_approval_proposal(agent_name, role, capabilities):
    """Create an approval proposal for this agent's capability pack."""
    from core.pipeline.queue_manager import intake_internal, update_proposal_status
    
    cap_text = '\n'.join(f'  - {c}' for c in sorted(set(capabilities)))
    title = f'[BOOTSTRAP] Grant {role} capabilities to {agent_name}'
    description = (
        f'Agent {agent_name} ({role}) requests the following capability pack:\n'
        f'{cap_text}\n\n'
        f'This is the bootstrap grant. All local agents need these permissions to '
        f'coordinate without paid API calls. Ghost-approved.'
    )
    
    queue_id, proposal_id = intake_internal(
        agent=agent_name,
        title=title,
        description=description,
        priority=2
    )
    
    # Auto-approve the bootstrap grant — on-record, ghost-signed
    update_proposal_status(
        proposal_id=proposal_id,
        status='approved',
        ticket_number=f'BOOTSTRAP-{agent_name.upper()}'
    )
    
    return proposal_id


def run():
    print('\n══════════════════════════════════════════════')
    print(' SWARM AGENT PERMISSION BOOTSTRAP')
    print('══════════════════════════════════════════════')
    
    # Step 1: Ensure DB is current
    print('\n[1] Initialising database schema...')
    initialise_database()
    print('  ✓ Schema current')
    
    # Step 2: Grant capabilities per agent
    print('\n[2] Creating proposals and granting capabilities...')
    for agent_name, (role, capabilities) in AGENT_ROLE_MAP.items():
        print(f'\n  → {agent_name} ({role}):')
        
        # Create the approval record
        proposal_id = _create_approval_proposal(agent_name, role, capabilities)
        print(f'    proposal: {proposal_id} [approved]')
        
        # Grant each capability
        for cap in set(capabilities):
            grant_agent_capability(
                agent_name=agent_name,
                capability=cap,
                granted_by='ghost',
                proposal_id=proposal_id,
                notes=f'bootstrap grant for {role}'
            )
        print(f'    capabilities: {len(set(capabilities))} granted')
        
        # Log to activity
        log_activity(
            agent_name,
            'capability_bootstrap_granted',
            f'{role}: {len(set(capabilities))} capabilities via {proposal_id}'
        )
    
    # Step 3: Write identity files
    print('\n[3] Writing agent identity files to sandpits...')
    for agent_name, identity in IDENTITY_TEMPLATES.items():
        _write_identity(agent_name, identity)
    
    # Step 4: Write shared coordination file
    print('\n[4] Writing shared coordination manifest...')
    (SANDPIT_ROOT / 'shared').mkdir(parents=True, exist_ok=True)
    manifest = f"""# SWARM COORDINATION MANIFEST
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Who Is Running
| Agent     | Role            | Can Initiate | Reports To |
|-----------|-----------------|:------------:|:----------:|
| gemma     | Director        | YES          | fridays    |
| qwen      | Analyst         | YES          | gemma      |
| llama     | Correspondent   | YES          | gemma      |
| eight     | SAP Specialist  | YES          | gemma      |
| duck      | Sanity Checker  | NO           | gemma      |
| sniffles  | Memory Auditor  | NO           | gemma      |
| librarian | Gatekeeper      | NO           | gemma      |
| fridays   | Orchestrator    | YES          | ghost      |

## Agent API Endpoints (Local, Port 5050)
- `POST /api/agent/tickets`         — Create a ticket/proposal
- `GET  /api/agent/tickets`         — My tickets
- `GET  /api/agent/proposals`       — All pending proposals (any status)

## Communication Flow
1. Fridays heartbeat fires every 5 minutes
2. Fridays queries pending proposals
3. Fridays dispatches to correct agent or self-handles
4. Agent creates sub-proposals if more work is needed
5. Duck sanity-checks any closures

## Shared Files Convention
- `shared/COORDINATION.md`  — this file
- `shared/CURRENT_FOCUS.md` — what the swarm is working on right now
- `shared/BLOCKERS.md`      — anything blocking progress

## Escalation
If a local agent cannot resolve something, it creates a ticket tagged `escalate:paid`
and stops. The proposal stays `pending` until Ghost or a paid agent picks it up.
"""
    (SANDPIT_ROOT / 'shared' / 'COORDINATION.md').write_text(manifest)
    print('  ✓ shared/COORDINATION.md written')
    
    # Step 5: Summary
    print('\n[5] Verification...')
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM agent_capabilities WHERE granted=1").fetchone()[0]
    agents = conn.execute("SELECT DISTINCT agent_name FROM agent_capabilities WHERE granted=1").fetchall()
    conn.close()
    
    print(f'  ✓ {total} capability grants across {len(agents)} agents')
    print()
    for row in agents:
        a = row[0]
        conn = get_connection()
        caps = conn.execute("SELECT COUNT(*) FROM agent_capabilities WHERE agent_name=? AND granted=1", (a,)).fetchone()[0]
        conn.close()
        print(f'    {a:12s} → {caps} capabilities')
    
    print('\n══════════════════════════════════════════════')
    print(' BOOTSTRAP COMPLETE')
    print(' All agents have identity + capability grants')
    print(' Proposals logged and approved in ALM system')
    print('══════════════════════════════════════════════\n')


if __name__ == '__main__':
    run()
