import sys
sys.path.insert(0, '/home/seven/swarm')
from database import get_connection
from config import DB_PATH
import sqlite3
from datetime import datetime

def archive_old_memories(days_old=30, min_importance=5):
    print(f'\n[Librarian] Running housekeeping...')
    conn = get_connection()
    c = conn.cursor()
    archived = 0

    # Archive low importance shared memories older than N days
    c.execute('''
        SELECT id, subject, importance, created_at FROM memory
        WHERE importance < ?
        AND created_at < datetime('now', ? || ' days')
        AND agent != 'Gemma'
    ''', (min_importance, f'-{days_old}'))
    old_entries = c.fetchall()

    for entry in old_entries:
        c.execute('DELETE FROM memory WHERE id = ?', (entry[0],))
        archived += 1
        print(f'[Librarian] Archived: {str(entry[1])[:50]} (importance: {entry[2]}, age: {entry[3]})')

    # Archive low importance agent memories older than 60 days
    for table in ['memory_llama', 'memory_qwen', 'memory_eight', 'memory_nine']:
        c.execute(f'''
            SELECT id, subject, importance, created_at FROM {table}
            WHERE importance < ?
            AND created_at < datetime('now', '-60 days')
        ''', (min_importance,))
        old_agent = c.fetchall()
        for entry in old_agent:
            c.execute(f'DELETE FROM {table} WHERE id = ?', (entry[0],))
            archived += 1
            print(f'[Librarian] Archived from {table}: {str(entry[1])[:50]}')

    # Never archive Gemma verdicts — they are permanent
    # Never archive memory_gemma

    conn.commit()
    conn.close()
    print(f'[Librarian] Housekeeping complete. {archived} entries archived.')
    return archived

def deduplicate_memories():
    print('[Librarian] Checking for duplicates...')
    conn = get_connection()
    c = conn.cursor()
    removed = 0

    for table in ['memory', 'memory_llama', 'memory_qwen', 'memory_eight', 'memory_nine']:
        c.execute(f'''
            DELETE FROM {table} WHERE id NOT IN (
                SELECT MIN(id) FROM {table}
                GROUP BY subject, content
            )
        ''')
        removed += c.rowcount

    conn.commit()
    conn.close()
    print(f'[Librarian] Removed {removed} duplicate entries.')
    return removed

def run_housekeeping():
    print(f'\n=== Librarian Housekeeping {datetime.now().strftime("%Y-%m-%d %H:%M")} ===')
    archived = archive_old_memories(days_old=30, min_importance=5)
    dupes = deduplicate_memories()
    print(f'\n[Librarian] Done. Archived: {archived}, Duplicates removed: {dupes}')

    # Agent play time — give idle agents a chance to draft proposals
    try:
        from swarm_tasks import run_play_time
        run_play_time()
    except Exception as e:
        print(f'[Librarian] Play time skipped: {e}')

if __name__ == '__main__':
    run_housekeeping()