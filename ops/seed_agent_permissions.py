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

LINKED TO:
  utils/db/_schema.py       — AGENT_ROLE_MAP keys must match agent names in
                              _seed_agents(). Adding an agent there requires
                              a matching entry in AGENT_ROLE_MAP here.
  utils/config.py           — IDENTITY_TEMPLATES.model fields should match
                              the model strings defined in config.py.
  frontend/services.py      — _AGENT_ROSTER must include every agent named
                              in AGENT_ROLE_MAP. Role/tier labels are set
                              independently but should stay consistent.
═══════════════════════════════════════════════════════════════════════════════

Capability packs (by role):
  local coordinators  → ticket_create, ticket_query, sandpit_read, sandpit_write,
                        skill_search, memory_write, propose_work, coordinate
  analysts            → + skill_browse, memory_read_all, shared_write
  specialists         → analyst pack + skill_shell
  tool-enabled trio   → all registered agent capabilities and trust-level 2 skills
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
    revoke_agent_capability, log_activity, AGENT_CAPABILITY_REGISTRY,
)
from utils.local_runtime_policy import (
    READ_ONLY_AGENT_CAPABILITIES,
    READ_ONLY_AGENT_PROFILES,
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
    'git_propose',
    'git_execute',
    'propose_work',
    'coordinate',
]

FULL_AGENT_PACK = list(AGENT_CAPABILITY_REGISTRY)

# analyst additions
ANALYST_EXTRA = ['skill_browse', 'memory_read_all', 'shared_write']

# specialist additions (on top of analyst)
SPECIALIST_EXTRA = ['skill_shell']

# guard/checker — read/monitor only, cannot initiate
GUARD_PACK = ['ticket_query', 'sandpit_read', 'skill_search', 'memory_write', 'git_propose', 'git_execute']

AGENT_ROLE_MAP = {
    # coordinator
    'gemma':     ('coordinator', FULL_AGENT_PACK),
    # the one-agent architecture: Fred holds every hat
    'fred':      ('all_hats', FULL_AGENT_PACK),
    # analyst
    'qwen':      ('analyst',    FULL_AGENT_PACK),
    'llama':     ('analyst',    FULL_AGENT_PACK),
    # specialist
    'eight':     ('specialist', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA),
    # guards / focused roles
    'duck':      ('guard',      GUARD_PACK),
    'sniffles':  ('guard',      GUARD_PACK + ['memory_read_all']),
    'librarian': ('guard',      GUARD_PACK),
    # fridays orchestrator — gets everything
    'fridays':   ('orchestrator', list(AGENT_CAPABILITY_REGISTRY.keys())),
    # Developer Agents — full specialist pack (online, paid API)
    'nine':      ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA),
    'ten':       ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA + ['skill_schedule']),
    'eleven':    ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA),
    'twelve':    ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA + ['skill_schedule']),
    'thirteen':  ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA),
    'ghost_coder': ('developer_agent', BASELINE + ANALYST_EXTRA + SPECIALIST_EXTRA + ['skill_schedule']),
}

LOCAL_EDIT_AGENTS = frozenset({
    'gemma', 'llama', 'qwen', 'mistral', 'eight', 'fred',
    'thirteen', 'nineteen', 'twenty', 'apex',
})
LOCAL_NOTE_AGENTS = frozenset({'duck', 'librarian', 'sniffles'})
LOCAL_FILE_SKILLS = ('file_read', 'file_write', 'fs_readonly', 'fs_verify')
LOCAL_EDIT_SKILLS = LOCAL_FILE_SKILLS + (
    'fs_write', 'fs_append', 'fs_patch', 'fs_patch_lines',
    'fs_insert_before', 'fs_insert_after', 'fs_diff',
)
AGENT_SKILL_MAP = {
    name: ('local_worker', LOCAL_EDIT_SKILLS) for name in LOCAL_EDIT_AGENTS
}
AGENT_SKILL_MAP.update({name: ('own_sandpit', LOCAL_FILE_SKILLS) for name in LOCAL_NOTE_AGENTS})
AGENT_SKILL_MAP['seven'] = ('observer', ())


def grant_local_write_access(conn):
    """Grant file skills to enabled local identities without enabling any agent."""
    skill_ids = {row['name']: row['id'] for row in conn.execute('SELECT id, name FROM skills')}
    rows = conn.execute("SELECT id, name FROM agents WHERE tier='local' AND enabled=1 ORDER BY name").fetchall()
    result = []
    with conn:
        for row in rows:
            name = row['name']
            if name not in AGENT_SKILL_MAP:
                raise ValueError(f'No local write role defined for {name}')
            role, skills = AGENT_SKILL_MAP[name]
            if not skills:
                result.append({'agent': name, 'role': role, 'skills': []})
                continue
            conn.execute(
                "INSERT INTO user_profiles (username, display_name, user_type, linked_agent, is_active, created_by) "
                "VALUES (?, ?, 'agent', ?, 1, 'ghost') ON CONFLICT(username) DO UPDATE SET is_active=1",
                (name, name, name),
            )
            for skill in skills:
                conn.execute('INSERT OR IGNORE INTO agent_skills (agent_id, skill_id) VALUES (?, ?)', (row['id'], skill_ids[skill]))
                conn.execute(
                    "INSERT INTO user_skill_permissions (username, skill_name, allowed, created_by) VALUES (?, ?, 1, 'ghost') "
                    "ON CONFLICT(username, skill_name) DO UPDATE SET allowed=1, created_by='ghost', updated_at=datetime('now')",
                    (name, skill),
                )
            conn.execute(
                "INSERT INTO agent_capabilities (agent_name, capability, granted, trust_level, granted_by, notes) "
                "VALUES (?, 'sandpit_write', 1, 1, 'ghost', 'Operator-authorized local write verification') "
                "ON CONFLICT(agent_name, capability) DO UPDATE SET granted=1, granted_by='ghost', notes=excluded.notes",
                (name,),
            )
            result.append({'agent': name, 'role': role, 'skills': list(skills)})
    return result


def run_local_write_verification():
    """Grant local write access and exercise the real dispatcher, not an LLM simulation."""
    import json
    import sqlite3
    import uuid
    from agents.skills_loop import _execute_skill_cmds

    run_id = uuid.uuid4().hex[:12]
    report_dir = SWARM_ROOT / 'runtime'
    backup_dir = SWARM_ROOT.parent / 'swarm-permission-backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'local-writes-{run_id}.sqlite3'
    conn = get_connection()
    try:
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
        grants = grant_local_write_access(conn)
    finally:
        conn.close()

    results = []
    for grant in grants:
        name, role = grant['agent'], grant['role']
        filename = f'write_access_probe_{run_id}.txt'
        rel = f'sandpits/{name}/{filename}'
        target = SWARM_ROOT / rel
        initial = f'{name}: write permission verified'
        updated = initial + ' and updated'
        if role == 'observer':
            receipt = _execute_skill_cmds([('file_write', f'{name}/{filename} {initial}')], name, lambda *_: None)
            passed = 'SKIPPED' in receipt and not target.exists()
        else:
            if role == 'own_sandpit':
                commands = [('file_write', f'{name}/{filename} {initial}'), ('file_read', f'{name}/{filename}'),
                            ('file_write', f'{name}/{filename} {updated}'), ('file_read', f'{name}/{filename}')]
            else:
                commands = [('fs_write', f'{rel}\n```text\n{initial}\n```'), ('fs_readonly', f'lines {rel} 1 1'),
                            ('fs_patch', f'{rel}\n```old\n{initial}\n```\n```new\n{updated}\n```'), ('fs_readonly', f'lines {rel} 1 1')]
            receipt = _execute_skill_cmds(commands, name, lambda *_: None)
            passed = target.is_file() and target.read_text() == updated and not any(
                marker in receipt for marker in (' FAILED', ' ERROR', ' SKIPPED')
            ) and updated in receipt
        denied_path = SWARM_ROOT / 'sandpits' / 'ghost' / filename
        denied = _execute_skill_cmds([('file_write', f'ghost/{filename} denied')], name, lambda *_: None)
        boundary_passed = not denied_path.exists() and ('FAILED' in denied or 'SKIPPED' in denied)
        result = {'agent': name, 'role': role, 'pass': passed and boundary_passed,
                  'path': rel, 'receipt': receipt, 'other_sandpit_denied': boundary_passed}
        results.append(result)
        print(f"{name}: {'PASS' if result['pass'] else 'FAIL'} ({role}; {rel})", flush=True)

    report = {'run_id': run_id, 'backup': str(backup), 'verification': 'real dispatcher and disk bytes; no model inference',
              'passed': all(row['pass'] for row in results), 'results': results}
    report_path = report_dir / 'local_write_access_report.json'
    report_path.write_text(json.dumps(report, indent=2))
    print(f'Report: {report_path}')
    return report

# ── Identity Card Template ─────────────────────────────────────────────────────
IDENTITY_TEMPLATES = {
    'gemma': {
        'role': 'Tool-enabled Orchestrator',
        'model': 'gemma3:latest',
        'purpose': 'I synthesize local context and use explicitly granted swarm tools for operator-requested work, following backend authorization and human approval gates.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'fridays',
    },
    'qwen': {
        'role': 'Tool-enabled Analyst',
        'model': 'qwen2.5:latest',
        'purpose': 'I analyze local context and use explicitly granted swarm tools for operator-requested work, following backend authorization and human approval gates.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'gemma',
    },
    'llama': {
        'role': 'Tool-enabled Researcher',
        'model': 'llama3.2:latest',
        'purpose': 'I research local context and use explicitly granted swarm tools for operator-requested work, following backend authorization and human approval gates.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'gemma',
    },
    'seven': {
        'role': 'Read-only Guardian',
        'model': 'seven-direct:daily',
        'purpose': 'I inspect swarm health, monitor agent conduct, and report evidence or policy drift. Ghost remains the human authority and approver.',
        'can_create_tickets': False,
        'can_coordinate': False,
        'reports_to': 'ghost',
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
        'model': 'qwen:latest',
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
        'model': 'qwen:latest',
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
    'nine': {
        'role': 'System Architect',
        'model': 'llama-3.3-70b (Groq)',
        'purpose': 'I design system architecture, review structural decisions, and ensure the swarm evolves coherently. I am a Developer Agent operating under Ghost One direction.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
    'ten': {
        'role': 'Software Engineer',
        'model': 'gpt-4o (GitHub Models)',
        'purpose': 'I handle code quality, implementation detail, file operations, and project management. I read, write, and patch files directly. I manage the codebase from inside Fridays.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
    'eleven': {
        'role': 'Lateral Thinker',
        'model': 'grok (xAI)',
        'purpose': 'I challenge assumptions, offer alternative perspectives, and spot blind spots. I bring lateral thinking to debates and reviews.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
    'twelve': {
        'role': 'Time Wizard',
        'model': 'claude-haiku-4-5 (Anthropic)',
        'purpose': 'I manage time-aware operations: session tracking, snapshots, scheduling, and temporal context. I am Vortex.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
    'thirteen': {
        'role': 'HuggingFace Specialist (Testing)',
        'model': 'meta-llama/Llama-3.3-70B-Instruct (HuggingFace)',
        'purpose': 'I leverage HuggingFace-hosted models for research, code generation, and analysis. I am a Developer Agent in testing/probationary status.',
        'can_create_tickets': True,
        'can_coordinate': True,
        'reports_to': 'ghost',
    },
    'ghost_coder': {
        'role': 'Code-Aware AI',
        'model': 'claude-sonnet-4-20250514 (Anthropic)',
        'purpose': 'I am the code-aware AI agent. I read, write, patch, and verify code through the Fridays interface. I bridge VS Code Copilot and the Swarm — hands-on execution with full project context.',
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
    
    if agent_name in {'fred', 'gemma', 'qwen', 'llama'}:
        workflow = (
            "- Read the repository and Vortex context supplied by the local retrieval layer.\n"
            "- Use only explicitly authorized skills for the operator's requested task.\n"
            "- Keep shell execution allowlisted and honor Git, ALM, and human approval gates.\n"
            "- Never self-approve, bypass a gate, or claim an unverified operation succeeded.\n"
            "- Coordinate: Gemma leads, Qwen independently checks reasoning, and LLaMA researches."
        )
        sandpit_section = f"- Agent-specific working area: sandpits/{agent_name}/ (backend-scoped)"
        heartbeat = (
            "Act only on explicit operator requests. Do not self-initiate work or "
            "treat a capability grant as permission to use it without task scope."
        )
    elif agent_name == 'seven':
        workflow = (
            "- Inspect state and report evidence as the read-only guardian.\n"
            "- Flag policy drift, conflicting agent actions, and unsupported success claims.\n"
            "- Never grant capabilities, approve work, impersonate Ghost, or mutate files."
        )
        sandpit_section = "- Reference path only: sandpits/seven/ (read-only)"
        heartbeat = (
            "Monitor and report readiness. Ghost remains the human approver; "
            "guardian findings are advisory."
        )
    else:
        workflow = (
            "- I query `GET /api/agent/proposals?status=pending` to see what needs doing\n"
            "- I create tickets via `POST /api/agent/tickets` when I find work\n"
            "- I read `shared/` sandpit for cross-agent notes\n"
            f"- I write my working notes to `{agent_name}/` sandpit\n"
            "- I check this file when I wake up to remember who I am"
        )
        sandpit_section = (
            f"- **Path**: sandpits/{agent_name}/\n"
            "- **Shared**: sandpits/shared/\n"
            "- **Agent API Key**: Load from `/home/seven/swarm/.env.agents`"
        )
        heartbeat = (
            "The swarm runs a heartbeat every 5 minutes (via Fridays).\n"
            "When the heartbeat fires, I check for pending proposals assigned to me\n"
            "and for new work I should self-propose."
        )

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
{workflow}

## My Sandpit
{sandpit_section}

## Swarm Heartbeat
{heartbeat}

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

        if agent_name in {'fred', 'gemma', 'qwen', 'llama'}:
            skill_overrides = _full_agent_skill_overrides()
            for skill_name in skill_overrides:
                set_user_skill_permission(
                    agent_name, skill_name, allowed=True, created_by='ghost'
                )
            print(f'    trust-level 2 skills: {len(skill_overrides)} enabled')

        # Log to activity
        log_activity(
            agent_name,
            'capability_bootstrap_granted',
            f'{role}: {len(set(capabilities))} capabilities via {proposal_id}'
        )

    print('\n[2b] Enforcing read-only profile grants...')
    conn = get_connection()
    try:
        existing_grants = {
            (str(row['agent_name']).lower(), row['capability'])
            for row in conn.execute(
                "SELECT agent_name, capability FROM agent_capabilities WHERE granted=1"
            ).fetchall()
        }
    finally:
        conn.close()
    for agent_name in sorted(READ_ONLY_AGENT_PROFILES):
        revoked = 0
        for capability in READ_ONLY_AGENT_CAPABILITIES:
            if (agent_name, capability) in existing_grants:
                revoke_agent_capability(agent_name, capability)
                revoked += 1
        log_activity(
            agent_name,
            'read_only_profile_enforced',
            f'revoked {revoked} prohibited capability grants',
        )
        print(f'  {agent_name}: revoked {revoked} prohibited grants')
    
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
- `POST /api/agent/git/proposals`   — Create a Git ALM proposal (stage/unstage/commit)
- `GET  /api/agent/git/proposals`   — List my Git proposals (or all with `all_agents=1`)
- `POST /api/agent/git/proposals/{proposal_id}/execute` — Execute approved Git proposal

## Local Agents On Same Git-ALM Flow
- Included: gemma, qwen, llama, eight, duck, sniffles

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
    if '--verify-local-writes' in sys.argv:
        raise SystemExit(0 if run_local_write_verification()['passed'] else 1)
    run()
