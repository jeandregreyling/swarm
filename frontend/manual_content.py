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
    'app-center': {
        'title': 'App Center',
        'body': (
            'Build mobile, tablet, desktop, web, and game projects from one '
            'place. Each project records its kind (mobile/tablet/desktop/web/'
            'game), framework (flutter, react-native, tauri, electron, godot, '
            'unity, etc.), and one or more build targets (ios, android, '
            'windows, macos, linux, web, wasm, itch, steam).\n\n'
            'How to use:\n'
            '1) Click "New project", choose kind + framework, attach the '
            'targets you want to ship to.\n'
            '2) Hit "Build" on a target — the swarm queues a build via the '
            'shared media-jobs pipeline (ghost_coder picks it up by default).\n'
            '3) Per-target status updates as builds succeed or fail; the last '
            'asset id is shown next to the target.\n\n'
            'Archived projects do not accept new builds — set the project '
            'back to active first if you need to ship.'
        ),
    },
    'synth-board': {
        'title': 'Synth Board',
        'body': (
            'Modular sound design surface. Drag oscillators, samplers, '
            'filters, envelopes, LFOs, and effects (delay, reverb, eq, '
            'compressor) onto the board and wire them together. Up to 256 '
            'nodes and 1024 edges per board.\n\n'
            'Each save creates a revision so you can roll back without '
            'losing experimental routings. Boards plug into the same render '
            'pipeline as Media Center, so anything you patch can be rendered '
            'to a job and recorded as a Studio asset.'
        ),
    },
    'video-editor': {
        'title': 'Video Editor',
        'body': (
            'Multi-track timeline for video, audio, captions, effects, and '
            'overlays. Build the cut, then click "Render" to queue an export '
            'through the swarm media pipeline.\n\n'
            'If a render fails to enqueue you will see a 502 with the failure '
            'persisted as a render-job row — the job stays visible in the '
            'render history so you can diagnose, rather than disappearing.'
        ),
    },
    'orientation': {
        'title': 'First-run orientation',
        'body': (
            'Welcome to Fridays. Three things to find first:\n\n'
            '1) Help (the "?" icon on every tile and window header) opens this manual '
            'for the surface you are looking at. Same content, contextual entry.\n'
            '2) The Spotlight search bar at the top of the home screen launches any '
            'tile by name — type "chat", "studio", "media", "manual" and hit Enter.\n'
            '3) The taskbar at the bottom shows pinned tools and your active windows; '
            'click an orb to focus, drag tiles back from there.\n\n'
            'Tip: the Manual tile (book icon) opens this entire manual for browsing. '
            'You can dismiss this orientation card from the home tile and re-open it any '
            'time via "?" → Orientation.'
        ),
    },
}


def get_manual(key: str) -> dict | None:
    return MANUAL.get(key)


def list_manual_keys() -> list[str]:
    return sorted(MANUAL.keys())
