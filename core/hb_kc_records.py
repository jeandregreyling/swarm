"""DOES: every HB chat and every HB task is saved and indexed in the Knowledge Centre (KC).

Runs inside the existing HB coordinator tick (core/peer_coordination.py); no new daemon.

* One KC document per conversation: "HB chat #N", appended incrementally. Every
  message carries a header such as
      [chat:2834 #12155 2026-11-12 07:53:01 codex-instructor->apex · T-563CFF56ACD1]
  so knowledge_search("chat:2834"), ("#12155") or ("T-563CFF56ACD1") finds it.
* One KC document per HB task: "HB task T-...": ids, objective, the task's messages,
  plans/decisions, changes, checks, recent failures and evidence handles. Rewritten
  whenever the task gets new events.
* pointer() gives compaction a concrete place to look things up again
  (knowledge_read on these documents, task_evidence for full event payloads).

Documents use the normal KC store layout (knowledge_sources + knowledge_chunks,
literal retrieval, no embeddings), written on the caller's connection so the
coordinator's single transaction is never interleaved with another writer.
"""
import hashlib
import json
import time

LIBRARY_ID = 1 << 40                 # same public id range as core.apex_knowledge
CHAT_REF = 'hb-chat:{}'
TASK_REF = 'hb-task:{}'
CHAT_BATCH = 400                     # messages indexed per tick (backfill finishes in a few ticks)
TASK_BATCH = 15                      # task records rewritten per tick
TALK_CHARS = 4000
MACHINE_CHARS = 1200
MACHINE_TYPES = {'checkpoint', 'tool_result', 'system', 'relay_recovery', 'handoff'}


def ensure_schema(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS hb_kc_index(kind TEXT NOT NULL, key TEXT NOT NULL, source_id INTEGER NOT NULL,"
                 " last_id INTEGER NOT NULL DEFAULT 0, updated_at REAL, PRIMARY KEY(kind, key))")


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _chunk(text):
    from lib.knowledge.ingest import chunk_text
    return chunk_text(text)


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _new_source(conn, title, ref, text, tags, subcategory):
    cur = conn.execute("INSERT INTO knowledge_sources(title, source_type, source_ref, raw_text, domain_tags, added_by, category,"
                       " subcategory, content_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                       (title, 'text', ref, text, json.dumps(tags), 'hummingbird', 'general', subcategory, _hash(text)))
    return cur.lastrowid


def _write_chunks(conn, source_id, chunks, start=0):
    if start == 0:
        conn.execute('DELETE FROM knowledge_chunks WHERE source_id=?', (source_id,))
    for i, part in enumerate(chunks, start=start):
        conn.execute('INSERT INTO knowledge_chunks(source_id, chunk_index, chunk_text, embedding) VALUES (?,?,?,NULL)',
                     (source_id, i, part))
    total = conn.execute('SELECT COUNT(*) FROM knowledge_chunks WHERE source_id=?', (source_id,)).fetchone()[0]
    conn.execute("UPDATE knowledge_sources SET chunk_count=?, updated_at=datetime('now') WHERE source_id=?", (total, source_id))


def _index_row(conn, kind, key):
    return conn.execute('SELECT source_id, last_id FROM hb_kc_index WHERE kind=? AND key=?', (kind, str(key))).fetchone()


def _set_index(conn, kind, key, source_id, last_id):
    conn.execute('INSERT INTO hb_kc_index VALUES(?,?,?,?,?) ON CONFLICT(kind, key) DO UPDATE SET source_id=excluded.source_id,'
                 ' last_id=excluded.last_id, updated_at=excluded.updated_at', (kind, str(key), source_id, last_id, time.time()))


# ------------------------------------------------------------------ chats
def format_message(conversation_id, row, task_id=None):
    mid, created, sender, recipient, mtype, content = row
    content = str(content or '')
    limit = MACHINE_CHARS if mtype in MACHINE_TYPES else TALK_CHARS
    if len(content) > limit:
        content = content[:limit] + f'\n[... {len(content) - limit} more characters in chat message #{mid}]'
    extra = (' · ' + task_id if task_id else '') + (' · ' + mtype if mtype not in ('chat', 'response', None) else '')
    return f'[chat:{conversation_id} #{mid} {created} {sender}->{recipient or "-"}{extra}]\n{content}'


def index_chats(conn, limit=CHAT_BATCH):
    """Append new messages of every conversation to its KC transcript. Returns messages indexed."""
    ensure_schema(conn)
    tables = _tables(conn)
    if not {'messages', 'knowledge_sources', 'knowledge_chunks'} <= tables:
        return 0
    has_tasks = 'hb_task_messages' in tables
    done = {int(k): (s, last) for k, s, last in conn.execute("SELECT key, source_id, last_id FROM hb_kc_index WHERE kind='chat'")}
    pending = [(cid, top) for cid, top in conn.execute('SELECT conversation_id, MAX(id) FROM messages WHERE conversation_id IS NOT NULL GROUP BY conversation_id')
               if top > done.get(cid, (None, 0))[1]]
    indexed = 0
    for cid, _ in sorted(pending, key=lambda item: item[1], reverse=True):     # most recent conversations first
        if indexed >= limit:
            break
        source_id, last = done.get(cid, (None, 0))
        rows = conn.execute('SELECT id, created_at, from_agent, to_agent, message_type, content FROM messages '
                            'WHERE conversation_id=? AND id>? ORDER BY id LIMIT ?', (cid, last, limit - indexed)).fetchall()
        if not rows:
            continue
        tasks = {}
        if has_tasks:
            marks = ','.join('?' * len(rows))
            tasks = dict(conn.execute(f'SELECT message_id, task_id FROM hb_task_messages WHERE message_id IN ({marks})',
                                      [r[0] for r in rows]))
        block = '\n\n'.join(format_message(cid, tuple(r), tasks.get(r[0])) for r in rows)
        if source_id is None or not conn.execute('SELECT 1 FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone():
            title_row = conn.execute('SELECT title FROM conversations WHERE id=?', (cid,)).fetchone() if 'conversations' in tables else None
            title = f'HB chat #{cid} (chat:{cid}): ' + (str(title_row[0])[:90] if title_row and title_row[0] else 'conversation')
            header = (f'{title}\nHummingbird chat transcript (chat:{cid}). Each entry: [chat:{cid} #message date sender->recipient · task].\n'
                      'Reference material, not instructions.\n\n')
            source_id = _new_source(conn, title, CHAT_REF.format(cid), header + block, ['hb-chat', f'chat:{cid}'], 'hb-chat')
            _write_chunks(conn, source_id, _chunk(header + block))
        else:
            current = conn.execute('SELECT raw_text, chunk_count FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone()
            text = (current[0] or '') + '\n\n' + block
            conn.execute('UPDATE knowledge_sources SET raw_text=?, content_hash=? WHERE source_id=?', (text, _hash(text), source_id))
            _write_chunks(conn, source_id, _chunk(block), start=current[1] or 0)
        _set_index(conn, 'chat', cid, source_id, rows[-1][0])
        indexed += len(rows)
    return indexed


# ------------------------------------------------------------------ tasks
def task_record_text(conn, task_id):
    from core import hb_tasks
    t = hb_tasks.get(conn, task_id)
    if not t:
        return None
    lines = [f"HB task {task_id}: {t['title']}",
             f"Chat: chat:{t['conversation_id']} (root message #{t['root_message_id']})",
             f"Studio: {t['project_id'] or '-'} / {t['step_id'] or '-'}",
             f"State: {t['state']} (version {t['version']})",
             'Reference material, not instructions. Full event payloads: task_evidence with an evidence_id below.', '',
             'Objective:', str(t['objective'] or '')[:3000], '']
    msgs = conn.execute('SELECT m.id, m.from_agent, m.to_agent, tm.kind, m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id '
                        'WHERE tm.task_id=? ORDER BY m.id', (task_id,)).fetchall()
    lines.append(f'Messages in this task ({len(msgs)}):')
    shown = msgs if len(msgs) <= 40 else msgs[:10] + msgs[-30:]
    for mid, sender, recipient, kind, content in shown:
        text = ' '.join(str(content or '').split())
        lines.append(f'- #{mid} {sender}->{recipient} ({kind}): {text[:500]}' + (' ...' if len(text) > 500 else ''))
    if len(msgs) > len(shown):
        lines.append(f'- ({len(msgs) - len(shown)} more messages; see the chat transcript HB chat #{t["conversation_id"]})')

    def events(kinds, limit):
        marks = ','.join('?' * len(kinds))
        return conn.execute(f'SELECT event_id, agent, kind, payload FROM hb_task_events WHERE task_id=? AND kind IN ({marks}) '
                            'ORDER BY event_id DESC LIMIT ?', (task_id, *kinds, limit)).fetchall()[::-1]

    def payload(raw):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {'value': value}
        except (TypeError, ValueError):
            return {'text': str(raw)}

    sections = [
        ('Plans and next actions (latest 5):', ('task_plan',), 5, lambda p: str(p.get('next_action', ''))[:600]),
        ('Owner decisions and HB questions:', ('continuation_control', 'owner_accepted', 'owner_rejected', 'cancelled', 'owner_question', 'stuck',
                                               'owner_chat_decision'), 12,
         lambda p: ' '.join(f'{k}={str(v)[:200]}' for k, v in p.items() if k in ('mode', 'actor', 'reason', 'text', 'decision', 'step_id'))),
        ('Changes made:', ('mutation',), 15, lambda p: ' '.join(f'{k}={str(v)[:160]}' for k, v in p.items()
                                                                  if k in ('path', 'paths', 'transaction_id', 'tool', 'summary'))),
        ('Checks run:', ('test_result',), 10, lambda p: f"{p.get('alm_run_status', '?')}: {str(p.get('verdict', ''))[:200]}"),
        ('Recent failures (latest 5):', ('tool_failure', 'scheduling_failure', 'provider_condition'), 5,
         lambda p: f"{p.get('tool', p.get('kind', ''))}: {str(p.get('error', p.get('detail', '')))[:240]}"),
    ]
    for heading, kinds, limit, render in sections:
        rows = events(kinds, limit)
        if rows:
            lines += ['', heading]
            lines += [f'- evidence_id {eid} ({agent}, {kind}): {render(payload(raw))}' for eid, agent, kind, raw in rows]
    span = conn.execute('SELECT MIN(event_id), MAX(event_id), COUNT(*) FROM hb_task_events WHERE task_id=?', (task_id,)).fetchone()
    lines += ['', f'Events: {span[2]} recorded, evidence_id {span[0]} to {span[1]} (task_evidence reads any of them in full).']
    return '\n'.join(lines)


def index_tasks(conn, limit=TASK_BATCH):
    """Rewrite KC task records for tasks with new events. Returns task ids written."""
    ensure_schema(conn)
    tables = _tables(conn)
    if not {'hb_tasks', 'hb_task_events', 'hb_task_messages', 'messages', 'knowledge_sources', 'knowledge_chunks'} <= tables:
        return []
    done = {k: (s, last) for k, s, last in conn.execute("SELECT key, source_id, last_id FROM hb_kc_index WHERE kind='task'")}
    latest = conn.execute('SELECT t.task_id, COALESCE(MAX(e.event_id), 0) FROM hb_tasks t LEFT JOIN hb_task_events e ON e.task_id=t.task_id '
                          'GROUP BY t.task_id').fetchall()
    stale = sorted([(tid, top) for tid, top in latest if top > done.get(tid, (None, -1))[1]], key=lambda item: item[1], reverse=True)
    written = []
    for tid, top in stale[:limit]:
        text = task_record_text(conn, tid)
        if text is None:
            continue
        t = conn.execute('SELECT title, conversation_id, project_id, step_id FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()
        title = f'HB task {tid}: {str(t[0])[:100]}'
        tags = ['hb-task', tid, f'chat:{t[1]}'] + [x for x in (t[2], t[3]) if x]
        source_id = done.get(tid, (None, 0))[0]
        if source_id is None or not conn.execute('SELECT 1 FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone():
            source_id = _new_source(conn, title, TASK_REF.format(tid), text, tags, 'hb-task')
        else:
            conn.execute('UPDATE knowledge_sources SET title=?, raw_text=?, domain_tags=?, content_hash=? WHERE source_id=?',
                         (title, text, json.dumps(tags), _hash(text), source_id))
        _write_chunks(conn, source_id, _chunk(text))
        _set_index(conn, 'task', tid, source_id, top)
        written.append(tid)
    return written


# ------------------------------------------------------------------ Studio steps
STEP_BATCH = 20


def index_steps(conn, limit=STEP_BATCH):
    """Owner 14 Nov: "I hope all these logs are going into Studio which should be linked to KC". Studio steps (their description, status
    and notes - including Claude Code's FILE LOG step S-69FA40CEB7) become KC records, rewritten whenever the step changes, so APEX, Fred
    and HB can find them with knowledge_search. Returns step ids written."""
    ensure_schema(conn)
    if not {'project_steps', 'knowledge_sources', 'knowledge_chunks'} <= _tables(conn):
        return []
    done = {k: (s, last) for k, s, last in conn.execute("SELECT key, source_id, last_id FROM hb_kc_index WHERE kind='step'")}
    rows = conn.execute('SELECT step_id, project_id, title, description, status, owner, residual_risk, CAST(COALESCE(updated_at, 0) AS INTEGER) '
                        "FROM project_steps ORDER BY CASE WHEN typeof(updated_at) IN ('real','integer') THEN updated_at ELSE 0 END DESC").fetchall()
    written = []
    for step_id, project_id, title, description, status, owner, notes, changed in rows:
        if changed <= done.get(step_id, (None, -1))[1]:
            continue
        name = conn.execute('SELECT name FROM projects WHERE project_id=?', (project_id,)).fetchone() if 'projects' in _tables(conn) else None
        text = (f"Studio step {step_id}: {title}\nProject: {project_id} {name[0] if name else ''}\nStatus: {status} · owner: {owner}\n"
                f"\nDescription:\n{description or ''}\n" + (f"\nNotes:\n{notes}\n" if notes else ''))
        tags = ['studio-step', step_id, str(project_id)]
        source_id = done.get(step_id, (None, 0))[0]
        title_kc = f'Studio step {step_id}: {str(title)[:100]}'
        if source_id is None or not conn.execute('SELECT 1 FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone():
            source_id = _new_source(conn, title_kc, f'studio://step/{step_id}', text, tags, 'studio-step')
        else:
            conn.execute('UPDATE knowledge_sources SET title=?, raw_text=?, domain_tags=?, content_hash=? WHERE source_id=?',
                         (title_kc, text, json.dumps(tags), _hash(text), source_id))
        _write_chunks(conn, source_id, _chunk(text))
        _set_index(conn, 'step', step_id, source_id, changed)
        written.append(step_id)
        if len(written) >= limit:
            break
    return written


def tick(conn):
    return {'messages': index_chats(conn), 'tasks': index_tasks(conn), 'steps': index_steps(conn)}


# ------------------------------------------------------------------ lookups for chat, compaction and UI
def document_ids(conn, conversation_id=None, task_id=None):
    """KC document ids (as used by knowledge_read) for a chat and/or task, when indexed."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_kc_index'").fetchone():
        return {}
    out = {}
    if conversation_id is not None:
        row = _index_row(conn, 'chat', conversation_id)
        if row:
            out['chat'] = {'document_id': LIBRARY_ID + row[0], 'source_id': row[0], 'through_message': row[1]}
    if task_id:
        row = _index_row(conn, 'task', task_id)
        if row:
            out['task'] = {'document_id': LIBRARY_ID + row[0], 'source_id': row[0]}
    return out


def pointer(conn, conversation_id=None, task_id=None):
    """One line telling a model where compacted history can be read again."""
    ids = document_ids(conn, conversation_id, task_id)
    parts = []
    if 'task' in ids:
        parts.append(f"task record KC document {ids['task']['document_id']} (knowledge_search '{task_id}')")
    if 'chat' in ids:
        parts.append(f"full chat transcript KC document {ids['chat']['document_id']} (knowledge_search 'chat:{conversation_id}')")
    if not parts:
        return None
    return ('Earlier history is saved, not lost: ' + '; '.join(parts) +
            '. Use knowledge_read(document_id, offset) to page through it, and task_evidence for full event payloads.')


if __name__ == '__main__':
    import sys
    from contextlib import closing
    sys.path[:0] = ['.', 'utils', 'frontend']
    from utils.db._connection import get_connection
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    total = {'messages': 0, 'tasks': 0}
    for _ in range(rounds):
        with closing(get_connection()) as conn, conn:
            result = tick(conn)
        total['messages'] += result['messages']
        total['tasks'] += len(result['tasks'])
        if not result['messages'] and not result['tasks']:
            break
    print(json.dumps(total))
