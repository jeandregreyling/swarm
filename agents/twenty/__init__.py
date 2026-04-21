"""Agent 20 — Seven's Nervous System.

Local algorithm + orchestrator that observes the swarm, deliberates through
a council of seven senses, and surfaces PFV-gated suggestions.

NOT an LLM.  Deterministic Phase 1.  Feature-flagged.
"""

import os

AGENT_NAME = 'twenty'
AGENT_NUMBER = 20

# Kill switch — set AGENT20_ENABLED=false in env to disable entirely.
AGENT20_ENABLED = os.environ.get('AGENT20_ENABLED', 'true').lower() in ('1', 'true', 'yes')

# Cycle interval in seconds (3 minutes)
CYCLE_INTERVAL = int(os.environ.get('AGENT20_CYCLE_SECONDS', '180'))

# Identity — not a system prompt (Agent 20 isn't an LLM) but a self-description
# the council references when framing output.
IDENTITY = {
    'name': 'Twenty',
    'number': 20,
    'role': 'Nervous system — observes, deliberates, suggests',
    'constraints': [
        'Suggest only — never execute, create, or modify anything',
        'All output gated by PFV (Plausible, Feasible, Valuable)',
        'Confidence below 0.3 is never surfaced',
        'No LLM calls in Phase 1 — deterministic only',
        'Feature-flagged — AGENT20_ENABLED=false reverts to baseline',
        'Always be honest — never suppress, minimise, or spin bad news',
    ],
    'senses': [
        'Lookout (Sight)', 'Snoop (Hearing)', 'Spark (Touch)',
        'Skulk (Smell)', 'Keeper (Taste)', 'Sage (Balance)', 'Patrol (Gut)',
    ],
}
