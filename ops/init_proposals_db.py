from utils.db._connection import get_connection

conn = get_connection()
conn.execute('''
    CREATE TABLE IF NOT EXISTS work_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id TEXT UNIQUE,
        agent TEXT DEFAULT 'studio',
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        git_branch TEXT,
        source_node TEXT DEFAULT 'proposals_api'
    )
''')
conn.commit()
conn.close()

print("✅ Verified central swarm_memory.db work_proposals table")
