"""
file_versioning.py — Seven's Swarm File Versioning & Change Tracking
═══════════════════════════════════════════════════════════════════════════════
Database-backed file version control with before/after content storage.
Point-in-time restoration without duplication. All changes logged with agent 
attribution and exact timestamps (HH:MM:SS precision).

Version Store: /home/seven/swarm/.swarm_versions/ (for file metadata)
Database Store: swarm_memory.db table:file_versions (for content & history)

Usage:
  from file_versioning import track_file_change, get_version_history, restore_to_date
  
  # Log a file change
  track_file_change(
    file_path='/home/seven/swarm/test.py',
    agent='Nine',
    action='write',  # 'write', 'edit', 'delete'
    content_before='original code...',
    content_after='new code...'
  )
  
  # Get version history for a file
  history = get_version_history('/home/seven/swarm/test.py', limit=10)
  
  # Restore file to specific date
  restore_to_date('/home/seven/swarm/test.py', date='2026-03-26')

═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
from system_clock import get_timestamp, get_timestamp_date
from database import get_connection

sys.path.insert(0, '/home/seven/swarm')

# Version metadata directory
VERSIONS_DIR = '/home/seven/swarm/.swarm_versions'
RESTORE_BIN_DIR = '/home/seven/swarm/.restore_bin'


def _ensure_dirs():
    """Create version and restore bin directories if they don't exist."""
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    os.makedirs(RESTORE_BIN_DIR, exist_ok=True)


def _init_versioning_tables():
    """Create file_versions and audit_log tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS file_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            timestamp_date TEXT NOT NULL,
            content_before TEXT,
            content_after TEXT,
            commit_hash TEXT,
            checkpoint_tag TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_file_versions_path ON file_versions(file_path);
        CREATE INDEX IF NOT EXISTS idx_file_versions_date ON file_versions(timestamp_date);
        CREATE INDEX IF NOT EXISTS idx_file_versions_agent ON file_versions(agent);
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checkpoint_date TEXT UNIQUE NOT NULL,
            description TEXT,
            created_by TEXT DEFAULT 'system',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def track_file_change(file_path, agent, action, content_before=None, content_after=None, checkpoint_tag=None):
    """
    Log a file change with before/after content.
    
    Args:
        file_path: Absolute path to file
        agent: Agent name making the change (e.g., 'Nine', 'Copilot', 'shell_agent')
        action: 'write', 'edit', or 'delete'
        content_before: Content before change (None for new files)
        content_after: Content after change (None for deletes)
        checkpoint_tag: Optional tag for daily checkpoints (e.g., 'daily_2026-03-26')
    
    Returns:
        Version record ID
    """
    _ensure_dirs()
    _init_versioning_tables()
    
    timestamp = get_timestamp()           # "2026-03-26 14:45:33"
    date_only = get_timestamp_date()      # "2026-03-26"
    
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO file_versions 
        (file_path, agent, action, timestamp, timestamp_date, content_before, 
         content_after, checkpoint_tag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (file_path, agent, action, timestamp, date_only, content_before, 
          content_after, checkpoint_tag))
    
    version_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"[FileVersioning] {timestamp} {agent} → {action} {file_path} (v{version_id})")
    return version_id


def get_version_history(file_path, limit=20):
    """
    Get version history for a specific file.
    
    Args:
        file_path: Absolute path to file
        limit: Maximum number of versions to return
    
    Returns:
        List of version records (dicts)
    """
    _init_versioning_tables()
    
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, agent, action, timestamp, timestamp_date, 
               length(content_before) as before_size, 
               length(content_after) as after_size,
               checkpoint_tag
        FROM file_versions
        WHERE file_path = ?
        ORDER BY id DESC
        LIMIT ?
    """, (file_path, limit)).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def restore_to_date(file_path, date):
    """
    Find the last committed version of a file before given date 
    and move current version to restore bin for review.
    
    Args:
        file_path: Absolute path to file
        date: Date string 'YYYY-MM-DD' to restore to
    
    Returns:
        Dictionary with 'status', 'versions_found', 'backup_location'
    """
    _ensure_dirs()
    _init_versioning_tables()
    
    conn = get_connection()
    
    # Find all versions from the given date forward
    rows = conn.execute("""
        SELECT id, agent, action, timestamp, content_after
        FROM file_versions
        WHERE file_path = ? AND timestamp_date >= ?
        ORDER BY timestamp ASC
    """, (file_path, date)).fetchall()
    
    versions_found = len(rows)
    
    if versions_found == 0:
        conn.close()
        return {
            'status': 'no_changes_found',
            'file_path': file_path,
            'date': date,
            'versions_found': 0
        }
    
    # Move current file to restore bin
    if os.path.exists(file_path):
        bin_subdir = os.path.join(RESTORE_BIN_DIR, os.path.basename(file_path))
        os.makedirs(bin_subdir, exist_ok=True)
        
        timestamp = get_timestamp().replace(' ', '_').replace(':', '-')
        backup_path = os.path.join(bin_subdir, f"{timestamp}.backup")
        
        with open(file_path, 'r') as f:
            current_content = f.read()
        
        with open(backup_path, 'w') as f:
            f.write(current_content)
        
        # Get the first version after the date to restore
        first_change = rows[0]
        restored_content = first_change['content_after']
        
        # Write the restored version (if it has content)
        if restored_content:
            with open(file_path, 'w') as f:
                f.write(restored_content)
        
        conn.close()
        
        return {
            'status': 'restored_for_review',
            'file_path': file_path,
            'date': date,
            'versions_found': versions_found,
            'backup_location': backup_path,
            'first_change_by': first_change['agent'],
            'first_change_time': first_change['timestamp']
        }
    else:
        conn.close()
        return {
            'status': 'file_not_found',
            'file_path': file_path,
            'date': date,
            'versions_found': versions_found
        }


def create_daily_checkpoint(checkpoint_date, description=''):
    """
    Create a daily checkpoint tag for point-in-time restoration.
    
    Args:
        checkpoint_date: Date string 'YYYY-MM-DD'
        description: Optional description
    
    Returns:
        Checkpoint record ID
    """
    _init_versioning_tables()
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO daily_checkpoints 
            (checkpoint_date, description, created_by)
            VALUES (?, ?, 'system')
        """, (checkpoint_date, description))
        
        checkpoint_id = cursor.lastrowid
        conn.commit()
        
        # Tag all versions from this date with the checkpoint tag
        tag = f'daily_{checkpoint_date}'
        conn.execute("""
            UPDATE file_versions
            SET checkpoint_tag = ?
            WHERE timestamp_date = ? AND checkpoint_tag IS NULL
        """, (tag, checkpoint_date))
        conn.commit()
        
        print(f"[FileVersioning] Created daily checkpoint: {checkpoint_date}")
        return checkpoint_id
    
    except Exception as e:
        print(f"[FileVersioning] Checkpoint creation failed: {e}")
        return None
    
    finally:
        conn.close()


def get_checkpoint_history(limit=30):
    """Get recent daily checkpoints for restoration options."""
    _init_versioning_tables()
    
    conn = get_connection()
    rows = conn.execute("""
        SELECT checkpoint_date, description, created_at
        FROM daily_checkpoints
        ORDER BY checkpoint_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


if __name__ == '__main__':
    print("[FileVersioning] Module loaded successfully")
    print(f"Versions dir: {VERSIONS_DIR}")
    print(f"Restore bin: {RESTORE_BIN_DIR}")
