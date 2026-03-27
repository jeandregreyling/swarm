"""
vs_tools.py — VS tab file read/memory tools for Nine
═══════════════════════════════════════════════════════════════════════════════
Endpoints called by the VS tab when Nine requests a file read or writes
to her own memory. Imported and registered in terminal.py.

Endpoints:
  1. POST /api/vs/read          Read file content
  2. POST /api/vs/ls            List directory entries
  3. POST /api/vs/memory/save   Save entry to memory_nine
  4. GET  /api/vs/memory        Get recent history from memory_nine
  5. POST /api/vs/memory/search Search Nine's memory
  6. POST /api/vs/memory/archive Complete/Hide an action entry
═══════════════════════════════════════════════════════════════════════════════
"""

import os
from flask import Blueprint, request, jsonify
from database import get_connection, log_activity, save_agent_memory, get_timestamp
from file_versioning import track_file_change

vs_bp = Blueprint('vs', __name__)

_SWARM_ROOT = '/home/seven/swarm'
_MAX_READ   = 200_000   # chars — large enough for any single file


def _safe_path(path_str):
    """Resolve and validate path is inside swarm root. Returns (path, error_str)."""
    if not path_str:
        return None, 'path required'
    resolved = os.path.realpath(path_str)
    if not resolved.startswith(_SWARM_ROOT):
        return None, f'path must be inside {_SWARM_ROOT}'
    return resolved, None


def _ls_internal(path):
    """Logic for directory listing used by both vs_ls and as a fallback for vs_read."""
    try:
        entries = []
        for name in sorted(os.listdir(path)):
            # Skip temporary SQLite WAL files that cause ENOENT errors
            if name.endswith(('.db-shm', '.db-wal')):
                continue

            full = os.path.join(path, name)
            if not os.path.exists(full):
                continue

            entries.append({
                'name':     name,
                'type':     'dir' if os.path.isdir(full) else 'file',
                'size':     os.path.getsize(full) if os.path.isfile(full) else 0,
                'modified': int(os.path.getmtime(full)),
            })
        # Sort dirs first
        entries.sort(key=lambda x: (x['type'] != 'dir', x['name']))
        return {'path': path, 'entries': entries}
    except Exception as e:
        return {'error': str(e)}


# ── 1. File read ─────────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/read', methods=['POST'])
def vs_read():
    data = request.get_json() or {}
    path, err = _safe_path((data.get('path') or '').strip())
    if err: return jsonify({'error': err}), 400

    if not os.path.exists(path):
        return jsonify({'error': f'not found: {path}'}), 404

    if os.path.isdir(path):
        res = _ls_internal(path)
        return jsonify({**res, 'type': 'directory'})

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(_MAX_READ)
        log_activity('terminal', 'nine_read', path.replace(_SWARM_ROOT, ''))
        return jsonify({
            'type':      'file',
            'path':      path,
            'content':   content,
            'lines':     content.count('\n') + 1,
            'truncated': len(content) == _MAX_READ,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 2. Directory listing ─────────────────────────────────────────────────────

@vs_bp.route('/api/vs/ls', methods=['POST'])
def vs_ls():
    data = request.get_json() or {}
    path, err = _safe_path((data.get('path') or _SWARM_ROOT).strip())
    if err: return jsonify({'error': err}), 400
    if not os.path.isdir(path): return jsonify({'error': 'not a directory'}), 400
    
    res = _ls_internal(path)
    if 'error' in res:
        return jsonify(res), 500
    return jsonify(res)


# ── Grep Tool ────────────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/grep', methods=['POST'])
def vs_grep():
    """Project-wide string search for Nine."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query or len(query) < 3:
        return jsonify({'error': 'search query too short'}), 400
    
    import subprocess
    try:
        # Use grep -r, exclude sandpits and db
        cmd = ['grep', '-r', '-n', '--exclude-dir=sandpits', '--exclude=*.db', query, _SWARM_ROOT]
        out = subprocess.check_output(cmd, text=True, errors='replace', timeout=10)
        log_activity('terminal', 'nine_grep', query[:50])
        return jsonify({'query': query, 'results': out})
    except subprocess.CalledProcessError:
        return jsonify({'query': query, 'results': '(no matches)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ── 3. Memory save ───────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/memory/save', methods=['POST'])
def vs_memory_save():
    data = request.get_json() or {}
    subj = (data.get('subject') or '').strip()
    cont = (data.get('content') or '').strip()
    tags = (data.get('tags') or 'vs_tool').strip()
    imp  = int(data.get('importance', 7))

    if not cont: return jsonify({'error': 'content required'}), 400

    ok = save_agent_memory('nine', subj or 'VS Note', cont, tags=tags, importance=imp, source='vs_tab')
    log_activity('terminal', 'nine_memory_save', subj[:80])
    return jsonify({'ok': ok})


# ── 4. Architectural Backlog ──────────────────────────────────────────────────

@vs_bp.route('/api/vs/actions', methods=['GET'])
def vs_actions_list():
    """Fetch only Nine's 'action' items for the VS Backlog pane."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND tags LIKE '%action%' "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'title': r['subject'],
        'description': r['content'],
        'ts': str(r['created_at'] or '')[:16]
    } for r in rows])


# ── 4. Memory history ────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/memory', methods=['GET'])
def vs_memory_list():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, content, tags, created_at FROM memory_nine "
        "WHERE archived=0 ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── 7. File write ────────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/write', methods=['POST'])
def vs_write():
    """Propose or execute a file write. Replaces logic previously in terminal.py."""
    data = request.get_json() or {}
    path, err = _safe_path((data.get('path') or '').strip())
    content = data.get('content', '')
    desc = (data.get('description') or 'Written via VS tab').strip()

    if err: return jsonify({'error': err}), 400
    if not content: return jsonify({'error': 'content required'}), 400

    try:
        # Audit previous content
        previous = ''
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                previous = f.read(5000) # Only store start for audit

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        # RL-031: Track change in file_versions table
        track_file_change(path, 'Nine', 'write', content_before=previous, content_after=content)

        conn = get_connection()
        conn.execute(
            "INSERT INTO file_writes (path, description, previous_content, new_content, applied_by, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (path, desc, previous, content[:5000], 'ghost', get_timestamp())
        )
        conn.commit()
        conn.close()

        log_activity('terminal', 'nine_write', path.replace(_SWARM_ROOT, ''))
        return jsonify({'ok': True, 'path': path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 8. File delete ───────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/rm', methods=['POST'])
def vs_rm():
    """Delete a file. Files only, no recursive directory deletion allowed."""
    data = request.get_json() or {}
    path, err = _safe_path((data.get('path') or '').strip())
    if err: return jsonify({'error': err}), 400
    if not os.path.isfile(path): return jsonify({'error': 'not a file or already deleted'}), 400

    try:
        os.remove(path)
        log_activity('terminal', 'nine_rm', path.replace(_SWARM_ROOT, ''))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 9. Service Logs ──────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/logs/<service>', methods=['GET'])
def vs_service_logs(service):
    """Tail logs for a swarm service. Only allows swarm-* services."""
    if not service.startswith('swarm-'): return jsonify({'error': 'invalid service'}), 400
    import subprocess
    try:
        out = subprocess.check_output(['journalctl', '-u', service, '-n', '50', '--no-pager'], text=True)
        return jsonify({'service': service, 'logs': out})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── 5. Memory search ─────────────────────────────────────────────────────────

@vs_bp.route('/api/vs/memory/search', methods=['POST'])
def vs_memory_search():
    data = request.get_json() or {}
    q = (data.get('query') or '').strip()
    if not q: return jsonify([])
    like = f'%{q}%'
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, content, tags, created_at FROM memory_nine "
        "WHERE archived=0 AND (subject LIKE ? OR content LIKE ? OR tags LIKE ?) "
        "ORDER BY created_at DESC LIMIT 20", (like, like, like)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── 6. Memory archive (Delete) ───────────────────────────────────────────────

@vs_bp.route('/api/vs/memory/archive', methods=['POST'])
def vs_memory_archive():
    data = request.get_json() or {}
    row_id = data.get('id')
    if not row_id: return jsonify({'error': 'id required'}), 400
    conn = get_connection()
    conn.execute("UPDATE memory_nine SET archived=1 WHERE id=?", (row_id,))
    conn.commit()
    conn.close()
    log_activity('terminal', 'nine_memory_archive', f'id={row_id}')
    return jsonify({'ok': True})