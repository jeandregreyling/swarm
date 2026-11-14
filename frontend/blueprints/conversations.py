"""conversations.py — Conversations routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

conversations_bp = Blueprint('conversations', __name__)


@conversations_bp.route('/api/conversations/<int:conv_id>/resume', methods=['POST'])
def api_resume_recovery_conversation(conv_id):
    """The authenticated owner explicitly resumes history after storage recovery."""
    import sqlite3
    from core.chat_continuity import ContinuityChat
    from core.recovery_resume import import_journal

    try:
        user = get_current_user()
    except sqlite3.DatabaseError:
        return jsonify({'ok': False, 'error': 'Authentication storage unavailable; recovery history preserved'}), 503
    if not user or user.get('role') != 'owner':
        return jsonify({'ok': False, 'error': 'Owner access required'}), 403
    if not request.is_json:
        return jsonify({'ok': False, 'error': 'JSON request required'}), 415
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        return jsonify({'ok': False, 'error': 'Same-origin request required'}), 403
    continuity = ContinuityChat()
    if not continuity.owns_id(conv_id):
        return jsonify({'ok': False, 'error': 'Not a recovery conversation'}), 400
    conn = None
    try:
        # Take the same lock as the writer so no in-flight reply is lost.
        import fcntl
        lock_path = continuity.path(conv_id).with_suffix('.lock')
        if lock_path.is_symlink():
            raise ValueError('Continuity lock cannot be a symlink')
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            thread = continuity.read(conv_id, user['username'])
            conn = get_connection()
            result = import_journal(conn, thread, user['username'])
        return jsonify({'ok': True, 'state': 'ok', 'resumed_from': conv_id, **result})
    except FileNotFoundError:
        return jsonify({'ok': False, 'error': 'Recovery conversation not found'}), 404
    except PermissionError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 403
    except (BlockingIOError, ValueError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 409
    except sqlite3.DatabaseError as exc:
        return jsonify({'ok': False, 'error': 'Storage verification failed; recovery history preserved: ' + str(exc)}), 503
    finally:
        if conn is not None:
            conn.close()


def _recent_conversations(limit=40):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.id, c.title, c.source, c.created_at, "
            "(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id=c.id) AS last_message_at, "
            "(SELECT m.from_agent FROM messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_from "
            "FROM conversations c ORDER BY c.id DESC LIMIT ?",   # 12 Nov: last activity, for "other chats active"
            (limit,)
        ).fetchall()
        # Alias created_at to timestamp for frontend compatibility
        return [dict(r, timestamp=r['created_at']) for r in rows]
    finally:
        conn.close()



@conversations_bp.route('/api/conversations')
def api_conversations():
    from core.chat_continuity import ContinuityChat, storage_fault

    continuity = ContinuityChat()
    fault = storage_fault(get_connection)
    identity, error = _resolve_identity_or_response({})
    if error:
        return error
    recovery_threads = continuity.recent(identity['effective_user'])
    if fault:
        response = jsonify(recovery_threads if recovery_threads else {
            'ok': False, 'storage_degraded': True,
            'error': 'Primary history unavailable; no recovery threads have been created yet.',
        })
        response.headers['X-Fridays-Storage-Status'] = 'degraded; recovery-threads-only'
        return response, 200 if recovery_threads else 503
    return jsonify(recovery_threads + _recent_conversations())



@conversations_bp.route('/api/conversations/<int:conv_id>/messages')
def api_conversation_messages(conv_id):
    from core.chat_continuity import ContinuityChat

    continuity = ContinuityChat()
    if continuity.owns_id(conv_id):
        identity, error = _resolve_identity_or_response({})
        if error:
            return error
        try:
            thread = continuity.read(conv_id, identity['effective_user'])
        except FileNotFoundError:
            return jsonify({'ok': False, 'error': 'Recovery conversation not found'}), 404
        except PermissionError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 403
        return jsonify({
            'conv': {key: thread[key] for key in ('id', 'title', 'source', 'created_at')},
            'messages': thread['messages'], 'jobs': [], 'proposals': [], 'ticket': None,
            'storage_degraded': True, 'mode': 'local_recovery',
        })
    conn = get_connection()
    # Conversation metadata
    conv = conn.execute(
        "SELECT id, title, source, created_at FROM conversations WHERE id=?",
        (conv_id,)
    ).fetchone()
    # All messages for this conversation, ordered chronologically
    rows = conn.execute(
        """SELECT id, from_agent AS sender, content, to_agent, message_type, tokens_used, created_at
           FROM messages WHERE conversation_id=? ORDER BY id ASC""",
        (conv_id,)
    ).fetchall()
    # Owner 13 Nov: ?limit=N returns the newest N messages (oldest first); &before=ID the N before that message.
    limit = request.args.get('limit', type=int)
    before = request.args.get('before', type=int)
    has_more = False
    if limit:
        older = [r for r in rows if not before or r['id'] < before]
        has_more = len(older) > limit
        rows = older[-limit:]
    job_rows = conn.execute(
        """SELECT job_id, conversation_id, agent, status, runtime_class,
                  stage, eta_seconds, elapsed_ms, tokens, error,
                  stage_trace_json, started_at, updated_at
           FROM chat_jobs
           WHERE conversation_id=?
           ORDER BY started_at ASC""",
        (conv_id,),
    ).fetchall()
    if not conv:
        if not rows and not job_rows:
            conn.close()
            return jsonify({'error': 'not found'}), 404
        created_at = None
        if rows:
            created_at = rows[0]['created_at']
        elif job_rows:
            created_at = job_rows[0]['started_at']
        conv = {
            'id': conv_id,
            'title': f'Archived chat #{conv_id}',
            'source': 'recovered',
            'created_at': created_at,
        }
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

    # Linked proposals referencing this conversation
    linked_proposals = []
    try:
        linked_proposals = [dict(r) for r in conn.execute(
            """SELECT proposal_id, title, status, agent, created_at
               FROM work_proposals WHERE source_conv_id=?
               ORDER BY id DESC""",
            (conv_id,)
        ).fetchall()]
    except Exception:
        pass

    import json as _json
    jobs = []
    for row in job_rows:
        item = dict(row)
        try:
            item['stage_trace'] = _json.loads(item.pop('stage_trace_json') or '[]')
        except Exception:
            item.pop('stage_trace_json', None)
            item['stage_trace'] = []
        jobs.append(item)

    from core.hb_workflow import visible_jobs
    jobs.extend(visible_jobs(conn,conv_id))
    from core import hb_tasks
    messages=hb_tasks.enrich(conn,[dict(r) for r in rows])
    conn.close()
    return jsonify({
        'conv': dict(conv),
        'messages': messages,
        'jobs': jobs,
        'ticket': ticket_info,
        'proposals': linked_proposals,
        'has_more': has_more,
    })



@conversations_bp.route('/api/conversations/<int:conv_id>/messages/<int:msg_id>', methods=['PATCH'])
@require_auth
def api_conversation_message_patch(conv_id, msg_id, current_user=None):
    """Edit a single user-authored prompt message inside a conversation."""
    from core.chat_continuity import ContinuityChat

    if ContinuityChat().owns_id(conv_id):
        return jsonify({'ok': False, 'error': 'Recovery journals are append-only; send a correction as a new message.'}), 409
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
@require_auth
def api_conversation_message_delete(conv_id, msg_id, current_user=None):
    from core.chat_continuity import ContinuityChat

    if ContinuityChat().owns_id(conv_id):
        return jsonify({'ok': False, 'error': 'Recovery journals are preserved; message deletion is unavailable.'}), 409
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
    from core.chat_continuity import ContinuityChat

    if ContinuityChat().owns_id(conv_id):
        return jsonify({'ok': False, 'error': 'Recovery journals are preserved; renaming is unavailable.'}), 409
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
    from core.chat_continuity import ContinuityChat

    if ContinuityChat().owns_id(conv_id):
        return jsonify({'ok': False, 'error': 'Recovery journals are preserved; deletion is unavailable.'}), 409
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


@conversations_bp.route('/api/conversations/<int:conv_id>/timeline')
def api_conversation_timeline(conv_id):
    """Return the agent action timeline for a conversation."""
    try:
        from database import timeline_get
        limit = min(int(request.args.get('limit', 200)), 500)
        rows = timeline_get(conv_id, limit=limit)
        return jsonify({'conv_id': conv_id, 'events': rows})
    except Exception as e:
        return jsonify({'conv_id': conv_id, 'events': [], 'error': str(e)})


@conversations_bp.route('/api/trace/<job_id>')
def api_trace_job(job_id):
    """Full end-to-end trace for a single chat job.

    Assembles chat_job metadata, conv_timeline events, and the response
    message into a single unified trace view.
    """
    conn = get_connection()
    try:
        job = conn.execute(
            """SELECT job_id, conversation_id, agent, status, runtime_class,
                      stage, eta_seconds, elapsed_ms, tokens, error,
                      stage_trace_json, started_at, updated_at
               FROM chat_jobs WHERE job_id=?""", (job_id,)
        ).fetchone()
        if not job:
            conn.close()
            return jsonify({'error': f'job {job_id} not found'}), 404
        job_dict = dict(job)
        conv_id = job_dict.get('conversation_id')

        # Timeline events linked to this job
        from utils.db.timeline import timeline_get_job
        timeline = timeline_get_job(job_id)

        # Also get conv_timeline events by conv_id + agent + time window as fallback
        if not timeline and conv_id:
            started = job_dict.get('started_at') or ''
            rows = conn.execute(
                """SELECT id, conv_id, agent, event_type, payload, created_at
                   FROM conv_timeline
                   WHERE conv_id=? AND agent=? AND created_at >= ?
                   ORDER BY id ASC LIMIT 100""",
                (conv_id, job_dict.get('agent', ''), started),
            ).fetchall()
            timeline = [dict(r) for r in rows]

        # Response message (if stored)
        response_msg = None
        if conv_id:
            row = conn.execute(
                """SELECT content, tokens_used, created_at
                   FROM messages
                   WHERE conversation_id=? AND from_agent=?
                   ORDER BY id DESC LIMIT 1""",
                (conv_id, job_dict.get('agent', '')),
            ).fetchone()
            if row:
                response_msg = dict(row)

        conn.close()

        import json as _j
        stage_trace = []
        try:
            stage_trace = _j.loads(job_dict.get('stage_trace_json') or '[]')
        except Exception:
            pass

        return jsonify({
            'job': job_dict,
            'stage_trace': stage_trace,
            'timeline': timeline,
            'response': response_msg,
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@conversations_bp.route('/api/trace/conversation/<int:conv_id>')
def api_trace_conversation(conv_id):
    """Full trace for all jobs in a conversation, ordered chronologically."""
    conn = get_connection()
    try:
        jobs = conn.execute(
            """SELECT job_id, agent, status, runtime_class, elapsed_ms,
                      tokens, error, stage_trace_json, started_at, updated_at
               FROM chat_jobs WHERE conversation_id=?
               ORDER BY started_at ASC""", (conv_id,)
        ).fetchall()

        timeline = conn.execute(
            """SELECT id, agent, event_type, payload, created_at, job_id
               FROM conv_timeline WHERE conv_id=?
               ORDER BY id ASC LIMIT 500""", (conv_id,)
        ).fetchall()

        messages = conn.execute(
            """SELECT id, from_agent, to_agent, content, message_type,
                      tokens_used, created_at
               FROM messages WHERE conversation_id=?
               ORDER BY id ASC""", (conv_id,)
        ).fetchall()
        conn.close()

        import json as _j
        job_list = []
        for j in jobs:
            jd = dict(j)
            try:
                jd['stage_trace'] = _j.loads(jd.pop('stage_trace_json', '[]') or '[]')
            except Exception:
                jd['stage_trace'] = []
            job_list.append(jd)

        return jsonify({
            'conversation_id': conv_id,
            'jobs': job_list,
            'timeline': [dict(r) for r in timeline],
            'messages': [dict(r) for r in messages],
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
