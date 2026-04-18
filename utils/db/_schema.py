"""
db._schema — Schema definition, initialisation, migrations, and seeding.

LINKED TO:
  utils/config.py           — reads all *_SYSTEM_PROMPT constants from there
                              and writes them into agents.system_prompt.
                              config.py is the source of truth for prompts.
  frontend/services.py      — _AGENT_ROSTER must list the same agents as the
                              roster seeded in _seed_agents() here. If you add
                              an agent row here, add it to services.py too.
  ops/seed_agent_permissions.py — AGENT_ROLE_MAP keys must match agent names
                              seeded in _seed_agents() here.
"""
from ._connection import get_connection, logger

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,
    temperature REAL DEFAULT 0.3,
    role TEXT,
    roles TEXT, -- JSON array of roles for multi-role support
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    source TEXT DEFAULT 'email',
    sender TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES conversations(id),
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'response',
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'unknown',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 5,
    source TEXT DEFAULT 'unknown',
    verified INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_llama (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'llama',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 5,
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_qwen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'qwen',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 5,
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_gemma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'gemma',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    source TEXT DEFAULT 'unknown',
    importance INTEGER DEFAULT 9,
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_eight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'eight',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 7,
    source TEXT DEFAULT 'learned',
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_nine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'nine',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 7,
    source TEXT DEFAULT 'session',
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_ten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'ten',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 7,
    source TEXT DEFAULT 'session',
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_addr TEXT NOT NULL,
    subject TEXT NOT NULL,
    question TEXT NOT NULL,
    tags TEXT DEFAULT '',
    priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'queued',
    source_type TEXT DEFAULT 'email',
    agent TEXT DEFAULT '',
    system_snapshot TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT UNIQUE NOT NULL,
    queue_id INTEGER,
    sender_email TEXT NOT NULL,
    question TEXT NOT NULL,
    tags TEXT DEFAULT '',
    routing_decision TEXT DEFAULT '',
    agents_assigned TEXT DEFAULT '',
    mode TEXT DEFAULT '',
    is_identity INTEGER DEFAULT 0,
    needs_web INTEGER DEFAULT 0,
    gemma_initial TEXT DEFAULT '',
    final_answer TEXT,
    web_results TEXT DEFAULT '',
    status TEXT DEFAULT 'open',
    gemma_routing TEXT DEFAULT '',
    duck_result TEXT DEFAULT '',
    duck_visited INTEGER DEFAULT 0,
    sniffles_result TEXT DEFAULT '',
    sniffles_checked INTEGER DEFAULT 0,
    email_message_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS ticket_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER REFERENCES tickets(id),
    agent TEXT NOT NULL,
    note_type TEXT DEFAULT 'response',
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.8,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS duck_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    ticket_number TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    result TEXT NOT NULL,
    reason TEXT DEFAULT '',
    agent_reactions TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sniffer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    entry_id INTEGER,
    result TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    audited_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sniffer_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    description TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    escalation_level TEXT DEFAULT 'bark',
    first_seen TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now')),
    reported INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trusted_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    added_by TEXT NOT NULL,
    notes TEXT DEFAULT '',
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS moderators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notification_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    added_by TEXT DEFAULT 'ghost',
    notes TEXT DEFAULT '',
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pending_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_addr TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    message_id TEXT DEFAULT '',
    received_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS ghost_circle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    ticket_ref TEXT DEFAULT '',
    severity TEXT DEFAULT 'info',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS claude_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    ticket_number TEXT NOT NULL,
    problem_type TEXT DEFAULT '',
    query_sent TEXT NOT NULL,
    response TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS system_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT DEFAULT (datetime('now')),
    ram_total_gb REAL,
    ram_used_gb REAL,
    ram_available_gb REAL,
    cpu_percent REAL,
    swap_used_gb REAL,
    active_model TEXT DEFAULT '',
    consultations_today INTEGER DEFAULT 0,
    last_consultation TEXT,
    cpu_temp_c REAL
);
CREATE TABLE IF NOT EXISTS project_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_name TEXT NOT NULL,
    content TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sandpit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    operation TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    reason TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS trusted_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    channel TEXT DEFAULT 'email',
    added_by TEXT NOT NULL,
    notes TEXT DEFAULT '',
    added_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS snoozed_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number TEXT NOT NULL,
    sender_email TEXT NOT NULL,
    wake_at TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    fired INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS approval_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    action TEXT NOT NULL,
    target_email TEXT NOT NULL DEFAULT '',
    created_by TEXT DEFAULT 'system',
    created_at TEXT DEFAULT (datetime('now')),
    used_at TEXT,
    status TEXT DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_grok (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'grok',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 7,
    source TEXT DEFAULT 'session',
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS memory_twelve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT DEFAULT 'twelve',
    subject TEXT DEFAULT '',
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    importance INTEGER DEFAULT 7,
    source TEXT DEFAULT 'session',
    ticket_ref TEXT DEFAULT '',
    archived INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    agent TEXT NOT NULL,
    component TEXT DEFAULT '',
    proposal_file TEXT DEFAULT '',
    decision TEXT NOT NULL,
    reasoning TEXT DEFAULT '',
    test_status TEXT DEFAULT 'PENDING',
    commit_hash TEXT DEFAULT '',
    checkpoint_id INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    archived INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS time_machine (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    agent TEXT NOT NULL,
    file_path TEXT NOT NULL,
    before_code TEXT DEFAULT '',
    after_code TEXT NOT NULL,
    before_hash TEXT DEFAULT '',
    after_hash TEXT DEFAULT '',
    test_results TEXT DEFAULT '',
    decision_id INTEGER DEFAULT 0,
    commit_hash TEXT DEFAULT '',
    outcome TEXT DEFAULT 'success',
    is_rollback_point INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS time_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT '',
    event_type TEXT NOT NULL,
    agent TEXT NOT NULL,
    action TEXT DEFAULT '',
    target TEXT DEFAULT '',
    state_hash TEXT DEFAULT '',
    details TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS time_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    timestamp TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    phase TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS time_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_name TEXT UNIQUE NOT NULL,
    timestamp TEXT DEFAULT '',
    description TEXT DEFAULT '',
    agent TEXT NOT NULL,
    full_state TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS daily_checkpoint (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    codebase_hash TEXT,
    memory_state TEXT,
    decisions_count INTEGER DEFAULT 0,
    description TEXT,
    is_stable INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ghost_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    brief_type TEXT DEFAULT 'on_demand',
    content TEXT NOT NULL,
    raw_data_snapshot TEXT,
    tokens_used INTEGER DEFAULT 0,
    triggered_by TEXT DEFAULT 'system'
);
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_data TEXT NOT NULL,
    last_run TEXT,
    next_run TEXT,
    enabled INTEGER DEFAULT 1,
    created_by TEXT DEFAULT 'ghost',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS work_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT UNIQUE NOT NULL,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    proposal_file TEXT DEFAULT '',
    ticket_number TEXT DEFAULT '',
    queue_id INTEGER DEFAULT 0,
    current_stage TEXT DEFAULT 'FRIDAYS',
    source_node TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    user_type TEXT DEFAULT 'human',
    linked_agent TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    can_proxy INTEGER DEFAULT 0,
    created_by TEXT DEFAULT 'system',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS user_skill_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    allowed INTEGER DEFAULT 1,
    created_by TEXT DEFAULT 'ghost',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(username, skill_name)
);
-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory(importance);
CREATE INDEX IF NOT EXISTS idx_work_proposals_agent ON work_proposals(agent);
CREATE INDEX IF NOT EXISTS idx_work_proposals_status ON work_proposals(status);
CREATE INDEX IF NOT EXISTS idx_work_proposals_status_agent ON work_proposals(status, agent);
CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(is_active);
CREATE INDEX IF NOT EXISTS idx_user_skill_permissions_user ON user_skill_permissions(username);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS agent_skills (
    agent_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    PRIMARY KEY (agent_id, skill_id),
    FOREIGN KEY (agent_id) REFERENCES agents(id),
    FOREIGN KEY (skill_id) REFERENCES skills(id)
);

-- Future: profiles and profile_skills tables for grouping skills

CREATE TABLE IF NOT EXISTS conv_timeline (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id     INTEGER NOT NULL,
    agent       TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL,
    -- event_type values:
    --   stage       — emit_fn stage label (e.g. "running requested skills")
    --   skill_call  — SKILL command sent (name + args preview)
    --   skill_result— SKILL output (ok/fail + preview)
    --   response    — intermediate LLM text with SKILL commands (reasoning visible)
    --   final       — final answer text
    --   proposal    — proposal state change (pending→approved→in_progress→done)
    --   health      — health_check result at alm_complete time
    payload     TEXT NOT NULL DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_timeline_conv ON conv_timeline (conv_id, id);

-- Shared swarm knowledge base (A.3.1)
CREATE TABLE IF NOT EXISTS swarm_knowledge (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_agent    TEXT NOT NULL DEFAULT '',
    source_proposal_id TEXT DEFAULT '',
    category        TEXT NOT NULL DEFAULT 'fact',
    importance      INTEGER DEFAULT 5,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_swarm_knowledge_cat ON swarm_knowledge (category);
CREATE INDEX IF NOT EXISTS idx_swarm_knowledge_agent ON swarm_knowledge (source_agent);

-- Swarm event broadcast table (A.3.4)
CREATE TABLE IF NOT EXISTS swarm_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '',
    source_agent TEXT NOT NULL DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_swarm_events_type ON swarm_events (event_type, created_at);

-- Tracks which agents have consumed each event (A.3.4)
CREATE TABLE IF NOT EXISTS swarm_event_acks (
    event_id    INTEGER NOT NULL,
    agent       TEXT NOT NULL,
    acked_at    TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (event_id, agent),
    FOREIGN KEY (event_id) REFERENCES swarm_events(id)
);

-- Internal message bus (A.4.2)
CREATE TABLE IF NOT EXISTS swarm_bus (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    source_service  TEXT NOT NULL DEFAULT 'local',
    created_at      TEXT DEFAULT (datetime('now')),
    consumed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_swarm_bus_topic ON swarm_bus (topic, created_at);
CREATE INDEX IF NOT EXISTS idx_swarm_bus_unconsumed ON swarm_bus (consumed_at) WHERE consumed_at IS NULL;

-- Node registry (A.4.5)
CREATE TABLE IF NOT EXISTS swarm_nodes (
    node_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL DEFAULT '',
    url             TEXT NOT NULL DEFAULT '',
    api_key_hash    TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'contributor',
    agents_json     TEXT NOT NULL DEFAULT '[]',
    capabilities    TEXT NOT NULL DEFAULT '[]',
    registered_at   TEXT DEFAULT (datetime('now')),
    last_seen       TEXT DEFAULT (datetime('now'))
);

-- Federated skill registry (D.2.1)
CREATE TABLE IF NOT EXISTS node_skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL,
    skill_name      TEXT NOT NULL,
    trust_level     INTEGER DEFAULT 0,
    description     TEXT DEFAULT '',
    available       INTEGER DEFAULT 1,
    last_seen       TEXT DEFAULT (datetime('now')),
    UNIQUE(node_id, skill_name)
);
CREATE INDEX IF NOT EXISTS idx_node_skills_name ON node_skills(skill_name);

-- Node config overrides (D.4.2)
CREATE TABLE IF NOT EXISTS node_config (
    key         TEXT PRIMARY KEY,
    value       TEXT DEFAULT '',
    node_id     TEXT DEFAULT '',
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Research sessions (B.1.1)
CREATE TABLE IF NOT EXISTS research_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    topic               TEXT NOT NULL,
    depth               TEXT NOT NULL DEFAULT 'standard',
    status              TEXT NOT NULL DEFAULT 'planning',
    phases_json         TEXT NOT NULL DEFAULT '[]',
    linked_proposal_id  TEXT DEFAULT '',
    requesting_agent    TEXT NOT NULL DEFAULT 'user',
    summary             TEXT DEFAULT '',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_research_sessions_status ON research_sessions (status);

-- Research evidence (B.1.1)
CREATE TABLE IF NOT EXISTS research_evidence (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL REFERENCES research_sessions(id),
    source_url          TEXT NOT NULL DEFAULT '',
    source_type         TEXT NOT NULL DEFAULT 'web',
    title               TEXT NOT NULL DEFAULT '',
    snippet             TEXT NOT NULL DEFAULT '',
    confidence          REAL DEFAULT 0.5,
    collecting_agent    TEXT NOT NULL DEFAULT '',
    snippet_hash        TEXT NOT NULL DEFAULT '',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_research_evidence_session ON research_evidence (session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_evidence_dedup ON research_evidence (session_id, source_url, snippet_hash);

-- Tool builds (C.1.1)
CREATE TABLE IF NOT EXISTS tool_builds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id         TEXT DEFAULT '',
    tool_type           TEXT NOT NULL DEFAULT 'script',
    tool_name           TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    entry_path          TEXT DEFAULT '',
    test_path           TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'scaffolded',
    test_output         TEXT DEFAULT '',
    building_agent      TEXT NOT NULL DEFAULT '',
    language            TEXT NOT NULL DEFAULT 'python',
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tool_builds_agent_status ON tool_builds (building_agent, status);
"""


def initialise_database():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate_schema(conn)
    conn.close()
    _seed_agents()
    _seed_moderator()
    _seed_user_profiles()
    _seed_skills()
    _seed_agent_skills()


def _seed_agent_skills():
    """Backfill agent_skills for each agent using AGENT_ROLE_MAP from ops/seed_agent_permissions.py."""
    import importlib.util
    import os
    perm_py = os.path.join(os.path.dirname(__file__), '../../ops/seed_agent_permissions.py')
    spec = importlib.util.spec_from_file_location('ops.seed_agent_permissions', perm_py)
    perm_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perm_mod)
    AGENT_ROLE_MAP = perm_mod.AGENT_ROLE_MAP
    conn = get_connection()
    # Build skill name to id map
    skill_rows = conn.execute('SELECT id, name FROM skills').fetchall()
    skill_name_to_id = {row['name']: row['id'] for row in skill_rows}
    # Build agent name to id map
    agent_rows = conn.execute('SELECT id, name FROM agents').fetchall()
    agent_name_to_id = {row['name'].lower(): row['id'] for row in agent_rows}
    for agent_name, (_role, skills) in AGENT_ROLE_MAP.items():
        agent_id = agent_name_to_id.get(agent_name.lower())
        if not agent_id:
            continue
        for skill in skills:
            skill_id = skill_name_to_id.get(skill)
            if not skill_id:
                continue
            try:
                conn.execute('INSERT OR IGNORE INTO agent_skills (agent_id, skill_id) VALUES (?, ?)', (agent_id, skill_id))
            except Exception as e:
                print(f'[agent_skills seed] Failed to insert {agent_name}:{skill}: {e}')
    conn.commit()
    conn.close()


def _seed_skills():
    """Seed the skills table with all skills from fridays/skills.py REGISTRY."""
    import importlib.util
    import os
    skills_py = os.path.join(os.path.dirname(__file__), '../../fridays/skills.py')
    spec = importlib.util.spec_from_file_location('fridays.skills', skills_py)
    skills_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skills_mod)
    skills = skills_mod.REGISTRY
    conn = get_connection()
    for name, meta in skills.items():
        desc = meta.get('description', '')
        try:
            conn.execute('INSERT OR IGNORE INTO skills (name, description) VALUES (?, ?)', (name, desc))
        except Exception as e:
            print(f'[skills seed] Failed to insert {name}: {e}')
    conn.commit()
    conn.close()


def _migrate_schema(conn=None):
    # Add columns/tables to existing deployments that were added after initial deploy.
    _close = conn is None
    if _close:
        conn = get_connection()
    # New columns on tickets
    ticket_cols = {row[1] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()}
    if 'email_message_id' not in ticket_cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN email_message_id TEXT DEFAULT ''")
        conn.commit()
    if 'conv_id' not in ticket_cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN conv_id INTEGER DEFAULT NULL")
        conn.commit()
    if 'channel' not in ticket_cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN channel TEXT DEFAULT 'email'")
        conn.commit()
    # New columns on queue
    queue_cols = {row[1] for row in conn.execute("PRAGMA table_info(queue)").fetchall()}
    if 'channel' not in queue_cols:
        conn.execute("ALTER TABLE queue ADD COLUMN channel TEXT DEFAULT 'email'")
        conn.commit()
    # New columns on messages
    message_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if 'tokens_used' not in message_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN tokens_used INTEGER DEFAULT 0")
        conn.commit()
    # New tables
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    # Add channel column to trusted_domains if missing
    if 'trusted_domains' in tables:
        domain_cols = {row[1] for row in conn.execute("PRAGMA table_info(trusted_domains)").fetchall()}
        if 'channel' not in domain_cols:
            conn.execute("ALTER TABLE trusted_domains ADD COLUMN channel TEXT DEFAULT 'email'")
            conn.commit()
    if 'trusted_domains' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS trusted_domains (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT UNIQUE NOT NULL, channel TEXT DEFAULT "email", added_by TEXT NOT NULL, notes TEXT DEFAULT "", added_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    if 'snoozed_tickets' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS snoozed_tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_number TEXT NOT NULL, sender_email TEXT NOT NULL, wake_at TEXT NOT NULL, note TEXT DEFAULT "", created_at TEXT DEFAULT (datetime("now")), fired INTEGER DEFAULT 0)')
        conn.commit()
    if 'project_docs' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS project_docs (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_name TEXT NOT NULL, content TEXT DEFAULT "", tags TEXT DEFAULT "all", created_at TEXT DEFAULT (datetime("now")), updated_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    else:
        # Add tags column to existing project_docs if missing
        doc_cols = {row[1] for row in conn.execute('PRAGMA table_info(project_docs)').fetchall()}
        if 'tags' not in doc_cols:
            conn.execute("ALTER TABLE project_docs ADD COLUMN tags TEXT DEFAULT 'all'")
            conn.commit()
    if 'memory_nine' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS memory_nine (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT "nine", subject TEXT DEFAULT "", content TEXT NOT NULL, tags TEXT DEFAULT "", importance INTEGER DEFAULT 7, source TEXT DEFAULT "session", ticket_ref TEXT DEFAULT "", archived INTEGER DEFAULT 0, created_at TEXT)')
        conn.commit()
    if 'memory_ten' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS memory_ten (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT "ten", subject TEXT DEFAULT "", content TEXT NOT NULL, tags TEXT DEFAULT "", importance INTEGER DEFAULT 7, source TEXT DEFAULT "session", ticket_ref TEXT DEFAULT "", archived INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    if 'approval_tokens' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS approval_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE NOT NULL, action TEXT NOT NULL, target_email TEXT NOT NULL DEFAULT "", created_by TEXT DEFAULT "system", created_at TEXT DEFAULT (datetime("now")), used_at TEXT, status TEXT DEFAULT "pending")')
        conn.commit()
    if 'debates' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS debates (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, initiator TEXT DEFAULT "nine", status TEXT DEFAULT "open", rounds INTEGER DEFAULT 0, consensus TEXT DEFAULT "", proposal_id INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")), closed_at TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS debate_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, debate_id INTEGER NOT NULL, agent TEXT NOT NULL, position TEXT NOT NULL, round INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    if 'file_writes' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS file_writes (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, description TEXT DEFAULT "", previous_content TEXT DEFAULT "", new_content TEXT NOT NULL, applied_by TEXT DEFAULT "ghost", created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    if 'user_profiles' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS user_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, display_name TEXT DEFAULT "", user_type TEXT DEFAULT "human", linked_agent TEXT DEFAULT "", is_active INTEGER DEFAULT 1, can_proxy INTEGER DEFAULT 0, created_by TEXT DEFAULT "system", created_at TEXT DEFAULT (datetime("now")), updated_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    if 'user_skill_permissions' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS user_skill_permissions (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, skill_name TEXT NOT NULL, allowed INTEGER DEFAULT 1, created_by TEXT DEFAULT "ghost", created_at TEXT DEFAULT (datetime("now")), updated_at TEXT DEFAULT (datetime("now")), UNIQUE(username, skill_name))')
        conn.commit()
    # memory_twelve: bootstrap test created it with a different schema; add missing columns
    if 'memory_twelve' in tables:
        mt_cols = {row[1] for row in conn.execute('PRAGMA table_info(memory_twelve)').fetchall()}
        if 'subject' not in mt_cols:
            conn.execute("ALTER TABLE memory_twelve ADD COLUMN subject TEXT DEFAULT ''")
            conn.commit()
        if 'source' not in mt_cols:
            conn.execute("ALTER TABLE memory_twelve ADD COLUMN source TEXT DEFAULT 'session'")
            conn.commit()
        if 'ticket_ref' not in mt_cols:
            conn.execute("ALTER TABLE memory_twelve ADD COLUMN ticket_ref TEXT DEFAULT ''")
            conn.commit()
    # Queue: add source_type and agent columns for internal entries
    queue_cols = {row[1] for row in conn.execute("PRAGMA table_info(queue)").fetchall()}
    if 'source_type' not in queue_cols:
        conn.execute("ALTER TABLE queue ADD COLUMN source_type TEXT DEFAULT 'email'")
        conn.commit()
    if 'agent' not in queue_cols:
        conn.execute("ALTER TABLE queue ADD COLUMN agent TEXT DEFAULT ''")
        conn.commit()
    # Time Wizard tables (exist in live DB, now added to schema; migrate for safety)
    for tbl, ddl in [
        ('memory_grok', 'CREATE TABLE IF NOT EXISTS memory_grok (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT "grok", subject TEXT DEFAULT "", content TEXT NOT NULL, tags TEXT DEFAULT "", importance INTEGER DEFAULT 7, source TEXT DEFAULT "session", ticket_ref TEXT DEFAULT "", archived INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")))'),
        ('memory_twelve', 'CREATE TABLE IF NOT EXISTS memory_twelve (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT "twelve", subject TEXT DEFAULT "", content TEXT NOT NULL, tags TEXT DEFAULT "", importance INTEGER DEFAULT 7, source TEXT DEFAULT "session", ticket_ref TEXT DEFAULT "", archived INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")))'),
        ('decisions', 'CREATE TABLE IF NOT EXISTS decisions (decision_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime("now")), agent TEXT NOT NULL, component TEXT DEFAULT "", proposal_file TEXT DEFAULT "", decision TEXT NOT NULL, reasoning TEXT DEFAULT "", test_status TEXT DEFAULT "PENDING", commit_hash TEXT DEFAULT "", checkpoint_id INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")), archived INTEGER DEFAULT 0)'),
        ('time_machine', 'CREATE TABLE IF NOT EXISTS time_machine (checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime("now")), agent TEXT NOT NULL, file_path TEXT NOT NULL, before_code TEXT DEFAULT "", after_code TEXT NOT NULL, before_hash TEXT DEFAULT "", after_hash TEXT DEFAULT "", test_results TEXT DEFAULT "", decision_id INTEGER DEFAULT 0, commit_hash TEXT DEFAULT "", outcome TEXT DEFAULT "success", is_rollback_point INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")))'),
        ('time_events', 'CREATE TABLE IF NOT EXISTS time_events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT "", event_type TEXT NOT NULL, agent TEXT NOT NULL, action TEXT DEFAULT "", target TEXT DEFAULT "", state_hash TEXT DEFAULT "", details TEXT DEFAULT "{}", created_at TEXT DEFAULT (datetime("now")))'),
        ('time_journal', 'CREATE TABLE IF NOT EXISTS time_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, timestamp TEXT DEFAULT "", session_id TEXT DEFAULT "", phase TEXT DEFAULT "", status TEXT DEFAULT "active", notes TEXT DEFAULT "", created_at TEXT DEFAULT (datetime("now")))'),
        ('time_checkpoints', 'CREATE TABLE IF NOT EXISTS time_checkpoints (id INTEGER PRIMARY KEY AUTOINCREMENT, checkpoint_name TEXT UNIQUE NOT NULL, timestamp TEXT DEFAULT "", description TEXT DEFAULT "", agent TEXT NOT NULL, full_state TEXT DEFAULT "{}", created_at TEXT DEFAULT (datetime("now")))'),
        ('daily_checkpoint', 'CREATE TABLE IF NOT EXISTS daily_checkpoint (checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, codebase_hash TEXT, memory_state TEXT, decisions_count INTEGER DEFAULT 0, description TEXT, is_stable INTEGER DEFAULT 0)'),
        ('ghost_briefs', 'CREATE TABLE IF NOT EXISTS ghost_briefs (id INTEGER PRIMARY KEY AUTOINCREMENT, generated_at TEXT DEFAULT CURRENT_TIMESTAMP, brief_type TEXT DEFAULT "on_demand", content TEXT NOT NULL, raw_data_snapshot TEXT, tokens_used INTEGER DEFAULT 0, triggered_by TEXT DEFAULT "system")'),
        ('scheduled_tasks', 'CREATE TABLE IF NOT EXISTS scheduled_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, schedule TEXT NOT NULL, action_type TEXT NOT NULL, action_data TEXT NOT NULL, last_run TEXT, next_run TEXT, enabled INTEGER DEFAULT 1, created_by TEXT DEFAULT "ghost", created_at TEXT)'),
        ('work_proposals', 'CREATE TABLE IF NOT EXISTS work_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT UNIQUE NOT NULL, agent TEXT NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT "", status TEXT DEFAULT "pending", proposal_file TEXT DEFAULT "", ticket_number TEXT DEFAULT "", queue_id INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime("now")), updated_at TEXT DEFAULT (datetime("now")))'),
        ('agent_capabilities', 'CREATE TABLE IF NOT EXISTS agent_capabilities (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT NOT NULL, capability TEXT NOT NULL, granted INTEGER DEFAULT 0, trust_level INTEGER DEFAULT 0, granted_by TEXT DEFAULT "system", proposal_id TEXT DEFAULT "", notes TEXT DEFAULT "", granted_at TEXT, created_at TEXT DEFAULT (datetime("now")), UNIQUE(agent_name, capability))'),
        ('chat_jobs', 'CREATE TABLE IF NOT EXISTS chat_jobs (job_id TEXT PRIMARY KEY, conversation_id INTEGER DEFAULT 0, agent TEXT DEFAULT "", status TEXT DEFAULT "running", runtime_class TEXT DEFAULT "", stage TEXT DEFAULT "", eta_seconds INTEGER DEFAULT 60, elapsed_ms INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0, error TEXT DEFAULT "", stage_trace_json TEXT DEFAULT "[]", started_at TEXT DEFAULT (datetime("now")), updated_at TEXT DEFAULT (datetime("now")))'),
    ]:
        if tbl not in tables:
            conn.execute(ddl)
            conn.commit()

    # Add number + label columns to agents table (idempotent — ALTER TABLE ignored if column exists)
    for col_ddl in [
        "ALTER TABLE agents ADD COLUMN number INTEGER DEFAULT 0",
        "ALTER TABLE agents ADD COLUMN label  TEXT    DEFAULT ''",
        "ALTER TABLE chat_jobs ADD COLUMN stage_trace_json TEXT DEFAULT '[]'",
    ]:
        try:
            conn.execute(col_ddl)
            conn.commit()
        except Exception:
            pass  # column already exists — safe to ignore

    # terminal_shortcuts table — all shortcuts (defaults + custom) stored in DB
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS terminal_shortcuts (id INTEGER PRIMARY KEY AUTOINCREMENT, icon TEXT NOT NULL DEFAULT "⚡", label TEXT NOT NULL, cmd TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    except Exception:
        pass

    # Custom sudo whitelist entries for the Fridays terminal
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS sudo_command_whitelist (id INTEGER PRIMARY KEY AUTOINCREMENT, command TEXT NOT NULL UNIQUE, note TEXT DEFAULT "", added_by TEXT DEFAULT "ghost", created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    except Exception:
        pass

    # Seed default shortcuts — insert each if its exact cmd doesn't already exist
    try:
        defaults = [
            ('🔁', 'Hard Boot Terminal',      'sudo systemctl restart swarm-terminal', 0),
            ('🎨', 'Theme Engine Check',       'head -n 80 /home/seven/swarm/themes/fridays.json', 1),
            ('📡', 'ALM Status',               'curl -s http://localhost:5050/api/alm/status', 2),
            ('💬', 'Restart Discord Bot',      'sudo systemctl restart swarm-discord', 3),
            ('📨', 'Restart Telegram Bot',     'sudo systemctl restart swarm-telegram', 4),
            ('✅', 'Terminal Service Status',  'systemctl status swarm-terminal', 5),
            ('🧠', 'System Memory',            'free -h', 6),
        ]
        existing_cmds = {r[0] for r in conn.execute("SELECT cmd FROM terminal_shortcuts").fetchall()}
        for icon, label, cmd, sort_order in defaults:
            if cmd not in existing_cmds:
                conn.execute(
                    "INSERT INTO terminal_shortcuts (icon, label, cmd, sort_order) VALUES (?, ?, ?, ?)",
                    (icon, label, cmd, sort_order)
                )
        conn.commit()
    except Exception:
        pass

    # agents table — add system_prompt and api_key_var columns
    for col_ddl in [
        "ALTER TABLE agents ADD COLUMN system_prompt TEXT DEFAULT ''",
        "ALTER TABLE agents ADD COLUMN api_key_var   TEXT DEFAULT ''",
        "ALTER TABLE agents ADD COLUMN tier          TEXT DEFAULT 'local'",
        "ALTER TABLE agents ADD COLUMN enabled       INTEGER DEFAULT 1",
        # Phase 2 — Agent Registry columns
        "ALTER TABLE agents ADD COLUMN memory_table   TEXT DEFAULT ''",
        "ALTER TABLE agents ADD COLUMN display_label  TEXT DEFAULT ''",
        "ALTER TABLE agents ADD COLUMN aliases        TEXT DEFAULT '[]'",
        "ALTER TABLE agents ADD COLUMN eta_seconds    INTEGER DEFAULT 60",
        "ALTER TABLE agents ADD COLUMN keep_alive     INTEGER DEFAULT NULL",
    ]:
        try:
            conn.execute(col_ddl)
            conn.commit()
        except Exception:
            pass

    # Sync system_prompt + api_key_var + tier for each agent from config.py.
    # system_prompt is always overwritten so config.py stays the source of truth.
    try:
        import config as _cfg
        GEMMA_SYSTEM_PROMPT      = getattr(_cfg, 'GEMMA_SYSTEM_PROMPT',     '')
        LLAMA_SYSTEM_PROMPT      = getattr(_cfg, 'LLAMA_SYSTEM_PROMPT',     '')
        QWEN_SYSTEM_PROMPT       = getattr(_cfg, 'QWEN_SYSTEM_PROMPT',      '')
        LIBRARIAN_SYSTEM_PROMPT  = getattr(_cfg, 'LIBRARIAN_SYSTEM_PROMPT', '')
        MISTRAL_SYSTEM_PROMPT    = getattr(_cfg, 'MISTRAL_SYSTEM_PROMPT',   '')
        NINE_SYSTEM_PROMPT       = getattr(_cfg, 'NINE_SYSTEM_PROMPT',      '')
        TEN_SYSTEM_PROMPT        = getattr(_cfg, 'TEN_SYSTEM_PROMPT',       '')
        ELEVEN_SYSTEM_PROMPT     = getattr(_cfg, 'ELEVEN_SYSTEM_PROMPT',    '')
        TWELVE_SYSTEM_PROMPT     = getattr(_cfg, 'TWELVE_SYSTEM_PROMPT',    '')
        THIRTEEN_SYSTEM_PROMPT   = getattr(_cfg, 'THIRTEEN_SYSTEM_PROMPT',  '')
        SCHOLAR_SYSTEM_PROMPT    = getattr(_cfg, 'SCHOLAR_SYSTEM_PROMPT',   '')
        SEEKER_SYSTEM_PROMPT     = getattr(_cfg, 'SEEKER_SYSTEM_PROMPT',    '')
    except Exception:
        GEMMA_SYSTEM_PROMPT = LLAMA_SYSTEM_PROMPT = QWEN_SYSTEM_PROMPT = ''
        LIBRARIAN_SYSTEM_PROMPT = MISTRAL_SYSTEM_PROMPT = ''
        NINE_SYSTEM_PROMPT = TEN_SYSTEM_PROMPT = ELEVEN_SYSTEM_PROMPT = TWELVE_SYSTEM_PROMPT = ''
        THIRTEEN_SYSTEM_PROMPT = SCHOLAR_SYSTEM_PROMPT = SEEKER_SYSTEM_PROMPT = ''

    _prompt_seed = [
        ('gemma',     GEMMA_SYSTEM_PROMPT,     '',                   'local'),
        ('llama',     LLAMA_SYSTEM_PROMPT,      '',                  'local'),
        ('mistral',   MISTRAL_SYSTEM_PROMPT,    '',                  'local'),
        ('qwen',      QWEN_SYSTEM_PROMPT,       '',                  'local'),
        ('librarian', LIBRARIAN_SYSTEM_PROMPT,  '',                  'local'),
        ('duck',      '',                       '',                  'local'),
        ('sniffles',  '',                       '',                  'local'),
        ('eight',     '',                       '',                  'local'),
        ('nine',      NINE_SYSTEM_PROMPT,       'GROQ_API_KEY',      'paid'),
        ('ten',       TEN_SYSTEM_PROMPT,        'GITHUB_TOKEN',      'paid'),
        ('eleven',    ELEVEN_SYSTEM_PROMPT,     'XAI_API_KEY',       'paid'),
        ('twelve',    TWELVE_SYSTEM_PROMPT,     'ANTHROPIC_API_KEY', 'paid'),
        ('thirteen',  THIRTEEN_SYSTEM_PROMPT,   'HF_API_KEY',        'paid'),
        ('scholar',   SCHOLAR_SYSTEM_PROMPT,    'GEMINI_API_KEY',    'service'),
        ('seeker',    SEEKER_SYSTEM_PROMPT,     'TAVILY_API_KEY',    'service'),
        ('ghost',     '',                       '',                  'human'),
    ]
    try:
        for name, prompt, key_var, tier in _prompt_seed:
            conn.execute(
                'UPDATE agents SET system_prompt = CASE WHEN ? != "" THEN ? ELSE system_prompt END, api_key_var = CASE WHEN (api_key_var IS NULL OR api_key_var = "") THEN ? ELSE api_key_var END, tier = CASE WHEN (tier IS NULL OR tier = "") THEN ? ELSE tier END WHERE name = ?',
                (prompt, prompt, key_var, tier, name)
            )
        conn.commit()
    except Exception:
        pass

    # Phase 2 — Seed registry metadata (memory_table, display_label, aliases, eta, keep_alive)
    # fmt: (name, memory_table, display_label, aliases_json, eta_seconds, keep_alive)
    _registry_seed = [
        ('ghost',     '',                'GHOST (OPERATOR)',                  '[]',                                   None, None),
        ('gemma',     'memory_gemma',    'GEMMA',                             '[]',                                   85,   -1),
        ('llama',     'memory_llama',    'LLAMA',                             '[]',                                   70,   -1),
        ('mistral',   'memory_mistral',  'MISTRAL',                           '[]',                                   90,   -1),
        ('qwen',      'memory_qwen',     'QWEN',                              '[]',                                   120,  -1),
        ('librarian', 'memory',          'LIBRARIAN',                         '[]',                                   50,   -1),
        ('duck',      'memory',          'DUCK',                              '[]',                                   35,   -1),
        ('sniffles',  'memory',          'SNIFFLES',                          '[]',                                   160,  -1),
        ('eight',     'memory_eight',    'EIGHT',                             '[]',                                   120,  -1),
        ('nine',      'memory_nine',     'NINE (GROQ LLAMA 3.3 70B)',        '["claude"]',                           8,    None),
        ('ten',       'memory_ten',      'TEN (GPT-5.3-CODEX)',              '["copilot","gpt"]',                    8,    None),
        ('eleven',    'memory_grok',     'ELEVEN (GROK API)',                 '["grok"]',                             10,   None),
        ('twelve',    'memory_twelve',   'TWELVE (CLAUDE HAIKU)',            '["timewizard","timewizardagent","haiku"]', 10, None),
        ('thirteen',  'memory_thirteen', 'THIRTEEN (HF)',                    '["huggingface"]',                      12,   None),
        ('scholar',   'memory_scholar',  'SCHOLAR (GEMINI)',                 '["gemini"]',                           12,   None),
        ('seeker',    'memory_seeker',   'SEEKER (TAVILY)',                  '["tavily"]',                           8,    None),
    ]
    try:
        for name, mem_tbl, disp, aliases, eta, ka in _registry_seed:
            # Always overwrite registry fields — these are managed by seed, not user edits
            conn.execute(
                """UPDATE agents SET
                     memory_table  = ?,
                     display_label = ?,
                     aliases       = ?,
                     eta_seconds   = ?,
                     keep_alive    = ?
                   WHERE name = ?""",
                (mem_tbl, disp, aliases, eta, ka, name)
            )
        conn.commit()
    except Exception:
        pass

    # swarm_globals table — shared rules and global parameters
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS swarm_globals (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, value TEXT NOT NULL DEFAULT "", description TEXT DEFAULT "", updated_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    except Exception:
        pass

    # Seed default globals
    _globals_seed = [
        ('global_rules',
         'Never hallucinate. Never fabricate facts. Never impersonate external services. Always state uncertainty. Do not break character.',
         'Rules prepended to every agent prompt'),
        ('global_max_tokens',
         '4096',
         'Default max tokens for API agents'),
        ('global_context_window',
         '8192',
         'Target context window size for all agents'),
    ]
    try:
        for key, value, desc in _globals_seed:
            conn.execute(
                "INSERT OR IGNORE INTO swarm_globals (key, value, description) VALUES (?, ?, ?)",
                (key, value, desc)
            )
        conn.commit()
    except Exception:
        pass

    # conv_timeline: add job_id column for per-message tracing
    tl_cols = {row[1] for row in conn.execute("PRAGMA table_info(conv_timeline)").fetchall()}
    if 'job_id' not in tl_cols:
        conn.execute("ALTER TABLE conv_timeline ADD COLUMN job_id TEXT DEFAULT ''")
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_timeline_job ON conv_timeline (job_id)")
        except Exception:
            pass
        conn.commit()

    # governance_log: audit trail for proposal state transitions (A.1.1)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS governance_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL,
            old_status  TEXT NOT NULL,
            new_status  TEXT NOT NULL,
            agent       TEXT NOT NULL DEFAULT '',
            actor       TEXT NOT NULL DEFAULT '',
            note        TEXT NOT NULL DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gov_log_proposal
        ON governance_log (proposal_id)
    """)
    conn.commit()

    # swarm_knowledge: shared knowledge base (A.3.1) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swarm_knowledge (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            key             TEXT NOT NULL,
            content         TEXT NOT NULL,
            source_agent    TEXT NOT NULL DEFAULT '',
            source_proposal_id TEXT DEFAULT '',
            category        TEXT NOT NULL DEFAULT 'fact',
            importance      INTEGER DEFAULT 5,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_knowledge_cat ON swarm_knowledge (category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_knowledge_agent ON swarm_knowledge (source_agent)")
    conn.commit()

    # swarm_events + acks: event broadcast (A.3.4) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swarm_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '',
            source_agent TEXT NOT NULL DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_events_type ON swarm_events (event_type, created_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swarm_event_acks (
            event_id    INTEGER NOT NULL,
            agent       TEXT NOT NULL,
            acked_at    TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (event_id, agent),
            FOREIGN KEY (event_id) REFERENCES swarm_events(id)
        )
    """)
    conn.commit()

    # swarm_bus: internal message bus (A.4.2) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swarm_bus (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            topic           TEXT NOT NULL,
            payload_json    TEXT NOT NULL DEFAULT '{}',
            source_service  TEXT NOT NULL DEFAULT 'local',
            created_at      TEXT DEFAULT (datetime('now')),
            consumed_at     TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_bus_topic ON swarm_bus (topic, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_bus_unconsumed ON swarm_bus (consumed_at) WHERE consumed_at IS NULL")
    conn.commit()

    # swarm_nodes: node registry (A.4.5) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS swarm_nodes (
            node_id         TEXT PRIMARY KEY,
            name            TEXT NOT NULL DEFAULT '',
            url             TEXT NOT NULL DEFAULT '',
            api_key_hash    TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'contributor',
            agents_json     TEXT NOT NULL DEFAULT '[]',
            capabilities    TEXT NOT NULL DEFAULT '[]',
            registered_at   TEXT DEFAULT (datetime('now')),
            last_seen       TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # research_sessions + research_evidence (B.1.1) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            topic               TEXT NOT NULL,
            depth               TEXT NOT NULL DEFAULT 'standard',
            status              TEXT NOT NULL DEFAULT 'planning',
            phases_json         TEXT NOT NULL DEFAULT '[]',
            linked_proposal_id  TEXT DEFAULT '',
            requesting_agent    TEXT NOT NULL DEFAULT 'user',
            summary             TEXT DEFAULT '',
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_sessions_status ON research_sessions (status)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_evidence (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL REFERENCES research_sessions(id),
            source_url          TEXT NOT NULL DEFAULT '',
            source_type         TEXT NOT NULL DEFAULT 'web',
            title               TEXT NOT NULL DEFAULT '',
            snippet             TEXT NOT NULL DEFAULT '',
            confidence          REAL DEFAULT 0.5,
            collecting_agent    TEXT NOT NULL DEFAULT '',
            snippet_hash        TEXT NOT NULL DEFAULT '',
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_evidence_session ON research_evidence (session_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_research_evidence_dedup ON research_evidence (session_id, source_url, snippet_hash)")
    conn.commit()

    # tool_builds (C.1.1) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_builds (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id         TEXT DEFAULT '',
            tool_type           TEXT NOT NULL DEFAULT 'script',
            tool_name           TEXT NOT NULL,
            description         TEXT NOT NULL DEFAULT '',
            entry_path          TEXT DEFAULT '',
            test_path           TEXT DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'scaffolded',
            test_output         TEXT DEFAULT '',
            building_agent      TEXT NOT NULL DEFAULT '',
            language            TEXT NOT NULL DEFAULT 'python',
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_builds_agent_status ON tool_builds (building_agent, status)")
    conn.commit()

    # node_skills (D.2.1) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS node_skills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id         TEXT NOT NULL,
            skill_name      TEXT NOT NULL,
            trust_level     INTEGER DEFAULT 0,
            description     TEXT DEFAULT '',
            available       INTEGER DEFAULT 1,
            last_seen       TEXT DEFAULT (datetime('now')),
            UNIQUE(node_id, skill_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_node_skills_name ON node_skills(skill_name)")
    conn.commit()

    # node_config (D.4.2) — migration for existing DBs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS node_config (
            key         TEXT PRIMARY KEY,
            value       TEXT DEFAULT '',
            node_id     TEXT DEFAULT '',
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # E.2.2: Additional performance indexes for hot query paths
    for idx_ddl in [
        "CREATE INDEX IF NOT EXISTS idx_work_proposals_status_agent ON work_proposals(status, agent)",
    ]:
        try:
            conn.execute(idx_ddl)
        except Exception:
            pass

    # User interests — persistent interest/preference store for onboarding & suggestions
    if 'user_interests' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        )''')
    # User login sessions — auth tokens for multi-user support
    if 'user_sessions' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            ip_address TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )''')
    # Add password_hash and role columns to user_profiles if missing
    if 'user_profiles' in tables:
        up_cols = {row[1] for row in conn.execute('PRAGMA table_info(user_profiles)').fetchall()}
        if 'password_hash' not in up_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN password_hash TEXT DEFAULT ''")
        if 'role' not in up_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN role TEXT DEFAULT 'viewer'")
        if 'approved' not in up_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN approved INTEGER DEFAULT 0")

    conn.commit()

    if _close:
        conn.close()


def _seed_agents():
    # number: permanent agent number (0=Ghost/human, 1-11=AI agents, -1=retired)
    # name:   stable internal code key — never changes even if model swaps
    # label:  display name shown in UI — change this when model/nickname changes
    # model:  current Ollama or API model string
    roster = [
        # num  name         label        model                        temp  role
        ( 0,  'ghost',     'Ghost',     'external',                  0.0,  'Human operator. Builds, approves, decides. Full system authority.'),
        ( 1,  'gemma',     'Gemma3',    'gemma3:latest',             0.3,  'Director — routes, synthesises, speaks last'),
        ( 2,  'llama',     'LlaMA',     'llama3.2:latest',           0.6,  'Correspondent — web search, fast first response'),
        ( 3,  'mistral',   'Mistral',   'mistral:latest',            0.7,  'Analyst — deep reasoning, debates, challenges Two'),
        ( 4,  'qwen',      'Qwen',      'qwen2.5:latest',            0.7,  'Deep Analyst — specialist depth, multilingual reasoning'),
        ( 5,  'librarian', 'Vortex',    'qwen:latest',               0.1,  'Gatekeeper + Vortex — tags, queues, closes, checkpoints'),
        ( 6,  'duck',      'Duck',      'qwen:latest',               0.1,  'Sanity checker — YES/NO after every ticket'),
        ( 7,  'sniffles',  'Sniffles',  'deepseek-r1:7b',            0.2,  'Inspector — memory auditor, read only, chain-of-thought'),
        ( 8,  'eight',     'Eight',     'gemma4:26b',                0.5,  'SAP specialist — three-voice debate (Functional/Technical/Devil)'),
        ( 9,  'nine',      'Groq',      'llama-3.3-70b-versatile',              0.5,  'Developer Agent — system architect, proposals, Ghost One-directed execution'),
        (10,  'ten',       'Github',    'gpt-4o',                                0.4,  'Developer Agent — software engineer, code quality, implementation'),
        (11,  'eleven',    'Grok',      'grok-api',                              0.5,  'Developer Agent — lateral thinker, creative synthesis, alternatives'),
        (12,  'twelve',    'Claude',    'claude-haiku-4-5',                      0.3,  'Developer Agent — time wizard, session continuity, Vortex'),
        (13,  'thirteen',  'HuggingFace', 'meta-llama/Llama-3.3-70B-Instruct',  0.5,  'Developer Agent — HuggingFace specialist (testing)'),
        (17,  'ghost_coder', 'Ghost Coder', 'claude-sonnet-4-20250514',        0.3,  'Developer Agent — code-aware AI, reads/writes/patches code, bridges Copilot and Fridays'),
    ]
    conn = get_connection()
    for number, name, label, model, temp, role in roster:
        conn.execute(
            """INSERT INTO agents (number, name, label, model, temperature, role)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                   number=excluded.number,
                   label=CASE WHEN agents.label IS NULL OR agents.label='' THEN excluded.label ELSE agents.label END,
                   model=CASE WHEN agents.model IS NULL OR agents.model='' THEN excluded.model ELSE agents.model END,
                   temperature=excluded.temperature,
                   role=excluded.role""",
            (number, name, label, model, temp, role)
        )
    # Retire agents that no longer exist as standalone entries
    for retired_name, retired_note in [
        ('grok',   'RETIRED 2026-04-04 — alias consolidated into eleven (Agent 11)'),
    ]:
        conn.execute(
            "UPDATE agents SET number=-1, label='Retired', role=? WHERE name=?",
            (retired_note, retired_name)
        )

    # ── proposal_attachments table (ALM file attachments) ─────────────────────
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS proposal_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, filename TEXT NOT NULL, original_name TEXT DEFAULT "", mime_type TEXT DEFAULT "application/octet-stream", size_bytes INTEGER DEFAULT 0, uploaded_by TEXT DEFAULT "ghost", created_at TEXT DEFAULT (datetime("now")))')
        conn.commit()
    except Exception:
        pass

    # ── work_proposals editable fields ────────────────────────────────────────
    for col_ddl in [
        "ALTER TABLE work_proposals ADD COLUMN ticket_id INTEGER DEFAULT 0",
        "ALTER TABLE work_proposals ADD COLUMN notes TEXT DEFAULT ''",
        # source_conv_id: the chat conversation_id this proposal was raised from
        # used to post approval/rejection notifications back to the originating thread
        "ALTER TABLE work_proposals ADD COLUMN source_conv_id INTEGER DEFAULT NULL",
        # duck_verdict: Duck's last approval decision ('approved' / 'rejected' / '')
        "ALTER TABLE work_proposals ADD COLUMN duck_verdict TEXT DEFAULT ''",
        # duck_note: Duck's review comment
        "ALTER TABLE work_proposals ADD COLUMN duck_note TEXT DEFAULT ''",
        # git_branch: proposal/<id> branch created at alm_self_approve
        "ALTER TABLE work_proposals ADD COLUMN git_branch TEXT DEFAULT ''",
        # git_commit: commit hash recorded at alm_complete for Ghost diff review
        "ALTER TABLE work_proposals ADD COLUMN git_commit TEXT DEFAULT ''",
        # test_results: output of DEV health check + syntax checks run at alm_complete
        "ALTER TABLE work_proposals ADD COLUMN test_results TEXT DEFAULT ''",
        # D.1.1: source_node tracks which node created this proposal
        "ALTER TABLE work_proposals ADD COLUMN source_node TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(col_ddl)
            conn.commit()
        except Exception:
            pass

    conn.commit()
    conn.close()


def _seed_moderator():
    try:
        from config import GHOST_EMAIL
        conn = get_connection()
        conn.execute("INSERT OR IGNORE INTO moderators (email) VALUES (?)", (GHOST_EMAIL.lower(),))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not seed moderator: {e}")


def _seed_user_profiles():
    # Create default profiles for Ghost and all known agents.
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_profiles (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by) VALUES ('ghost', 'Ghost', 'human', '', 1, 1, 'system')"
        )

        rows = conn.execute("SELECT name FROM agents").fetchall()
        for row in rows:
            name = (row['name'] or '').strip().lower()
            if not name:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO user_profiles (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by) VALUES (?, ?, 'agent', ?, 1, 0, 'system')",
                (name, name.capitalize(), name)
            )
        conn.commit()
    finally:
        conn.close()
