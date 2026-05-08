"""
db.memory — Shared memory, agent-specific memory, project docs.
"""
from ._connection import get_connection, logger, AGENT_POOL_MAP


def save_memory(agent, subject, content, tags='', importance=5):
    conn = get_connection()
    conn.execute(
        "INSERT INTO memory (agent,subject,content,tags,importance,source) VALUES (?,?,?,?,?,?)",
        (agent, subject[:200], content, tags, importance, agent.lower())
    )
    conn.commit()
    conn.close()


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
        # STEP-MEMORIES-HIVE-KNOWLEDGE-SYNC-20260430 — never silently drop
        # an agent memory write. Unknown agents fall back to the shared
        # 'memory' pool with the agent name preserved in the agent column.
        logger.warning(f"No personal pool for agent: {agent_name} — falling back to shared memory pool")
        table = 'memory'
    conn = get_connection()
    # All dedicated agent tables have a 'source' column; only the legacy shared 'memory'
    # table (librarian/duck/sniffles) doesn't. Check by table name.
    if table != 'memory':
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


def search_project_docs(query='', limit=3):
    """
    Keyword search across project_docs sections.
    Returns list of dicts with doc_name and content.
    Used by orchestrator to inject relevant architecture/context into agent prompts.
    """
    conn = get_connection()
    if query:
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


def get_project_docs(tag='all'):
    """Return docs tagged for a specific agent or 'all'. Used for agent context injection."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT doc_name, content FROM project_docs WHERE tags IS NULL OR tags='all' OR tags LIKE ? ORDER BY updated_at DESC",
        (f'%{tag}%',)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
