"""
fridays/orchestrator.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Fridays Orchestrator — the organic heartbeat brain.

This is what makes the swarm self-directing. Every HEARTBEAT_SECONDS:

  1. Read the pending proposal queue (all agents)
  2. For each pending proposal:
     - Identify the right agent to handle it
     - Dispatch (write to their sandpit + log)
     - Mark as dispatched
  3. Give each capable agent a "think cycle" to self-propose new work
  4. Check for stale proposals (> STALE_MINUTES) and escalate
  5. Update shared/CURRENT_FOCUS.md with what the swarm is doing

Local agents do NOT call paid APIs during the heartbeat.
Paid API escalation only happens when a ticket is tagged 'escalate:paid'.

Run as a standalone service:
  python3 fridays/orchestrator.py

Or import and call run_forever() from within a service.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))
sys.path.insert(0, str(SWARM_ROOT / 'utils'))
sys.path.insert(0, str(SWARM_ROOT / 'core' / 'pipeline'))

logger = logging.getLogger('seven.fridays.orchestrator')
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

HEARTBEAT_SECONDS = 300       # 5 minutes
STALE_MINUTES     = 60        # escalate proposals older than this
THINK_CYCLE_LIMIT = 3         # max new proposals per agent per heartbeat
SANDPIT_ROOT      = SWARM_ROOT / 'sandpits'
ENV_AGENTS_FILE   = SWARM_ROOT / '.env.agents'

# ── Which agents think proactively each heartbeat ─────────────────────────────
THINKING_AGENTS = ['gemma', 'qwen', 'llama', 'eight']

# ── Agent dispatch routing ─────────────────────────────────────────────────────
# Maps capability/tag patterns to agent names
DISPATCH_ROUTES = {
    'sap':       'eight',
    'hcm':       'eight',
    'analysis':  'qwen',
    'analyse':   'qwen',
    'research':  'llama',
    'search':    'llama',
    'route':     'gemma',
    'synthesis': 'gemma',
    'coordinate':'gemma',
    'audit':     'sniffles',
    'memory':    'sniffles',
}


def _load_agent_key():
    """Load the AGENT_API_KEY from .env.agents file or environment."""
    key = os.environ.get('AGENT_API_KEY', '').strip()
    if key:
        return key
    if ENV_AGENTS_FILE.exists():
        for line in ENV_AGENTS_FILE.read_text().splitlines():
            if line.startswith('AGENT_API_KEY='):
                return line.split('=', 1)[1].strip()
    return ''


def _agent_api(method, path, agent_id='fridays', data=None):
    """Make an internal HTTP call to the agent API on localhost:5050."""
    try:
        import urllib.request
        import urllib.error
        key = _load_agent_key()
        if not key:
            return None, 'AGENT_API_KEY not found'
        
        url = f'http://localhost:5050{path}'
        body = json.dumps(data or {}).encode() if data else b''
        req = urllib.request.Request(
            url,
            data=body if method == 'POST' else None,
            method=method,
            headers={
                'Content-Type': 'application/json',
                'X-Agent-Key': key,
                'X-Agent-Id': agent_id,
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()), None
    except Exception as e:
        return None, str(e)


def _get_pending_proposals():
    """Fetch all pending proposals from the API."""
    result, err = _agent_api('GET', '/api/agent/proposals?status=pending&limit=100')
    if err or not result:
        return []
    return result.get('proposals', [])


def _naive_route(proposal):
    """
    Look at a proposal's title/description and decide which agent should handle it.
    Uses keyword-based routing — same primitive Gemma uses, but local-only.
    """
    text = (proposal.get('title', '') + ' ' + proposal.get('description', '')).lower()
    for keyword, agent in DISPATCH_ROUTES.items():
        if keyword in text:
            return agent
    # Default: the agent that created it handles it
    return proposal.get('agent', 'gemma')


def _write_dispatch(agent_name, proposal):
    """Write a dispatch notice to the agent's sandpit for pickup on next think cycle."""
    sandpit = SANDPIT_ROOT / agent_name
    sandpit.mkdir(parents=True, exist_ok=True)
    
    dispatch_file = sandpit / 'DISPATCHED_WORK.md'
    
    existing = dispatch_file.read_text() if dispatch_file.exists() else ''
    new_entry = (
        f"\n## [{datetime.now().strftime('%H:%M')}] {proposal.get('proposal_id')}\n"
        f"**Title**: {proposal.get('title')}\n"
        f"**From**: {proposal.get('agent')}\n"
        f"**Description**: {proposal.get('description', '')[:300]}\n"
        f"**Status**: dispatched\n"
    )
    dispatch_file.write_text(existing + new_entry)


def _think_cycle(agent_name):
    """
    Give a local agent a "think cycle" — ask if it has new work to propose.
    
    This is a lightweight local check: read the agent's sandpit for a THINK.md file.
    Agents write self-proposals to their sandpit as THINK.md; we pick them up here,
    create tickets for them, then clear the file.
    
    THINK.md format (agent writes this):
    TITLE: short description
    DESCRIPTION: what I want to do
    PRIORITY: 1-10
    ---
    TITLE: another proposal
    ...
    """
    think_file = SANDPIT_ROOT / agent_name / 'THINK.md'
    if not think_file.exists():
        return 0
    
    content = think_file.read_text().strip()
    if not content:
        return 0
    
    count = 0
    blocks = content.split('---')
    proposals_created = []
    
    for block in blocks:
        if count >= THINK_CYCLE_LIMIT:
            break
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        title = ''
        desc = ''
        priority = 5
        for line in lines:
            if line.startswith('TITLE:'):
                title = line[6:].strip()
            elif line.startswith('DESCRIPTION:'):
                desc = line[12:].strip()
            elif line.startswith('PRIORITY:'):
                try:
                    priority = int(line[9:].strip())
                except ValueError:
                    pass
        
        if title:
            result, err = _agent_api('POST', '/api/agent/tickets', agent_id=agent_name, data={
                'title': title[:200],
                'description': desc[:500],
                'priority': priority,
            })
            if result and result.get('ok'):
                proposals_created.append(result.get('proposal_id'))
                count += 1
                logger.info(f'[Fridays] Think cycle: {agent_name} → {result.get("proposal_id")}: {title[:60]}')
    
    if proposals_created:
        # Clear the THINK.md so it isn't re-processed
        think_file.write_text(f'# Processed at {datetime.now().isoformat()}\n# {len(proposals_created)} proposals created: {proposals_created}\n')
    
    return count


def _update_focus_file(stats):
    """Update shared/CURRENT_FOCUS.md with what the swarm is actively working on."""
    focus_file = SANDPIT_ROOT / 'shared' / 'CURRENT_FOCUS.md'
    (SANDPIT_ROOT / 'shared').mkdir(parents=True, exist_ok=True)
    
    content = (
        f"# SWARM CURRENT FOCUS\n"
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Heartbeat Stats\n"
        f"- Pending proposals processed: {stats.get('dispatched', 0)}\n"
        f"- Think-cycle proposals created: {stats.get('self_proposed', 0)}\n"
        f"- Stale proposals escalated: {stats.get('escalated', 0)}\n"
        f"- Agents active this cycle: {', '.join(stats.get('active_agents', []))}\n\n"
        f"## Next Heartbeat\n"
        f"~{HEARTBEAT_SECONDS // 60} minutes\n\n"
        f"## How To Add Work\n"
        f"Any agent can write to their sandpit THINK.md:\n"
        f"```\n"
        f"TITLE: what I want to do\n"
        f"DESCRIPTION: why and how\n"
        f"PRIORITY: 5\n"
        f"---\n"
        f"```\n"
        f"Fridays will pick it up on the next heartbeat and create a proposal.\n"
    )
    focus_file.write_text(content)


def _check_stale_proposals(proposals):
    """Find and escalate very old pending proposals."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)
    escalated = []
    
    for p in proposals:
        try:
            created = datetime.fromisoformat(p.get('created_at', '').replace(' ', 'T'))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < threshold:
                escalated.append(p['proposal_id'])
                # Write to shared log
                stale_file = SANDPIT_ROOT / 'shared' / 'STALE_PROPOSALS.md'
                existing = stale_file.read_text() if stale_file.exists() else '# Stale Proposals\n'
                stale_file.write_text(
                    existing +
                    f"\n- [{datetime.now().strftime('%H:%M')}] {p['proposal_id']} ({p['agent']}): {p.get('title', '')[:80]}"
                )
        except Exception:
            pass
    
    return escalated


def run_heartbeat():
    """Execute one full heartbeat cycle. Returns a stats dict."""
    stats = {'dispatched': 0, 'self_proposed': 0, 'escalated': 0, 'active_agents': []}
    
    logger.info('[Fridays] ── Heartbeat ──────────────────────────')
    
    try:
        from database import log_activity
        log_activity('fridays', 'heartbeat_start', 'organic loop cycle started')
    except Exception:
        pass
    
    # 1. Get pending proposals
    proposals = _get_pending_proposals()
    logger.info(f'[Fridays] {len(proposals)} pending proposals in queue')
    
    # 2. Dispatch pending proposals to agents
    for proposal in proposals:
        target_agent = _naive_route(proposal)
        _write_dispatch(target_agent, proposal)
        stats['dispatched'] += 1
        if target_agent not in stats['active_agents']:
            stats['active_agents'].append(target_agent)
        logger.info(f'[Fridays] Dispatched {proposal["proposal_id"]} → {target_agent}')
    
    # 3. Think cycles for capable agents
    for agent_name in THINKING_AGENTS:
        n = _think_cycle(agent_name)
        if n > 0:
            stats['self_proposed'] += n
            if agent_name not in stats['active_agents']:
                stats['active_agents'].append(agent_name)
    
    # 4. Check stale proposals
    stale = _check_stale_proposals(proposals)
    stats['escalated'] = len(stale)
    if stale:
        logger.warning(f'[Fridays] {len(stale)} stale proposals: {stale}')
    
    # 5. Update focus file
    _update_focus_file(stats)
    
    # 6. Log completion
    try:
        from database import log_activity
        log_activity('fridays', 'heartbeat_complete',
                     f'dispatched={stats["dispatched"]} self_proposed={stats["self_proposed"]} escalated={stats["escalated"]}')
    except Exception:
        pass
    
    logger.info(f'[Fridays] Heartbeat done — dispatched={stats["dispatched"]}, self_proposed={stats["self_proposed"]}')
    return stats


def run_forever():
    """Run the orchestrator heartbeat loop indefinitely."""
    logger.info('[Fridays] Orchestrator starting — organic swarm heartbeat')
    logger.info(f'[Fridays] Heartbeat every {HEARTBEAT_SECONDS}s | {len(THINKING_AGENTS)} thinking agents')
    
    while True:
        try:
            run_heartbeat()
        except KeyboardInterrupt:
            logger.info('[Fridays] Graceful shutdown')
            break
        except Exception as e:
            logger.error(f'[Fridays] Heartbeat error: {e}', exc_info=True)
        
        time.sleep(HEARTBEAT_SECONDS)


if __name__ == '__main__':
    run_forever()
