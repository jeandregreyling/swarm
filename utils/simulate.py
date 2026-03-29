"""
simulate.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Dry-run simulation. Drives 3 fake tickets through the full pipeline.

No Gmail. No SMTP. All real DB writes (queue, tickets, duck_log, memories).
Email sends are intercepted and printed to console.

Usage:
    python3 simulate.py
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/lib/email')

# ── Patch send_reply before any import touches it ─────────────────────────
import email_handler as _eh

_sent_emails = []

def _fake_send(to_address, subject, body, **kwargs):
    _sent_emails.append({'to': to_address, 'subject': subject, 'body': body})
    print(f'\n  📧  [SIMULATED EMAIL]')
    print(f'      To:      {to_address}')
    print(f'      Subject: {subject}')
    preview = body[:300].replace('\r\n', '\n')
    for line in preview.split('\n')[:8]:
        print(f'      {line}')
    if len(body) > 300:
        print('      [...truncated...]')

_eh.send_reply = _fake_send

# ── Now import everything else ─────────────────────────────────────────────
import random
from database import new_conversation, log_message
from queue_manager import intake as queue_intake, get_queue_depth
from ticket import create as ticket_create, librarian_close
from orchestrator import consult_stage1, consult_stage2, consult_stage_eight

FAKE_SENDER = 'ghost@sevenpotato.local'

TICKETS = [
    {
        'subject': 'Australia trivia',
        'question': 'What is the longest river in Australia and how long is it?',
        'expected_route': 'web search — LLaMA/DDG + Gemma/Serper',
    },
    {
        'subject': 'System health check',
        'question': 'How much RAM is the swarm using right now and what is the CPU temperature?',
        'expected_route': 'IS_SYSTEM — Librarian health injection, no web search',
    },
    {
        'subject': 'SAP payroll question',
        'question': (
            'In SAP HCM payroll, what processing class should I set on a wage type '
            'to ensure it is included in the cumulation wage type for gross pay in T512W?'
        ),
        'expected_route': 'IS_SAP — Eight three-voice pipeline',
    },
    {
        'subject': 'Python question',
        'question': (
            'What is the difference between a list and a tuple in Python? '
            'When should I use each one?'
        ),
        'expected_route': 'both agents — LLaMA + Qwen + debate possible',
    },
]


def run_ticket(i, ticket):
    print(f'\n{"═"*70}')
    print(f'  TICKET {i+1} OF {len(TICKETS)}: {ticket["subject"]}')
    if ticket.get('expected_route'):
        print(f'  Expected route: {ticket["expected_route"]}')
    print(f'{"═"*70}')

    subject  = ticket['subject']
    question = ticket['question']

    # ── RL-004: Librarian intake ───────────────────────────────────────────
    queue_id, queue_position, tags = queue_intake(FAKE_SENDER, subject, question)
    print(f'\n[Librarian] Queue #{queue_id} — position {queue_position} — tags: {tags}')

    # ── Create conversation + ticket ───────────────────────────────────────
    conv_id       = new_conversation(question, source='simulate', sender=FAKE_SENDER)
    ticket_number = f'TICKET-{conv_id}'
    ticket_create(ticket_number, FAKE_SENDER, question, tags=tags, queue_id=queue_id)
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')
    print(f'[Ticket] {ticket_number} created.')

    # ── RL-006: Gemma read receipt — Email 0 ──────────────────────────────
    queue_line = (
        f'You are #{queue_position} in queue. Estimated wait: {queue_position * 3} minutes.\r\n\r\n'
        if queue_position > 1 else ''
    )
    email0 = (
        'I have your question.\r\n\r\n'
        + queue_line +
        'The swarm is deliberating. '
        'Full response coming shortly.\r\n\r\n'
        '---\r\n'
        'Re: ' + subject + '\r\n'
        "— Gemma | Seven's Swarm | sevenpotato9@gmail.com"
    )
    _fake_send(to_address=FAKE_SENDER, subject='[Swarm] On it: ' + subject, body=email0)
    print('[Listener] Read receipt sent (Gemma — Email 0).')

    # ── Stage 1: Gemma routes + LLaMA fast response ───────────────────────
    print(f'\n[Listener] Stage 1 — Gemma routing...')
    web_results, llama_answer, shared_context, routing = consult_stage1(question)
    print(f'[Routing] web={routing.get("needs_web")} agents={routing.get("agents")} '
          f'sap={routing.get("is_sap")} system={routing.get("is_system")} '
          f'identity={routing.get("is_identity")} mode={routing.get("mode")} '
          f'engines={routing.get("search_engines")}')

    if routing.get('is_sap'):
        email1 = (
            'Eight has picked up your SAP question. '
            'Specialist pipeline deliberating — this takes a few minutes.\r\n\r\n'
            '---\r\n'
            'Re: ' + subject + '\r\n'
            "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
        )
    else:
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
        email1 = (
            'Received your question and consulted the web immediately.\r\n\r\n'
            '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
            'The full swarm is now deliberating. Full response coming shortly.\r\n\r\n'
            '---\r\n'
            'Re: ' + question[:100] + '\r\n'
            "Sent by Seven's Swarm | sevenpotato9@gmail.com"
        )
    _fake_send(to_address=FAKE_SENDER, subject='[Swarm] Received: ' + subject, body=email1)
    print('[Listener] Stage 1 email sent.')

    # ── Stage 2: Eight (SAP) or Qwen + Gemma (standard) ──────────────────
    if routing.get('is_sap'):
        print('\n[Listener] IS_SAP — Eight specialist pipeline...')
        eight_result = consult_stage_eight(question, web_results, shared_context, conv_id)
        gemma_answer = eight_result['gemma_verdict']
        email2 = (
            'Eight has finished deliberating.\r\n\r\n'
            '[Functional]:\r\n' + eight_result.get('functional', '') + '\r\n\r\n'
            '[Technical]:\r\n' + eight_result.get('technical', '') + '\r\n\r\n'
            '[Devil\'s Advocate]:\r\n' + eight_result.get('devil', '') + '\r\n\r\n'
            '[Eight — Final verdict]:\r\n' + gemma_answer + '\r\n\r\n'
            '---\r\n'
            'Re: ' + question[:100] + '\r\n'
            "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
        )
    else:
        print('\n[Listener] Stage 2 — full swarm...')
        qwen_answer, gemma_answer, debate = consult_stage2(
            question, web_results, llama_answer, shared_context, conv_id, routing
        )
        if debate['fired']:
            print(f'\n[Debate] Challenge round fired — LLaMA R2: {debate["llama_r2"][:80]}...')
        email2 = (
            'The swarm has finished deliberating.\r\n\r\n'
            '[Qwen]:\r\n' + qwen_answer + '\r\n\r\n'
            '[Gemma — Final verdict]:\r\n' + gemma_answer + '\r\n\r\n'
            '---\r\n'
            'Re: ' + question[:100] + '\r\n'
            "Sent by Seven's Swarm | sevenpotato9@gmail.com"
        )
    _fake_send(to_address=FAKE_SENDER, subject='[Swarm] Full response: ' + subject, body=email2)
    print('[Listener] Stage 2 email sent.')

    # ── RL-007: Librarian closes ticket (Duck runs inside) ────────────────
    librarian_close(
        ticket_number, question, gemma_answer,
        queue_id=queue_id, sender_email=FAKE_SENDER
    )

    print(f'\n[Simulate] Ticket {ticket_number} complete. ✓')


def run():
    print("\n=== Seven's Swarm — DRY RUN SIMULATION ===")
    print(f'Sender:  {FAKE_SENDER}')
    print(f'Tickets: {len(TICKETS)}')
    print('No emails sent. All DB writes are real.')
    print('Covers: web search, IS_SYSTEM, IS_SAP (Eight), multi-agent debate.')
    print()

    passed = 0
    failed = []
    for i, ticket in enumerate(TICKETS):
        try:
            run_ticket(i, ticket)
            passed += 1
        except Exception as e:
            print(f'\n[FAIL] Ticket {i+1} "{ticket["subject"]}" raised: {e}')
            import traceback; traceback.print_exc()
            failed.append(ticket['subject'])

    print(f'\n{"═"*70}')
    print(f'  SIMULATION COMPLETE')
    print(f'  Passed: {passed}/{len(TICKETS)}')
    if failed:
        print(f'  FAILED: {", ".join(failed)}')
    print(f'  {len(_sent_emails)} simulated emails intercepted')
    print(f'{"═"*70}\n')


if __name__ == '__main__':
    run()
