"""Practice 236 (S-EEC7B9D03E): one living chat message per task run, updated in place as chunks finish."""
from __future__ import annotations

import time


def ensure_schema(conn):
    conn.execute(
        'CREATE TABLE IF NOT EXISTS hb_chunk_messages('
        'task_id TEXT PRIMARY KEY, conversation_id INTEGER NOT NULL, '
        'message_id INTEGER NOT NULL, updated_at REAL NOT NULL)'
    )


def render(title: str, chunks: list[dict]) -> str:
    """Render one living progress card for a task's chunks (done, current, todo)."""
    total = len(chunks)
    done = sum(1 for c in chunks if c.get('state') == 'done')
    lines = [f"▸ {str(title or 'Task')[:120]} ({done}/{total} chunks done)"]
    for c in chunks:
        st = c.get('state') or 'todo'
        mark = '✓' if st == 'done' else ('▶' if st == 'doing' else '○')
        lines.append(f"  {mark} {c.get('n', '')}. {str(c.get('text') or '')[:160]}")
    return '\n'.join(lines)


def upsert(conn, task: dict, chunks: list[dict], *, now: float | None = None) -> int:
    """Create or update in place the single main-chat message tracking this task's chunks."""
    ensure_schema(conn)
    now = time.time() if now is None else now
    task_id = str(task['task_id'])
    conv_id = int(task.get('conversation_id') or 2845)
    body = render(task.get('title') or task_id, chunks)
    row = conn.execute('SELECT message_id FROM hb_chunk_messages WHERE task_id=?', (task_id,)).fetchone()
    if row:
        mid = int(row[0])
        conn.execute('UPDATE messages SET content=? WHERE id=?', (body, mid))
        conn.execute('UPDATE hb_chunk_messages SET updated_at=? WHERE task_id=?', (now, task_id))
        return mid
    mid = conn.execute(
        "INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
        "VALUES (?,'hummingbird','user',?,'response',0)",
        (conv_id, body),
    ).lastrowid
    conn.execute(
        'INSERT INTO hb_chunk_messages(task_id, conversation_id, message_id, updated_at) VALUES (?,?,?,?)',
        (task_id, conv_id, mid, now),
    )
    return int(mid)


class HBChunkMessage:
    """Compatibility wrapper exposing upsert/render for chunk message tracking."""

    def record(self, conn, task, chunks):
        return upsert(conn, task, chunks)

