"""tickets.py — Tickets routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

tickets_bp = Blueprint('tickets', __name__)

def _tickets(limit=100, status=None):
    conn = get_connection()
    if status in ('open', 'closed'):
        where = "WHERE t.status = ?"
        params = (status, limit)
    else:
        where = ""
        params = (limit,)
    rows = conn.execute(
        f"""SELECT t.ticket_number, t.status, t.duck_result, t.gemma_routing,
                  t.created_at, t.closed_at, t.sender_email, t.question,
                  t.channel, t.conv_id,
                  COALESCE(q.priority, 5) AS priority,
                  COUNT(DISTINCT tn.id) AS note_count,
                  COUNT(DISTINCT CASE WHEN s.fired=0 THEN s.id END) AS snooze_count
           FROM tickets t
           LEFT JOIN queue q ON q.id = t.queue_id
           LEFT JOIN ticket_notes tn ON tn.ticket_id = t.id
           LEFT JOIN snoozed_tickets s ON s.ticket_number = t.ticket_number
           {where}
           GROUP BY t.id
           ORDER BY t.id DESC LIMIT ?""",
        params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]



@tickets_bp.route('/api/tickets')
def api_tickets():
    status = request.args.get('status')
    return jsonify(_tickets(status=status))



@tickets_bp.route('/api/tickets/<ticket_number>')
def api_ticket_detail(ticket_number):
    conn = get_connection()

    ticket = conn.execute(
        """SELECT ticket_number, status, duck_result, gemma_routing, question,
                  tags, sender_email, created_at, closed_at, final_answer,
                  sniffles_result, sniffles_checked, duck_visited,
                  channel, conv_id, email_message_id
           FROM tickets WHERE ticket_number=?""",
        (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # Pull messages via conv_id stored on ticket, or derive from ticket_number
    messages = []
    try:
        conv_id = ticket['conv_id']
        if not conv_id:
            # Fallback: derive from TG-N / DC-N / TICKET-N patterns
            parts = ticket_number.split('-')
            if len(parts) == 2 and parts[1].isdigit():
                conv_id = int(parts[1])
        if conv_id:
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



@tickets_bp.route('/api/tickets/<ticket_number>', methods=['PATCH'])
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
        # tags live in tickets; priority lives in queue (linked via queue_id)
        if 'tags' in allowed:
            conn.execute(
                'UPDATE tickets SET tags=? WHERE ticket_number=?',
                (allowed['tags'], ticket_number)
            )
        if 'priority' in allowed:
            conn.execute(
                '''UPDATE queue SET priority=?
                   WHERE id=(SELECT queue_id FROM tickets WHERE ticket_number=?)''',
                (allowed['priority'], ticket_number)
            )
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'ticket_patched', f'{ticket_number} | {allowed}')
    return jsonify({'ok': True, 'updated': allowed})



@tickets_bp.route('/api/tickets/<ticket_number>/notes', methods=['POST'])
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



@tickets_bp.route('/api/tickets/<ticket_number>/notes/<int:note_id>', methods=['DELETE'])
def delete_ticket_note_endpoint(ticket_number, note_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM ticket_notes WHERE id=?', (note_id,))
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'note_deleted', f'{ticket_number} | note_id={note_id}')
    return jsonify({'ok': True})



@tickets_bp.route('/api/tickets/<ticket_number>/snooze', methods=['POST'])
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



@tickets_bp.route('/api/tickets/<ticket_number>/resend', methods=['POST'])
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
        if mtype in ('eight_verdict',) or agent == 'eight':
            is_eight = True
            sections['eight'] = r['content']
        elif agent == 'llama' and 'llama' not in sections:
            sections['llama'] = r['content']
        elif agent == 'mistral' and mtype != 'debate_r2' and 'mistral' not in sections:
            sections['mistral'] = r['content']
        elif agent == 'qwen' and mtype != 'debate_r2' and 'qwen' not in sections:
            sections['qwen'] = r['content']  # backward compat with old conversations
        elif agent == 'gemma' and mtype == 'chat' and 'gemma' not in sections:
            sections['gemma'] = r['content']

    if is_eight:
        # SAP / Eight ticket
        verdict = (final_answer
                   or sections.get('eight')
                   or '(Eight did not complete)')
        parts = ['Eight has finished deliberating.\r\n']
        parts.append(f"[Eight — SAP verdict]:\r\n{verdict}\r\n")
        parts.append(f"---\r\nRe: {question[:100]}\r\nSent by Eight | Seven's Swarm | sevenpotato9@gmail.com")
    else:
        # Standard swarm ticket
        gemma_verdict = final_answer or sections.get('gemma', '(no verdict stored)')
        parts = ['The swarm has finished deliberating.\r\n']
        if sections.get('llama'):
            parts.append(f"[LLaMA]:\r\n{sections['llama']}\r\n")
        if sections.get('mistral'):
            parts.append(f"[Mistral]:\r\n{sections['mistral']}\r\n")
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



@tickets_bp.route('/api/tickets/<ticket_number>/assign', methods=['POST'])
def assign_ticket(ticket_number):
    """Manually assign a ticket to a specific agent."""
    _valid_agents = {a['name'].lower() for a in _AGENT_ROSTER if a['name'].lower() != 'ghost'}
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



@tickets_bp.route('/api/tickets/<ticket_number>/close', methods=['POST'])
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



@tickets_bp.route('/api/tickets/<ticket_number>/reopen', methods=['POST'])
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



@tickets_bp.route('/api/tickets/<ticket_number>', methods=['DELETE'])
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



