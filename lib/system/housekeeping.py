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

def curate_agent_memories(batch_size=40, model='gemma3:latest'):
    """
    AI-powered memory curation via Gemma3 (Ollama).
    For each agent table, pulls recent low-to-mid importance memories in batches,
    asks Gemma to strip fluff while preserving detail, then rewrites the rows.
    Exact duplicates and near-dupes are collapsed. High-importance (>=8) memories
    are never touched.
    """
    import requests, json as _json
    from utils.db._connection import AGENT_POOL_MAP

    OLLAMA_URL = 'http://localhost:11434/api/generate'

    # Build set of tables to curate — skip shared 'memory' (too broad, handled by archive)
    tables_done = set()
    agent_table_pairs = []
    for agent, table in AGENT_POOL_MAP.items():
        if table == 'memory':
            continue  # shared table — don't bulk-rewrite
        if table not in tables_done:
            agent_table_pairs.append((agent, table))
            tables_done.add(table)

    total_curated = 0
    total_removed = 0

    for agent, table in agent_table_pairs:
        conn = get_connection()
        try:
            rows = conn.execute(
                f"SELECT id, subject, content, importance FROM {table} "
                f"WHERE archived=0 AND importance < 8 "
                f"ORDER BY created_at DESC LIMIT ?", (batch_size,)
            ).fetchall()
        except Exception:
            conn.close()
            continue

        if not rows:
            conn.close()
            continue

        # Build prompt
        entries = '\n'.join(
            f"[{r['id']}] subject: {r['subject']}\ncontent: {r['content']}\nimportance: {r['importance']}"
            for r in rows
        )
        prompt = (
            "You are a memory curator for an AI agent. "
            "Below are memory entries. Your job:\n"
            "1. Remove entries that are vague, redundant, or contain no useful detail (return their IDs as DELETE list)\n"
            "2. For entries worth keeping, tighten the content — remove filler, preserve all specific facts, names, numbers, decisions\n"
            "3. Merge near-duplicate entries into one (keep the highest importance)\n\n"
            "Return ONLY valid JSON: {\"delete\": [id, ...], \"update\": [{\"id\": id, \"subject\": \"...\", \"content\": \"...\"}]}\n\n"
            f"ENTRIES:\n{entries}"
        )

        try:
            resp = requests.post(OLLAMA_URL, json={
                'model': model, 'prompt': prompt, 'stream': False,
                'options': {'temperature': 0.1, 'num_predict': 2048}
            }, timeout=120)
            raw = resp.json().get('response', '')
            # Extract JSON from response
            start = raw.find('{')
            end   = raw.rfind('}') + 1
            if start == -1 or end == 0:
                print(f'[Vortex] {table}: no JSON in response — skipped')
                conn.close()
                continue
            result = _json.loads(raw[start:end])
        except Exception as e:
            print(f'[Vortex] {table}: curation error — {e}')
            conn.close()
            continue

        # Apply deletions
        to_delete = [int(i) for i in result.get('delete', []) if str(i).isdigit()]
        if to_delete:
            placeholders = ','.join('?' * len(to_delete))
            conn.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", to_delete)
            total_removed += len(to_delete)

        # Apply updates
        for upd in result.get('update', []):
            try:
                conn.execute(
                    f"UPDATE {table} SET subject=?, content=? WHERE id=?",
                    (str(upd['subject'])[:200], str(upd['content']), int(upd['id']))
                )
                total_curated += 1
            except Exception:
                pass

        conn.commit()
        conn.close()
        print(f'[Vortex] {table}: {len(to_delete)} removed, {len(result.get("update",[]))} tightened')

    print(f'[Vortex] Curation complete — {total_removed} deleted, {total_curated} rewritten')
    return total_removed, total_curated


def run_housekeeping():
    print(f'\n=== Librarian Housekeeping {datetime.now().strftime("%Y-%m-%d %H:%M")} ===')
    archived = archive_old_memories(days_old=30, min_importance=5)
    dupes = deduplicate_memories()
    print(f'\n[Vortex] Starting AI memory curation...')
    try:
        removed, rewritten = curate_agent_memories()
        print(f'[Vortex] Curation: {removed} removed, {rewritten} rewritten')
    except Exception as e:
        print(f'[Vortex] Curation skipped: {e}')
    print(f'\n[Librarian] Done. Archived: {archived}, Duplicates removed: {dupes}')

    # Agent play time — give idle agents a chance to draft proposals
    try:
        from swarm_tasks import run_play_time
        run_play_time()
    except Exception as e:
        print(f'[Librarian] Play time skipped: {e}')

if __name__ == '__main__':
    run_housekeeping()