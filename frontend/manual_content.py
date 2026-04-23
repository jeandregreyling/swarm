"""manual_content.py — Single-source manual entries.

Every '?' tooltip / Window Help modal pulls from this one dict via
`/api/manual/<key>`. Update here and all tiles update.
"""

MANUAL: dict[str, dict[str, str]] = {
    'home': {
        'title': 'Fridays Home',
        'body': (
            'Landing dashboard for quick access. Open tiles to use specific swarm tools. '
            'Use Settings for theme and transparency controls.\n\n'
            'Quick chat relay guide:\n'
            '1) Agents can request another agent using @agent, AGENT:, or route/ask language.\n'
            '2) If Auto Relay is ON, detected relay routes are queued automatically.\n'
            '3) Route buttons still appear for manual control when you want to review first.\n'
            '4) Relay temporarily targets the requested agent for that turn.'
        ),
    },
    'chat': {
        'title': 'Chat Window',
        'body': (
            'Review conversation history, open full transcripts, and manage conversation titles. '
            'Use this for swarm dialogue and message context.\n\n'
            'How to relay:\n'
            '- Write @gemma (or another agent) followed by a request.\n'
            '- You can also use: "ask gemma ..." or "Gemma, ...".\n'
            '- Turn on Auto Relay in Chat controls for automatic chaining.\n'
            '- Keep Auto Relay off when you want explicit human approval per hop.'
        ),
    },
    'terminal': {
        'title': 'Fridays Native Terminal',
        'body': (
            'This is the Fridays native terminal, not your host shell. Commands are routed '
            'through API controls and ALM proposal governance, and are intended for swarm '
            'operations (services, health checks, diagnostics). For unrestricted host access, '
            'use an external terminal session.'
        ),
    },
    'files': {
        'title': 'Workspace Files',
        'body': (
            'Browse the workspace tree, preview files, run file-scoped terminal actions, and '
            'edit text files with ALM-governed save operations.'
        ),
    },
    'memory': {
        'title': 'Memory Browser',
        'body': (
            'Search and inspect swarm memory entries across agents. Use this to audit what was '
            'learned and when.'
        ),
    },
    'monitor': {
        'title': 'System Monitor',
        'body': 'View system health, queue depth, and ALM governance status in one place.',
    },
    'docs': {
        'title': 'Documentation Center',
        'body': (
            'Browse docs plus ALM history evidence. Use Docs tab for references and ALM '
            'History for proposal lifecycle traceability.'
        ),
    },
    'knowledge': {
        'title': 'Knowledge',
        'body': (
            'Files, docs, memory & library — the single knowledge surface for the swarm. '
            'Ingest sources, browse memories, and cross-link references.'
        ),
    },
    'skills': {
        'title': 'Skills',
        'body': 'See available skill commands and usage examples to trigger specific workflows.',
    },
    'tickets': {
        'title': 'Tickets',
        'body': (
            'Inspect ticket lifecycle details, notes, and outcomes. Use this for task-level '
            'operational tracking.'
        ),
    },
    'studio': {
        'title': 'Studio',
        'body': 'Proposal governance cockpit: review pending approvals and inspect full proposal history.',
    },
    'time-wizard': {
        'title': 'Vortex',
        'body': (
            'Decision timeline and architecture checkpoints. Use it to track state changes '
            'across sessions inside the Swarm boundary.'
        ),
    },
    'ghost-brief': {
        'title': 'Ghost Brief',
        'body': 'Summarized intelligence feed generated from current swarm state and recent activity.',
    },
    'agents': {
        'title': 'Agents',
        'body': (
            'Roster, skills, Local AI & nodes. Per-agent keep-warm, unload, and hard-kill '
            'controls live inside each agent detail pane.'
        ),
    },
    'trace': {
        'title': 'Trace',
        'body': (
            'Follow a conversation or job through every relay hop, queue, and agent response. '
            'Error and warning counts surface on the tile badge.'
        ),
    },
    'feeds': {
        'title': 'Feeds',
        'body': (
            'Connect social and developer feeds. Custom RSS/Atom URLs can be added under '
            'Custom Feeds; provider tiles toggle tracked state.'
        ),
    },
    'tasker': {
        'title': 'Tasker',
        'body': 'Scheduled jobs and recurring swarm tasks. Pause, resume, or trigger on demand.',
    },
}


def get_manual(key: str) -> dict | None:
    return MANUAL.get(key)


def list_manual_keys() -> list[str]:
    return sorted(MANUAL.keys())
