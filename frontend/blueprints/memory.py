"""memory.py — Memory routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

memory_bp = Blueprint('memory', __name__)

# Agent memory table mapping — add new agents here only; _memory_search is fully dynamic
_AGENT_TABLES = {
    'llama':     'memory_llama',
    'mistral':   'memory_mistral',
    'qwen':      'memory_qwen',
    'gemma':     'memory_gemma',
    'eight':     'memory_eight',
    'nine':      'memory_nine',
    'ten':       'memory_ten',
    'eleven':    'memory_grok',
    'grok':      'memory_grok',
    'twelve':    'memory_twelve',
    'thirteen':  'memory_thirteen',
    'scholar':   'memory',
    'seeker':    'memory',
    'librarian': 'memory',
    'duck':      'memory',
    'sniffles':  'memory',
}

# Tables that have a `subject` column (vs memory_twelve which doesn't)
_SUBJECT_TABLES = {
    'memory_llama', 'memory_mistral', 'memory_qwen', 'memory_gemma',
    'memory_eight', 'memory_nine', 'memory_ten', 'memory_grok',
}

# Full set of valid tables for write/delete operations — derived from _AGENT_TABLES
_ALL_MEMORY_TABLES = {'memory'} | set(_AGENT_TABLES.values())




def _collect_local_file_memories(query='', agent='', limit=120):
    """Collect local file-based memories from sandpits for UI visibility."""
    sandpit_root = Path('/home/seven/swarm/sandpits')
    if not sandpit_root.exists():
        return []

    query_l = str(query or '').strip().lower()
    agent_l = str(agent or '').strip().lower()
    rows = []

    file_priority = (
        'WHO_AM_I.md',
        'DISPATCHED_WORK.md',
        'THINK.md',
        'MEMORY.md',
        'NOTES.md',
        'notes.md',
    )
    shared_files = ('COORDINATION.md', 'CURRENT_FOCUS.md', 'STALE_PROPOSALS.md')

    def _match_and_add(path: Path, owner_agent: str, importance: int):
        if not path.exists() or not path.is_file():
            return
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return

        subject = path.name
        searchable = f"{subject}\n{content}".lower()
        if query_l and query_l not in searchable:
            return

        synthetic_id = int(uuid.uuid5(uuid.NAMESPACE_URL, str(path)).int % 2_000_000_000)
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')

        rows.append({
            'id': synthetic_id,
            'source_table': 'local_file',
            'agent': owner_agent,
            'subject': subject,
            'content': content[:4000],
            'tags': 'local_file,sandpit',
            'importance': importance,
            'created_at': mtime,
            'source': str(path),
        })

    for child in sandpit_root.iterdir():
        if not child.is_dir():
            continue
        name_l = child.name.lower()
        if agent_l and agent_l not in (name_l,):
            continue

        if name_l == 'shared':
            for fname in shared_files:
                _match_and_add(child / fname, 'shared', 6)
            continue

        for fname in file_priority:
            imp = 8 if fname == 'WHO_AM_I.md' else 5
            _match_and_add(child / fname, name_l, imp)

    rows.sort(key=lambda r: (r.get('created_at') or ''), reverse=True)
    return rows[:max(1, int(limit or 120))]


def _memory_search(query='', min_importance=3, agent='', limit=50):
    """
    Dynamic memory search across all agent tables.
    Adding an agent to _AGENT_TABLES is all that's needed — no SQL changes required.
    """
    conn = get_connection()
    like = f'%{query}%'
    agent_key = agent.lower() if agent else ''

    # ── Single agent query ────────────────────────────────────────────────────
    if agent_key and agent_key in _AGENT_TABLES:
        tbl = _AGENT_TABLES[agent_key]
        if tbl in _SUBJECT_TABLES:
            sql = f"""SELECT id, '{tbl}' AS source_table, agent, subject, content, tags, importance, created_at
                      FROM {tbl}
                      WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                        AND importance >= ? AND archived = 0
                      ORDER BY created_at DESC, importance DESC LIMIT ?"""
            params = (like, like, like, min_importance, limit)
        else:
            sql = f"""SELECT id, '{tbl}' AS source_table, agent, '' AS subject, content, tags, importance, created_at
                      FROM {tbl}
                      WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                        AND importance >= ? AND archived = 0
                      ORDER BY created_at DESC, importance DESC LIMIT ?"""
            params = (like, like, like, min_importance, limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Generic agent not in our tables (fallback to shared memory table) ────
    if agent_key:
        rows = conn.execute(
            """SELECT id, 'memory' AS source_table, agent, subject AS subject, content, tags, importance, created_at
               FROM memory
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0 AND agent LIKE ?
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, f'%{agent}%', limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── All agents — build UNION dynamically from _AGENT_TABLES ──────────────
    seen_tables = set()
    union_parts = []
    params = []

    # Always include the shared memory table first
    union_parts.append(
        """SELECT id, 'memory' AS source_table, agent, subject, content, tags, importance, created_at
           FROM memory
           WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
             AND importance >= ? AND archived = 0"""
    )
    params.extend([like, like, like, min_importance])
    seen_tables.add('memory')

    for tbl in set(_AGENT_TABLES.values()):
        if tbl in seen_tables or tbl == 'memory':
            continue
        seen_tables.add(tbl)
        if tbl in _SUBJECT_TABLES:
            union_parts.append(
                f"""SELECT id, '{tbl}' AS source_table, agent, subject, content, tags, importance, created_at
                   FROM {tbl}
                   WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                     AND importance >= ? AND archived = 0"""
            )
        else:
            union_parts.append(
                f"""SELECT id, '{tbl}' AS source_table, agent, '' AS subject, content, tags, importance, created_at
                   FROM {tbl}
                   WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                     AND importance >= ? AND archived = 0"""
            )
        params.extend([like, like, like, min_importance])

    sql = ' UNION ALL '.join(union_parts) + ' ORDER BY created_at DESC, importance DESC LIMIT ?'
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]



@memory_bp.route('/api/memory')
def api_memory():
    q     = request.args.get('q', '')
    mn    = int(request.args.get('min', 3))
    agent = request.args.get('agent', '')
    limit = max(1, min(int(request.args.get('limit', 120) or 120), 500))
    include_local = request.args.get('include_local', '1') != '0'

    rows = _memory_search(q, mn, agent, limit=limit)
    if include_local:
        local_rows = _collect_local_file_memories(query=q, agent=agent, limit=limit)
        rows = list(rows) + local_rows
        rows.sort(key=lambda r: (r.get('created_at') or ''), reverse=True)
        rows = rows[:limit]

    grouped = {}
    for row in rows:
        agent_name = row.get('agent', 'unknown')
        if agent_name not in grouped:
            grouped[agent_name] = []
        grouped[agent_name].append(row)

    return jsonify({'results': grouped, 'limit': limit})



@memory_bp.route('/api/studio')
def api_studio():
    """Studio cockpit data — agents, queue, config status."""
    status = get_system_status()
    conn = get_connection()
    queue_info = conn.execute('SELECT COUNT(*) as count FROM queue').fetchone()
    conn.close()
    return jsonify({
        'queue_length': queue_info['count'] if queue_info else 0,
        'system_load': status.get('cpu_percent', 0),
        'memory_usage': status.get('ram_percent', 0),
        'active_model': status.get('active_model', 'none'),
    })



@memory_bp.route('/api/memory/bulk', methods=['PATCH'])
def bulk_update_memory():
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list) or not entries:
        return jsonify({'error': 'entries required'}), 400

    updates = data.get('updates') or {}
    if not isinstance(updates, dict) or not updates:
        return jsonify({'error': 'updates required'}), 400

    conn = get_connection()
    try:
        updated_entries = []
        skipped = []

        for item in entries:
            if not isinstance(item, dict):
                skipped.append({'entry': item, 'reason': 'invalid entry payload'})
                continue

            row_id = item.get('id')
            table = str(item.get('table') or 'memory').strip()
            if not row_id:
                skipped.append({'entry': item, 'reason': 'missing id'})
                continue
            if table not in _ALL_MEMORY_TABLES:
                skipped.append({'id': row_id, 'table': table, 'reason': 'invalid table'})
                continue

            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
            if not row:
                skipped.append({'id': row_id, 'table': table, 'reason': 'memory row not found'})
                continue

            row_updates = []
            params = []

            if 'subject' in updates and 'subject' in cols:
                row_updates.append('subject=?')
                params.append(str(updates.get('subject') or '').strip()[:300])

            if 'content' in updates and 'content' in cols:
                row_updates.append('content=?')
                params.append(str(updates.get('content') or ''))

            append_text = str(updates.get('append') or '').strip()
            if append_text and 'content' in cols:
                current = str(row['content'] or '')
                merged = current + ('\n\n' if current else '') + append_text
                row_updates.append('content=?')
                params.append(merged)

            if 'tags' in updates and 'tags' in cols:
                row_updates.append('tags=?')
                params.append(str(updates.get('tags') or '').strip()[:400])

            if 'importance' in updates and 'importance' in cols:
                try:
                    imp = int(updates.get('importance'))
                except Exception:
                    skipped.append({'id': row_id, 'table': table, 'reason': 'importance must be an integer'})
                    continue
                if imp < 1 or imp > 10:
                    skipped.append({'id': row_id, 'table': table, 'reason': 'importance must be 1-10'})
                    continue
                row_updates.append('importance=?')
                params.append(imp)

            if not row_updates:
                skipped.append({'id': row_id, 'table': table, 'reason': 'no applicable updatable fields'})
                continue

            if 'updated_at' in cols:
                row_updates.append('updated_at=?')
                params.append(datetime.now(timezone.utc).isoformat())

            params.append(row_id)
            conn.execute(f"UPDATE {table} SET {', '.join(row_updates)} WHERE id=?", tuple(params))
            updated_entries.append({'id': row_id, 'table': table})

        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True, 'updated': updated_entries, 'skipped': skipped})


@memory_bp.route('/api/memory/bulk', methods=['DELETE'])
def bulk_delete_memory():
    data = request.get_json(silent=True) or {}
    entries = data.get('entries') or []
    if not isinstance(entries, list) or not entries:
        return jsonify({'error': 'entries required'}), 400

    conn = get_connection()
    try:
        deleted = []
        skipped = []

        for item in entries:
            if not isinstance(item, dict):
                skipped.append({'entry': item, 'reason': 'invalid entry payload'})
                continue

            row_id = item.get('id')
            table = str(item.get('table') or 'memory').strip()
            if not row_id:
                skipped.append({'entry': item, 'reason': 'missing id'})
                continue
            if table not in _ALL_MEMORY_TABLES:
                skipped.append({'id': row_id, 'table': table, 'reason': 'invalid table'})
                continue

            cur = conn.execute(f'DELETE FROM {table} WHERE id=?', (row_id,))
            if cur.rowcount:
                deleted.append({'id': row_id, 'table': table})
            else:
                skipped.append({'id': row_id, 'table': table, 'reason': 'memory row not found'})

        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True, 'deleted': deleted, 'skipped': skipped})


@memory_bp.route('/api/memory/<int:row_id>', methods=['DELETE'])
def delete_memory(row_id):
    table = request.args.get('table', 'memory')
    if table not in _ALL_MEMORY_TABLES:
        return jsonify({'error': 'invalid table'}), 400
    conn = get_connection()
    try:
        conn.execute(f'DELETE FROM {table} WHERE id=?', (row_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'deleted': row_id, 'table': table})



@memory_bp.route('/api/memory/<int:row_id>', methods=['PATCH'])
def update_memory(row_id):
    data = request.get_json(silent=True) or {}
    table = (data.get('table') or request.args.get('table') or 'memory').strip()
    if table not in _ALL_MEMORY_TABLES:
        return jsonify({'error': 'invalid table'}), 400

    conn = get_connection()
    try:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        if not row:
            return jsonify({'error': 'memory row not found'}), 404

        updates = []
        params = []

        if 'subject' in data and 'subject' in cols:
            updates.append('subject=?')
            params.append(str(data.get('subject') or '').strip()[:300])

        if 'content' in data and 'content' in cols:
            updates.append('content=?')
            params.append(str(data.get('content') or ''))

        append_text = str(data.get('append') or '').strip()
        if append_text and 'content' in cols:
            current = str(row['content'] or '')
            merged = current + ('\n\n' if current else '') + append_text
            updates.append('content=?')
            params.append(merged)

        if 'tags' in data and 'tags' in cols:
            updates.append('tags=?')
            params.append(str(data.get('tags') or '').strip()[:400])

        if 'importance' in data and 'importance' in cols:
            try:
                imp = int(data.get('importance'))
            except Exception:
                return jsonify({'error': 'importance must be an integer'}), 400
            if imp < 1 or imp > 10:
                return jsonify({'error': 'importance must be 1-10'}), 400
            updates.append('importance=?')
            params.append(imp)

        if not updates:
            return jsonify({'error': 'no updatable fields provided'}), 400

        if 'updated_at' in cols:
            updates.append('updated_at=?')
            params.append(datetime.now(timezone.utc).isoformat())

        params.append(row_id)
        conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE id=?", tuple(params))
        conn.commit()
        updated = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    finally:
        conn.close()

    return jsonify({'ok': True, 'table': table, 'entry': dict(updated) if updated else None})



@memory_bp.route('/api/memory/<int:row_id>/attach', methods=['POST'])
def attach_memory(row_id):
    data = request.get_json(silent=True) or {}
    label = (data.get('label') or '').strip()
    value = (data.get('value') or '').strip()
    table = (data.get('table') or request.args.get('table') or 'memory').strip()
    if table not in _ALL_MEMORY_TABLES:
        return jsonify({'error': 'invalid table'}), 400
    if not label or not value:
        return jsonify({'error': 'label and value required'}), 400

    attachment = f"[attachment:{label}] {value}"
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT id, content FROM {table} WHERE id=?", (row_id,)).fetchone()
        if not row:
            return jsonify({'error': 'memory row not found'}), 404
        merged = (str(row['content'] or '') + ('\n\n' if row['content'] else '') + attachment)
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'updated_at' in cols:
            conn.execute(
                f"UPDATE {table} SET content=?, updated_at=? WHERE id=?",
                (merged, datetime.now(timezone.utc).isoformat(), row_id),
            )
        else:
            conn.execute(f"UPDATE {table} SET content=? WHERE id=?", (merged, row_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True, 'table': table, 'id': row_id})



@memory_bp.route('/api/memory/<int:row_id>/assign', methods=['POST'])
def assign_memory(row_id):
    data = request.get_json(silent=True) or {}
    from_table = (data.get('table') or request.args.get('table') or 'memory').strip()
    targets = data.get('targets') or []
    if isinstance(targets, str):
        targets = [x.strip() for x in targets.split(',') if x.strip()]
    targets = [str(t).strip().lower() for t in targets if str(t).strip()]
    if not targets:
        return jsonify({'error': 'targets required'}), 400

    if from_table not in _ALL_MEMORY_TABLES:
        return jsonify({'error': 'invalid source table'}), 400

    conn = get_connection()
    try:
        src = conn.execute(f"SELECT * FROM {from_table} WHERE id=?", (row_id,)).fetchone()
        if not src:
            return jsonify({'error': 'memory row not found'}), 404

        assigned = []
        skipped = []
        for agent_name in targets:
            tgt_table = _AGENT_TABLES.get(agent_name)
            if not tgt_table or tgt_table not in _ALL_MEMORY_TABLES:
                skipped.append({'agent': agent_name, 'reason': 'unknown target'})
                continue

            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tgt_table})").fetchall()}
            now_iso = datetime.now(timezone.utc).isoformat()
            field_values = {}

            if 'agent' in cols:
                field_values['agent'] = agent_name
            if 'subject' in cols:
                src_subject = str(src['subject'] or '').strip() if 'subject' in src.keys() else ''
                field_values['subject'] = src_subject or str(src['content'] or '')[:120]
            if 'content' in cols:
                note = str(data.get('note') or '').strip()
                body = str(src['content'] or '')
                field_values['content'] = (body + (f"\n\n[assigned-note] {note}" if note else ''))
            if 'tags' in cols:
                base_tags = str(src['tags'] or '').strip() if 'tags' in src.keys() else ''
                merged_tags = ','.join([x for x in [base_tags, 'assigned'] if x])
                field_values['tags'] = merged_tags[:400]
            if 'importance' in cols:
                try:
                    imp = int(src['importance'] or 5)
                except Exception:
                    imp = 5
                field_values['importance'] = max(1, min(10, imp))
            if 'source' in cols:
                field_values['source'] = f'assigned_from:{from_table}:{row_id}'
            if 'type' in cols:
                field_values['type'] = 'assigned'
            if 'archived' in cols:
                field_values['archived'] = 0
            if 'created_at' in cols:
                field_values['created_at'] = now_iso
            if 'updated_at' in cols:
                field_values['updated_at'] = now_iso

            keys = list(field_values.keys())
            placeholders = ','.join(['?'] * len(keys))
            conn.execute(
                f"INSERT INTO {tgt_table} ({', '.join(keys)}) VALUES ({placeholders})",
                tuple(field_values[k] for k in keys),
            )
            assigned.append({'agent': agent_name, 'table': tgt_table})

        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True, 'assigned': assigned, 'skipped': skipped,
                    'source': {'table': from_table, 'id': row_id}})
