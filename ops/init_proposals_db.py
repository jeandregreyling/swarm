import sqlite3
import os

DB_PATH = os.path.expanduser("~/swarm/studio_proposals.db")

conn = sqlite3.connect(DB_PATH)
conn.execute('''
    CREATE TABLE IF NOT EXISTS work_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT,
        rejected_at TEXT,
        promoted_at TEXT,
        git_branch TEXT,
        studio_link TEXT
    )
''')
conn.commit()
conn.close()

print("✅ Created studio_proposals.db with work_proposals table")
print(f"Location: {DB_PATH}")
