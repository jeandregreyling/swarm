"""legacy.py — Legacy Pipeline & Approval routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

legacy_bp = Blueprint('legacy', __name__)

@legacy_bp.route('/chat', methods=['POST'])
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
                q.put({'type': 'agent', 'agent': 'Eight', 'text': result['gemma_verdict']})
                final_answer = result['gemma_verdict']
            else:
                # ── Standard pipeline ─────────────────────────────────────────
                q.put({'type': 'agent', 'agent': 'LLaMA', 'text': llama})

                q.put({'type': 'status', 'text': 'Mistral analysing...'})
                mistral, gemma, debate = orchestrator.consult_stage2(
                    question, web, llama, ctx, conv_id, routing
                )
                q.put({'type': 'agent', 'agent': 'Mistral', 'text': mistral})

                if debate['fired']:
                    q.put({'type': 'status', 'text': 'Debate detected — running challenge round...'})
                    q.put({'type': 'debate_r2', 'agent': 'LLaMA',   'text': debate['llama_r2']})
                    q.put({'type': 'debate_r2', 'agent': 'Mistral', 'text': debate['mistral_r2']})

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



@legacy_bp.route('/stream/<ticket_number>')
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
            mistral_answer, gemma_answer, debate = consult_stage2(
                pending_body, web_results, llama_answer, shared_context, conv_id, routing
            )
            debate_section = ''
            if debate['fired']:
                debate_section = (
                    '[Debate]\r\nLLaMA: ' + debate['llama_r2'] + '\r\n'
                    'Mistral: ' + debate['mistral_r2'] + '\r\n\r\n'
                )
            email2_body = (
                '[Mistral]:\r\n' + mistral_answer + '\r\n\r\n' +
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



@legacy_bp.route('/approve/<action>/<token>')
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



