"""
terminal.py — Fridays / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Swarm terminal web UI. Port 5050. Tailscale only.

Three agent panels, SSE streaming, kill switches, memory browser, ticket log.
Bypasses email. Creates real tickets. Duck still runs. Memory still writes.

python3 terminal.py
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/frontend')

from flask import Flask, render_template, request, Response, jsonify
import json
import queue
import threading
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from database import (get_connection, new_conversation, log_message,
                       use_approval_token, add_trusted_sender, remove_trusted_sender,
                       add_notification_sender, remove_notification_sender,
                       get_pending_emails, mark_pending_processed, log_activity)
from ticket import create as ticket_create, librarian_close
from queue_manager import (
    intake as queue_intake,
    estimate_wait_minutes,
    mark_processing,
    intake_internal,
    update_proposal_status,
    get_queue_entries,
)
import orchestrator
from monitor import get_system_status
from sandpits import get_sandpit_stats, get_recent_log as sandpit_log
from system_clock import get_timestamp, get_timestamp_iso, get_full_time_string
from theme_engine import get_themed_html

# ALM reminder: UI/API changes that affect visibility must be mirrored in theme_engine + templates.
THEME_SYNC_REMINDER = 'ALM REMINDER: Mirror UI/API visibility changes in theme layer (theme_engine + templates).'

# Time Machine & Kill Switches  
sys.path.insert(0, '/home/seven/swarm/core')
from time_machine import time_wizard
from kill_switch import kill_switch

app = Flask(__name__)

# Cache ALM status payload briefly to keep endpoint stable under aggressive UI polling.
_alm_status_cache = {'ts': 0.0, 'payload': None}

# ── Kill switches ──────────────────────────────────────────────────────────────
# Any agent name in this set is skipped by the pipeline.
DISABLED_AGENTS = set()

_original_ask_agent = orchestrator.ask_agent

def _patched_ask_agent(agent_name, prompt):
    if agent_name in DISABLED_AGENTS:
        print(f'[Terminal] {agent_name} offline — kill switch active')
        return f'[{agent_name} is currently offline]'
    return _original_ask_agent(agent_name, prompt)

orchestrator.ask_agent = _patched_ask_agent

# ── Active SSE streams  ────────────────────────────────────────────────────────
# ticket_number → queue.Queue of event dicts. None = stream closed.
_streams = {}

from vs_tools import vs_bp
app.register_blueprint(vs_bp)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _recent_conversations(limit=40):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, source, created_at FROM conversations ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    # Alias created_at to timestamp for frontend compatibility
    return [dict(r, timestamp=r['created_at']) for r in rows]


def _tickets(limit=100):
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.ticket_number, t.status, t.duck_result, t.gemma_routing,
                  t.created_at, t.closed_at, t.sender_email, t.question,
                  COALESCE(q.priority, 5) AS priority,
                  COUNT(DISTINCT tn.id) AS note_count,
                  COUNT(DISTINCT CASE WHEN s.fired=0 THEN s.id END) AS snooze_count
           FROM tickets t
           LEFT JOIN queue q ON q.id = t.queue_id
           LEFT JOIN ticket_notes tn ON tn.ticket_id = t.id
           LEFT JOIN snoozed_tickets s ON s.ticket_number = t.ticket_number
           GROUP BY t.id
           ORDER BY t.id DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


_AGENT_TABLES = {
    'llama':    'memory_llama',
    'qwen':     'memory_qwen',
    'gemma':    'memory_gemma',
    'eight':    'memory_eight',
    'nine':     'memory_nine',
    'ten':      'memory_ten',
    'eleven':   'memory_grok',
    'grok':     'memory_grok',
    'twelve':   'memory_twelve',
    'librarian':'memory',
    'duck':     'memory',
    'sniffles': 'memory',
}

def _memory_search(query='', min_importance=3, agent='', limit=50):
    conn = get_connection()
    like = f'%{query}%'

    agent_key = agent.lower() if agent else ''
    if agent_key in ('llama', 'qwen', 'gemma', 'eight', 'nine', 'ten', 'grok', 'eleven'):
        tbl = _AGENT_TABLES[agent_key]
        archived_clause = "AND archived = 0"
        rows = conn.execute(
            f"""SELECT id, '{tbl}' AS source_table, agent, subject, content, tags, importance, created_at
               FROM {tbl}
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? {archived_clause}
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, limit)
        ).fetchall()
    elif agent_key == 'twelve':
        rows = conn.execute(
            """SELECT id, 'memory_twelve' AS source_table, agent, '' AS subject, content, tags, importance, created_at
               FROM memory_twelve
               WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, limit)
        ).fetchall()
    elif agent_key:
        rows = conn.execute(
            """SELECT id, 'memory' AS source_table, agent, subject AS title, content, tags, importance, created_at
               FROM memory
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
                 AND agent LIKE ?
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, f'%{agent}%', limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, 'memory' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_llama' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_llama
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_qwen' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_qwen
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_gemma' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_gemma
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_eight' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_eight
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_nine' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_nine
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_ten' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_ten
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_grok' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_grok
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_twelve' AS source_table, agent, '' AS subject, content, tags, importance, created_at
               FROM memory_twelve
               WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             limit)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def _duck_stats():
    conn = get_connection()
    total  = conn.execute("SELECT COUNT(*) FROM duck_log").fetchone()[0]
    passed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'").fetchone()[0]
    conn.close()
    return {'total': total, 'passed': passed, 'failed': failed}


def _is_time_wizard_active():
    """Time Wizard is considered active when at least one session exists."""
    # ALM gate defaults to ON; set ALM_REQUIRE_APPROVALS=0 to disable explicitly.
    if os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1':
        return True
    try:
        sessions = time_wizard.get_sessions(limit=1)
        return bool(sessions)
    except Exception:
        return False


def _alm_gate_or_response(data, action_name):
    """
    Enforce proposal approval for mutating actions while Time Wizard is active.
    Returns a Flask response tuple on failure, else None.
    """
    if not _is_time_wizard_active():
        return None

    proposal_id = (data.get('proposal_id') or '').strip()
    if not proposal_id:
        return jsonify({
            'ok': False,
            'error': 'proposal_id required while Time Wizard is active',
            'action': action_name,
            'required_status': ['approved', 'executed']
        }), 428

    conn = get_connection()
    row = conn.execute(
        "SELECT proposal_id, status, agent, title FROM work_proposals WHERE proposal_id=?",
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({
            'ok': False,
            'error': f'proposal not found: {proposal_id}',
            'action': action_name
        }), 404

    if row['status'] not in ('approved', 'executed'):
        return jsonify({
            'ok': False,
            'error': f'proposal status not permitted: {row["status"]}',
            'action': action_name,
            'proposal_id': proposal_id,
            'required_status': ['approved', 'executed']
        }), 403

    log_activity('terminal', 'alm_gate_pass', f'{action_name}:{proposal_id}')
    return None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Render themed terminal. Theme engine handles CSS injection."""
    html = get_themed_html()
    return Response(html, mimetype='text/html')

@app.route('/v2')
def index_v2():
    """Render raw console layer (terminal_ui_v2.html) with theme injection."""
    html = get_themed_html(template='terminal_ui_v2.html')
    return Response(html, mimetype='text/html')


@app.route('/api/conversations')
def api_conversations():
    return jsonify(_recent_conversations())


@app.route('/api/system/time')
def api_system_time():
    """Return current system time in multiple formats for UI clock"""
    return jsonify({
        'timestamp': get_timestamp(),           # "2026-03-26 14:45:33"
        'iso': get_timestamp_iso(),             # ISO 8601 with timezone
        'full_string': get_full_time_string(),  # "Wed, March 26 • 2:45:33 PM UTC"
        'unix': int(__import__('time').time())  # Unix timestamp for JS
    })


@app.route('/api/system')
def api_system():
    """Return full system status for System tab"""
    return jsonify(get_system_status())


@app.route('/api/conversations/<int:conv_id>/messages')
def api_conversation_messages(conv_id):
    conn = get_connection()
    # Conversation metadata
    conv = conn.execute(
        "SELECT id, title, source, created_at FROM conversations WHERE id=?",
        (conv_id,)
    ).fetchone()
    if not conv:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    # All messages for this conversation, ordered chronologically
    rows = conn.execute(
        """SELECT from_agent AS sender, content, to_agent, message_type, created_at
           FROM messages WHERE conversation_id=? ORDER BY id ASC""",
        (conv_id,)
    ).fetchall()
    conn.close()
    return jsonify({
        'conv': dict(conv),
        'messages': [dict(r) for r in rows]
    })


@app.route('/api/tickets')
def api_tickets():
    return jsonify(_tickets())


@app.route('/api/tickets/<ticket_number>')
def api_ticket_detail(ticket_number):
    conn = get_connection()

    ticket = conn.execute(
        """SELECT ticket_number, status, duck_result, gemma_routing, question,
                  tags, sender_email, created_at, closed_at, final_answer,
                  sniffles_result, sniffles_checked, duck_visited
           FROM tickets WHERE ticket_number=?""",
        (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # Pull messages via conversation id (TICKET-N → N)
    messages = []
    try:
        conv_id = int(ticket_number.split('-')[-1])
        rows = conn.execute(
            """SELECT from_agent AS sender, content, to_agent, message_type, created_at
               FROM messages WHERE conversation_id=? ORDER BY id ASC""",
            (conv_id,)
        ).fetchall()
        messages = [dict(r) for r in rows]
    except Exception:
        pass

    # Duck log entry for this ticket
    duck = conn.execute(
        """SELECT question, answer, result, reason, created_at
           FROM duck_log WHERE ticket_number=? ORDER BY id DESC LIMIT 1""",
        (ticket_number,)
    ).fetchone()

    # Ticket notes (ghost notes + agent notes)
    try:
        ticket_row = conn.execute(
            "SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)
        ).fetchone()
        notes = [dict(r) for r in conn.execute(
            "SELECT id, agent, note_type, content, created_at FROM ticket_notes "
            "WHERE ticket_id=? ORDER BY id ASC",
            (ticket_row['id'],)
        ).fetchall()] if ticket_row else []
    except Exception:
        notes = []

    # Active snoozes for this ticket
    try:
        snoozes = [dict(r) for r in conn.execute(
            "SELECT id, wake_at, note, created_at, fired FROM snoozed_tickets "
            "WHERE ticket_number=? ORDER BY wake_at ASC",
            (ticket_number,)
        ).fetchall()]
    except Exception:
        snoozes = []

    conn.close()
    return jsonify({
        'ticket':   dict(ticket),
        'messages': messages,
        'duck':     dict(duck) if duck else None,
        'notes':    notes,
        'snoozes':  snoozes,
    })


@app.route('/api/memory')
def api_memory():
    q     = request.args.get('q', '')
    mn    = int(request.args.get('min', 3))
    agent = request.args.get('agent', '')
    
    rows = _memory_search(q, mn, agent)
    
    # Group results by agent for frontend
    grouped = {}
    for row in rows:
        agent_name = row.get('agent', 'unknown')
        if agent_name not in grouped:
            grouped[agent_name] = []
        grouped[agent_name].append(row)
    
    return jsonify({'results': grouped})


@app.route('/api/studio')
def api_studio():
    """Studio cockpit data — agents, queue, config status."""
    status = get_system_status()
    conn = get_connection()
    
    # Get queue length
    queue_info = conn.execute('SELECT COUNT(*) as count FROM queue').fetchone()
    conn.close()
    
    return jsonify({
        'queue_length': queue_info['count'] if queue_info else 0,
        'system_load': status.get('cpu_percent', 0),
        'memory_usage': status.get('ram_percent', 0),
        'active_model': status.get('active_model', 'none'),
    })


@app.route('/api/memory/<int:row_id>', methods=['DELETE'])
def delete_memory(row_id):
    _ALLOWED_TABLES = {'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight',
                        'memory_nine', 'memory_ten', 'memory_grok', 'memory_twelve'}
    table = request.args.get('table', 'memory')
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': 'invalid table'}), 400
    conn = get_connection()
    try:
        conn.execute(f'DELETE FROM {table} WHERE id=?', (row_id,))
        conn.commit()
    finally:
        conn.close()
    print(f'[Terminal] Deleted memory row {row_id} from {table}')
    return jsonify({'deleted': row_id, 'table': table})


@app.route('/api/tickets/<ticket_number>', methods=['PATCH'])
def api_ticket_patch(ticket_number):
    """Update editable ticket fields: tags, priority."""
    data = request.get_json() or {}
    allowed = {}
    if 'tags' in data:
        allowed['tags'] = str(data['tags'])[:200]
    if 'priority' in data:
        try:
            p = int(data['priority'])
            allowed['priority'] = max(1, min(10, p))
        except (ValueError, TypeError):
            return jsonify({'error': 'priority must be 1-10'}), 400
    if not allowed:
        return jsonify({'error': 'no editable fields provided'}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id FROM tickets WHERE ticket_number=?', (ticket_number,)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        set_clause = ', '.join(f'{k}=?' for k in allowed)
        conn.execute(
            f"UPDATE tickets SET {set_clause} WHERE ticket_number=?",
            (*allowed.values(), ticket_number)
        )
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'ticket_patched', f'{ticket_number} | {allowed}')
    return jsonify({'ok': True, 'updated': allowed})


@app.route('/api/tickets/<ticket_number>/notes', methods=['POST'])
def add_ticket_note_endpoint(ticket_number):
    from database import add_ticket_note_by_number
    data    = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'empty note'}), 400
    ok = add_ticket_note_by_number(ticket_number, 'ghost@dashboard', content, note_type='ghost_note')
    if not ok:
        return jsonify({'error': 'ticket not found'}), 404
    log_activity('terminal', 'note_added', f'{ticket_number} | {content[:80]}')
    return jsonify({'ok': True})


@app.route('/api/tickets/<ticket_number>/notes/<int:note_id>', methods=['DELETE'])
def delete_ticket_note_endpoint(ticket_number, note_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM ticket_notes WHERE id=?', (note_id,))
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'note_deleted', f'{ticket_number} | note_id={note_id}')
    return jsonify({'ok': True})


# ── Project Docs ────────────────────────────────────────────────────────────────

@app.route('/api/kb')
def api_kb_list():
    conn = get_connection()
    rows = conn.execute(
        'SELECT id, doc_name, tags, updated_at FROM project_docs ORDER BY updated_at DESC'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/kb/<int:doc_id>')
def api_kb_get(doc_id):
    conn = get_connection()
    row = conn.execute('SELECT * FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@app.route('/api/kb', methods=['POST'])
def api_kb_create():
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    if not doc_name:
        return jsonify({'error': 'doc_name required'}), 400
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
        (doc_name, content, tags)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'ok': True, 'id': new_id})


@app.route('/api/kb/<int:doc_id>', methods=['PUT'])
def api_kb_update(doc_id):
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    conn = get_connection()
    conn.execute(
        "UPDATE project_docs SET doc_name=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
        (doc_name, content, tags, doc_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/kb/<int:doc_id>', methods=['DELETE'])
def api_kb_delete(doc_id):
    conn = get_connection()
    conn.execute('DELETE FROM project_docs WHERE id=?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/proposals')
def api_proposals_list():
    """List all pending agent proposals with preview."""
    from sandpits import list_proposals, read_proposal
    proposals = list_proposals()
    result = []
    for p in proposals:
        content = read_proposal(p['filename']) or ''
        result.append({**p, 'preview': content[:600]})
    return jsonify({'proposals': result})


@app.route('/api/proposals/approve', methods=['POST'])
def api_proposals_approve():
    """
    Approve a proposal:
    - Import it as a KB doc
    - Write approval to agent's memory
    - Delete the proposal file
    """
    from sandpits import read_proposal, delete_proposal
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    content = read_proposal(filename)
    if content is None:
        return jsonify({'error': 'proposal not found'}), 404

    # Import as KB doc
    conn = get_connection()
    doc_name = f'Proposal: {filename.replace(".md", "")}'
    existing = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
    if existing:
        conn.execute("UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                     (content, agent, existing[0]))
    else:
        conn.execute("INSERT INTO project_docs (doc_name, content, tags) VALUES (?, ?, ?)",
                     (doc_name, content, agent))

    # Write approval note to agent's memory using unified helper
    from database import save_agent_memory
    save_agent_memory(
        agent_name=agent,
        subject='Proposal Approved',
        content=f'My proposal "{filename}" was approved by Ghost and added to the KB.',
        importance=7,
        source='proposal_approved'
    )

    conn.commit()
    conn.close()

    # Delete the proposal file
    delete_proposal(filename)

    from database import log_activity
    log_activity('terminal', 'proposal_approved', filename)

    return jsonify({'ok': True})


@app.route('/api/proposals/reject', methods=['POST'])
def api_proposals_reject():
    """
    Reject a proposal:
    - Optionally write feedback to agent's sandpit
    - Delete the proposal file
    """
    from sandpits import delete_proposal, write_file
    from database import log_activity
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()
    feedback = (data.get('feedback') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    # Write feedback to agent's sandpit if provided
    if feedback and agent:
        try:
            from datetime import datetime
            fb_filename = f'rejection_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            write_file(agent, fb_filename,
                       f'Proposal rejected: {filename}\n\nGhost feedback:\n{feedback}')
        except Exception:
            pass

    delete_proposal(filename)
    log_activity('terminal', 'proposal_rejected', filename)

    return jsonify({'ok': True})


@app.route('/api/queue', methods=['GET'])
def api_queue_list():
    """List queue entries, optionally filtered by source_type and status."""
    source_type = (request.args.get('source_type') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    try:
        limit = int(request.args.get('limit', 50))
    except Exception:
        limit = 50

    rows = get_queue_entries(source_type=source_type, status=status, limit=max(1, min(limit, 500)))
    return jsonify({'ok': True, 'queue': rows, 'count': len(rows)})


@app.route('/api/queue', methods=['POST'])
def api_queue_create_internal():
    """Create an internal queue entry and matching work proposal."""
    data = request.get_json() or {}
    agent = (data.get('agent') or '').strip().lower()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)

    if not agent or not title:
        return jsonify({'ok': False, 'error': 'agent and title required'}), 400

    queue_id, proposal_id = intake_internal(agent, title, description, priority=priority)
    log_activity('terminal', 'queue_internal_created', f'{proposal_id} ({agent})')
    return jsonify({'ok': True, 'queue_id': queue_id, 'proposal_id': proposal_id}), 201


@app.route('/api/queue/<int:queue_id>', methods=['GET'])
def api_queue_get(queue_id):
    """Return one queue entry and linked proposal if present."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    proposal = conn.execute(
        'SELECT proposal_id, agent, title, status, queue_id, created_at, updated_at '
        'FROM work_proposals WHERE queue_id=?',
        (queue_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    return jsonify({
        'ok': True,
        'queue': dict(row),
        'proposal': dict(proposal) if proposal else None
    })


@app.route('/api/queue/<int:queue_id>', methods=['PATCH'])
def api_queue_patch(queue_id):
    """Patch queue status and priority for manual workflow control."""
    data = request.get_json() or {}
    status = (data.get('status') or '').strip()
    priority = data.get('priority', None)

    updates = []
    params = []
    if status:
        updates.append('status=?')
        params.append(status)
    if priority is not None:
        updates.append('priority=?')
        params.append(int(priority))

    if not updates:
        return jsonify({'ok': False, 'error': 'no fields to update'}), 400

    params.append(queue_id)
    conn = get_connection()
    conn.execute(f"UPDATE queue SET {', '.join(updates)} WHERE id=?", tuple(params))
    conn.commit()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    log_activity('terminal', 'queue_updated', f'queue_id={queue_id}')
    return jsonify({'ok': True, 'queue': dict(row)})


@app.route('/api/work-proposals', methods=['GET'])
def api_work_proposals_list():
    """List work proposals from DB with optional status/agent filters."""
    status = (request.args.get('status') or '').strip()
    agent = (request.args.get('agent') or '').strip()
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100

    clauses = []
    params = []
    if status:
        clauses.append('status=?')
        params.append(status)
    if agent:
        clauses.append('agent=?')
        params.append(agent)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    conn = get_connection()
    rows = conn.execute(
        f"SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, created_at, updated_at "
        f"FROM work_proposals {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [max(1, min(limit, 500))])
    ).fetchall()
    conn.close()

    payload = [dict(r) for r in rows]
    return jsonify({'ok': True, 'proposals': payload, 'count': len(payload)})


@app.route('/api/work-proposals/<proposal_id>', methods=['PATCH'])
def api_work_proposals_patch(proposal_id):
    """Update proposal status for approval/execution workflows."""
    data = request.get_json() or {}
    status = (data.get('status') or '').strip().lower()
    ticket_number = (data.get('ticket_number') or '').strip()
    valid = {'pending', 'approved', 'rejected', 'executed'}

    if status not in valid:
        return jsonify({'ok': False, 'error': f'invalid status: {status}'}), 400

    update_proposal_status(proposal_id, status, ticket_number=ticket_number)

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    log_activity('terminal', 'proposal_status_updated', f'{proposal_id} -> {status}')
    return jsonify({'ok': True, 'proposal': dict(row)})


@app.route('/api/tickets/<ticket_number>/snooze', methods=['POST'])
def add_snooze_endpoint(ticket_number):
    from database import snooze_ticket
    from listener import _parse_snooze_time
    data     = request.get_json() or {}
    when_raw = (data.get('when') or '').strip()
    note     = (data.get('note') or '').strip()
    conn     = get_connection()
    ticket   = conn.execute(
        "SELECT sender_email FROM tickets WHERE ticket_number=?", (ticket_number,)
    ).fetchone()
    conn.close()
    if not ticket:
        return jsonify({'error': 'ticket not found'}), 404
    wake_at = _parse_snooze_time(when_raw)
    if not wake_at:
        return jsonify({'error': f'could not parse time: {when_raw}'}), 400
    snooze_ticket(ticket_number, ticket['sender_email'], wake_at, note)
    log_activity('terminal', 'snooze_added', f'{ticket_number} until {wake_at}')
    return jsonify({'ok': True, 'wake_at': wake_at})


@app.route('/api/tickets/<ticket_number>/resend', methods=['POST'])
def resend_ticket(ticket_number):
    """Re-send the full final response for a ticket to its sender_email."""
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, sender_email, question, final_answer, status, gemma_routing '
        'FROM tickets WHERE ticket_number=?', (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    sender = ticket['sender_email']
    question = ticket['question'] or ''
    final_answer = ticket['final_answer'] or ''

    if not sender:
        conn.close()
        return jsonify({'error': 'no sender_email on ticket'}), 400

    # Reconstruct the full response body from stored messages
    try:
        conv_id = int(ticket_number.split('-')[-1])
        rows = conn.execute(
            'SELECT from_agent, content, message_type FROM messages '
            'WHERE conversation_id=? ORDER BY id ASC', (conv_id,)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()

    # Build sections from stored messages
    sections = {}
    is_eight = False
    for r in rows:
        agent = (r['from_agent'] or '').lower()
        mtype = r['message_type'] or ''
        if mtype == 'index':
            continue
        if mtype in ('eight_voice', 'eight_verdict'):
            is_eight = True
            sections[r['from_agent']] = r['content']
        elif agent == 'llama' and 'llama' not in sections:
            sections['llama'] = r['content']
        elif agent == 'qwen' and mtype != 'debate_r2' and 'qwen' not in sections:
            sections['qwen'] = r['content']
        elif agent == 'gemma' and mtype == 'chat' and 'gemma' not in sections:
            sections['gemma'] = r['content']

    if is_eight:
        # SAP / Eight ticket — reconstruct Eight email format
        gemma_verdict = (final_answer
                         or sections.get('Eight/Gemma')
                         or '(Eight synthesis did not complete)')
        parts = ['Eight has finished deliberating.\r\n']
        if sections.get('Eight/Functional'):
            parts.append(f"[Functional analysis]:\r\n{sections['Eight/Functional']}\r\n")
        if sections.get('Eight/Technical'):
            parts.append(f"[Technical analysis]:\r\n{sections['Eight/Technical']}\r\n")
        if sections.get('Eight/Devil'):
            parts.append(f"[Devil's Advocate]:\r\n{sections['Eight/Devil']}\r\n")
        parts.append(f"[Eight — Final verdict]:\r\n{gemma_verdict}\r\n")
        parts.append(f"---\r\nRe: {question[:100]}\r\nSent by Eight | Seven's Swarm | sevenpotato9@gmail.com")
    else:
        # Standard swarm ticket
        gemma_verdict = final_answer or sections.get('gemma', '(no verdict stored)')
        parts = ['The swarm has finished deliberating.\r\n']
        if sections.get('llama'):
            parts.append(f"[LLaMA]:\r\n{sections['llama']}\r\n")
        if sections.get('qwen'):
            parts.append(f"[Qwen]:\r\n{sections['qwen']}\r\n")
        parts.append(f"[Gemma — Final verdict]:\r\n{gemma_verdict}\r\n")
        parts.append(f"---\r\nRe: {question[:100]}\r\nSent by Seven's Swarm | sevenpotato9@gmail.com")

    body = '\r\n'.join(parts)
    subject = f'[Swarm] Full response: {question[:60]}'

    from email_handler import send_reply
    ok = send_reply(to_address=sender, subject=subject, body=body)
    if ok:
        print(f'[Terminal] Resent {ticket_number} to {sender}')
        log_activity('terminal', 'ticket_resent', f'{ticket_number} → {sender}')
        return jsonify({'ok': True, 'sent_to': sender})
    else:
        return jsonify({'error': 'send failed'}), 500


@app.route('/api/tickets/<ticket_number>/assign', methods=['POST'])
def assign_ticket(ticket_number):
    """Manually assign a ticket to a specific agent."""
    _valid_agents = {'gemma', 'llama', 'qwen', 'eight', 'librarian'}
    data  = request.get_json() or {}
    agent = (data.get('agent') or '').strip()
    if agent not in _valid_agents:
        return jsonify({'error': f'invalid agent — must be one of {sorted(_valid_agents)}'}), 400

    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, gemma_routing FROM tickets WHERE ticket_number=?',
        (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # Update agents_assigned and patch gemma_routing to reflect manual override
    import json as _json
    routing = {}
    try:
        routing = _json.loads(ticket['gemma_routing'] or '{}')
    except Exception:
        pass
    routing['agents']           = agent.lower()
    routing['manual_assign']    = True
    routing['manual_assign_to'] = agent

    conn.execute(
        'UPDATE tickets SET agents_assigned=?, gemma_routing=? WHERE ticket_number=?',
        (agent, _json.dumps(routing), ticket_number)
    )
    conn.commit()
    conn.close()
    print(f'[Terminal] Assigned {ticket_number} to {agent}')
    log_activity('terminal', 'ticket_assigned', f'{ticket_number} → {agent}')
    return jsonify({'ok': True, 'ticket': ticket_number, 'assigned_to': agent})


@app.route('/api/tickets/<ticket_number>/close', methods=['POST'])
def force_close_ticket(ticket_number):
    """Manually close a ticket — runs Duck, indexes to memory, marks queue done."""
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, question, final_answer, queue_id, sender_email, status '
        'FROM tickets WHERE ticket_number=?', (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    if ticket['status'] == 'closed':
        conn.close()
        return jsonify({'error': 'ticket already closed'}), 400

    question     = ticket['question']     or '(no question)'
    final_answer = ticket['final_answer'] or '(no answer stored — manually closed)'
    queue_id     = ticket['queue_id']
    sender_email = ticket['sender_email']
    conn.close()

    # Run librarian_close in a background thread so the response returns immediately
    import threading
    def _do_close():
        try:
            from ticket import librarian_close
            librarian_close(ticket_number, question, final_answer,
                            queue_id=queue_id, sender_email=sender_email)
            log_activity('terminal', 'ticket_force_closed', f'{ticket_number} by Ghost via dashboard')
            print(f'[Terminal] Force-closed {ticket_number}')
        except Exception as ex:
            print(f'[Terminal] Force-close error on {ticket_number}: {ex}')
            log_activity('terminal', 'ticket_force_close_error', f'{ticket_number}: {ex}')

    threading.Thread(target=_do_close, daemon=True).start()
    return jsonify({'ok': True, 'ticket': ticket_number, 'status': 'closing'})


@app.route('/api/tickets/<ticket_number>/reopen', methods=['POST'])
def reopen_ticket_endpoint(ticket_number):
    """Manually reopen a closed ticket."""
    from database import reopen_ticket
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, status FROM tickets WHERE ticket_number=?',
        (ticket_number,)
    ).fetchone()
    conn.close()
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    if ticket['status'] == 'open':
        return jsonify({'error': 'ticket already open'}), 400
    reopen_ticket(ticket_number)
    log_activity('terminal', 'ticket_reopened', f'{ticket_number} by Ghost via dashboard')
    print(f'[Terminal] Reopened {ticket_number}')
    return jsonify({'ok': True, 'ticket': ticket_number, 'status': 'open'})


@app.route('/api/tickets/<ticket_number>', methods=['DELETE'])
def delete_ticket(ticket_number):
    conn = get_connection()
    try:
        conn.execute(
            'DELETE FROM ticket_notes WHERE ticket_id=(SELECT id FROM tickets WHERE ticket_number=?)',
            (ticket_number,)
        )
        conn.execute('DELETE FROM tickets WHERE ticket_number=?', (ticket_number,))
        conn.commit()
    finally:
        conn.close()
    print(f'[Terminal] Deleted ticket {ticket_number}')
    return jsonify({'deleted': ticket_number})


# ── Docs (swarm_docs/) ─────────────────────────────────────────────────────────

import os as _os

_DOCS_DIR = _os.path.join(_os.path.dirname(__file__), '..', 'docs')

_DOC_DESCRIPTIONS = {
    '00_index.html':        'Master index — all sections, quick-reference tables',
    '01_overview.html':     'What it is, hardware, the three-layer architecture',
    '02_agents.html':       'All agents, personalities, temperatures, roles',
    '03_pipeline.html':     'Email, Terminal, Telegram and Eight pipeline flows',
    '04_database.html':     'All tables, schema, memory design',
    '05_files.html':        'Complete file reference with code highlights',
    '06_access.html':       'Trust levels, Ghost commands, Fridays trust ladder',
    '07_ghost_circle.html': 'Claude API advisory layer, ghost_circle table',
    '08_sessions.html':     'Chronological build log, all sessions',
    '09_roadmap.html':      'What\'s done, what\'s next, backlog phases',
}


# ── Senders / Access control ──────────────────────────────────────────────────

def _get_sender_lists():
    conn = get_connection()
    trusted = [dict(r) for r in conn.execute(
        "SELECT id, email, added_by, notes, added_at FROM trusted_senders ORDER BY added_at DESC"
    ).fetchall()]
    notification = [dict(r) for r in conn.execute(
        "SELECT id, email, added_by, notes, added_at FROM notification_senders ORDER BY added_at DESC"
    ).fetchall()]
    domains = [dict(r) for r in conn.execute(
        "SELECT id, domain, channel, added_by, notes, added_at FROM trusted_domains ORDER BY added_at DESC"
    ).fetchall()]
    conn.close()
    return {'trusted': trusted, 'notification': notification, 'domains': domains}


@app.route('/api/senders')
def api_senders():
    return jsonify(_get_sender_lists())


@app.route('/api/senders', methods=['POST'])
def add_sender():
    from database import add_trusted_domain
    data    = request.get_json() or {}
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    note    = (data.get('note') or '').strip()
    channel = (data.get('channel') or 'email').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        add_trusted_sender(address, added_by='dashboard', note=note)
    elif lst == 'domain':
        add_trusted_domain(address.lstrip('@'), added_by='dashboard', note=note, channel=channel)
    else:
        add_notification_sender(address, added_by='dashboard', note=note)
    print(f'[Terminal] Added {address} to {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})


@app.route('/api/senders', methods=['DELETE'])
def remove_sender():
    data    = request.get_json() or {}
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        remove_trusted_sender(address)
    elif lst == 'domain':
        conn = get_connection()
        conn.execute("DELETE FROM trusted_domains WHERE LOWER(domain)=?", (address.lstrip('@'),))
        conn.commit()
        conn.close()
    else:
        remove_notification_sender(address)
    print(f'[Terminal] Removed {address} from {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})


@app.route('/api/docs')
def api_docs():
    html_dir = _os.path.join(_DOCS_DIR, 'html')
    if not _os.path.isdir(html_dir):
        return jsonify([])
    docs = []
    for f in sorted(_os.listdir(html_dir)):
        if f.endswith('.html') and f != 'swarm_flow_v3.html':
            path = _os.path.join(html_dir, f)
            docs.append({
                'filename':    f,
                'description': _DOC_DESCRIPTIONS.get(f, ''),
                'size':        _os.path.getsize(path),
            })
    return jsonify(docs)


@app.route('/docs/html/<filename>')
def serve_doc_html(filename):
    """Serve a raw HTML doc file (used by iframe in the docs accordion)."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    return content, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/docs/download/<filename>')
def download_doc_html(filename):
    """Download an HTML doc file."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    from flask import send_file
    return send_file(path, as_attachment=True, download_name=filename,
                     mimetype='text/html')


@app.route('/api/project-md')
def api_project_md():
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/project-md', methods=['POST'])
def api_project_md_save():
    """Save edited PROJECT.md content from the dashboard."""
    data    = request.get_json() or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'empty content'}), 400
    path = '/home/seven/swarm/docs/PROJECT.md'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    log_activity('terminal', 'project_md_saved', f'{len(content)} chars')
    return jsonify({'ok': True, 'chars': len(content)})


@app.route('/api/kb/seed-swarm-docs', methods=['POST'])
def api_kb_seed_swarm_docs():
    """
    Seed the KB with key PROJECT.md sections so agents can read about the system.
    Idempotent — updates existing docs, inserts new ones.
    """
    import re
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'PROJECT.md not found'}), 404

    with open(path, encoding='utf-8') as fh:
        text = fh.read()

    # Split into H2 sections
    sections = re.split(r'\n(?=## )', text)
    seeded = 0
    conn = get_connection()
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip('#').strip()
        content = '\n'.join(lines).strip()
        if len(content) < 40:
            continue
        # Determine which agents see this
        if any(k in heading for k in ('SAP', 'Eight')):
            tags = 'eight'
        elif any(k in heading for k in ('Ghost', 'Nine', 'Layer')):
            tags = 'all'
        else:
            tags = 'all'

        doc_name = f'[Swarm] {heading}'
        existing = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE doc_name=?",
                (content[:4000], tags, doc_name)
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc_name, content[:4000], tags)
            )
        seeded += 1

    conn.commit()
    conn.close()
    log_activity('terminal', 'kb_seeded', f'{seeded} sections from PROJECT.md')
    return jsonify({'ok': True, 'sections_seeded': seeded})


@app.route('/api/project-md/raw')
def api_project_md_raw():
    from flask import send_file as _sf
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return 'Not found', 404
    return _sf(path, as_attachment=True, download_name='PROJECT.md', mimetype='text/markdown')


@app.route('/api/testing-md')
def api_testing_md():
    """Return the content of UAT_TEST_SCRIPTS.md for the dashboard."""
    path = '/home/seven/swarm/docs/UAT_TEST_SCRIPTS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/bugs-md')
def api_bugs_md():
    """Return the content of BUGS.md for the dashboard."""
    path = '/home/seven/swarm/docs/BUGS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/testing/run-simulation', methods=['POST'])
def api_run_simulation():
    """Trigger simulate.py and return the output captured from stdout/stderr."""
    import subprocess
    import os
    try:
        script_path = '/home/seven/swarm/utils/simulate.py'
        # Run via the current interpreter to ensure paths and env are correct
        result = subprocess.run([sys.executable, script_path], 
                                capture_output=True, text=True, timeout=600)
        return jsonify({
            'ok': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/shell/execute', methods=['POST'])
def api_shell_execute():
    """Execute a whitelisted shell command via shell_agent."""
    from fridays.shell_agent import run as shell_run
    data = request.get_json() or {}
    command = data.get('command', '').strip()

    gate = _alm_gate_or_response(data, 'shell_execute')
    if gate:
        return gate
    
    if not command:
        return jsonify({'ok': False, 'output': 'No command provided', 'message': 'Command is required'}), 400
    
    try:
        success, output = shell_run(command, agent='terminal_ui', notify_ghost=True)
        return jsonify({
            'ok': success,
            'output': output,
            'command': command,
        })
    except Exception as e:
        return jsonify({
            'ok': False,
            'output': f'Error executing command: {str(e)}',
            'command': command,
        }), 500


@app.route('/api/terminal/run', methods=['POST'])
def api_terminal_run():
    """Alias for /api/shell/execute for backward compatibility."""
    return api_shell_execute()


@app.route('/api/hands/run', methods=['POST'])
def api_hands_run():
    """Alias for /api/shell/execute - named for Ghost/terminal metaphor."""
    return api_shell_execute()


@app.route('/api/monitor/stats')
def api_monitor_stats():
    """System snapshot + API usage counts for Monitor tab."""
    import subprocess
    conn = get_connection()

    # System snapshot (live)
    try:
        import psutil
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu  = psutil.cpu_percent(interval=0.2)
        sys_snap = {
            'ram_used_gb':   round(mem.used  / 1e9, 1),
            'ram_total_gb':  round(mem.total / 1e9, 1),
            'ram_percent':   mem.percent,
            'swap_used_gb':  round(swap.used  / 1e9, 1),
            'swap_total_gb': round(swap.total / 1e9, 1),
            'swap_percent':  swap.percent,
            'cpu_percent':   cpu,
        }
    except Exception:
        sys_snap = {}

    # Claude usage
    claude_today = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log WHERE date(created_at)=date('now')"
    ).fetchone()
    claude_total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log"
    ).fetchone()

    # Serper usage
    serper_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    serper_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search'"
    ).fetchone()[0]

    # Tavily usage
    tavily_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    tavily_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search'"
    ).fetchone()[0]

    # Service health (systemctl)
    services = {
        'swarm-listener':  'Listener',
        'swarm-telegram':  'Telegram',
        'swarm-discord':   'Discord',
        'swarm-scheduler': 'Scheduler',
        'swarm-terminal':  'Terminal',
        'swarm-skills':    'Skills',
    }
    health = {}
    for svc, label in services.items():
        try:
            r = subprocess.run(['systemctl', 'is-active', svc],
                               capture_output=True, text=True, timeout=3)
            health[svc] = {'label': label, 'state': r.stdout.strip()}
        except Exception:
            health[svc] = {'label': label, 'state': 'unknown'}

    return jsonify({
        'system': sys_snap,
        'claude': {
            'calls_today': claude_today[0],
            'tokens_today': claude_today[1],
            'calls_total': claude_total[0],
            'tokens_total': claude_total[1],
        },
        'serper': {'calls_today': serper_today, 'calls_total': serper_total},
        'tavily': {'calls_today': tavily_today, 'calls_total': tavily_total},
        'services': health,
    })


@app.route('/api/tailscale')
def api_tailscale():
    """Return Tailscale peer list from cached status."""
    import subprocess, json
    try:
        r = subprocess.run(['tailscale', 'status', '--json'],
                           capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        peers = []
        self_node = data.get('Self', {})
        peers.append({
            'name':   self_node.get('HostName', 'self'),
            'ip':     (self_node.get('TailscaleIPs') or [''])[0],
            'online': True,
            'self':   True,
            'os':     self_node.get('OS', ''),
        })
        for key, peer in (data.get('Peer') or {}).items():
            peers.append({
                'name':   peer.get('HostName', key[:8]),
                'ip':     (peer.get('TailscaleIPs') or [''])[0],
                'online': peer.get('Online', False),
                'self':   False,
                'os':     peer.get('OS', ''),
            })
        return jsonify({'peers': peers, 'error': None})
    except Exception as e:
        return jsonify({'peers': [], 'error': str(e)})


@app.route('/api/sandpits')
def api_sandpits():
    stats = get_sandpit_stats()
    # Normalise into agents list for VS Explorer + keep raw stats
    agents = [
        {'agent': k, 'file_count': v.get('files', 0), 'bytes': v.get('bytes', 0)}
        for k, v in stats.items()
        if k != '_total'
    ]
    return jsonify({
        'agents': agents,
        'stats':  stats,
        'log':    sandpit_log(50),
    })


@app.route('/api/skills')
def api_skills():
    from fridays.skills import list_skills
    return jsonify(list_skills())


@app.route('/api/skills/run', methods=['POST'])
def api_skills_run():
    data = request.get_json() or {}
    skill_name = (data.get('skill') or '').strip().lower()
    args       = (data.get('args')  or '').strip()

    gate = _alm_gate_or_response(data, 'skills_run')
    if gate:
        return gate

    if not skill_name:
        return jsonify({'error': 'skill name required'}), 400
    from fridays.skills import call as skill_call
    ok, output = skill_call(skill_name, args=args, agent='terminal')
    return jsonify({'ok': ok, 'output': output})


@app.route('/api/ghost_circle')
def api_ghost_circle():
    from database import get_ghost_circle_entries
    limit = int(request.args.get('limit', 50))
    return jsonify(get_ghost_circle_entries(limit=limit))


@app.route('/api/monitor')
def api_monitor():
    """Monitor data for the home dashboard."""
    from monitor import get_system_status
    status = get_system_status()
    return jsonify({
        'agents_online':  status.get('open_tickets', 0),   # repurposed for display
        'last_activity':  status.get('timestamp', '—'),
        'pending_tasks':  status.get('queue_depth', 0),
        'system_load':    f"{status.get('cpu_percent', 0):.0f}%",
        'memory_usage':   f"{status.get('ram_percent', 0):.0f}%",
        # Rich fields for the Monitor window
        'cpu_percent':    status.get('cpu_percent', 0),
        'cpu_temp_c':     status.get('cpu_temp_c', 0),
        'ram_percent':    status.get('ram_percent', 0),
        'ram_used_gb':    status.get('ram_used_gb', 0),
        'ram_total_gb':   status.get('ram_total_gb', 0),
        'swap_percent':   status.get('swap_percent', 0),
        'active_model':   status.get('active_model', 'none'),
        'open_tickets':   status.get('open_tickets', 0),
        'queue_depth':    status.get('queue_depth', 0),
        'queue_processing': status.get('queue_processing', 0),
        'consults_today': status.get('consults_today', 0),
        'disks':          status.get('disks', []),
        'memory_pools':   status.get('memory_pools', {}),
    })


@app.route('/api/alm/status')
def api_alm_status():
    """Return ALM governance status for UI visibility and audits."""
    now = time.time()
    if _alm_status_cache['payload'] is not None and (now - _alm_status_cache['ts']) < 2.0:
        return jsonify(_alm_status_cache['payload'])

    require_approvals = os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1'
    time_wizard_active = _is_time_wizard_active()
    sniffles_enabled = 'Sniffles' not in DISABLED_AGENTS

    pending = 0
    approved = 0
    executed = 0
    total = 0
    legacy_pending_files = 0

    conn = get_connection()
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='work_proposals'"
        ).fetchone()
        if table:
            rows = conn.execute(
                "SELECT status, COUNT(*) as c FROM work_proposals GROUP BY status"
            ).fetchall()
            for r in rows:
                st = (r['status'] or '').lower()
                c = int(r['c'])
                total += c
                if st == 'pending':
                    pending += c
                elif st == 'approved':
                    approved += c
                elif st == 'executed':
                    executed += c
    finally:
        conn.close()

    try:
        from sandpits import list_proposals
        legacy_pending_files = len(list_proposals() or [])
    except Exception:
        legacy_pending_files = 0

    status = 'enforced' if (require_approvals and time_wizard_active) else 'warn'
    payload = {
        'ok': True,
        'status': status,
        'time_wizard_active': time_wizard_active,
        'alm_require_approvals': require_approvals,
        'sniffles_enabled': sniffles_enabled,
        'work_proposals': {
            'total': total,
            'pending': pending,
            'approved': approved,
            'executed': executed,
        },
        'legacy_pending_files': legacy_pending_files,
    }
    _alm_status_cache['ts'] = now
    _alm_status_cache['payload'] = payload
    return jsonify(payload)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Send a chat message to the swarm with 10-second timeout."""
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'ok': False, 'response': 'Empty message'}), 400
    
    try:
        # Create new conversation or use existing
        conv_id = new_conversation('terminal-ui', message[:100])
        log_message(conv_id, 'user', message)
        
        # Route to appropriate agent with 10-second timeout
        response = None
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(orchestrator.ask_agent, 'gemma', message)
            response = future.result(timeout=10)
            executor.shutdown(wait=False)
        except FuturesTimeoutError:
            # Timeout occurred - return fallback response
            response = (
                "I'm taking longer than expected to respond. This might be because:\n"
                "1. The AI model is processing a complex request\n"
                "2. The system is under heavy load\n"
                "3. The Ollama backend may need a restart\n\n"
                "Please try again in a moment, or check the system monitor."
            )
            executor.shutdown(wait=False)
        
        log_message(conv_id, 'swarm', response)
        
        return jsonify({
            'ok': True,
            'response': response,
            'conversation_id': conv_id,
        })
    except Exception as e:
        return jsonify({'ok': False, 'response': f'Error: {str(e)}'}), 500


@app.route('/api/activity')
def api_activity():
    from database import get_activity_log
    since = int(request.args.get('since', 0))
    limit = int(request.args.get('limit', 100))
    logs = get_activity_log(limit=limit, since_id=since)
    
    # Format for frontend
    activities = []
    for log in logs:
        activities.append({
            'timestamp': log.get('created_at', '—')[:16],
            'message': f"{log.get('service', 'System')}: {log.get('event', '')} {log.get('detail', '')}".strip(),
            'level': 'info',  # Could be enhanced based on event type
        })
    
    return jsonify({'activities': activities})


@app.route('/api/activity/stream')
def api_activity_stream():
    """SSE stream — sends new activity_log entries as they arrive."""
    from database import get_activity_log
    import time

    def generate():
        since_id = 0
        # Send last 20 entries on connect so the feed isn't empty
        rows = get_activity_log(limit=20)
        rows.reverse()
        for row in rows:
            yield f"data: {__import__('json').dumps(row)}\n\n"
            since_id = max(since_id, row['id'])

        while True:
            time.sleep(2)
            new_rows = get_activity_log(limit=50, since_id=since_id)
            new_rows.reverse()
            for row in new_rows:
                yield f"data: {__import__('json').dumps(row)}\n\n"
                since_id = max(since_id, row['id'])

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


_AGENT_ROSTER = [
    {'name': 'Gemma',     'model': 'gemma3:latest',          'role': 'Director',                    'default_temp': 0.3},
    {'name': 'LLaMA',     'model': 'llama3.2:latest',        'role': 'Researcher',                  'default_temp': 0.6},
    {'name': 'Qwen',      'model': 'qwen2.5:latest',         'role': 'Analyst',                     'default_temp': 0.7},
    {'name': 'Librarian', 'model': 'qwen:latest',            'role': 'Archivist',                   'default_temp': 0.1},
    {'name': 'Duck',      'model': 'qwen:latest',            'role': 'Checker',                     'default_temp': 0.1},
    {'name': 'Sniffles',  'model': 'deepseek-r1:7b',         'role': 'Auditor',                     'default_temp': 0.1},
    {'name': 'Eight',     'model': 'qwen2.5:latest',         'role': 'SAP Specialist',              'default_temp': 0.7},
    {'name': 'Nine',      'model': 'claude-sonnet-4-6',      'role': 'System Architect · Ghost Layer', 'default_temp': None, 'no_temp': True,  'ghost_layer': True},
    {'name': 'Ten',       'model': 'gemini-1.5-pro',         'role': 'Software Engineering Advisor · Ghost Layer', 'default_temp': 0.4, 'ghost_layer': True},
    {'name': 'Eleven',    'model': 'grok-api',               'role': 'Reasoning Advisor · Ghost Layer', 'default_temp': None, 'no_temp': True, 'ghost_layer': True},
    {'name': 'Twelve',    'model': 'claude-haiku',           'role': 'Time Wizard · Ghost Layer',   'default_temp': 0.3, 'ghost_layer': True},
    {'name': 'Sonic',     'model': 'claude-3-5-sonnet',      'role': 'Velocity Coder · Ghost Layer', 'default_temp': 0.2, 'ghost_layer': True},
    {'name': 'Scholar',   'model': 'gemini-2.0-flash',       'role': 'Vision & Reasoning · Ghost Layer', 'default_temp': 0.4, 'ghost_layer': True},
    {'name': 'Seeker',    'model': 'tavily-search',          'role': 'Real-Time Intelligence · Ghost Layer', 'default_temp': 0.5, 'ghost_layer': True},
    {'name': 'Ghost',     'model': '(human operator)',        'role': 'Operator · Ghost Layer',      'default_temp': None, 'no_temp': True,  'ghost_layer': True, 'no_toggle': True},
]


@app.route('/api/agents')
def api_agents():
    result = []
    for a in _AGENT_ROSTER:
        entry = dict(a)
        entry['enabled']     = a['name'] not in DISABLED_AGENTS
        entry['temperature'] = orchestrator.TEMPERATURES.get(a['name'], a['default_temp'])
        entry['status']      = 'online'  # All roster agents are online
        entry['ghost_layer'] = a.get('ghost_layer', False)  # Pass through boolean for frontend classification
        result.append(entry)
    return jsonify(result)


@app.route('/api/agents/<name>/toggle', methods=['POST'])
def toggle_agent(name):
    if name in DISABLED_AGENTS:
        DISABLED_AGENTS.discard(name)
        enabled = True
    else:
        DISABLED_AGENTS.add(name)
        enabled = False
    print(f'[Terminal] {name} {"enabled" if enabled else "disabled"}')
    return jsonify({'name': name, 'enabled': enabled})


@app.route('/api/agents/<name>/temperature', methods=['POST'])
def set_agent_temperature(name):
    data = request.get_json() or {}
    try:
        temp = float(data.get('temperature', 0.5))
        temp = round(max(0.0, min(1.0, temp)), 2)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid temperature'}), 400
    orchestrator.TEMPERATURES[name] = temp
    print(f'[Terminal] {name} temperature → {temp}')
    return jsonify({'name': name, 'temperature': temp})


@app.route('/chat', methods=['POST'])
def chat():
    data     = request.get_json() or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'empty question'}), 400

    # Librarian intake — queue entry created, same as email path
    queue_id, queue_position, tags = queue_intake('ghost@terminal', 'Terminal', question)

    # Create conversation + ticket — Duck will run inside librarian_close
    conv_id       = new_conversation(question, source='terminal', sender='ghost')
    ticket_number = f'TICKET-{conv_id}'
    ticket_create(ticket_number, 'ghost@terminal', question, tags=tags, queue_id=queue_id)
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')

    # Event queue for this ticket's SSE stream
    q = queue.Queue()
    _streams[ticket_number] = q

    def run_pipeline():
        try:
            q.put({'type': 'status', 'text': 'Gemma reading the question...'})
            mark_processing(queue_id)
            web, llama, ctx, routing = orchestrator.consult_stage1(question)
            q.put({'type': 'routing', 'routing': routing})
            # Save routing to ticket so Tickets view shows it
            _conn = get_connection()
            _conn.execute(
                "UPDATE tickets SET gemma_routing=? WHERE ticket_number=?",
                (json.dumps(routing), ticket_number)
            )
            _conn.commit()
            _conn.close()

            if routing.get('is_sap'):
                # ── Eight pipeline ────────────────────────────────────────────
                q.put({'type': 'status', 'text': 'Eight engaged — SAP specialist deliberating...'})
                def eight_status(msg):
                    q.put({'type': 'status', 'text': msg})
                result = orchestrator.consult_stage_eight(
                    question, web, ctx, conv_id, status_cb=eight_status
                )
                q.put({'type': 'eight_voice', 'voice': 'Functional', 'text': result['functional']})
                q.put({'type': 'eight_voice', 'voice': 'Technical',  'text': result['technical']})
                q.put({'type': 'eight_voice', 'voice': 'Devil',      'text': result['devil']})
                q.put({'type': 'agent', 'agent': 'Gemma', 'text': result['gemma_verdict']})
                final_answer = result['gemma_verdict']
            else:
                # ── Standard pipeline ─────────────────────────────────────────
                q.put({'type': 'agent', 'agent': 'LLaMA', 'text': llama})

                q.put({'type': 'status', 'text': 'Qwen analysing...'})
                qwen, gemma, debate = orchestrator.consult_stage2(
                    question, web, llama, ctx, conv_id, routing
                )
                q.put({'type': 'agent', 'agent': 'Qwen', 'text': qwen})

                if debate['fired']:
                    q.put({'type': 'status', 'text': 'Debate detected — running challenge round...'})
                    q.put({'type': 'debate_r2', 'agent': 'LLaMA', 'text': debate['llama_r2']})
                    q.put({'type': 'debate_r2', 'agent': 'Qwen',  'text': debate['qwen_r2']})

                q.put({'type': 'agent', 'agent': 'Gemma', 'text': gemma})
                final_answer = gemma

            q.put({'type': 'status', 'text': 'Duck checking...'})
            librarian_close(ticket_number, question, final_answer,
                            queue_id=queue_id, sender_email='ghost@terminal')

            q.put({'type': 'done', 'ticket': ticket_number})

        except Exception as e:
            print(f'[Terminal] Pipeline error: {e}')
            q.put({'type': 'error', 'text': str(e)})
        finally:
            q.put(None)  # sentinel — stream ends

    threading.Thread(target=run_pipeline, daemon=True).start()
    return jsonify({'ticket': ticket_number, 'conv_id': conv_id})


@app.route('/stream/<ticket_number>')
def stream(ticket_number):
    def generate():
        q = _streams.get(ticket_number)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'text': 'stream not found'})}\n\n"
            return
        while True:
            try:
                event = q.get(timeout=900)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'text': 'timeout'})}\n\n"
                break
            if event is None:
                _streams.pop(ticket_number, None)
                break
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── One-click approval endpoints ───────────────────────────────────────────────

def _run_pending_for_trusted(target_email, approved_by):
    """Process any pending emails from newly trusted sender in a background thread."""
    from email_cleaner import clean_subject
    from orchestrator import consult_stage1, consult_stage2, consult_stage_eight
    from email_handler import send_reply

    pending = get_pending_emails(target_email)
    if not pending:
        return

    for p in pending:
        pending_from    = p[1]
        pending_subject = clean_subject(p[2]) if p[2] else 'Your question'
        pending_body    = p[3] or pending_subject

        queue_id, position, tags = queue_intake(pending_from, pending_subject, pending_body)
        from database import new_conversation, log_message
        conv_id       = new_conversation(pending_body, source='email', sender=pending_from)
        ticket_number = f'TICKET-{conv_id}'
        ticket_create(ticket_number, pending_from, pending_body, tags=tags, queue_id=queue_id)
        log_message(conv_id, 'Ghost', pending_body, to_agent='Gemma', message_type='chat')

        send_reply(
            to_address=pending_from,
            subject='[Swarm] On it: ' + pending_subject,
            body=(
                'Welcome! Seven\'s Swarm has received your message.\r\n\r\n'
                'The swarm is deliberating. Full response coming shortly.\r\n\r\n'
                '---\r\n'
                'Re: ' + pending_subject + '\r\n'
                "— Gemma | Seven's Swarm | sevenpotato9@gmail.com"
            )
        )

        web_results, llama_answer, shared_context, routing = consult_stage1(pending_body)
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')

        send_reply(
            to_address=pending_from,
            subject='[Swarm] Received: ' + pending_subject,
            body=(
                'Consulted the web immediately.\r\n\r\n'
                '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
                'Full swarm deliberating. Response coming shortly.\r\n\r\n'
                '---\r\n'
                "Sent by Seven's Swarm | sevenpotato9@gmail.com"
            )
        )

        if routing.get('is_sap'):
            eight_result = consult_stage_eight(pending_body, web_results, shared_context, conv_id)
            gemma_answer = eight_result['gemma_verdict']
            email2_body  = (
                '[Eight — Final verdict]:\r\n' + gemma_answer
            )
        else:
            qwen_answer, gemma_answer, debate = consult_stage2(
                pending_body, web_results, llama_answer, shared_context, conv_id, routing
            )
            debate_section = ''
            if debate['fired']:
                debate_section = (
                    '[Debate]\r\nLLaMA: ' + debate['llama_r2'] + '\r\n'
                    'Qwen: ' + debate['qwen_r2'] + '\r\n\r\n'
                )
            email2_body = (
                '[Qwen]:\r\n' + qwen_answer + '\r\n\r\n' +
                debate_section +
                '[Gemma — Final verdict]:\r\n' + gemma_answer
            )

        send_reply(
            to_address=pending_from,
            subject='[Swarm] Full response: ' + pending_subject,
            body=email2_body + '\r\n\r\n---\r\nSent by Seven\'s Swarm | sevenpotato9@gmail.com'
        )

        librarian_close(ticket_number, pending_body, gemma_answer,
                        queue_id=queue_id, sender_email=pending_from)
        mark_pending_processed(p[0])
        print(f'[Approval] {ticket_number} processed for {pending_from}')


@app.route('/approve/<action>/<token>')
def approval_action(action, token):
    """
    One-click approval endpoint. Ghost clicks link in email.
    action: trust | notify | ignore
    token: UUID from approval_tokens table
    """
    result = use_approval_token(token)

    if not result:
        return (
            '<html><body style="font-family:monospace;padding:40px;background:#1a1a1a;color:#f00">'
            '<h2>Invalid or already used token.</h2>'
            '<p>This link has already been actioned or has expired.</p>'
            '</body></html>'
        ), 400

    target  = result['target_email']
    act     = result['action']

    # Validate action matches URL (belt and braces)
    if act != action.lower():
        return ('<html><body>Token/action mismatch.</body></html>'), 400

    if act == 'trust':
        add_trusted_sender(target, 'ghost@terminal', 'Approved via one-click link')
        threading.Thread(
            target=_run_pending_for_trusted,
            args=(target, 'ghost@terminal'),
            daemon=True
        ).start()
        colour = '#0f0'
        heading = '✅ Sender trusted'
        detail  = f'{target} added to trusted senders. Any pending emails are being processed now.'
    elif act == 'notify':
        add_notification_sender(target, 'ghost@terminal', 'Filed via one-click link')
        colour = '#fa0'
        heading = '🔕 Sender filed as notification'
        detail  = f'{target} will be filed silently. No response ever.'
    elif act == 'ignore':
        add_notification_sender(target, 'ghost@terminal', 'Ignored via one-click link')
        colour = '#888'
        heading = '🚫 Sender ignored'
        detail  = f'{target} will be silently ignored from now on.'
    else:
        return ('<html><body>Unknown action.</body></html>'), 400

    print(f'[Approval] One-click: {act} → {target}')
    return (
        f'<html><body style="font-family:monospace;padding:40px;background:#1a1a1a;color:{colour}">'
        f'<h2>{heading}</h2>'
        f'<p style="color:#ccc">{detail}</p>'
        f'<p style="color:#555;font-size:12px">You can close this tab.</p>'
        f'</body></html>'
    )


# ── Nine / VS tab ─────────────────────────────────────────────────────────────

@app.route('/api/swarm/status')
def api_swarm_status():
    """Quick swarm health snapshot — no LLM, pure DB. Used by VS tab dashboard."""
    from database import log_activity as _la
    import subprocess, datetime
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    try:
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        closed_t   = conn.execute("SELECT COUNT(*) FROM tickets WHERE DATE(closed_at)=DATE('now')").fetchone()[0]
        duck_yes   = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES' AND DATE(created_at)=DATE('now')").fetchone()[0]
        duck_no    = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'  AND DATE(created_at)=DATE('now')").fetchone()[0]
        recent_act = conn.execute(
            "SELECT service, event, detail, created_at FROM activity_log ORDER BY id DESC LIMIT 8"
        ).fetchall()
        
        nine_mem = []
        if 'memory_nine' in tables:
            nine_mem = conn.execute("SELECT subject, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        ten_mem = []
        if 'memory_ten' in tables:
            ten_mem = conn.execute("SELECT subject, created_at FROM memory_ten WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        debates = []
        if 'debates' in tables:
            debates = conn.execute("SELECT topic, status, rounds FROM debates ORDER BY created_at DESC LIMIT 4").fetchall()
            
        proposals  = []
        try:
            from sandpits import list_proposals
            proposals = [p.get('agent','?') + ': ' + str(p.get('filename',''))[:60] for p in list_proposals()[:4]]
        except Exception:
            pass
    finally:
        conn.close()

    # Service health via systemctl
    svcs = {}
    for svc in ('swarm-listener', 'swarm-telegram', 'swarm-discord', 'swarm-terminal'):
        try:
            r = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True, timeout=2)
            svcs[svc] = r.stdout.strip()
        except Exception:
            svcs[svc] = 'unknown'

    return jsonify({
        'ts':         datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'queue':      {'queued': queued, 'processing': processing},
        'tickets':    {'open': open_t, 'closed_today': closed_t},
        'duck':       {'yes': duck_yes, 'no': duck_no},
        'services':   svcs,
        'activity':   [{'service': r[0], 'event': r[1], 'detail': str(r[2] or '')[:80], 'ts': str(r[3] or '')[:16]} for r in recent_act],
        'nine_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in nine_mem],
        'ten_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in ten_mem],
        'debates':    [{'topic': r[0][:60], 'status': r[1], 'rounds': r[2]} for r in debates],
        'proposals':  proposals,
    })


@app.route('/api/nine/history')
def api_nine_history():
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if 'memory_nine' not in tables:
        conn.close()
        return jsonify([])
        
    rows = conn.execute(
        "SELECT subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND source IN ('vs_tab','repl_session','dashboard') "
        "ORDER BY created_at ASC LIMIT 40"
    ).fetchall()
    conn.close()
    return jsonify([{'question': r['subject'], 'answer': r['content'], 'ts': str(r['created_at'] or '')[:16]} for r in rows])


@app.route('/api/nine/actions')
def api_nine_actions():
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


@app.route('/api/nine', methods=['POST'])
def api_nine_chat():
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from claude_api import _load_api_key, CLAUDE_MODEL
        from config import NINE_SYSTEM_PROMPT
        import anthropic

        api_key = _load_api_key()
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY not configured — add to /etc/environment'}), 500

        conn       = get_connection()
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        
        # Recall: Recent flow + Relevant context
        nine_history  = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 10").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=5)

        # Pending proposals
        try:
            from sandpits import list_proposals
            proposals = list_proposals()[:5]
        except Exception:
            proposals = []
        # Open debates
        open_debates = conn.execute(
            "SELECT topic, rounds FROM debates WHERE status='open' ORDER BY created_at DESC LIMIT 5"
        ).fetchall() if 'debates' in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else []
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued, {processing} processing\n"
        ctx += f"Open tickets: {open_t}\n"
        if proposals:
            ctx += f"Pending proposals: {len(proposals)}\n"
            for p in proposals[:3]:
                ctx += f"  - {str(p.get('title',''))[:80]}\n"
        if open_debates:
            ctx += f"Open debates: {len(open_debates)}\n"
            for d in open_debates:
                ctx += f"  - {d[0][:60]} ({d[1]} rounds)\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"

        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client   = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=NINE_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': full_message}]
        )
        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        save_agent_memory(
            agent_name='nine', subject=message[:100], content=answer,
            tags='vs,dashboard', importance=8, source='vs_tab'
        )

        from database import log_activity
        log_activity('terminal', 'nine_consulted', f'tokens={tokens} | {message[:80]}')

        return jsonify({'answer': answer, 'tokens': tokens})

    except Exception as e:
        print(f'[Terminal] Nine error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/nine/stream', methods=['POST'])
def api_nine_stream():
    """Streaming version of Nine chat via SSE."""
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from claude_api import _load_api_key, CLAUDE_MODEL
        from config import NINE_SYSTEM_PROMPT
        import anthropic

        api_key = _load_api_key()
        if not api_key:
            def _err():
                yield 'data: {"error": "ANTHROPIC_API_KEY not set"}\n\n'
            return Response(_err(), mimetype='text/event-stream')

        conn       = get_connection()
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        nine_history = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 8").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=4)
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued | Open tickets: {open_t}\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client = anthropic.Anthropic(api_key=api_key)

        def _generate():
            full_answer = []
            try:
                with client.messages.stream(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    system=NINE_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': full_message}]
                ) as stream:
                    for text in stream.text_stream:
                        full_answer.append(text)
                        yield f'data: {json.dumps({"text": text})}\n\n'
                answer = ''.join(full_answer)
                tokens = stream.get_final_message().usage
                total  = tokens.input_tokens + tokens.output_tokens
                save_agent_memory(
                    agent_name='nine', subject=message[:100], content=answer,
                    tags='vs,dashboard', importance=8, source='vs_tab'
                )
                from database import log_activity
                log_activity('terminal', 'nine_consulted', f'tokens={total} | {message[:80]}')
                yield f'data: {json.dumps({"done": True, "tokens": total})}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

        return Response(_generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Terminal tab ───────────────────────────────────────────────────────────────


# ── Ghost Layer exec (Nine + Ghost, elevated) ─────────────────────────────────

# Commands Nine/Ghost can run directly from the VS tab.
# systemctl swarm-* uses NOPASSWD sudoers rule.
# Everything else goes through the shell_agent whitelist.
import re as _re
_SUDO_ALLOWED = _re.compile(
    r'^sudo\s+systemctl\s+(restart|start|stop|status)\s+swarm-\w+$'
)

@app.route('/api/exec', methods=['POST'])
def api_exec():
    import subprocess as _sp
    data = request.get_json() or {}
    cmd  = (data.get('command') or '').strip()

    gate = _alm_gate_or_response(data, 'exec')
    if gate:
        return gate

    if not cmd:
        return jsonify({'output': '', 'ok': True})

    from database import log_activity

    if _SUDO_ALLOWED.match(cmd):
        try:
            result = _sp.run(
                cmd.split(), capture_output=True, text=True, timeout=15
            )
            output = (result.stdout + result.stderr).strip() or '(done)'
            ok     = result.returncode == 0
            log_activity('terminal', 'ghost_exec_sudo', cmd[:80])
            return jsonify({'output': output, 'ok': ok})
        except Exception as e:
            return jsonify({'output': f'Error: {e}', 'ok': False})

    # Fallback: shell_agent whitelist
    from fridays.skills import call as skill_call
    ok, output = skill_call('shell', args=cmd, agent='ghost')
    log_activity('terminal', 'ghost_exec', cmd[:80])
    return jsonify({'output': output, 'ok': ok})


# ── Ghost Layer file write (Nine proposes, Ghost applies via VS tab) ───────────

import os as _os

_SWARM_ROOT = '/home/seven/swarm'

@app.route('/api/exec/write', methods=['POST'])
def api_exec_write():
    """Write a file. Path must be inside /home/seven/swarm."""
    data    = request.get_json() or {}
    path    = (data.get('path') or '').strip()
    content = data.get('content', '')
    desc    = (data.get('description') or '').strip()

    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    if not path or not path.startswith(_SWARM_ROOT):
        return jsonify({'error': 'Path must be within /home/seven/swarm'}), 400
    if '..' in path:
        return jsonify({'error': 'Invalid path'}), 400

    try:
        # Read previous content for audit trail
        try:
            with open(path, 'r') as f:
                previous = f.read()
        except FileNotFoundError:
            previous = ''

        # Ensure parent dir exists
        _os.makedirs(_os.path.dirname(path), exist_ok=True)

        with open(path, 'w') as f:
            f.write(content)

        conn = get_connection()
        conn.execute(
            "INSERT INTO file_writes (path, description, previous_content, new_content, applied_by) VALUES (?,?,?,?,?)",
            (path, desc, previous[:2000], content[:4000], 'ghost')
        )
        conn.commit()
        conn.close()

        from database import log_activity
        log_activity('terminal', 'file_write', f'{path} — {desc[:60]}')

        lines_old = len(previous.splitlines())
        lines_new = len(content.splitlines())
        return jsonify({'ok': True, 'output': f'Written: {path}\n{lines_old} → {lines_new} lines'})
    except Exception as e:
        return jsonify({'error': str(e), 'ok': False}), 500


# ── Debates (agent deliberation protocol) ─────────────────────────────────────

@app.route('/api/debates')
def api_debates_list():
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT id, topic, initiator, status, rounds, consensus, created_at FROM debates ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'topic': r[1], 'initiator': r[2],
        'status': r[3], 'rounds': r[4], 'consensus': r[5], 'ts': str(r[6] or '')[:16]
    } for r in rows])


@app.route('/api/debates', methods=['POST'])
def api_debates_create():
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    conn = get_connection()
    conn.execute("INSERT INTO debates (topic, initiator) VALUES (?, ?)", (topic, 'nine'))
    conn.commit()
    debate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    from database import log_activity
    log_activity('terminal', 'debate_opened', topic[:80])
    return jsonify({'id': debate_id, 'ok': True})


@app.route('/api/debates/<int:debate_id>/turns')
def api_debate_turns(debate_id):
    conn  = get_connection()
    turns = conn.execute(
        "SELECT agent, position, round, created_at FROM debate_turns WHERE debate_id=? ORDER BY round, created_at",
        (debate_id,)
    ).fetchall()
    conn.close()
    return jsonify([{'agent': t[0], 'position': t[1], 'round': t[2], 'ts': str(t[3] or '')[:16]} for t in turns])


@app.route('/api/debates/<int:debate_id>/run', methods=['POST'])
def api_debate_run(debate_id):
    """Run a debate asynchronously — returns immediately, debate runs in background thread."""
    import threading
    def _run():
        try:
            from debate import run_debate
            result = run_debate(debate_id)
            print(f'[Terminal] Debate #{debate_id} finished: {result["status"]}')
        except Exception as e:
            print(f'[Terminal] Debate #{debate_id} error: {e}')
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True, 'message': f'Debate #{debate_id} started in background'})


@app.route('/api/debates/quick', methods=['POST'])
def api_debate_quick():
    """Open + run a debate from VS tab. Topic in request body."""
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    import threading
    results = {}
    def _run():
        try:
            from debate import run_and_resolve
            results['result'] = run_and_resolve(topic, initiator='nine')
        except Exception as e:
            results['error'] = str(e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=0)  # Fire and forget — VS tab polls for result
    conn = get_connection()
    debate_id = conn.execute("SELECT id FROM debates WHERE topic=? ORDER BY id DESC LIMIT 1", (topic,)).fetchone()
    conn.close()
    return jsonify({'ok': True, 'debate_id': debate_id[0] if debate_id else None,
                    'message': f'Debate started: {topic[:60]}'})


# ── Agent Autonomy Endpoints ──────────────────────────────────────────────────

@app.route('/api/agents/<agent>/memory')
def api_agent_memory(agent):
    """Browse an agent's persistent memory pool. Query params: ?query=... &limit=10 &importance=5+"""
    query = request.args.get('query', '').strip()
    limit = int(request.args.get('limit', 10))
    min_importance = int(request.args.get('min_importance', 0))
    
    conn = get_connection()
    
    # Map agent name to memory table
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    # Check what columns exist in this table
    try:
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        # Build query based on available columns
        if 'subject' in columns:
            # Schema: memory_gemma, memory_eight, memory_nine style
            search_clause = "(subject LIKE ? OR content LIKE ?)" if query else "1=1"
            search_params = (f'%{query}%', f'%{query}%') if query else ()
            
            rows = conn.execute(f"""
                SELECT id, subject, content, tags, importance, created_at 
                FROM {table}
                WHERE {search_clause}
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, search_params + (min_importance, limit)).fetchall()
        else:
            # Schema: memory_twelve style (no subject)
            rows = conn.execute(f"""
                SELECT id, content, tags, type, importance, created_at 
                FROM {table}
                WHERE content LIKE ?
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, (f'%{query}%', min_importance, limit)).fetchall()
        
        conn.close()
        return jsonify({
            'agent': agent,
            'table': table,
            'query': query,
            'limit': limit,
            'entries': [dict(r) for r in rows]
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/agents/<agent>/memory/write', methods=['POST'])
def api_agent_memory_write(agent):
    """Write to an agent's memory pool. Body: {content, tags?, importance?} for memory_twelve style"""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    tags = (data.get('tags') or '').strip()
    importance = int(data.get('importance', 5))
    memo_type = (data.get('type') or 'observation').strip()  # For memory_twelve
    subject = (data.get('subject') or '').strip()  # For memory_gemma/eight/nine
    
    if not content:
        return jsonify({'error': 'content required'}), 400
    
    if not 1 <= importance <= 10:
        return jsonify({'error': 'importance must be 1-10'}), 400
    
    conn = get_connection()
    
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    try:
        now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        
        # Detect schema
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        if 'subject' in columns:
            # memory_gemma/eight/nine style
            source = data.get('source', 'api')
            conn.execute(f"""
                INSERT INTO {table} (agent, subject, content, tags, importance, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (agent_key, (subject or content[:100])[:200], content, tags, importance, source, now))
        else:
            # memory_twelve style  
            conn.execute(f"""
                INSERT INTO {table} (agent, content, tags, importance, type, created_at, updated_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (agent_key, content, tags, importance, memo_type, now, now))
        
        conn.commit()
        
        entry_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        conn.close()
        
        return jsonify({
            'ok': True,
            'agent': agent,
            'table': table,
            'entry_id': entry_id,
            'importance': importance
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/agents/memories/query')
def api_agents_memories_query():
    """Cross-agent memory search. Find what any agent knows about a topic."""
    q = request.args.get('q', '').strip()
    agents_filter = [a.strip().lower() for a in request.args.get('agents', '').split(',') if a.strip()]  # Handle empty strings
    limit = int(request.args.get('limit', 5))
    min_importance = int(request.args.get('min_importance', 1))  # Changed default to 1 for broader search
    
    if not q:
        return jsonify({'error': 'q (query) required'}), 400
    
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    conn = get_connection()
    results = {}
    
    # If agents specified, search only those; otherwise search all
    tables_to_search = {k: v for k, v in memory_tables.items() 
                       if not agents_filter or k in agents_filter}
    
    for agent_key, table in tables_to_search.items():
        try:
            # Detect schema for this table
            c = conn.cursor()
            c.execute(f"PRAGMA table_info({table})")
            columns = {col[1] for col in c.fetchall()}
            
            if 'subject' in columns:
                # memory_gemma/eight/nine style
                rows = conn.execute(f"""
                    SELECT id, subject, content, tags, importance, created_at 
                    FROM {table}
                    WHERE (subject LIKE ? OR content LIKE ?) 
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', f'%{q}%', min_importance, limit)).fetchall()
            else:
                # memory_twelve style
                rows = conn.execute(f"""
                    SELECT id, content, tags, type, importance, created_at 
                    FROM {table}
                    WHERE content LIKE ?
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', min_importance, limit)).fetchall()
            
            if rows:
                results[agent_key] = [dict(r) for r in rows]
        except:
            pass  # Table might not exist, skip
    
    conn.close()
    
    return jsonify({
        'query': q,
        'agents': list(results.keys()),
        'results': results
    })


# ═══════════════════════════════════════════════════════════════════════════════
# TIME MACHINE — Agent Twelve's temporal tracking endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/time/timeline', methods=['GET'])
def api_time_timeline():
    """Get agent timeline — all recorded events."""
    agent = request.args.get('agent', None)
    start_time = request.args.get('start', None)
    end_time = request.args.get('end', None)
    limit = int(request.args.get('limit', 100))
    
    timeline = time_wizard.get_timeline(
        agent=agent,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'agent': agent,
        'count': len(timeline),
        'timeline': timeline
    })


@app.route('/api/time/sessions', methods=['GET'])
def api_time_sessions():
    """Get all temporal sessions."""
    agent = request.args.get('agent', None)
    status = request.args.get('status', None)
    
    sessions = time_wizard.get_sessions(agent=agent, status=status)
    
    return jsonify({
        'agent': agent,
        'status': status,
        'count': len(sessions),
        'sessions': sessions
    })


@app.route('/api/time/checkpoint/<name>', methods=['GET'])
def api_time_checkpoint(name):
    """Retrieve a specific checkpoint."""
    checkpoint = time_wizard.get_checkpoint(name)
    
    if not checkpoint:
        return jsonify({'error': f'Checkpoint "{name}" not found'}), 404
    
    return jsonify(checkpoint)


@app.route('/api/time/checkpoints', methods=['GET'])
def api_time_checkpoints():
    """List all checkpoints."""
    before = request.args.get('before', None)
    after = request.args.get('after', None)
    
    checkpoints = time_wizard.list_checkpoints(before_time=before, after_time=after)
    
    return jsonify({
        'count': len(checkpoints),
        'checkpoints': checkpoints
    })


@app.route('/api/time/stats/<agent>', methods=['GET'])
def api_time_stats(agent):
    """Get temporal statistics for an agent."""
    stats = time_wizard.get_temporal_stats(agent)
    return jsonify(stats)


@app.route('/api/time/bootstrap', methods=['POST'])
def api_time_bootstrap():
    """Initialize a new Time Wizard session."""
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            return jsonify({'ok': True, 'session_id': session_id}), 201
        else:
            return jsonify({'ok': False, 'error': 'Bootstrap failed'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/log-decision', methods=['POST'])
def api_time_log_decision():
    """Log a decision execution event."""
    data = request.get_json() or {}
    decision_id = data.get('decision_id')
    agent = data.get('agent', 'twelve')
    status = data.get('status', 'executed')
    details = data.get('details', {})
    
    if not decision_id:
        return jsonify({'ok': False, 'error': 'decision_id required'}), 400
    
    try:
        event_id = time_wizard.log_decision_execution(
            decision_id, agent, status, details
        )
        return jsonify({
            'ok': True,
            'event_id': event_id,
            'decision_id': decision_id
        }), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/decision-history/<decision_id>', methods=['GET'])
def api_time_decision_history(decision_id):
    """Get execution history for a decision."""
    try:
        history = time_wizard.get_decision_history(decision_id)
        return jsonify({
            'ok': True,
            'decision_id': decision_id,
            'events': history,
            'total': len(history)
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# KILL SWITCHES — Emergency control endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/killswitch/buttons', methods=['GET'])
def api_killswitch_buttons():
    """Get desktop kill switch button configuration."""
    return jsonify(kill_switch.create_desktop_buttons())


@app.route('/api/killswitch/emergency', methods=['POST'])
def api_killswitch_emergency():
    """EMERGENCY SHUTDOWN — immediate stop all agents."""
    reason = request.json.get('reason', 'Manual emergency shutdown') if request.json else 'Manual emergency shutdown'
    
    kill_switch.record_kill_event('emergency_shutdown', agent='system', reason=reason)
    success = kill_switch.emergency_shutdown(reason=reason)
    
    return jsonify({
        'action': 'emergency_shutdown',
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/api/killswitch/pause', methods=['POST'])
def api_killswitch_pause():
    """Pause all active agents."""
    reason = request.json.get('reason', 'Manual pause') if request.json else 'Manual pause'
    
    kill_switch.record_kill_event('pause_all', agent='system', reason=reason)
    success = kill_switch.pause_all_agents(reason=reason)
    
    return jsonify({
        'action': 'pause_all',
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/api/killswitch/resume', methods=['POST'])
def api_killswitch_resume():
    """Resume paused agents."""
    kill_switch.record_kill_event('resume_all', agent='system')
    success = kill_switch.resume_agents()
    
    return jsonify({
        'action': 'resume_all',
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/api/killswitch/restart', methods=['POST'])
def api_killswitch_restart():
    """Restart swarm server."""
    kill_switch.record_kill_event('restart_server', agent='system')
    kill_switch.broadcast_alert('🔄 RESTART SERVER initiated')
    
    # Spawn restart in background
    def _restart():
        import time
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    threading.Thread(target=_restart, daemon=True).start()
    
    return jsonify({
        'action': 'restart',
        'success': True,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'note': 'Server restarting in 1 second...'
    })


@app.route('/api/killswitch/agent/<agent_name>/reset', methods=['POST'])
def api_killswitch_agent_reset(agent_name):
    """Reset specific agent."""
    kill_switch.record_kill_event('agent_reset', agent=agent_name)
    success = kill_switch.reset_agent(agent_name)
    
    return jsonify({
        'action': 'agent_reset',
        'agent': agent_name,
        'success': success,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


# ══════════════════════════════════════════════════════════════════════════════
# GHOST BRIEF — Swarm Intelligence Feed
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/brief')
def api_brief_get():
    """Return latest Ghost Brief. If stale (>6h), generate a new one."""
    from brief_engine import get_latest_brief, generate_brief, is_brief_stale
    try:
        if is_brief_stale(max_age_hours=6):
            brief = generate_brief(trigger='auto_refresh')
        else:
            brief = get_latest_brief()
        if not brief:
            return jsonify({'error': 'Brief generation failed — check Claude API key'}), 503
        return jsonify(brief)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/brief/generate', methods=['POST'])
def api_brief_generate():
    """Force-generate a new Ghost Brief immediately."""
    from brief_engine import generate_brief
    try:
        brief = generate_brief(trigger='manual')
        if not brief:
            return jsonify({'error': 'Brief generation failed — check Claude API key'}), 503
        return jsonify(brief)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/brief/history')
def api_brief_history():
    """Return list of past Ghost Briefs."""
    from brief_engine import get_brief_history
    try:
        limit = int(request.args.get('limit', 10))
        return jsonify({'briefs': get_brief_history(limit=limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# TIME WIZARD — Decision Logging & Audit Trail API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/decisions')
def api_decisions():
    """
    List all decisions from the Time Wizard decision index.
    Returns decision metadata from sandpits/twelve/DECISION_INDEX.md
    """
    import os
    import re
    
    index_path = '/home/seven/swarm/sandpits/twelve/DECISION_INDEX.md'
    
    if not os.path.exists(index_path):
        return jsonify({'decisions': [], 'total': 0, 'message': 'No decisions logged yet'})
    
    try:
        with open(index_path, 'r') as f:
            content = f.read()
        
        # Parse decisions from markdown table 
        # | ID | Title | Status | Proposed | Category | Impact |
        lines = content.split('\n')
        decisions = []
        
        for line in lines:
            if line.startswith('|') and 'Title' not in line and '---' not in line and line.count('|') >= 5:
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 5:
                    decisions.append({
                        'id': parts[0],
                        'title': parts[1],
                        'status': parts[2],
                        'proposed': parts[3],
                        'category': parts[4] if len(parts) > 4 else '',
                        'impact': parts[5] if len(parts) > 5 else ''
                    })
        
        return jsonify({
            'decisions': decisions,
            'total': len(decisions),
            'last_updated': datetime.utcnow().isoformat() + 'Z'
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'decisions': []}), 500


@app.route('/api/decisions/<decision_id>')
def api_decision_detail(decision_id):
    """
    Get full details of a specific decision.
    Reads from sandpits/twelve/proposals/DECISION-NNN-*.md
    """
    import os
    import glob
    
    proposal_dir = '/home/seven/swarm/sandpits/twelve/proposals'
    
    # Find the proposal file — decision_id is already full e.g. "DECISION-001"
    pattern = f'{proposal_dir}/{decision_id}-*.md'
    matches = glob.glob(pattern)
    # Fallback: bare numeric id e.g. "001"
    if not matches:
        pattern = f'{proposal_dir}/DECISION-{decision_id}-*.md'
        matches = glob.glob(pattern)

    if not matches:
        return jsonify({'error': f'Decision {decision_id} not found'}), 404

    try:
        with open(matches[0], 'r') as f:
            content = f.read()

        # Parse markdown decision
        lines = content.split('\n')
        decision_data = {
            'id': decision_id,
            'file': os.path.basename(matches[0]),
            'content': content,
            'sections': {}
        }

        # Extract flat fields from well-known header lines
        for line in lines[:12]:
            if line.startswith('# '):
                decision_data['title'] = line.lstrip('# ').strip()
            if line.startswith('**Status**:'):
                decision_data['status'] = line.split(':', 1)[1].strip().strip('*')
            if line.startswith('**Agent**:'):
                decision_data['agent'] = line.split(':', 1)[1].strip().strip('*')

        current_section = None
        for line in lines:
            if line.startswith('## '):
                current_section = line.replace('## ', '').strip()
                decision_data['sections'][current_section] = []
            elif current_section and line.strip():
                decision_data['sections'][current_section].append(line)

        # Map sections to flat fields expected by the UI
        sec = decision_data['sections']
        decision_data['issue']      = '\n'.join(sec.get('Issue', sec.get('Problem', [])))
        decision_data['solution']   = '\n'.join(sec.get('Proposed Solution', sec.get('Solution', [])))
        decision_data['scope']      = '\n'.join(sec.get('Scope', sec.get('Impact', [])))
        decision_data['risks']      = '\n'.join(sec.get('Risks', sec.get('Risk', [])))
        decision_data['next_steps'] = '\n'.join(sec.get('Next Steps', sec.get('Actions', [])))

        return jsonify(decision_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline')
def api_decision_timeline():
    """
    Get chronological timeline of all decisions.
    Useful for audit trail and dependency visualization.
    """
    import os
    import glob
    from datetime import datetime as dt
    
    proposal_dir = '/home/seven/swarm/sandpits/twelve/proposals'
    timeline = []
    
    # Find all decision files
    decision_files = glob.glob(f'{proposal_dir}/DECISION-*.md')
    
    for file_path in sorted(decision_files):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Extract metadata from top of file
            lines = content.split('\n')
            entry = {
                'file': os.path.basename(file_path),
                'decision_id': os.path.basename(file_path).split('-')[1],
                'proposed': None,
                'status': 'UNKNOWN',
                'title': ''
            }
            
            for line in lines[:20]:
                if line.startswith('# Decision'):
                    entry['title'] = line.replace('# Decision', '').strip()
                elif line.startswith('**Status**:'):
                    entry['status'] = line.split('**Status**:')[1].strip().split('|')[0].strip()
                elif line.startswith('**Proposed**:'):
                    entry['proposed'] = line.split('**Proposed**:')[1].strip()
            
            timeline.append(entry)
        
        except Exception as e:
            print(f'[Time Wizard] Error parsing {file_path}: {e}')
    
    # Sort by proposed date
    timeline.sort(key=lambda x: x['proposed'] or '', reverse=True)
    
    return jsonify({
        'timeline': timeline,
        'total': len(timeline),
        'last_update': datetime.utcnow().isoformat() + 'Z'
    })


if __name__ == '__main__':
    print("\n╔═══════════════════════════════╗")
    print("║   Fridays Terminal  —  5050   ║")
    print("╚═══════════════════════════════╝")
    print("  http://localhost:5050")
    print("  Tailscale only in production.\n")
    print(f"  {THEME_SYNC_REMINDER}")
    
    # Initialize Time Wizard on startup (both layers)
    try:
        session_id = time_wizard.bootstrap_session()
        print(f"  Time Wizard initialized: {session_id}\n")
    except Exception as e:
        print(f"  Time Wizard init warning: {e}\n")
    
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
