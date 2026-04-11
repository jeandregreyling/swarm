"""
listener.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Entry point. Gmail Push Notifications (RL-011) when gmail_token.json exists,
falls back to IMAP poll every 60 seconds if not configured.

Flow for trusted senders:
    Librarian intake (RL-004)
    → Ticket created (RL-005)
    → Gemma read receipt — Email 0 (RL-006)
    → Stage 1 — LLaMA fast response — Email 1
    → Stage 2 — Qwen + Gemma full verdict — Email 2
    → Librarian closes ticket — Duck check + queue complete (RL-007)
    → Sniffles random trigger, 1-in-5 chance (RL-008)
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/lib/email')
sys.path.insert(0, '/home/seven/swarm/lib/system')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')

from config import GMAIL_ADDRESS, SEVEN_EMAIL, GHOST_EMAIL, DB_PATH, GMAIL_PASSWORD
from email_handler import fetch_unread, send_reply, mark_as_read
from email_cleaner import extract_subject_question, clean_subject, filter_non_english
from database import (get_all_email_lists, add_trusted_sender,
                      save_pending_email, get_pending_emails, mark_pending_processed,
                      remove_trusted_sender, remove_notification_sender,
                      add_notification_sender, new_conversation, log_message,
                      create_approval_token, log_activity,
                      find_ticket_by_thread, reopen_ticket, get_connection,
                      get_trusted_domains, add_trusted_domain,
                      update_ticket_tags, add_ticket_note_by_number,
                      snooze_ticket)
from system_clock import get_system_clock, get_timestamp
from orchestrator import consult_stage1, consult_stage2
from queue_manager import intake as queue_intake, get_queue_depth, estimate_wait_minutes, mark_processing
from ticket import create as ticket_create, librarian_close, set_routing as ticket_set_routing
from duck import on_queue_clear
from logging_bridge import log_action, log_ticket_lifecycle
import imaplib
import time
import random
import os
import logging

logger = logging.getLogger('seven.listener')


PUSH_RECOVERY_INTERVAL_SECONDS = 900


def _try_enable_gmail_push():
    """Best-effort Gmail Push activation without requiring a process restart."""
    try:
        from gmail_push import renew_watch_if_needed
        renew_watch_if_needed()
        return True, ''
    except Exception as exc:
        return False, str(exc)

# RL-010 — Simulation mode: SIMULATE=true intercepts all sends, no real emails
_SIMULATE = os.environ.get('SIMULATE', '').lower() in ('1', 'true', 'yes')
if _SIMULATE:
    print('[Listener] *** SIMULATE MODE — all emails intercepted, no sends ***')
    _real_send = send_reply
    def send_reply(to_address, subject, body, **kwargs):   # type: ignore[misc]
        print(f'  [SIMULATE] To: {to_address} | {subject}')
        preview = body[:200].replace('\r\n', '\n')
        for line in preview.split('\n')[:5]:
            print(f'  {line}')
        return True


def _send_reply_checked(*, to_address, subject, body, **kwargs):
    """Send and record telemetry on failure so missing confirmations are visible."""
    ok = send_reply(to_address=to_address, subject=subject, body=body, **kwargs)
    if not ok:
        try:
            log_activity('listener', 'send_failed', f'{to_address} | {subject[:120]}')
        except Exception:
            pass
    return ok


# ─────────────────────────────────────────────────────────────
# IMAP helpers
# ─────────────────────────────────────────────────────────────

def get_imap_connection():
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
    return mail


def ensure_gmail_label(mail, label):
    mail.create(label)


def move_to_label(mail, msg_id, label):
    try:
        ensure_gmail_label(mail, label)
        mail.copy(msg_id, label)
        mail.store(msg_id, '+FLAGS', '\\Deleted')
        mail.expunge()
    except Exception as e:
        print(f'[Label] Could not move email: {e}')


def move_to_notifications(mail, msg_id):
    """
    Move an email to the Notifications Gmail label, leaving it unread.
    Removes it from inbox so the listener doesn't reprocess it,
    but does NOT set the \\Seen flag — user can browse it in Notifications.
    """
    try:
        ensure_gmail_label(mail, 'Notifications')
        mail.copy(msg_id, 'Notifications')
        mail.store(msg_id, '+FLAGS', '\\Deleted')
        mail.expunge()
        print('[Listener] Moved to Notifications (unread).')
    except Exception as e:
        print(f'[Label] Could not move to Notifications: {e}')
        # Fallback: at least mark as read so it doesn't loop
        try:
            mail.store(msg_id, '+FLAGS', '\\Seen')
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# Email address helpers
# ─────────────────────────────────────────────────────────────

def extract_email_address(raw):
    if '<' in raw and '>' in raw:
        return raw.split('<')[1].split('>')[0].strip().lower()
    return raw.strip().lower()


def extract_all_recipients(email_data):
    recipients = []
    for field in ['to', 'cc']:
        value = email_data.get(field, '')
        if value:
            for addr in value.split(','):
                extracted = extract_email_address(addr)
                if extracted and extracted != SEVEN_EMAIL.lower():
                    recipients.append(extracted)
    return list(set(recipients))


def is_own_email(from_addr):
    return SEVEN_EMAIL.lower() in from_addr.lower()


# ─────────────────────────────────────────────────────────────
# Sender classification
# ─────────────────────────────────────────────────────────────

def classify_sender(from_addr):
    trusted, mods, notifications = get_all_email_lists()
    clean = extract_email_address(from_addr)
    if clean == SEVEN_EMAIL.lower():
        return 'self'
    if clean in mods:
        return 'moderator'
    if clean in trusted:
        return 'trusted'
    if clean in notifications:
        return 'notification'
    # Check trusted domains
    domain = clean.split('@')[-1] if '@' in clean else ''
    if domain and domain in get_trusted_domains():
        return 'trusted'
    return 'unknown'


# ─────────────────────────────────────────────────────────────
# Moderator command handler
# ─────────────────────────────────────────────────────────────

def _parse_snooze_time(raw):
    """
    Parse a snooze time string into an ISO datetime string.
    Supports: 30m, 2h, 2026-04-01, 2026-04-01 09:00
    Returns ISO string or None if unparseable.
    """
    from datetime import timedelta, datetime
    raw = raw.strip()
    now = get_system_clock().now()
    try:
        if raw.endswith('m') and raw[:-1].isdigit():
            return (now + timedelta(minutes=int(raw[:-1]))).isoformat(timespec='seconds')
        if raw.endswith('h') and raw[:-1].isdigit():
            return (now + timedelta(hours=int(raw[:-1]))).isoformat(timespec='seconds')
        if raw.endswith('d') and raw[:-1].isdigit():
            return (now + timedelta(days=int(raw[:-1]))).isoformat(timespec='seconds')
        # Try date or datetime
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw, fmt).isoformat(timespec='seconds')
            except ValueError:
                pass
    except Exception:
        pass
    return None


def handle_moderator_command(body, from_addr, subject=''):
    """
    Parse and execute a moderator command from the email body.

    Supports full commands:   NOTIFY email@addr.com
    Supports bare commands:   NOTIFY   (address extracted from subject)

    Subject format for bare commands: '[Swarm] Unknown sender: email@addr.com'
    Returns True if a command was found and executed, False otherwise.
    """
    # Extract target address from subject — covers bare one-word replies
    # Subject: '[Swarm] Unknown sender: noreply@service.com'
    # Subject: '[Swarm] Unknown sender: telegram:123456789'
    target_from_subject = ''
    if 'Unknown sender:' in subject:
        candidate = subject.split('Unknown sender:')[-1].strip()
        # Handle telegram: keys directly; otherwise parse as email
        if candidate.lower().startswith('telegram:'):
            target_from_subject = candidate.lower()
        else:
            target_from_subject = extract_email_address(candidate).lower()

    lines = body.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Expand bare one-word command using subject-extracted address
        upper = line.upper()
        if target_from_subject and upper in ('TRUST', 'NOTIFY', 'IGNORE'):
            print(f'[Listener] Bare command "{upper}" — expanding with subject address: {target_from_subject}')
            line = f'{upper} {target_from_subject}'

        if line.upper().startswith('TRUST '):
            email_to_trust = line[6:].strip().lower()
            add_trusted_sender(email_to_trust, from_addr, 'Approved by moderator')

            pending = get_pending_emails(email_to_trust)
            if pending:
                print(f'[Pending] Found {len(pending)} pending email(s) from {email_to_trust}')
                for p in pending:
                    pending_from    = p[1]
                    pending_subject = clean_subject(p[2])
                    pending_body    = p[3]
                    print(f'[Pending] Processing: {pending_subject} from {pending_from}')

                    # Librarian intake for the pending email
                    queue_id, position, tags = queue_intake(pending_from, pending_subject, pending_body)
                    conv_id       = new_conversation(pending_body, source='email', sender=pending_from)
                    ticket_number = f'TICKET-{conv_id}'
                    ticket_create(ticket_number, pending_from, pending_body, tags=tags, queue_id=queue_id)
                    log_message(conv_id, 'Ghost', pending_body, to_agent='Gemma', message_type='chat', created_at=get_timestamp())

                    # Stage 1
                    web_results, llama_answer, shared_context, routing = consult_stage1(pending_body)
                    ticket_set_routing(ticket_number, routing)
                    log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')

                    email1 = (
                        f'Received your question and consulted the web immediately. ({get_timestamp()})\r\n\r\n'
                        '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
                        'The full swarm is now deliberating. Full response coming shortly.\r\n\r\n'
                        '---\r\n'
                        'Re: ' + pending_subject + '\r\n'
                        "Sent by Seven's Swarm | sevenpotato9@gmail.com"
                    )
                    send_reply(to_address=pending_from, subject=pending_subject, body=email1)

                    # Stage 2
                    qwen_answer, gemma_answer, debate = consult_stage2(
                        pending_body, web_results, llama_answer, shared_context, conv_id, routing
                    )
                    debate_section = ''
                    if debate['fired']:
                        debate_section = (
                            '[Debate — Challenge round]\r\n'
                            'LLaMA: ' + debate['llama_r2'] + '\r\n'
                            'Qwen: ' + debate['qwen_r2'] + '\r\n\r\n'
                        )
                    email2 = (
                        'The swarm has finished deliberating.\r\n\r\n'
                        f'[Qwen]: ({get_timestamp()})\r\n' + qwen_answer + '\r\n\r\n' +
                        debate_section +
                        '[Gemma - Final verdict]:\r\n' + gemma_answer + '\r\n\r\n'
                        '---\r\n'
                        'Re: ' + pending_subject + '\r\n'
                        "Sent by Seven's Swarm | sevenpotato9@gmail.com"
                    )
                    send_reply(to_address=pending_from, subject=pending_subject, body=email2)

                    # Librarian closes
                    librarian_close(
                        ticket_number, pending_body, gemma_answer,
                        queue_id=queue_id, sender_email=pending_from
                    )
                    mark_pending_processed(p[0])

            send_reply(
                to_address=from_addr,
                subject='[Swarm] Sender approved',
                body=( # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
                    f'{email_to_trust} has been added to the trusted list. \r\n'
                    f'{len(pending) if pending else 0} pending email(s) processed.'
                ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
            )
            return True

        elif line.upper().startswith('NOTIFY '):
            email_to_notify = line[7:].strip().lower()
            add_notification_sender(email_to_notify, from_addr, 'Filed as notification by moderator')
            send_reply(
                to_address=from_addr,
                subject='[Swarm] Sender added to notifications',
                body=f'{email_to_notify} will be filed silently as a notification. \r\n\r\n(Timestamp: {get_timestamp()})'
            )
            return True

        elif line.upper().startswith('IGNORE '):
            email_to_ignore = line[7:].strip().lower()
            add_notification_sender(email_to_ignore, from_addr, 'Ignored by moderator')
            send_reply(
                to_address=from_addr,
                subject='[Swarm] Sender ignored',
                body=f'{email_to_ignore} will be silently ignored from now on. \r\n\r\n(Timestamp: {get_timestamp()})'
            )
            return True

        elif line.upper().startswith('REMOVE '):
            email_to_remove = line[7:].strip().lower()
            remove_trusted_sender(email_to_remove)
            send_reply(
                to_address=from_addr,
                subject='[Swarm] Sender removed',
                body=f'{email_to_remove} has been removed from the trusted list and is now unknown again. ({get_timestamp()})'
            )
            return True

        elif line.upper().startswith('TRUST DOMAIN '):
            domain = line[13:].strip().lower().lstrip('@')
            add_trusted_domain(domain, from_addr, 'Trusted by moderator')
            send_reply(
                to_address=from_addr,
                subject='[Swarm] Domain trusted',
                body=f'All senders from @{domain} will now be treated as trusted. ({get_timestamp()})'
            )
            return True

        elif line.upper().startswith('TAG '):
            # TAG TICKET-42 tag1 tag2 tag3
            parts = line.split(None, 2)
            if len(parts) >= 3:
                tn   = parts[1].upper()
                tags = parts[2].strip()
                ok   = update_ticket_tags(tn, tags)
                send_reply(
                    to_address=from_addr,
                    subject=f'[Swarm] Tags updated: {tn}',
                    body=f'Tags added to {tn}: {tags} ({get_timestamp()})' if ok else f'Ticket {tn} not found. ({get_timestamp()})'
                )
            return True

        elif line.upper().startswith('NOTE '):
            # NOTE TICKET-42 some note text
            parts = line.split(None, 2)
            if len(parts) >= 3:
                tn   = parts[1].upper()
                note = parts[2].strip()
                ok   = add_ticket_note_by_number(tn, from_addr, note, note_type='ghost_note')
                send_reply(
                    to_address=from_addr,
                    subject=f'[Swarm] Note added: {tn}',
                    body=f'Note logged on {tn}. ({get_timestamp()})' if ok else f'Ticket {tn} not found. ({get_timestamp()})'
                )
            return True

        elif line.upper().startswith('SNOOZE '):
            # SNOOZE TICKET-42 2h  OR  SNOOZE TICKET-42 2026-04-01  OR  SNOOZE TICKET-42 30m optional note
            parts = line.split(None, 3)
            if len(parts) >= 3:
                tn       = parts[1].upper()
                when_raw = parts[2].strip()
                note     = parts[3].strip() if len(parts) > 3 else ''
                wake_at  = _parse_snooze_time(when_raw)
                if wake_at:
                    snooze_ticket(tn, from_addr, wake_at, note)
                    send_reply(
                        to_address=from_addr,
                        subject=f'[Swarm] Snoozed: {tn}',
                        body=f'{tn} snoozed until {wake_at}.\nNote: {note} ({get_timestamp()})' if note else f'{tn} snoozed until {wake_at}. ({get_timestamp()})'
                    )
                else:
                    send_reply(
                        to_address=from_addr,
                        subject=f'[Swarm] Snooze parse error',
                        body=f'Could not parse time: {when_raw}\nUse: 30m, 2h, 2026-04-01, or 2026-04-01 09:00 ({get_timestamp()})'
                    )
            return True

        elif line.upper().startswith('REMOVENOTIFY '):
            email_to_remove = line[13:].strip().lower()
            remove_notification_sender(email_to_remove)
            send_reply(
                to_address=from_addr,
                subject='[Swarm] Notification sender removed',
                body=f'{email_to_remove} has been removed from the notification list. ({get_timestamp()})'
            )
            return True

        # ── RL-021: Skills — SKILL command ────────────────────
        elif line.upper().startswith('SKILL'):
            try:
                from fridays.skills import parse_skill_command, call as skill_call
                parsed = parse_skill_command(line)
                if parsed:
                    skill_name, args = parsed
                    ok, output = skill_call(skill_name, args=args, agent=from_addr)
                    send_reply(
                        to_address=from_addr,
                        subject=f'[Swarm] Skill: {skill_name}',
                        body=(
                            f'Skill: {skill_name} ({get_timestamp()})\n'
                            f'Args:  {args[:200]}\n'
                            f'{"✓ Success" if ok else "✗ Failed"}\n\n'
                            f'{output}'
                        )
                    )
                else:
                    from fridays.skills import list_skills
                    skills = list_skills()
                    lines = ['Available skills:\n']
                    for s in skills:
                        lines.append(f'  {s["name"]:12s} — {s["description"]}')
                        lines.append(f'               {s["usage"]}\n')
                    send_reply(
                        to_address=from_addr,
                        subject='[Swarm] Available skills',
                        body='\n'.join(lines) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
                    )
            except Exception as e:
                send_reply(
                    to_address=from_addr,
                    subject='[Swarm] Skill error',
                    body=f'Error running skill: {e}\n\nCommand: {line} ({get_timestamp()})'
                )
            return True

        # ── RL-020: Scheduler — SCHEDULE command ──────────────
        elif line.upper().startswith('SCHEDULE '):
            try:
                from fridays.scheduler import parse_schedule_command, add_task
                parsed = parse_schedule_command(line)
                if parsed:
                    name, schedule, action_type, action_data = parsed
                    task_id = add_task(name, schedule, action_type, action_data, created_by=from_addr)
                    send_reply(
                        to_address=from_addr,
                        subject='[Swarm] Task scheduled',
                        body=( # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
                            f'Task #{task_id} scheduled.\n\n'
                            f'Name:        {name}\n'
                            f'Schedule:    {schedule}\n'
                            f'Action:      {action_type}\n'
                            f'Data:        {action_data}\n\n'
                            f'Send: SCHEDULE LIST to see all tasks.\n'
                            f'Send: SCHEDULE CANCEL {task_id} to disable it.'
                        ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
                    )
                else:
                    send_reply(
                        to_address=from_addr,
                        subject='[Swarm] Schedule command failed',
                        body=( # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
                            f'Could not parse schedule command:\n  {line}\n\n'
                            f'Format: SCHEDULE <schedule> <action> <data>\n\n'
                            f'Examples:\n'
                            f'  SCHEDULE daily 09:00 QUESTION What is today\'s news?\n'
                            f'  SCHEDULE weekly mon 08:00 SHELL df -h\n'
                            f'  SCHEDULE once 2026-04-01 09:00 REMIND Check lease renewal\n'
                            f'  SCHEDULE interval 30 SHELL free -h\n'
                        ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
                    )
            except Exception as e:
                send_reply(
                    to_address=from_addr,
                    subject='[Swarm] Schedule error',
                    body=f'Error scheduling task: {e}\n\nCommand: {line} ({get_timestamp()})'
                )
            return True

        # ── Ghost Brief — on-demand intelligence synthesis ──────
        elif line.upper() in ('BRIEF', 'STATUS BRIEF', 'SWARM BRIEF'):
            try:
                from brief_engine import generate_brief
                brief = generate_brief(trigger='ghost_email_request')
                if brief:
                    body = brief['content'] + f'\r\n\r\n---\nGenerated by Nine · {brief["tokens_used"]} tokens used'
                    send_reply(to_address=from_addr, subject='[Swarm] Ghost Brief', body=body)
                else:
                    send_reply(to_address=from_addr, subject='[Swarm] Brief failed',
                               body=f'Ghost Brief generation failed. Check ANTHROPIC_API_KEY and logs.\r\n\r\n(Timestamp: {get_timestamp()})')
            except Exception as e:
                send_reply(to_address=from_addr, subject='[Swarm] Brief error', body=f'Error generating brief: {e}')
            return True

        # ── RL-020: Scheduler — list / cancel commands ─────────
        elif line.upper() in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
            try:
                from fridays.scheduler import list_tasks
                tasks = list_tasks()
                if tasks:
                    rows = '\n'.join(
                        f'#{t["id"]} | {t["schedule"]:20s} | {t["action_type"]:8s} | {t["action_data"][:40]} | next: {t["next_run"]}'
                        for t in tasks
                    )
                    body = f'Scheduled tasks ({len(tasks)}):\n\n{rows}\r\n\r\n(Timestamp: {get_timestamp()})'
                else:
                    body = f'No scheduled tasks. ({get_timestamp()})'
                send_reply(to_address=from_addr, subject='[Swarm] Scheduled tasks', body=body)
            except Exception as e:
                send_reply(to_address=from_addr, subject='[Swarm] List error', body=f'Error: {e}')
            return True # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body

        elif line.upper().startswith('SCHEDULE CANCEL '):
            try:
                from fridays.scheduler import disable_task
                task_id = int(line.split()[-1])
                disable_task(task_id)
                send_reply(
                    to_address=from_addr,
                    subject='[Swarm] Task cancelled',
                    body=f'Task #{task_id} has been disabled. ({get_timestamp()})'
                )
            except Exception as e:
                send_reply(to_address=from_addr, subject='[Swarm] Cancel error', body=f'Error: {e}')
            return True # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body

    return False


# ─────────────────────────────────────────────────────────────
# Unknown sender — notify moderator
# ─────────────────────────────────────────────────────────────

TERMINAL_URL = 'http://localhost:5050'


def ask_moderator_about(from_addr, subject, body_preview):
    trusted, mods, notifications = get_all_email_lists()
    if not mods:
        return

    trust_tok  = create_approval_token('trust',  from_addr, 'moderator_email')
    notify_tok = create_approval_token('notify', from_addr, 'moderator_email')
    ignore_tok = create_approval_token('ignore', from_addr, 'moderator_email')
    trust_link  = f'{TERMINAL_URL}/approve/trust/{trust_tok}'
    notify_link = f'{TERMINAL_URL}/approve/notify/{notify_tok}'
    ignore_link = f'{TERMINAL_URL}/approve/ignore/{ignore_tok}'

    plain = (
        f'Seven received an email from an unknown sender.\n\n'
        f'From:    {from_addr}\n'
        f'Subject: {subject or "(no subject)"}\n'
        f'Preview: {body_preview[:200]}\n\n'
        f'One-click action links (open in browser):\n\n'
        f'TRUST   {trust_link}\n\n'
        f'NOTIFY  {notify_link}\n\n'
        f'IGNORE  {ignore_link}\n'
    )
    html = f"""<!DOCTYPE html>
<html><body style="background:#0f0f0f;color:#e0e0e0;font-family:monospace;padding:20px;max-width:600px">
<p style="color:#888;font-size:13px">Seven received an email from an unknown sender.</p>
<table style="margin:14px 0;font-size:13px;border-collapse:collapse">
  <tr><td style="color:#555;padding:3px 12px 3px 0">From</td><td style="color:#e0e0e0">{from_addr}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0">Subject</td><td style="color:#e0e0e0">{subject or '(no subject)'}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0;vertical-align:top">Preview</td><td style="color:#aaa">{body_preview[:200]}</td></tr>
</table>
<p style="color:#555;font-size:11px;margin-bottom:12px">Click an action — one click, no reply needed.</p>
<table style="border-collapse:collapse">
  <tr>
    <td style="padding:4px 8px 4px 0"><a href="{trust_link}"  style="background:#1a3a1a;color:#66cc66;border:1px solid #2d6b2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">TRUST</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{notify_link}" style="background:#1a1a3a;color:#6666cc;border:1px solid #2d2d6b;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">NOTIFY</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{ignore_link}" style="background:#2a1a0d;color:#cc8844;border:1px solid #6b4a2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">IGNORE</a></td>
  </tr>
</table>
<p style="color:#333;font-size:10px;margin-top:20px">Seven's Swarm — seven-potato</p>
</body></html>"""

    for mod in mods:
        ok = _send_reply_checked(
            to_address=mod,
            subject=f'[Swarm] Unknown sender: {from_addr}',
            body=plain + f'\r\n\r\n(Timestamp: {get_timestamp()})',
            html_body=html
        )
        if ok:
            log_activity('listener', 'notify_sent', f'{from_addr} -> {mod}')
        else:
            log_activity('listener', 'notify_failed', f'{from_addr} -> {mod}')
    try:
        import discord_notify
        discord_notify.notify_unknown_sender(from_addr, subject, body_preview, source='email')
    except Exception:
        pass
    print(f'[Trust] Moderator notified about: {from_addr}')


def _notify_ignored(from_addr, subject, body_preview, reason):
    """
    Notify moderators that Librarian auto-ignored an unknown sender.
    Sends HTML email with TRUST / NOTIFY / IGNORE action buttons.
    Only called once per sender (caller checks activity_log).
    """
    trusted, mods, notifications = get_all_email_lists()
    if not mods:
        return

    trust_tok  = create_approval_token('trust',  from_addr, 'moderator_email')
    notify_tok = create_approval_token('notify', from_addr, 'moderator_email')
    ignore_tok = create_approval_token('ignore', from_addr, 'moderator_email')
    trust_link  = f'{TERMINAL_URL}/approve/trust/{trust_tok}'
    notify_link = f'{TERMINAL_URL}/approve/notify/{notify_tok}'
    ignore_link = f'{TERMINAL_URL}/approve/ignore/{ignore_tok}'

    plain = (
        f'Librarian automatically ignored an email from an unknown sender.\n\n'
        f'From:    {from_addr}\n'
        f'Subject: {subject or "(no subject)"}\n'
        f'Reason:  {reason}\n'
        f'Preview: {body_preview[:200]}\n\n'
        f'The email has been moved to your Notifications folder (unread).\n'
        f'Future emails from this sender will be moved silently — no more notifications.\n\n'
        f'If this was a mistake, click one of these one-click links:\n\n'
        f'TRUST   {trust_link}\n\n'
        f'NOTIFY  {notify_link}\n\n'
        f'IGNORE  {ignore_link}\n'
    )
    html = f"""<!DOCTYPE html>
<html><body style="background:#0f0f0f;color:#e0e0e0;font-family:monospace;padding:20px;max-width:600px">
<p style="color:#888;font-size:13px">Librarian automatically ignored an email from an unknown sender.</p>
<table style="margin:14px 0;font-size:13px;border-collapse:collapse">
  <tr><td style="color:#555;padding:3px 12px 3px 0">From</td><td style="color:#e0e0e0">{from_addr}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0">Subject</td><td style="color:#e0e0e0">{subject or '(no subject)'}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0">Reason</td><td style="color:#cc8844">{reason}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0;vertical-align:top">Preview</td><td style="color:#aaa">{body_preview[:200]}</td></tr>
</table>
<p style="color:#555;font-size:11px;margin-bottom:4px">Email moved to <strong style="color:#6699cc">Notifications</strong> folder (unread). Future emails from this sender will be moved silently.</p>
<p style="color:#555;font-size:11px;margin-bottom:12px">Click an action if this was a mistake — one click, no reply needed.</p>
<table style="border-collapse:collapse">
  <tr>
    <td style="padding:4px 8px 4px 0"><a href="{trust_link}"  style="background:#1a3a1a;color:#66cc66;border:1px solid #2d6b2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">TRUST</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{notify_link}" style="background:#1a1a3a;color:#6666cc;border:1px solid #2d2d6b;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">NOTIFY</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{ignore_link}" style="background:#2a1a0d;color:#cc8844;border:1px solid #6b4a2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">IGNORE</a></td>
  </tr>
</table>
<p style="color:#333;font-size:10px;margin-top:20px">Seven's Swarm — seven-potato</p>
</body></html>"""

    for mod in mods:
        ok = _send_reply_checked(
            to_address=mod,
            subject=f'[Swarm] Auto-ignored: {from_addr}',
            body=plain + f'\r\n\r\n(Timestamp: {get_timestamp()})',
            html_body=html
        )
        if ok:
            log_activity('listener', 'notify_sent', f'auto-ignored {from_addr} -> {mod}')
        else:
            log_activity('listener', 'notify_failed', f'auto-ignored {from_addr} -> {mod}')
    try:
        import discord_notify
        discord_notify.notify_unknown_sender(from_addr, subject, body_preview[:200], source='email (auto-ignored)')
    except Exception:
        pass
    print(f'[Triage] Moderator notified about ignored sender: {from_addr}')


# ─────────────────────────────────────────────────────────────
# Librarian triage — auto-decide unknown senders
# ─────────────────────────────────────────────────────────────

def librarian_triage(from_addr, subject, body):
    """
    Ask Librarian whether an email from an unknown sender is worth answering.
    Returns ('ANSWER', reason) or ('IGNORE', reason).

    ANSWER — Librarian thinks it's a genuine question worth processing.
    IGNORE — Looks like spam, newsletter, notification, or junk.
    """
    import ollama

    preview = body[:600].strip()
    prompt = (
        f'You are Librarian, the archivist for Seven\'s Swarm. An email has arrived from an unknown sender.\n\n'
        f'From:    {from_addr}\n'
        f'Subject: {subject or "(no subject)"}\n'
        f'Body:\n{preview}\n\n'
        f'Decide whether this email is worth answering. Reply with exactly one of:\n'
        f'ANSWER — it is a genuine question or message that deserves a response\n'
        f'IGNORE — it is spam, a newsletter, a notification, marketing, or automated junk\n\n'
        f'Then on the next line, give a single short sentence explaining why (max 15 words).\n'
        f'Reply in this exact format:\nANSWER\nReason here.\n\nOR\n\nIGNORE\nReason here.'
    )

    try:
        response = ollama.chat(
            model='qwen:latest',
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.1},
            keep_alive=-1,
        )
        text = response['message']['content'].strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        decision = lines[0].upper() if lines else 'IGNORE'
        reason = lines[1] if len(lines) > 1 else 'No reason given.'
        if 'ANSWER' in decision:
            return 'ANSWER', reason
        return 'IGNORE', reason
    except Exception as e:
        logger.error(f'[Triage] Librarian triage failed: {e}')
        return 'IGNORE', f'Triage error — defaulting to ignore: {e}'


# ─────────────────────────────────────────────────────────────
# Follow-up handler — reply to existing ticket thread
# ─────────────────────────────────────────────────────────────

def handle_followup_email(e, clean_from, subject, body, thread_cc, ticket):
    """
    Process an email that is a reply to an existing ticket thread.
    Reopens the ticket, logs the follow-up, and runs the full pipeline
    with prior conversation history injected as context.
    """
    ticket_number = ticket['ticket_number']
    # Derive conv_id from ticket_number (format: TICKET-{conv_id})
    try:
        conv_id = int(ticket_number.split('-')[1])
    except (IndexError, ValueError):
        conv_id = None

    # Reopen the ticket if it was closed
    reopen_ticket(ticket_number)

    # Clean the new question
    clean_subj = clean_subject(subject)
    followup_q = extract_subject_question(clean_subj, body)

    # Build history context from prior messages in this conversation
    history_context = ''
    if conv_id:
        prior = get_connection().execute(
            'SELECT from_agent, content FROM messages '
            'WHERE conversation_id=? ORDER BY id',
            (conv_id,)
        ).fetchall()
        if prior:
            lines = []
            for row in prior:
                agent = row['from_agent']
                snippet = row['content'][:300].replace('\r\n', ' ').replace('\n', ' ')
                lines.append(f'{agent}: {snippet}')
            history_context = (
                '\n\n[Prior conversation history for this ticket]\n' +
                '\n'.join(lines)
            )

    # Compose augmented question with history
    augmented_q = followup_q
    if history_context:
        augmented_q = followup_q + history_context

    log_message(conv_id, 'Ghost', followup_q, to_agent='Gemma', message_type='chat', created_at=get_system_clock().timestamp_compact())
    log_activity('listener', 'followup_start',
                 f'{ticket_number} | {clean_from} | {followup_q[:80]}')

    # Read receipt
    email0 = (
        f'Follow-up received for {ticket_number}.\r\n\r\n'
        'The swarm is deliberating on your follow-up. Full response coming shortly.\r\n\r\n'
        '---\r\n'
        f'Re: {clean_subj}\r\n'
        "— Gemma | Seven's Swarm | sevenpotato9@gmail.com"
    )
    _send_reply_checked(
        to_address=e['from'],
        subject=f'[Swarm] Follow-up received: {clean_subj}',
        body=email0 + f'\r\n\r\n(Timestamp: {get_timestamp()})',
        original_message_id=e.get('message_id'),
        cc=thread_cc
    )

    # Stage 1
    from queue_manager import mark_processing, get_queue_depth
    queue_id, _, tags = queue_intake(clean_from, clean_subj, augmented_q)
    mark_processing(queue_id)
    web_results, llama_answer, shared_context, routing = consult_stage1(augmented_q)
    ticket_set_routing(ticket_number, routing)

    if routing.get('is_sap'):
        email1 = (
            'Eight has picked up your SAP follow-up. '
            'The specialist pipeline is deliberating — this takes a few minutes.\r\n\r\n'
            '---\r\n'
            f'Re: {clean_subj}\r\n' # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
            "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
        )
    else:
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
        email1 = (
            'Received your follow-up and consulted the web immediately.\r\n\r\n'
            '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
            'The full swarm is deliberating. Full response coming shortly.\r\n\r\n'
            '---\r\n'
            f'Re: {augmented_q[:100]}\r\n'
            "Sent by Seven's Swarm | sevenpotato9@gmail.com" # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
        )
    _send_reply_checked(
        to_address=e['from'],
        subject=f'[Swarm] Follow-up received: {clean_subj}',
        body=email1,
        original_message_id=e.get('message_id'),
        cc=thread_cc
    )

    # Stage 2
    if routing.get('is_sap'):
        from orchestrator import consult_stage_eight
        eight_result = {}
        try:
            eight_result = consult_stage_eight(augmented_q, web_results, shared_context, conv_id)
            gemma_answer = eight_result['gemma_verdict']
            email2 = (
                'Eight has finished deliberating on your follow-up.\r\n\r\n'
                '[Eight — SAP verdict]:\r\n' + gemma_answer + '\r\n\r\n'
                '---\r\n'
                f'Re: {augmented_q[:100]}\r\n'
                "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
            )
        except Exception as eight_err:
            log_activity('listener', 'eight_error', f'{ticket_number} followup: {eight_err}')
            gemma_answer = '(Eight did not complete)'
            email2 = (
                'Eight encountered an error on your follow-up.\r\n\r\n'
                f'⚠ Error: {str(eight_err)[:200]}\r\n\r\n'
                '---\r\n'
                f'Re: {augmented_q[:100]}\r\n'
                "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
            )
    else:
        qwen_answer, gemma_answer, debate = consult_stage2(
            augmented_q, web_results, llama_answer, shared_context, conv_id, routing
        )
        debate_section = ''
        if debate['fired']:
            debate_section = (
                '[Debate — Challenge round]\r\n'
                'LLaMA: ' + debate['llama_r2'] + '\r\n'
                'Qwen: ' + debate['qwen_r2'] + '\r\n\r\n'
            )
        qwen_section = ('[Qwen]:\r\n' + qwen_answer + '\r\n\r\n') if qwen_answer else ''
        email2 = (
            'The swarm has finished deliberating on your follow-up.\r\n\r\n' +
            qwen_section + debate_section +
            '[Gemma — Final verdict]:\r\n' + gemma_answer + '\r\n\r\n'
            '---\r\n'
            f'Re: {augmented_q[:100]}\r\n'
            "Sent by Seven's Swarm | sevenpotato9@gmail.com" # [2026-03-26 17:15:00] Agent Ten: Added timestamp to email body
        )

    _send_reply_checked(
        to_address=e['from'],
        subject=f'[Swarm] Follow-up response: {clean_subj}',
        body=email2,
        original_message_id=e.get('message_id'),
        cc=thread_cc
    )
    log_activity('listener', 'followup_done', f'{ticket_number} | reply sent to {clean_from}')

    # Close ticket
    librarian_close(
        ticket_number, augmented_q, gemma_answer,
        queue_id=queue_id, sender_email=clean_from
    )
    from queue_manager import get_queue_depth as _gqd
    if _gqd() == 0:
        from duck import on_queue_clear
        on_queue_clear()


# ─────────────────────────────────────────────────────────────
# Main processing loop
# ─────────────────────────────────────────────────────────────

def process_emails(emails=None):
    if emails is None:
        print('\n[Listener] Checking inbox...')
        emails = fetch_unread()

    if not emails:
        print('[Listener] No new emails.')
        return

    print(f'[Listener] Found {len(emails)} unread email(s).')

    already_notified  = set()
    emails_processed  = 0

    for e in emails:
        from_addr  = e['from']
        clean_from = extract_email_address(from_addr)
        subject    = e['subject']
        body       = e['body']
        msg_id     = e['id']

        print(f'\n[Listener] From: {from_addr}')
        print(f'[Listener] Subject: {subject}')

        classification = classify_sender(from_addr)
        print(f'[Listener] Classification: {classification}')
        log_activity('listener', 'email_received', f'From: {clean_from} | {subject[:80]} | {classification}')

        # ── Self ──────────────────────────────────────────────
        if classification == 'self':
            print('[Listener] Skipping — own email.')
            mark_as_read(msg_id)
            continue

        # ── Notification ──────────────────────────────────────
        if classification == 'notification':
            print('[Listener] Filing as notification — moving to Notifications label (unread).')
            try:
                mail = get_imap_connection()
                mail.select('inbox')
                move_to_notifications(mail, msg_id)
                mail.logout()
            except Exception as ex:
                print(f'[Listener] Could not file notification: {ex}')
                mark_as_read(msg_id)  # fallback so it doesn't loop
            continue

        # ── Moderator commands ────────────────────────────────
        if classification == 'moderator':
            if handle_moderator_command(body, clean_from, subject=subject):
                print('[Listener] Moderator command processed.')
                log_activity('listener', 'command_processed', f'From: {clean_from} | {body.strip()[:60]}')
                mark_as_read(msg_id)
                continue
            else:
                # No command — treat as a question from Ghost, fall through to pipeline
                print('[Listener] Moderator — no command found, treating as trusted question.')
                classification = 'trusted'

        # ── Unknown sender — Librarian triage ────────────────
        if classification == 'unknown':
            clean_body = extract_subject_question(subject, body)
            clean_subj = clean_subject(subject)

            if clean_from not in already_notified:
                already_notified.add(clean_from)
                print(f'[Triage] Librarian assessing email from {clean_from}...')
                decision, reason = librarian_triage(clean_from, clean_subj, clean_body)
                log_activity('listener', 'triage', f'{clean_from} → {decision} | {reason}')
                print(f'[Triage] Decision: {decision} — {reason}')

                if decision == 'ANSWER':
                    # Librarian says worth answering — run pipeline without adding to trusted list
                    print(f'[Triage] Answering email from unknown sender: {clean_from}')
                    classification = 'trusted'
                    # Fall through to trusted pipeline below
                else:
                    # Librarian says ignore — move to Notifications (unread), notify Ghost once
                    log_activity('listener', 'triage_ignored', f'{clean_from} | {reason}')
                    try:
                        _mail = get_imap_connection()
                        _mail.select('inbox')
                        move_to_notifications(_mail, msg_id)
                        _mail.logout()
                    except Exception as _me:
                        print(f'[Listener] Move failed: {_me}')
                        mark_as_read(msg_id)

                    # Only notify Ghost the first time we see this sender
                    _conn = get_connection()
                    _prev = _conn.execute(
                        "SELECT id FROM activity_log WHERE service='listener' "
                        "AND event='ignored_notified' AND detail LIKE ? LIMIT 1",
                        (f'{clean_from}%',)
                    ).fetchone()
                    _conn.close()
                    if not _prev:
                        _notify_ignored(clean_from, clean_subj, clean_body[:300], reason)
                        log_activity('listener', 'ignored_notified', f'{clean_from} | {reason}')
                    else:
                        print(f'[Triage] Already notified about {clean_from} — silent move.')
                    continue
            else:
                # Already triaged this sender this pass — move silently
                try:
                    _mail = get_imap_connection()
                    _mail.select('inbox')
                    move_to_notifications(_mail, msg_id)
                    _mail.logout()
                except Exception:
                    mark_as_read(msg_id)
                continue

        # ── Trusted sender — full pipeline ────────────────────

        # Reply-all: collect all To/CC addresses from the original email,
        # excluding seven's own address. Auto-trust any new ones.
        thread_cc = extract_all_recipients(e)
        trusted, mods, notifications = get_all_email_lists()
        for recipient in thread_cc:
            if recipient not in trusted and recipient not in mods and recipient not in notifications:
                add_trusted_sender(
                    recipient, clean_from,
                    f'Auto-added via reply-all from {clean_from}'
                )
                log_activity('listener', 'auto_trusted', f'{recipient} — added from thread with {clean_from}')
                print(f'[Listener] Auto-trusted: {recipient}')

        # ── Thread matching — Message-ID then subject fallback ───────────────
        in_reply_to = e.get('in_reply_to', '')
        references  = e.get('references', '')
        matched_ticket = find_ticket_by_thread(in_reply_to, references)

        # Subject fallback: parse [Swarm #42] from subject
        if not matched_ticket:
            import re as _re
            _m = _re.search(r'\[Swarm #(\d+)\]', subject, _re.IGNORECASE)
            if _m:
                _tn = f'TICKET-{_m.group(1)}'
                _conn = get_connection()
                _row = _conn.execute(
                    'SELECT * FROM tickets WHERE ticket_number=?', (_tn,)
                ).fetchone()
                _conn.close()
                if _row:
                    matched_ticket = dict(_row)

        if matched_ticket:
            # Check if this is a ghost NOTE: shortcut (reply body starts with NOTE:)
            _note_body = body.strip()
            if _note_body.upper().startswith('NOTE:'):
                _note_text = _note_body[5:].strip()
                add_ticket_note_by_number(matched_ticket['ticket_number'], clean_from,
                                          _note_text, note_type='ghost_note')
                send_reply(
                    to_address=from_addr,
                    subject=f'[Swarm] Note logged: {matched_ticket["ticket_number"]}',
                    body=f'Note added to {matched_ticket["ticket_number"]}.',
                    cc=thread_cc
                )
                log_activity('listener', 'note_added',
                             f'{matched_ticket["ticket_number"]} | {_note_text[:80]}')
                mark_as_read(msg_id)
                continue

            print(f'[Listener] Thread match — follow-up to {matched_ticket["ticket_number"]}')
            log_activity('listener', 'thread_match',
                         f'{matched_ticket["ticket_number"]} | from {clean_from}')
            handle_followup_email(e, clean_from, subject, body, thread_cc, matched_ticket)
            mark_as_read(msg_id)
            emails_processed += 1
            if emails_processed >= 1:
                print('[Listener] One email fully processed. Next on next cycle.')
                break
            continue

        # Clean the question
        subject  = clean_subject(subject)
        question = extract_subject_question(subject, body)

        # ── URGENT detection — jump the queue ─────────────────
        is_urgent = 'URGENT' in (subject + ' ' + body[:200]).upper()
        if is_urgent:
            print(f'[Listener] URGENT flag detected — priority queue.')
            log_activity('listener', 'urgent', f'From: {clean_from} | {subject[:80]}')

        # ── RL-004: Librarian intake ──────────────────────────
        queue_id, queue_position, tags = queue_intake(
            clean_from, subject, question, priority=1 if is_urgent else 5
        )
        print(f'[Librarian] Queue position {queue_position} assigned.')

        # Create conversation + ticket
        conv_id       = new_conversation(question, source='email', sender=clean_from)
        ticket_number = f'TICKET-{conv_id}'
        ticket_ref    = f'[Swarm #{conv_id}]'  # embedded in subjects for thread matching
        ticket_create(ticket_number, clean_from, question, tags=tags, queue_id=queue_id, email_message_id=e.get('message_id', ''))
        log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')
        try:
            import discord_notify
            discord_notify.notify_ticket_opened(ticket_number, clean_from, question,
                                                is_urgent=is_urgent, source='email')
        except Exception:
            pass

        # ── RL-006: Gemma read receipt — Email 0 ─────────────
        queue_line = (
            f'You are #{queue_position} in queue. '
            f'Estimated wait: {estimate_wait_minutes(queue_position)} minutes.\r\n\r\n'
            if queue_position > 1 else ''
        )
        urgent_line = '⚡ Marked URGENT — jumped to front of queue.\r\n\r\n' if is_urgent else ''
        email0 = (
            'I have your question.\r\n\r\n'
            + urgent_line
            + queue_line +
            'The swarm is deliberating. LLaMA is searching now. '
            'Full response coming shortly.\r\n\r\n'
            '---\r\n'
            'Re: ' + subject + '\r\n'
            "— Gemma | Seven's Swarm | sevenpotato9@gmail.com"
        ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
        _send_reply_checked(
            to_address=from_addr,
            subject=ticket_ref + ' On it: ' + subject,
            body=email0,
            original_message_id=e.get('message_id'),
            cc=thread_cc
        )
        print('[Listener] Read receipt sent (Gemma — Email 0).')

        # ── Stage 1: Gemma routes + LLaMA fast response ──────
        mark_processing(queue_id)
        log_activity('listener', 'pipeline_start', f'{ticket_number} | {clean_from} | {question[:80]}')
        print(f'[Listener] Stage 1 — fast response: {question[:80]}...')
        web_results, llama_answer, shared_context, routing = consult_stage1(question)
        ticket_set_routing(ticket_number, routing)
        log_activity('listener', 'stage1_done', f'{ticket_number} | routing: {routing.get("agents","?")} sap={routing.get("is_sap",False)}')

        if routing.get('is_sap'):
            print('[Listener] IS_SAP=yes — Eight specialist engaged.')
            email1 = (
                'Eight has picked up your SAP question. '
                'The specialist pipeline is deliberating — this takes a few minutes.\r\n\r\n'
                '---\r\n'
                'Re: ' + subject + '\r\n'
                "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
            ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
        else:
            log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
            email1 = (
                'Received your question and consulted the web immediately.\r\n\r\n'
                '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
                'The full swarm is now deliberating. Full response coming shortly.\r\n\r\n'
                '---\r\n'
                'Re: ' + question[:100] + '\r\n'
                "Sent by Seven's Swarm | sevenpotato9@gmail.com"
            ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
        _send_reply_checked(
            to_address=from_addr,
            subject=ticket_ref + ' Received: ' + subject,
            body=email1,
            original_message_id=e.get('message_id'),
            cc=thread_cc
        )
        print('[Listener] Stage 1 email sent.')

        # ── Stage 2: Eight (SAP) or Qwen + Gemma (standard) ──
        if routing.get('is_sap'):
            print('[Listener] Eight pipeline...')
            from orchestrator import consult_stage_eight
            eight_result = {}
            try:
                eight_result = consult_stage_eight(question, web_results, shared_context, conv_id)
                gemma_answer = eight_result['gemma_verdict']
                email2 = (
                    'Eight has finished deliberating.\r\n\r\n'
                    '[Eight — SAP verdict]:\r\n' + gemma_answer + '\r\n\r\n'
                    '---\r\n'
                    'Re: ' + question[:100] + '\r\n'
                    "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
                ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
            except Exception as eight_err:
                print(f'[Listener] Eight pipeline error: {eight_err}')
                log_activity('listener', 'eight_error', f'{ticket_number}: {eight_err}')
                gemma_answer = '(Eight did not complete)'
                email2 = (
                    'Eight encountered an error.\r\n\r\n'
                    f'⚠ Error: {str(eight_err)[:200]}\r\n\r\n'
                    '---\r\n'
                    'Re: ' + question[:100] + '\r\n'
                    "Sent by Eight | Seven's Swarm | sevenpotato9@gmail.com"
                ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
        else:
            print('[Listener] Stage 2 — full swarm...')
            qwen_answer, gemma_answer, debate = consult_stage2(
                question, web_results, llama_answer, shared_context, conv_id, routing
            )
            debate_section = ''
            if debate['fired']:
                debate_section = (
                    '[Debate — Challenge round]\r\n'
                    'LLaMA: ' + debate['llama_r2'] + '\r\n'
                    'Qwen: ' + debate['qwen_r2'] + '\r\n\r\n'
                )
            qwen_section = ('[Qwen]:\r\n' + qwen_answer + '\r\n\r\n') if qwen_answer else ''
            email2 = (
                'The swarm has finished deliberating.\r\n\r\n' +
                qwen_section +
                debate_section +
                '[Gemma — Final verdict]:\r\n' + gemma_answer + '\r\n\r\n'
                '---\r\n'
                'Re: ' + question[:100] + '\r\n'
                "Sent by Seven's Swarm | sevenpotato9@gmail.com"
            ) + f'\r\n\r\n(Timestamp: {get_timestamp()})'
        _send_reply_checked(
            to_address=from_addr,
            subject=ticket_ref + ' Full response: ' + subject,
            body=email2,
            original_message_id=e.get('message_id'),
            cc=thread_cc
        )
        print('[Listener] Stage 2 email sent.')
        log_activity('listener', 'stage2_done', f'{ticket_number} | reply sent to {clean_from}')

        # ── RL-007: Librarian closes ticket ───────────────────
        # Duck sanity check runs inside librarian_close.
        # Ticket status updated. Queue entry marked completed.
        librarian_close(
            ticket_number, question, gemma_answer,
            queue_id=queue_id, sender_email=clean_from
        )
        log_activity('listener', 'ticket_closed', f'{ticket_number} | Duck verdict pending')
        try:
            import discord_notify
            conn_dc = get_connection()
            duck_row = conn_dc.execute(
                'SELECT result FROM duck_log WHERE ticket_number=? ORDER BY id DESC LIMIT 1',
                (ticket_number,)
            ).fetchone()
            conn_dc.close()
            discord_notify.notify_ticket_closed(ticket_number, duck_row['result'] if duck_row else '—')
        except Exception:
            pass

        # ── RL-008: Random Sniffles trigger ───────────────────
        # 1-in-5 chance on every email processed, independent of Duck verdict.
        # Sniffles' own should_run() guard means it won't do unnecessary work.
        if random.random() < 0.2:
            print('[Listener] RL-008: Random Sniffles audit triggered.')
            import subprocess
            subprocess.Popen(['python3', '/home/seven/swarm/agents/ghost/sniffer.py'])

        # ── Duck queue-clear notification ─────────────────────
        # If nothing left processing or queued, Duck sends Ghost the all-clear.
        if get_queue_depth() == 0:
            on_queue_clear()

        # BUG-008 fix: mark as read only after full successful processing
        mark_as_read(msg_id)
        emails_processed += 1
        if emails_processed >= 1:
            print('[Listener] One email fully processed. Next on next cycle.')
            break


# ─────────────────────────────────────────────────────────────
# Service loop
# ─────────────────────────────────────────────────────────────

def _ensure_digest_scheduled():
    """Register the daily digest and Ghost Brief tasks if not already in the scheduler."""
    try:
        from fridays.scheduler import list_tasks, add_task
        tasks = list_tasks()
        if not any('digest' in (t.get('name') or '').lower() for t in tasks):
            add_task('daily_digest', 'daily 07:00', 'SHELL',
                     'python3 /home/seven/swarm/swarm_tasks.py digest',
                     created_by='system')
            print('[Listener] Daily digest scheduled at 07:00.')
        if not any('brief' in (t.get('name') or '').lower() for t in tasks):
            add_task('daily_brief', 'daily 07:05', 'SHELL',
                     'python3 /home/seven/swarm/utils/brief_engine.py daily',
                     created_by='system')
            print('[Listener] Daily Ghost Brief scheduled at 07:05.')
    except Exception as e:
        print(f'[Listener] Could not schedule digest: {e}')


def _startup_queue_cleanup():
    """
    On restart: any queue entries stuck as 'processing' are orphaned — the worker
    that was processing them died with the service. Reset them to 'queued' so they
    get picked up again. Also abandon 'queued' entries older than 2 hours that
    were never picked up (crashed runs, manual restarts mid-pipeline).
    """
    from database import get_connection
    conn = get_connection()
    # Reset orphaned processing entries → queued (were being worked on when we died)
    reset = conn.execute(
        "UPDATE queue SET status='queued' WHERE status='processing'"
    ).rowcount
    # Abandon very old queued entries (2h+) — they're stale, not worth re-running
    abandoned = conn.execute(
        "UPDATE queue SET status='abandoned' WHERE status='queued' "
        "AND created_at < datetime('now', '-2 hours')"
    ).rowcount
    conn.commit()
    conn.close()
    if reset:
        print(f'[Listener] Startup: reset {reset} orphaned processing entries → queued.')
        log_activity('listener', 'startup_reset', f'{reset} processing entries reset to queued')
    if abandoned:
        print(f'[Listener] Startup: abandoned {abandoned} stale queue entries (2h+ old).')


def run_forever(interval=60):
    # Ensure DB schema is up to date (adds any columns added after initial deploy)
    from database import _migrate_schema
    _migrate_schema()
    _ensure_digest_scheduled()
    _startup_queue_cleanup()

    # Use Gmail Push if token exists, otherwise fall back to IMAP poll
    push_token = '/home/seven/swarm/lib/email/gmail_token.json'
    use_push = os.path.exists(push_token)

    if use_push:
        try:
            from gmail_push import pull_new_emails, renew_watch_if_needed
            renew_watch_if_needed()
            print(f"\n=== Seven's Swarm Email Listener (Gmail Push) ===")
            print(f'Watching: {GMAIL_ADDRESS}')
            print('Mode: Gmail Push Notifications — instant delivery.\n')

            # Startup sweep — catch anything missed while listener was down
            print('[Listener] Startup sweep (IMAP) — catching missed emails...')
            log_activity('listener', 'startup', 'Gmail Push mode — startup IMAP sweep')
            process_emails()

            _last_imap_sweep = time.time()
            while True:
                try:
                    emails = pull_new_emails(timeout_seconds=55)
                    if emails:
                        process_emails(emails)
                    else:
                        # Safety net — IMAP sweep every 5 min in case a push was missed
                        if time.time() - _last_imap_sweep > 300:
                            process_emails()
                            _last_imap_sweep = time.time()
                    # RL-020: Check scheduled tasks every loop
                    try:
                        from fridays.scheduler import check_due
                        check_due()
                    except Exception as e:
                        pass
                    # Swarm tasks: snooze + SLA (every 5 min)
                    if time.time() - _last_imap_sweep > 300:
                        try:
                            from swarm_tasks import check_snoozed, check_sla, check_proposals
                            check_snoozed()
                            check_sla(hours=4)
                            check_proposals()
                        except Exception as _te:
                            print(f'[Tasks] Error: {_te}')
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    err_str = str(e)
                    print(f'[Listener] Push error: {e}')
                    if 'invalid_grant' in err_str or 'Token has been expired' in err_str:
                        print('[Listener] OAuth token expired — falling back to IMAP poll.')
                        log_activity('listener', 'push_fallback', 'invalid_grant: switched to IMAP poll')
                        use_push = False
                        break
                    time.sleep(5)
        except ImportError as e:
            print(f'[Listener] Gmail Push unavailable ({e}), falling back to IMAP poll.')
            use_push = False
        except Exception as push_init_err:
            # Covers expired/revoked OAuth tokens and any other startup failure
            err_str = str(push_init_err)
            print(f'[Listener] Gmail Push init failed ({err_str[:120]}), falling back to IMAP poll.')
            if 'invalid_grant' in err_str or 'expired' in err_str.lower() or 'revoked' in err_str.lower():
                log_activity('listener', 'push_fallback', f'OAuth error at startup: {err_str[:200]}')
            use_push = False

    if not use_push:
        print(f"\n=== Seven's Swarm Email Listener (IMAP Poll) ===")
        print(f'Watching: {GMAIL_ADDRESS}')
        print(f'Checking every {interval} seconds.')
        print('Tip: run python3 gmail_auth.py to enable instant Gmail Push.\n')
        _last_task_check = 0.0
        _last_push_recovery_attempt = 0.0
        while True:
            try:
                process_emails()
            except Exception as e:
                print(f'[Listener] Error: {e}')
            # Swarm tasks every 5 min
            if time.time() - _last_task_check > 300:
                try:
                    from swarm_tasks import check_snoozed, check_sla, check_proposals
                    check_snoozed()
                    check_sla(hours=4)
                    check_proposals()
                    _last_task_check = time.time()
                except Exception as _te:
                    print(f'[Tasks] Error: {_te}')

            # Self-healing: periodically retry Gmail Push activation.
            if os.path.exists(push_token) and time.time() - _last_push_recovery_attempt > PUSH_RECOVERY_INTERVAL_SECONDS:
                _last_push_recovery_attempt = time.time()
                ok, err = _try_enable_gmail_push()
                if ok:
                    print('[Listener] Gmail Push recovered — switching back to instant delivery.')
                    log_activity('listener', 'push_recovered', 'push watch renewed during IMAP fallback')
                    return run_forever(interval=interval)
                if err:
                    log_activity('listener', 'push_retry_failed', err[:300])
            time.sleep(interval)


if __name__ == '__main__':
    run_forever(interval=60)
