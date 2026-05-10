"""
time_machine.py — Seven's Swarm Time Machine - Point-in-Time Restore System
═══════════════════════════════════════════════════════════════════════════════
Backup and restore system with daily checkpoints. Uses git-like commit model
with before/after content diffs. No duplication - uses database references.

Usage:
  from time_machine import create_checkpoint, restore_to_checkpoint, get_checkpoint_list
  
  # Create a daily checkpoint
  checkpoint_id = create_checkpoint(date='2026-03-26', description='Stable version')
  
  # List available checkpoints
  checkpoints = get_checkpoint_list()
  
  # Restore a file to a specific checkpoint
  restore_to_checkpoint(
    file_path='/home/seven/swarm/test.py',
    checkpoint_date='2026-03-24'
  )

═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
from datetime import datetime, timedelta
from system_clock import get_timestamp_date, get_system_clock
from file_versioning import track_file_change, get_version_history, create_daily_checkpoint
from database import get_connection

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _SWARM_ROOT)


def create_checkpoint(date=None, description=''):
    """
    Create a daily checkpoint for point-in-time restoration.
    
    Args:
        date: Date string 'YYYY-MM-DD' (defaults to today)
        description: Optional description of checkpoint
    
    Returns:
        Checkpoint ID
    """
    if date is None:
        date = get_timestamp_date()
    
    checkpoint_id = create_daily_checkpoint(date, description)
    print(f"[TimeMachine] Checkpoint created: {date}")
    return checkpoint_id


def get_checkpoint_list(limit=30):
    """Get list of available checkpoints for restoration."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT checkpoint_date, description
        FROM daily_checkpoints
        ORDER BY checkpoint_date DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    
    return [dict(r) for r in rows]


def restore_to_checkpoint(file_path, checkpoint_date):
    """
    Restore a file to a specific checkpoint date.
    
    Args:
        file_path: Absolute path to file
        checkpoint_date: Date string 'YYYY-MM-DD'
    
    Returns:
        Restoration result dict
    """
    print(f"[TimeMachine] Restoring {file_path} to {checkpoint_date}")
    
    # Use file_versioning restore logic
    from file_versioning import restore_to_date
    result = restore_to_date(file_path, checkpoint_date)
    
    return result


def auto_checkpoint():
    """
    Automatic daily checkpoint creation (called by scheduler).
    Creates checkpoint for today if not already created.
    """
    today = get_timestamp_date()
    
    # Check if checkpoint already exists for today
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM daily_checkpoints WHERE checkpoint_date = ?",
        (today,)
    ).fetchone()
    conn.close()
    
    if not existing:
        create_checkpoint(date=today, description=f'Automatic daily checkpoint')
        return True
    
    return False


def cleanup_old_backups(days=90):
    """
    Clean up restore bin entries older than specified days.
    
    Args:
        days: Remove backups older than N days (default: 90)
    
    Returns:
        Number of backups removed
    """
    from file_versioning import RESTORE_BIN_DIR
    
    if not os.path.exists(RESTORE_BIN_DIR):
        return 0
    
    cutoff_date = datetime.now() - timedelta(days=days)
    count = 0
    
    for root, dirs, files in os.walk(RESTORE_BIN_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            if file_mtime < cutoff_date:
                try:
                    os.remove(file_path)
                    count += 1
                except OSError:
                    pass
    
    return count


if __name__ == '__main__':
    print("[TimeMachine] Module loaded successfully")
    print(f"Time: {get_system_clock().get_full_string()}")
    print(f"Checkpoints available: {len(get_checkpoint_list())}")
