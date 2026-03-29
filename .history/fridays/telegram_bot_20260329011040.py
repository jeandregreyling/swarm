"""
fridays/telegram_bot.py — Seven's Swarm (RL-022)
═══════════════════════════════════════════════════════════════════════════════
Telegram front door for Fridays. Same trusted sender model as email.
Bot: @Seven_FridaysBot

Flow for trusted users:
    Message received → queue intake → read receipt
    → Stage 1 (LLaMA fast) → Stage 2 (Qwen + Gemma full verdict)
    → Librarian closes ticket → Duck check

Unknown users: Ghost notified, reply TRUST/NOTIFY/IGNORE.

Trusted senders stored as 'telegram:<chat_id>' in trusted_senders table.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import asyncio
import logging

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

from config import TELEGRAM_TOKEN, TELEGRAM_BOT_NAME, GHOST_EMAIL
from database import log_activity
from database import (get_all_email_lists, add_trusted_sender,
                      add_notification_sender, new_conversation,
                      log_message, get_connection)
from queue_manager import intake as queue_intake, get_queue_depth, mark_processing
from ticket import create as ticket_create, librarian_close, set_routing as ticket_set_routing
from orchestrator import consult_stage1, consult_stage2
from duck import on_queue_clear

logger = logging.getLogger('seven.telegram')

# ── Sender classification ─────────────────────────────────────────────────────

def _telegram_key(chat_id):
    return f'telegram:{chat_id}'


def _classify(chat_id):
    trusted, moderators, notification = get_all_email_lists()
    key = _telegram_key(chat_id)
    if key in trusted:
        return 'trusted'
    if key in notification:
        return 'notification'
    return 'unknown'


def _get_moderators():
    conn = get_connection()
    rows = conn.execute('SELECT email FROM moderators').fetchall()
    conn.close()
    return [r['email'] for r in rows]


# ── Notify Ghost about unknown Telegram user ──────────────────────────────────

async def _notify_ghost(app, chat_id, username, preview):
    """Send Ghost an email about an unknown Telegram user."""
    from email_handler import send_reply
    from urllib.parse import quote

    key     = _telegram_key(chat_id)
    display = f'@{username}' if username else str(chat_id)

    _subj_enc   = quote(f'[Swarm] Unknown sender: {key}', safe='')
    trust_link  = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=TRUST'
    notify_link = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=NOTIFY'
    ignore_link = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=IGNORE'

    plain = (
        f'Fridays received a Telegram message from an unknown user.\n\n'
        f'User:    {display}\n'
        f'Chat ID: {chat_id}\n'
        f'Preview: {preview[:200]}\n\n'
        f'Action links (copy into browser if links are broken):\n\n'
        f'TRUST   {trust_link}\n\n'
        f'NOTIFY  {notify_link}\n\n'
        f'IGNORE  {ignore_link}\n'
    )
    html = f"""<!DOCTYPE html>
<html><body style="background:#0f0f0f;color:#e0e0e0;font-family:monospace;padding:20px;max-width:600px">
<p style="color:#888;font-size:13px">Fridays received a Telegram message from an unknown user.</p>
<table style="margin:14px 0;font-size:13px;border-collapse:collapse">
  <tr><td style="color:#555;padding:3px 12px 3px 0">User</td><td style="color:#e0e0e0">{display}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0">Chat ID</td><td style="color:#e0e0e0">{chat_id}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0;vertical-align:top">Preview</td><td style="color:#aaa">{preview[:200]}</td></tr>
</table>
<p style="color:#555;font-size:11px;margin-bottom:12px">Click an action — opens a pre-filled reply in Thunderbird. Just hit Send.</p>
<table style="border-collapse:collapse">
  <tr>
    <td style="padding:4px 8px 4px 0"><a href="{trust_link}"  style="background:#1a3a1a;color:#66cc66;border:1px solid #2d6b2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">TRUST</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{notify_link}" style="background:#1a1a3a;color:#6666cc;border:1px solid #2d2d6b;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">NOTIFY</a></td>
    <td style="padding:4px 8px 4px 0"><a href="{ignore_link}" style="background:#2a1a0d;color:#cc8844;border:1px solid #6b4a2d;border-radius:4px;padding:8px 18px;text-decoration:none;font-size:13px;font-family:monospace">IGNORE</a></td>
  </tr>
</table>
<p style="color:#333;font-size:10px;margin-top:20px">Seven's Swarm — seven-potato</p>
</body></html>"""

    mods = _get_moderators()
    if not mods:
        logger.warning(f'[Telegram] No moderators found — cannot notify about {chat_id}')
        log_activity('telegram', 'notify_failed', f'chat_id={chat_id} — no moderators in table')
        return
    for mod in mods:
        try:
            send_reply(to_address=mod,
                       subject=f'[Swarm] Unknown sender: {key}',
                       body=plain,
                       html_body=html)
            logger.info(f'[Telegram] Notified {mod} about unknown user {chat_id}')
            log_activity('telegram', 'notify_sent', f'chat_id={chat_id} → {mod}')
        except Exception as e:
            logger.error(f'[Telegram] Failed to notify {mod} about {chat_id}: {e}')
            log_activity('telegram', 'notify_failed', f'chat_id={chat_id} → {mod} | {e}')


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(update: Update, question: str, is_urgent: bool = False):
    """Full swarm pipeline for a trusted Telegram message."""
    chat_id  = update.effective_chat.id
    username = update.effective_user.username or str(chat_id)
    sender   = _telegram_key(chat_id)
    priority = 1 if is_urgent else 5

    # Queue intake
    queue_id, position, tags = queue_intake(sender, f'Telegram: {username}', question,
                                             priority=priority)
    log_activity('telegram', 'message_received', f'@{username} | {question[:80]}')

    # Read receipt
    urgent_line = '\n⚡ Marked URGENT — jumped to front of queue.' if is_urgent else ''
    await update.message.reply_text(
        f'Got it. You are #{position} in queue.{urgent_line}\nThe swarm is on it — full response coming shortly.'
    )
    await update.effective_chat.send_action(ChatAction.TYPING)

    # Ticket
    conv_id       = new_conversation(question, source='telegram', sender=sender)
    ticket_number = f'TG-{conv_id}'
    ticket_ref    = f'[Swarm #{conv_id}]'
    ticket_create(ticket_number, sender, question, tags=tags, queue_id=queue_id)
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')
    mark_processing(queue_id)

    # Stage 1
    log_activity('telegram', 'pipeline_start', f'{ticket_number} | @{username}')
    web_results, llama_answer, shared_context, routing = consult_stage1(question)
    ticket_set_routing(ticket_number, routing)
    log_activity('telegram', 'stage1_done', f'{ticket_number} | routing: {routing.get("agents","?")} sap={routing.get("is_sap",False)}')

    if routing.get('is_sap'):
        await update.message.reply_text(
            'Eight has picked up your SAP question. The specialist pipeline is deliberating — give it a few minutes.'
        )
    else:
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
        await update.message.reply_text(f'[LLaMA]\n{llama_answer[:4000]}')
        await update.effective_chat.send_action(ChatAction.TYPING)

    # Stage 2
    qwen_answer, gemma_answer, debate = consult_stage2(
        question, web_results, llama_answer, shared_context, conv_id, routing
    )

    # Build full response
    parts = []
    if qwen_answer and not routing.get('is_sap'):
        parts.append(f'[Qwen]\n{qwen_answer[:4000]}')
    if debate.get('fired'):
        parts.append('[Debate — challenge round fired]')
    parts.append(f'[Gemma — verdict] {ticket_ref}\n{gemma_answer[:4000]}')

    for part in parts:
        await update.message.reply_text(part)
    log_activity('telegram', 'stage2_done', f'{ticket_number} | reply sent to @{username}')

    # Close ticket
    librarian_close(ticket_number, question, gemma_answer,
                    queue_id=queue_id, sender_email=sender)
    log_activity('telegram', 'ticket_closed', f'{ticket_number} | reply sent to @{username}')

    # Queue clear check
    if get_queue_depth() == 0:
        on_queue_clear()


# ── Moderator commands ────────────────────────────────────────────────────────

async def _handle_mod_command(update: Update, text: str):
    """Handle NOTE / TAG / SNOOZE / TRUST DOMAIN from a trusted Telegram user."""
    upper  = text.strip().upper()
    sender = _telegram_key(update.effective_chat.id)

    # Find most recent ticket for this sender
    conn = get_connection()
    latest = conn.execute(
        "SELECT ticket_number FROM tickets WHERE sender_email=? ORDER BY id DESC LIMIT 1",
        (sender,)
    ).fetchone()
    conn.close()
    if not latest:
        await update.message.reply_text('No ticket found to attach this to.')
        return
    ticket_number = latest['ticket_number']

    if upper.startswith('NOTE:'):
        note_text = text[5:].strip()
        from database import add_ticket_note_by_number
        add_ticket_note_by_number(ticket_number, 'ghost-telegram', note_text, note_type='manual')
        log_activity('telegram', 'note_added', f'{ticket_number} | {note_text[:80]}')
        await update.message.reply_text(f'📝 Note added to {ticket_number}.')

    elif upper.startswith('TAG:'):
        tags_raw = text[4:].strip()
        new_tags = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]
        from database import update_ticket_tags
        update_ticket_tags(ticket_number, new_tags)
        log_activity('telegram', 'tag_added', f'{ticket_number} | {", ".join(new_tags)}')
        await update.message.reply_text(f'🏷 Tags added: {", ".join(new_tags)}')

    elif upper.startswith('SNOOZE:'):
        raw = text[7:].strip()
        from listener import _parse_snooze_time
        from database import snooze_ticket
        wake_at = _parse_snooze_time(raw)
        if not wake_at:
            await update.message.reply_text(
                f'⚠️ Could not parse: "{raw}"\nFormats: 30m, 2h, 2d, 2026-04-01, 2026-04-01 09:00'
            )
            return
        snooze_ticket(ticket_number, sender, wake_at, note=f'Telegram snooze: {raw}')
        log_activity('telegram', 'snooze_set', f'{ticket_number} | wake={wake_at}')
        await update.message.reply_text(f'💤 {ticket_number} snoozed until {wake_at}.')

    elif upper.startswith('TRUST DOMAIN '):
        domain = text.split(None, 2)[2].strip().lower()
        from database import add_trusted_domain
        add_trusted_domain(domain, added_by=sender, note='Added via Telegram', channel='telegram')
        log_activity('telegram', 'domain_trusted', domain)
        await update.message.reply_text(f'✓ Domain {domain} trusted.')


# ── Skills (RL-021) ───────────────────────────────────────────────────────────

async def _handle_skill_command(update: Update, text: str):
    """Handle SKILL commands from Telegram."""
    from fridays.skills import parse_skill_command, call as skill_call, list_skills

    sender = _telegram_key(update.effective_chat.id)
    parsed = parse_skill_command(text)

    if not parsed:
        skills = list_skills()
        lines = ['Available skills:\n']
        for s in skills:
            lines.append(f'{s["name"]} — {s["description"]}')
            lines.append(f'  {s["usage"]}\n')
        await update.message.reply_text('\n'.join(lines))
        return

    skill_name, args = parsed
    await update.effective_chat.send_action('typing')
    ok, output = skill_call(skill_name, args=args, agent=sender)
    prefix = '✓' if ok else '✗'
    reply = f'{prefix} [{skill_name}]\n\n{output}'
    # Telegram 4096 char limit
    await update.message.reply_text(reply[:4096])


# ── Scheduler commands (RL-020) ───────────────────────────────────────────────

async def _handle_schedule_command(update: Update, text: str):
    """Handle SCHEDULE / LIST TASKS / SCHEDULE CANCEL commands from Telegram."""
    from fridays.scheduler import parse_schedule_command, add_task, list_tasks, disable_task

    upper = text.strip().upper()

    if upper in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
        tasks = list_tasks()
        if tasks:
            rows = '\n'.join(
                f'#{t["id"]} {t["schedule"]} | {t["action_type"]} | {t["action_data"][:30]} | next: {t["next_run"]}'
                for t in tasks
            )
            await update.message.reply_text(f'Scheduled tasks ({len(tasks)}):\n\n{rows}')
        else:
            await update.message.reply_text('No scheduled tasks.')
        return

    if upper.startswith('SCHEDULE CANCEL '):
        try:
            task_id = int(text.strip().split()[-1])
            disable_task(task_id)
            await update.message.reply_text(f'Task #{task_id} disabled.')
        except Exception as e:
            await update.message.reply_text(f'Error: {e}')
        return

    parsed = parse_schedule_command(text)
    if parsed:
        name, schedule, action_type, action_data = parsed
        sender = _telegram_key(update.effective_chat.id)
        task_id = add_task(name, schedule, action_type, action_data, created_by=sender)
        await update.message.reply_text(
            f'Task #{task_id} scheduled.\n'
            f'Schedule: {schedule}\n'
            f'Action:   {action_type}\n'
            f'Data:     {action_data[:80]}\n\n'
            f'Send "SCHEDULE LIST" to see all tasks.\n'
            f'Send "SCHEDULE CANCEL {task_id}" to disable it.'
        )
    else:
        await update.message.reply_text(
            'Could not parse schedule command.\n\n'
            'Format: SCHEDULE <schedule> <action> <data>\n\n'
            'Examples:\n'
            '  SCHEDULE daily 09:00 QUESTION What is today\'s news?\n'
            '  SCHEDULE weekly mon 08:00 SHELL df -h\n'
            '  SCHEDULE once 2026-04-01 09:00 REMIND Check lease renewal\n'
            '  SCHEDULE interval 30 SHELL free -h'
        )


# ── Message handler ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id  = update.effective_chat.id
    username = update.effective_user.username or str(chat_id)
    text     = update.message.text.strip()

    logger.info(f'[Telegram] Message from {chat_id} (@{username}): {text[:80]}')

    classification = _classify(chat_id)

    if classification == 'trusted':
        upper = text.upper()

        # ── Skill commands ────────────────────────────────────
        if upper.startswith('SKILL'):
            await _handle_skill_command(update, text)
            return

        # ── Scheduler commands ────────────────────────────────
        if upper.startswith('SCHEDULE ') or upper in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
            await _handle_schedule_command(update, text)
            return

        # ── Moderator commands ────────────────────────────────
        if any(upper.startswith(cmd) for cmd in ('NOTE:', 'TAG:', 'SNOOZE:', 'TRUST DOMAIN ')):
            await _handle_mod_command(update, text)
            return

        # ── URGENT flag ───────────────────────────────────────
        is_urgent = upper.startswith('URGENT:') or upper.startswith('URGENT ')
        question  = text[7:].strip() if is_urgent else text

        try:
            await _run_pipeline(update, question, is_urgent=is_urgent)
        except Exception as e:
            logger.error(f'[Telegram] Pipeline error: {e}')
            await update.message.reply_text(f'Something went wrong in the swarm: {e}')

    elif classification == 'notification':
        logger.info(f'[Telegram] Notification user {chat_id} — silent filing.')

    else:
        # Unknown Telegram user — run pipeline directly.
        # Telegram requires knowing the bot URL to message it, so anyone who
        # reaches the bot is presumed to have a reason.
        log_activity('telegram', 'unknown_sender', f'chat_id={chat_id} @{username} | auto-answering')
        try:
            await _run_pipeline(update, text)
        except Exception as e:
            logger.error(f'[Telegram] Pipeline error for unknown user: {e}')
            await update.message.reply_text(f'Something went wrong: {e}')


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    print(f'\n=== {TELEGRAM_BOT_NAME} Telegram Bot ===')
    print(f'Bot: @Seven_FridaysBot')
    print('Polling for messages...\n')

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    run()
