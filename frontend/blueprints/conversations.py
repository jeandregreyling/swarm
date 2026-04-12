"""conversations.py — Conversations routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

conversations_bp = Blueprint('conversations', __name__)

def _recent_conversations(limit=40):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, source, created_at FROM conversations ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    # Alias created_at to timestamp for frontend compatibility
    return [dict(r, timestamp=r['created_at']) for r in rows]



@conversations_bp.route('/api/conversations')
def api_conversations():
    return jsonify(_recent_conversations())



@conversations_bp.route('/api/conversations/<int:conv_id>/messages')
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
        """SELECT id, from_agent AS sender, content, to_agent, message_type, tokens_used, created_at
           FROM messages WHERE conversation_id=? ORDER BY id ASC""",
        (conv_id,)
    ).fetchall()
    # Look up any linked ticket for this conversation
    ticket_info = None
    try:
        t = conn.execute(
            """SELECT t.ticket_number, t.sender_email, t.status, t.channel,
                      t.question, t.final_answer, t.created_at,
                      q.subject, q.source_type
               FROM tickets t
               LEFT JOIN queue q ON t.queue_id = q.id
               WHERE t.conv_id = ?
               LIMIT 1""",
            (conv_id,)
        ).fetchone()
        if t:
            ticket_info = dict(t)
        else:
            # Fallback: derive ticket from conversation source pattern (TG-N, DC-N)
            src = conv['source'] or ''
            if src in ('telegram', 'discord'):
                prefix = 'TG' if src == 'telegram' else 'DC'
                t2 = conn.execute(
                    "SELECT ticket_number, sender_email, status, channel, question, final_answer, created_at FROM tickets WHERE ticket_number=? LIMIT 1",
                    (f'{prefix}-{conv_id}',)
                ).fetchone()
                if t2:
                    ticket_info = dict(t2)
    except Exception:
        pass
    conn.close()
    return jsonify({
        'conv': dict(conv),
        'messages': [dict(r) for r in rows],
        'ticket': ticket_info,
    })



@conversations_bp.route('/api/conversations/<int:conv_id>/messages/<int:msg_id>', methods=['PATCH'])
def api_conversation_message_patch(conv_id, msg_id):
    """Edit a single user-authored prompt message inside a conversation."""
    data = request.get_json() or {}
    new_content = str(data.get('content') or '').strip()
    if not new_content:
        return jsonify({'ok': False, 'error': 'content required'}), 400

    conn = get_connection()
    row = conn.execute(
        "SELECT id, from_agent FROM messages WHERE id=? AND conversation_id=?",
        (msg_id, conv_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'message not found'}), 404

    if str(row['from_agent'] or '').strip().lower() != 'user':
        conn.close()
        return jsonify({'ok': False, 'error': 'only user prompts are editable'}), 403

    conn.execute(
        "UPDATE messages SET content=? WHERE id=? AND conversation_id=?",
        (new_content, msg_id, conv_id)
    )
    conn.commit()
    updated = conn.execute(
        "SELECT id, from_agent AS sender, content, to_agent, message_type, created_at FROM messages WHERE id=?",
        (msg_id,)
    ).fetchone()
    conn.close()

    log_activity('terminal', 'conversation_message_updated', f'conv_id={conv_id} msg_id={msg_id}')
    return jsonify({'ok': True, 'message': dict(updated) if updated else None})



@conversations_bp.route('/api/conversations/<int:conv_id>/messages/<int:msg_id>', methods=['DELETE'])
def api_conversation_message_delete(conv_id, msg_id):
    """Delete a single message inside a conversation."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, from_agent, to_agent FROM messages WHERE id=? AND conversation_id=?",
        (msg_id, conv_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'message not found'}), 404

    conn.execute("DELETE FROM messages WHERE id=? AND conversation_id=?", (msg_id, conv_id))
    conn.commit()
    conn.close()

    log_activity('terminal', 'conversation_message_deleted', f'conv_id={conv_id} msg_id={msg_id}')
    return jsonify({'ok': True, 'deleted': msg_id})



@conversations_bp.route('/api/conversations/<int:conv_id>', methods=['PATCH'])
def api_conversation_patch(conv_id):
    """Update editable conversation fields (currently: title)."""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400

    conn = get_connection()
    row = conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'conversation not found'}), 404

    conn.execute("UPDATE conversations SET title=? WHERE id=?", (title[:200], conv_id))
    conn.commit()
    updated = conn.execute(
        "SELECT id, title, source, created_at FROM conversations WHERE id=?",
        (conv_id,)
    ).fetchone()
    conn.close()

    log_activity('terminal', 'conversation_updated', f'conv_id={conv_id}')
    return jsonify({'ok': True, 'conversation': dict(updated)})



@conversations_bp.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
def api_conversation_delete(conv_id):
    """Delete a conversation and all linked messages."""
    conn = get_connection()
    row = conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'conversation not found'}), 404

    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()

    log_activity('terminal', 'conversation_deleted', f'conv_id={conv_id}')
    return jsonify({'ok': True, 'deleted': conv_id})



