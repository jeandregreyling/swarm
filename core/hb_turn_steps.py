"""Practice 181 (owner 20 Nov 2026: "the thinking bubbles also disappear completely after the thought is done, I can't see what was the
process unless it's running actively, this needs to be saved"): the step lines APEX reports during a turn (Practice 176) are stored with
the reply message, and main chat shows them under the answer as "How APEX got here (N steps)".

save(conn, conversation_id, message_id, steps)   steps: [{'t': seconds since the turn started, 'text': line}]
for_messages(conn, ids) -> {message_id: steps}"""
import json
import time


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_turn_steps(message_id INTEGER PRIMARY KEY, conversation_id INTEGER, steps TEXT, created_at REAL)')


def save(conn, conversation_id, message_id, steps):
    steps = [s for s in (steps or []) if isinstance(s, dict) and str(s.get('text') or '').strip()][-200:]
    if not message_id or not steps:
        return False
    ensure(conn)
    conn.execute('INSERT OR REPLACE INTO hb_turn_steps VALUES (?,?,?,?)', (int(message_id), conversation_id, json.dumps(steps), time.time()))
    return True


def for_messages(conn, ids):
    ids = [int(i) for i in ids if str(i).isdigit()][:200]
    if not ids:
        return {}
    ensure(conn)
    rows = conn.execute(f"SELECT message_id, steps FROM hb_turn_steps WHERE message_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    out = {}
    for mid, raw in rows:
        try:
            out[int(mid)] = json.loads(raw)
        except (TypeError, ValueError):
            pass
    return out
