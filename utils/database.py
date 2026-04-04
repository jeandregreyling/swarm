"""
database.py — Seven's Swarm
Complete database layer. All 20 tables. All functions the swarm calls.
Run: python3 database.py to initialise.
"""

import sqlite3
import logging

logger = logging.getLogger('seven.database')
DB_PATH = '/home/seven/swarm/swarm_memory.db'

# Global mapping to ensure consistency across the swarm
AGENT_POOL_MAP = {
    'llama': 'memory_llama', 'qwen': 'memory_qwen',
    'mistral': 'memory_mistral',
    'gemma': 'memory_gemma', 'eight': 'memory_eight',
    'nine': 'memory_nine', 'librarian': 'memory',
    'duck': 'memory', 'sniffles': 'memory',
    'ten': 'memory_ten', 'twelve': 'memory_twelve',
    'eleven': 'memory_grok', 'grok': 'memory_grok',
    'scholar': 'memory', 'seeker': 'memory'
}

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,
    temperature REAL DEFAULT 0.3,
    role TEXT,
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
    target_email TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_user_profiles_active ON user_profiles(is_active);
CREATE INDEX IF NOT EXISTS idx_user_skill_permissions_user ON user_skill_permissions(username);
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


def _migrate_schema(conn=None):
    """Add columns/tables to existing deployments that were added after initial deploy."""
    _close = conn is None
    if _close:
        conn = get_connection()
    # New columns on tickets
    ticket_cols = {row[1] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()}
    if 'email_message_id' not in ticket_cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN email_message_id TEXT DEFAULT ''")
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
        conn.execute("""CREATE TABLE IF NOT EXISTS trusted_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            channel TEXT DEFAULT 'email',
            added_by TEXT NOT NULL,
            notes TEXT DEFAULT '',
            added_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
    if 'snoozed_tickets' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS snoozed_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            sender_email TEXT NOT NULL,
            wake_at TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            fired INTEGER DEFAULT 0
        )""")
        conn.commit()
    if 'project_docs' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS project_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name TEXT NOT NULL,
            content TEXT DEFAULT '',
            tags TEXT DEFAULT 'all',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
    else:
        # Add tags column to existing project_docs if missing
        doc_cols = {row[1] for row in conn.execute('PRAGMA table_info(project_docs)').fetchall()}
        if 'tags' not in doc_cols:
            conn.execute("ALTER TABLE project_docs ADD COLUMN tags TEXT DEFAULT 'all'")
            conn.commit()
    if 'memory_nine' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS memory_nine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'nine',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7,
            source TEXT DEFAULT 'session',
            ticket_ref TEXT DEFAULT '',
            archived INTEGER DEFAULT 0,
            created_at TEXT
        )""")
        conn.commit()
    if 'memory_ten' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS memory_ten (
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
        )""")
        conn.commit()
    if 'approval_tokens' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS approval_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            action TEXT NOT NULL,
            target_email TEXT NOT NULL DEFAULT '',
            created_by TEXT DEFAULT 'system',
            created_at TEXT DEFAULT (datetime('now')),
            used_at TEXT,
            status TEXT DEFAULT 'pending'
        )""")
        conn.commit()
    if 'debates' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS debates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            initiator TEXT DEFAULT 'nine',
            status TEXT DEFAULT 'open',
            rounds INTEGER DEFAULT 0,
            consensus TEXT DEFAULT '',
            proposal_id INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            closed_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS debate_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debate_id INTEGER NOT NULL,
            agent TEXT NOT NULL,
            position TEXT NOT NULL,
            round INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
    if 'file_writes' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS file_writes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            description TEXT DEFAULT '',
            previous_content TEXT DEFAULT '',
            new_content TEXT NOT NULL,
            applied_by TEXT DEFAULT 'ghost',
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
    if 'user_profiles' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
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
        )""")
        conn.commit()
    if 'user_skill_permissions' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS user_skill_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            allowed INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'ghost',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, skill_name)
        )""")
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
        ('memory_grok', """CREATE TABLE IF NOT EXISTS memory_grok (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT 'grok',
            subject TEXT DEFAULT '', content TEXT NOT NULL, tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7, source TEXT DEFAULT 'session',
            ticket_ref TEXT DEFAULT '', archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')))"""),
        ('memory_twelve', """CREATE TABLE IF NOT EXISTS memory_twelve (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT DEFAULT 'twelve',
            subject TEXT DEFAULT '', content TEXT NOT NULL, tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7, source TEXT DEFAULT 'session',
            ticket_ref TEXT DEFAULT '', archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')))"""),
        ('decisions', """CREATE TABLE IF NOT EXISTS decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')), agent TEXT NOT NULL,
            component TEXT DEFAULT '', proposal_file TEXT DEFAULT '',
            decision TEXT NOT NULL, reasoning TEXT DEFAULT '',
            test_status TEXT DEFAULT 'PENDING', commit_hash TEXT DEFAULT '',
            checkpoint_id INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')), archived INTEGER DEFAULT 0)"""),
        ('time_machine', """CREATE TABLE IF NOT EXISTS time_machine (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')), agent TEXT NOT NULL,
            file_path TEXT NOT NULL, before_code TEXT DEFAULT '',
            after_code TEXT NOT NULL, before_hash TEXT DEFAULT '',
            after_hash TEXT DEFAULT '', test_results TEXT DEFAULT '',
            decision_id INTEGER DEFAULT 0, commit_hash TEXT DEFAULT '',
            outcome TEXT DEFAULT 'success', is_rollback_point INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')))"""),
        ('time_events', """CREATE TABLE IF NOT EXISTS time_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT '',
            event_type TEXT NOT NULL, agent TEXT NOT NULL,
            action TEXT DEFAULT '', target TEXT DEFAULT '',
            state_hash TEXT DEFAULT '', details TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')))"""),
        ('time_journal', """CREATE TABLE IF NOT EXISTS time_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL,
            timestamp TEXT DEFAULT '', session_id TEXT DEFAULT '',
            phase TEXT DEFAULT '', status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')))"""),
        ('time_checkpoints', """CREATE TABLE IF NOT EXISTS time_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, checkpoint_name TEXT UNIQUE NOT NULL,
            timestamp TEXT DEFAULT '', description TEXT DEFAULT '',
            agent TEXT NOT NULL, full_state TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')))"""),
        ('daily_checkpoint', """CREATE TABLE IF NOT EXISTS daily_checkpoint (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            codebase_hash TEXT, memory_state TEXT,
            decisions_count INTEGER DEFAULT 0,
            description TEXT, is_stable INTEGER DEFAULT 0)"""),
        ('ghost_briefs', """CREATE TABLE IF NOT EXISTS ghost_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            brief_type TEXT DEFAULT 'on_demand',
            content TEXT NOT NULL, raw_data_snapshot TEXT,
            tokens_used INTEGER DEFAULT 0,
            triggered_by TEXT DEFAULT 'system')"""),
        ('scheduled_tasks', """CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, schedule TEXT NOT NULL,
            action_type TEXT NOT NULL, action_data TEXT NOT NULL,
            last_run TEXT, next_run TEXT, enabled INTEGER DEFAULT 1,
            created_by TEXT DEFAULT 'ghost', created_at TEXT)"""),
        ('work_proposals', """CREATE TABLE IF NOT EXISTS work_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE NOT NULL, agent TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', proposal_file TEXT DEFAULT '',
            ticket_number TEXT DEFAULT '', queue_id INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')))"""),
        ('agent_capabilities', """CREATE TABLE IF NOT EXISTS agent_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            capability TEXT NOT NULL,
            granted INTEGER DEFAULT 0,
            trust_level INTEGER DEFAULT 0,
            granted_by TEXT DEFAULT 'system',
            proposal_id TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            granted_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(agent_name, capability))"""),
        ('chat_jobs', """CREATE TABLE IF NOT EXISTS chat_jobs (
            job_id TEXT PRIMARY KEY,
            conversation_id INTEGER DEFAULT 0,
            agent TEXT DEFAULT '',
            status TEXT DEFAULT 'running',
            runtime_class TEXT DEFAULT '',
            stage TEXT DEFAULT '',
            eta_seconds INTEGER DEFAULT 60,
            elapsed_ms INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            started_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )"""),
    ]:
        if tbl not in tables:
            conn.execute(ddl)
            conn.commit()
    if _close:
        conn.close()


def persist_chat_job(job_id, conversation_id, agent, runtime_class, eta_seconds, started_at):
    """Record a new chat job. Best-effort — never raises."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO chat_jobs
                   (job_id, conversation_id, agent, status, runtime_class,
                    eta_seconds, started_at, updated_at)
                   VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
                (str(job_id), int(conversation_id or 0), str(agent or ''),
                 str(runtime_class or ''), int(eta_seconds or 60),
                 str(started_at or ''), str(started_at or ''))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def update_chat_job_db(job_id, status, stage='', error='', elapsed_ms=0, tokens=0):
    """Update a chat job record. Best-effort — never raises."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE chat_jobs
                   SET status=?, stage=?, error=?, elapsed_ms=?, tokens=?,
                       updated_at=datetime('now')
                   WHERE job_id=?""",
                (str(status), str(stage or ''), str(error or '')[:500],
                 int(elapsed_ms or 0), int(tokens or 0), str(job_id))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_chat_jobs_by_ids(job_ids):
    """Fetch chat_jobs rows for a set of job IDs. Returns list of dicts."""
    job_ids = [str(j) for j in (job_ids or []) if j]
    if not job_ids:
        return []
    try:
        conn = get_connection()
        try:
            placeholders = ','.join('?' for _ in job_ids)
            rows = conn.execute(
                f'SELECT * FROM chat_jobs WHERE job_id IN ({placeholders})',
                job_ids
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def mark_orphaned_chat_jobs():
    """Mark any 'running' chat_jobs rows as failed. Call once on server startup."""
    try:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE chat_jobs
                   SET status='failed', stage='failed',
                       error='server restarted — job lost',
                       updated_at=datetime('now')
                   WHERE status='running'"""
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_project_docs(tag='all'):
    """Return docs tagged for a specific agent or 'all'. Used for agent context injection."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT doc_name, content FROM project_docs WHERE tags IS NULL OR tags='all' OR tags LIKE ? ORDER BY updated_at DESC",
        (f'%{tag}%',)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _seed_agents():
    roster = [
        ('gemma',     'gemma3:latest',   0.3, 'Director — routes, synthesises, speaks last'),
        ('llama',     'llama3.2:latest', 0.6, 'Correspondent — web search, fast first response'),
        ('qwen',      'qwen2.5:latest',  0.7, 'Analyst — deep reasoning, debates, challenges'),
        ('librarian', 'qwen:1.5b',       0.1, 'Gatekeeper — tags only, never speaks'),
        ('eight',     'qwen2.5:latest',  0.7, 'SAP specialist — three-voice debate (Functional/Technical/Devil) + synthesis'),
        ('duck',      'qwen:1.5b',       0.1, 'Sanity checker — YES/NO after every ticket'),
        ('sniffles',  'deepseek-r1:7b',  0.2, 'Inspector — memory auditor, read only'),
        ('ghost',     'external',        0.0, 'Human operator. Ghost Layer. Builds, approves, decides. Full access.'),
        ('nine',      'claude-sonnet-4-6',     0.3, 'Nine (Claude Sonnet) — system architect. Ghost Layer. Session memory in memory_nine.'),
        ('ten',       'gpt-4.1',               0.4, 'Ten (GPT) — software engineering advisor, code quality, implementation clarity. Ghost Layer.'),
        ('eleven',    'grok-3',                0.5, 'Eleven (Grok 3) — lateral thinking, creative synthesis. Ghost Layer.'),
        ('twelve',    'claude-haiku-4-5-20251001', 0.3, 'Twelve (Claude Haiku) — time wizard, temporal awareness, decision tracking, time machine.'),
    ]
    conn = get_connection()
    for name, model, temp, role in roster:
        conn.execute(
            """INSERT INTO agents (name,model,temperature,role)
               VALUES (?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                   model=excluded.model,
                   temperature=excluded.temperature,
                   role=excluded.role""",
            (name, model, temp, role)
        )
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
    """Create default profiles for Ghost and all known agents."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO user_profiles
               (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by)
               VALUES ('ghost', 'Ghost', 'human', '', 1, 1, 'system')"""
        )

        rows = conn.execute("SELECT name FROM agents").fetchall()
        for row in rows:
            name = (row['name'] or '').strip().lower()
            if not name:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO user_profiles
                   (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by)
                   VALUES (?, ?, 'agent', ?, 1, 0, 'system')""",
                (name, name.capitalize(), name)
            )
        conn.commit()
    finally:
        conn.close()


def list_user_profiles(include_inactive=False):
    conn = get_connection()
    try:
        sql = (
            "SELECT username, display_name, user_type, linked_agent, is_active, can_proxy, "
            "created_by, created_at, updated_at "
            "FROM user_profiles"
        )
        params = []
        if not include_inactive:
            sql += " WHERE is_active=1"
        sql += " ORDER BY CASE WHEN username='ghost' THEN 0 ELSE 1 END, username ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_profile(username):
    uname = (username or '').strip().lower()
    if not uname:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT username, display_name, user_type, linked_agent, is_active, can_proxy,
                      created_by, created_at, updated_at
               FROM user_profiles WHERE username=?""",
            (uname,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_user_profile(username, display_name='', user_type='human', linked_agent='',
                        is_active=1, can_proxy=0, created_by='ghost'):
    uname = (username or '').strip().lower()
    if not uname:
        raise ValueError('username required')
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM user_profiles WHERE username=?",
            (uname,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE user_profiles
                   SET display_name=?, user_type=?, linked_agent=?, is_active=?, can_proxy=?,
                       updated_at=datetime('now')
                   WHERE username=?""",
                (
                    (display_name or uname).strip(),
                    (user_type or 'human').strip().lower(),
                    (linked_agent or '').strip().lower(),
                    1 if is_active else 0,
                    1 if can_proxy else 0,
                    uname,
                )
            )
        else:
            conn.execute(
                """INSERT INTO user_profiles
                   (username, display_name, user_type, linked_agent, is_active, can_proxy, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uname,
                    (display_name or uname).strip(),
                    (user_type or 'human').strip().lower(),
                    (linked_agent or '').strip().lower(),
                    1 if is_active else 0,
                    1 if can_proxy else 0,
                    (created_by or 'ghost').strip().lower(),
                )
            )
        conn.commit()
    finally:
        conn.close()
    return get_user_profile(uname)


def list_user_skill_permissions(username):
    uname = (username or '').strip().lower()
    if not uname:
        return []
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT username, skill_name, allowed, created_by, created_at, updated_at
               FROM user_skill_permissions
               WHERE username=?
               ORDER BY skill_name ASC""",
            (uname,)
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item['allowed'] = bool(item.get('allowed'))
            out.append(item)
        return out
    finally:
        conn.close()


def set_user_skill_permission(username, skill_name, allowed=True, created_by='ghost'):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not uname:
        raise ValueError('username required')
    if not sk:
        raise ValueError('skill_name required')
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO user_skill_permissions
               (username, skill_name, allowed, created_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(username, skill_name)
               DO UPDATE SET allowed=excluded.allowed,
                             created_by=excluded.created_by,
                             updated_at=datetime('now')""",
            (uname, sk, 1 if allowed else 0, (created_by or 'ghost').strip().lower())
        )
        conn.commit()
    finally:
        conn.close()


def remove_user_skill_permission(username, skill_name):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not uname or not sk:
        return
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM user_skill_permissions WHERE username=? AND skill_name=?",
            (uname, sk)
        )
        conn.commit()
    finally:
        conn.close()


def can_user_invoke_skill(username, skill_name, default_allow=True):
    uname = (username or '').strip().lower()
    sk = (skill_name or '').strip().lower()
    if not sk:
        return False
    if not uname:
        return bool(default_allow)

    profile = get_user_profile(uname)
    if not profile or not profile.get('is_active'):
        return False

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT allowed FROM user_skill_permissions WHERE username=? AND skill_name=?",
            (uname, sk)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return bool(default_allow)
    return bool(row['allowed'])


# ── Agent Capability Registry ─────────────────────────────────────────────────

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


def new_conversation(title, source='email', sender=''):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO conversations (title,source,sender) VALUES (?,?,?)",
        (title[:100], source, sender)
    )
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conv_id


def log_message(conv_id, from_agent, content, to_agent='', message_type='chat', tokens_used=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,?,?,?,?,?)",
        (conv_id, from_agent, to_agent, content, message_type, int(tokens_used or 0))
    )
    conn.commit()
    conn.close()


def save_memory(agent, subject, content, tags='', importance=5):
    conn = get_connection()
    conn.execute(
        "INSERT INTO memory (agent,subject,content,tags,importance,source) VALUES (?,?,?,?,?,?)",
        (agent, subject[:200], content, tags, importance, agent.lower())
    )
    conn.commit()
    conn.close()


def search_project_docs(query='', limit=3):
    """
    Keyword search across project_docs sections.
    Returns list of dicts with doc_name and content.
    Used by orchestrator to inject relevant architecture/context into agent prompts.
    """
    conn = get_connection()
    if query:
        # Match against section name or content
        rows = conn.execute(
            'SELECT doc_name, content FROM project_docs '
            'WHERE doc_name LIKE ? OR content LIKE ? '
            'ORDER BY CASE WHEN doc_name LIKE ? THEN 0 ELSE 1 END LIMIT ?',
            (f'%{query}%', f'%{query}%', f'%{query}%', limit)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT doc_name, content FROM project_docs LIMIT ?', (limit,)
        ).fetchall()
    conn.close()
    return [{'doc_name': r['doc_name'], 'content': r['content']} for r in rows]


def search_memory(query='', min_importance=5, limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM memory
        WHERE archived=0 AND importance>=?
        AND (subject LIKE ? OR content LIKE ?)
        ORDER BY importance DESC, created_at DESC LIMIT ?
    """, (min_importance, f'%{query}%', f'%{query}%', limit)).fetchall()
    conn.close()
    return rows


def get_all_memories(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM memory WHERE archived=0 ORDER BY importance DESC, created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_ghost_history(limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT m.content, m.created_at, c.title
        FROM messages m JOIN conversations c ON m.conversation_id=c.id
        WHERE m.from_agent='Ghost'
        ORDER BY m.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return list(reversed(rows))


def save_gemma_verdict(subject, content, tags=''):
    conn = get_connection()
    conn.execute(
        "INSERT INTO memory_gemma (agent,subject,content,tags,importance,source) VALUES ('gemma',?,?,?,9,'verdict')",
        (subject[:200], content, tags)
    )
    conn.commit()
    conn.close()


def promote_to_verified(subject, content, tags=''):
    conn = get_connection()
    conn.execute(
        "INSERT INTO memory (agent,subject,content,tags,importance,source,verified) VALUES ('gemma',?,?,?,9,'verdict',1)",
        (subject[:200], content, tags)
    )
    conn.commit()
    conn.close()


def save_agent_memory(agent_name, subject, content, tags='', importance=5, source='learned'):
    table = AGENT_POOL_MAP.get(agent_name.lower())
    if not table:
        logger.warning(f"No personal pool for agent: {agent_name}")
        return False
    conn = get_connection()
    # memory_gemma, memory_eight, and memory_nine have a 'source' column
    if agent_name.lower() in ('gemma', 'eight', 'nine'):
        conn.execute(
            f"INSERT INTO {table} (agent,subject,content,tags,importance,source) VALUES (?,?,?,?,?,?)",
            (agent_name.lower(), subject[:200], content, tags, importance, source)
        )
    else:
        conn.execute(
            f"INSERT INTO {table} (agent,subject,content,tags,importance) VALUES (?,?,?,?,?)",
            (agent_name.lower(), subject[:200], content, tags, importance)
        )
    conn.commit()
    conn.close()
    return True


def get_agent_memory(agent_name, query='', limit=5):
    table = AGENT_POOL_MAP.get(agent_name.lower())
    if not table:
        return []
    archive_filter = "AND archived=0"
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT id,subject,content,tags,importance,created_at FROM {table}
        WHERE (subject LIKE ? OR content LIKE ?) {archive_filter}
        ORDER BY importance DESC, created_at DESC LIMIT ?
    """, (f'%{query}%', f'%{query}%', limit)).fetchall()
    conn.close()
    return rows


def close_ticket(ticket_number, final_answer):
    conn = get_connection()
    conn.execute("""
        UPDATE tickets SET status='closed', final_answer=?, sniffles_checked=0,
        closed_at=datetime('now'), updated_at=datetime('now')
        WHERE ticket_number=?
    """, (final_answer, ticket_number))
    conn.commit()
    conn.close()


def find_ticket_by_thread(in_reply_to='', references=''):
    """
    Look for an existing ticket whose original email Message-ID appears in the
    incoming email's In-Reply-To or References headers (which contain the full
    thread chain). Returns the ticket row dict, or None.
    """
    combined = (in_reply_to + ' ' + references).strip()
    if not combined:
        return None
    conn = get_connection()
    # Pull all tickets that have a stored email_message_id
    rows = conn.execute(
        "SELECT * FROM tickets WHERE email_message_id != '' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    for row in rows:
        mid = row['email_message_id'].strip()
        if mid and mid in combined:
            return dict(row)
    return None


def reopen_ticket(ticket_number):
    """Re-open a closed ticket for a follow-up reply."""
    conn = get_connection()
    conn.execute(
        "UPDATE tickets SET status='open', closed_at=NULL, updated_at=datetime('now') "
        "WHERE ticket_number=?",
        (ticket_number,)
    )
    conn.commit()
    conn.close()


def update_ticket_tags(ticket_number, new_tags):
    """Append tags to a ticket (space-separated, deduped)."""
    conn = get_connection()
    row = conn.execute("SELECT tags FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
    if not row:
        conn.close()
        return False
    existing = set((row['tags'] or '').split())
    combined = ' '.join(sorted(existing | set(new_tags.split())))
    conn.execute("UPDATE tickets SET tags=?, updated_at=datetime('now') WHERE ticket_number=?",
                 (combined, ticket_number))
    conn.commit()
    conn.close()
    return True


def add_ticket_note_by_number(ticket_number, agent, content, note_type='ghost_note'):
    """Log a note against a ticket by ticket number."""
    conn = get_connection()
    ticket = conn.execute("SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)).fetchone()
    if not ticket:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO ticket_notes (ticket_id, agent, note_type, content) VALUES (?,?,?,?)",
        (ticket['id'], agent, note_type, content)
    )
    conn.commit()
    conn.close()
    return True


def add_trusted_domain(domain, added_by='ghost', note='', channel='email'):
    """Trust all senders from a domain (e.g. example.com)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO trusted_domains (domain, channel, added_by, notes) VALUES (?,?,?,?)",
        (domain.lower().lstrip('@'), channel, added_by, note)
    )
    conn.commit()
    conn.close()


def get_trusted_domains():
    """Return set of trusted domains."""
    conn = get_connection()
    rows = conn.execute("SELECT domain FROM trusted_domains").fetchall()
    conn.close()
    return {row[0] for row in rows}


def snooze_ticket(ticket_number, sender_email, wake_at_iso, note=''):
    """Park a ticket until wake_at_iso (ISO datetime string)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO snoozed_tickets (ticket_number, sender_email, wake_at, note) VALUES (?,?,?,?)",
        (ticket_number, sender_email, wake_at_iso, note)
    )
    conn.commit()
    conn.close()


def get_due_snoozed():
    """Return snoozed tickets whose wake_at time has passed and haven't fired yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM snoozed_tickets WHERE fired=0 AND wake_at <= datetime('now')"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_snooze_fired(snooze_id):
    conn = get_connection()
    conn.execute("UPDATE snoozed_tickets SET fired=1 WHERE id=?", (snooze_id,))
    conn.commit()
    conn.close()


def get_overdue_tickets(hours=4):
    """Return open tickets that have been open longer than `hours` hours."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT ticket_number, sender_email, question, created_at FROM tickets "
        "WHERE status='open' AND created_at <= datetime('now', ?)",
        (f'-{hours} hours',)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_digest_stats():
    """Stats for the daily email digest."""
    conn = get_connection()
    opened  = conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at >= datetime('now','-1 day')").fetchone()[0]
    closed  = conn.execute("SELECT COUNT(*) FROM tickets WHERE closed_at  >= datetime('now','-1 day')").fetchone()[0]
    open_ct = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    duck_yes = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES' AND created_at >= datetime('now','-1 day')").fetchone()[0]
    duck_no  = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'  AND created_at >= datetime('now','-1 day')").fetchone()[0]
    top_tags = conn.execute(
        "SELECT tags FROM tickets WHERE created_at >= datetime('now','-7 day') AND tags != ''"
    ).fetchall()
    conn.close()
    # Count individual tags
    from collections import Counter
    tag_counts = Counter()
    for row in top_tags:
        for t in (row['tags'] or '').split():
            tag_counts[t] += 1
    return {
        'opened': opened, 'closed': closed, 'open': open_ct,
        'duck_yes': duck_yes, 'duck_no': duck_no,
        'top_tags': tag_counts.most_common(5)
    }


def get_all_email_lists():
    conn = get_connection()
    trusted = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM trusted_senders").fetchall())
    mods    = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM moderators").fetchall())
    notifs  = set(row[0] for row in conn.execute("SELECT LOWER(email) FROM notification_senders").fetchall())
    conn.close()
    return trusted, mods, notifs


def add_trusted_sender(email, added_by='ghost', note=''):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO trusted_senders (email,added_by,notes) VALUES (?,?,?)",
        (email.lower(), added_by, note)
    )
    conn.commit()
    conn.close()


def remove_trusted_sender(email):
    conn = get_connection()
    conn.execute("DELETE FROM trusted_senders WHERE LOWER(email)=?", (email.lower(),))
    conn.commit()
    conn.close()


def add_notification_sender(email, added_by='ghost', note=''):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO notification_senders (email, added_by, notes) VALUES (?,?,?)",
        (email.lower(), added_by, note)
    )
    conn.commit()
    conn.close()


def remove_notification_sender(email):
    conn = get_connection()
    conn.execute("DELETE FROM notification_senders WHERE LOWER(email)=?", (email.lower(),))
    conn.commit()
    conn.close()


def save_pending_email(from_addr, subject, body, message_id=''):
    conn = get_connection()
    conn.execute(
        "INSERT INTO pending_emails (from_addr,subject,body,message_id) VALUES (?,?,?,?)",
        (from_addr, subject, body, message_id or '')
    )
    conn.commit()
    conn.close()


def get_pending_emails(from_addr=None):
    conn = get_connection()
    if from_addr:
        rows = conn.execute("""
            SELECT id,from_addr,subject,body,message_id,status,received_at
            FROM pending_emails WHERE status='pending' AND from_addr=?
            ORDER BY received_at ASC
        """, (from_addr,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id,from_addr,subject,body,message_id,status,received_at
            FROM pending_emails WHERE status='pending'
            ORDER BY received_at ASC
        """).fetchall()
    conn.close()
    return rows


def mark_pending_processed(pending_id):
    conn = get_connection()
    conn.execute(
        "UPDATE pending_emails SET status='processed' WHERE id=?",
        (pending_id,)
    )
    conn.commit()
    conn.close()


# ── Approval tokens — clickable TRUST/NOTIFY/IGNORE links ──────────────────

def create_approval_token(action, target_email, created_by='system'):
    """Generate a UUID token for a TRUST/NOTIFY/IGNORE action. Returns the token."""
    import uuid
    token = uuid.uuid4().hex
    conn = get_connection()
    conn.execute(
        "INSERT INTO approval_tokens (token, action, target_email, created_by) VALUES (?,?,?,?)",
        (token, action.lower(), target_email.lower(), created_by)
    )
    conn.commit()
    conn.close()
    return token


def use_approval_token(token):
    """
    Consume a token. Returns dict with action+target_email, or None if invalid/used/missing.
    Marks token as used so it cannot fire twice.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT action, target_email, status FROM approval_tokens WHERE token=?",
        (token,)
    ).fetchone()
    if not row or row['status'] != 'pending':
        conn.close()
        return None
    conn.execute(
        "UPDATE approval_tokens SET status='used', used_at=datetime('now') WHERE token=?",
        (token,)
    )
    conn.commit()
    conn.close()
    return {'action': row['action'], 'target_email': row['target_email']}


def get_ghost_circle_entries(limit=50, severity_filter=None):
    conn = get_connection()
    if severity_filter:
        rows = conn.execute(
            "SELECT * FROM ghost_circle WHERE severity=? ORDER BY created_at DESC LIMIT ?",
            (severity_filter, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ghost_circle ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return rows


def log_activity(service, event, detail='', severity='info'):
    """
    Write a line to the activity_log. Called from listener, telegram, scheduler, skills.
    service: 'listener' | 'telegram' | 'scheduler' | 'terminal' | 'skills'
    event:   short label e.g. 'email_received', 'pipeline_start', 'stage1_done', etc.
    detail:  human-readable context string
    severity: 'info' | 'warning' | 'error' | 'critical' (accepted but not stored — for compat)
    """
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO activity_log (service, event, detail) VALUES (?, ?, ?)",
            (service, event, detail[:500])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f'[Activity] log_activity failed: {e}')


def get_activity_log(limit=100, since_id=0):
    """Return recent activity entries, optionally after a given id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, service, event, detail, created_at FROM activity_log WHERE id > ? ORDER BY id DESC LIMIT ?",
        (since_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]




if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
    print("\n  Initialising Seven's Swarm database...")
    initialise_database()
    conn = get_connection()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    conn.close()
    print(f"  {len(tables)} tables ready:")
    for t in tables:
        print(f"    ✓ {t[0]}")
    print()

