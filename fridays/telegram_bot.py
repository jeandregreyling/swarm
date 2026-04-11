"""
fridays/telegram_bot.py — Seven's Swarm (RL-022)
═══════════════════════════════════════════════════════════════════════════════
Telegram front door for Fridays. Same trusted sender model as email.
Bot: @Seven_FridaysBot

Flow for trusted users:
    Message received → queue intake → read receipt
    → Stage 1 (LLaMA fast) → Stage 2 (Mistral + Gemma full verdict)
    → Librarian closes ticket → Duck check

Unknown users: Ghost notified, reply TRUST/NOTIFY/IGNORE.

Trusted senders stored as 'telegram:<chat_id>' in trusted_senders table.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import asyncio
import logging
import io

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from telegram.error import NetworkError, TimedOut

from config import TELEGRAM_TOKEN, TELEGRAM_BOT_NAME, GHOST_EMAIL
from database import log_activity
from database import (get_all_email_lists, add_trusted_sender,
                      add_notification_sender, new_conversation,
                      log_message, get_connection)
from queue_manager import intake as queue_intake, get_queue_depth, mark_processing, mark_failed
from ticket import create as ticket_create, librarian_close, set_routing as ticket_set_routing
from orchestrator import consult_stage1, consult_stage2, ask_agent
from duck import on_queue_clear

logger = logging.getLogger('seven.telegram')

_DIRECT_AGENTS = {'gemma', 'llama', 'mistral', 'librarian', 'duck', 'sniffles'}


def _parse_direct_agent_command(text: str):
    """Parse direct-agent message formats:
    - AGENT <name> <message>
    - @<name> <message>
    Returns (agent, message) or None.
    """
    raw = (text or '').strip()
    if not raw:
        return None

    parts = raw.split(None, 2)
    if len(parts) >= 3 and parts[0].upper() == 'AGENT':
        agent = parts[1].strip().lower().lstrip('@').rstrip(':')
        msg = parts[2].strip()
        if agent and msg:
            return agent, msg

    if raw.startswith('@'):
        pieces = raw.split(None, 1)
        if len(pieces) == 2:
            agent = pieces[0][1:].strip().lower().rstrip(':')
            msg = pieces[1].strip()
            if agent and msg:
                return agent, msg

    return None


def _llama_action_trace(question: str, routing: dict):
    return (
        'Action Trace:\n'
        f'- route.agents: {routing.get("agents", "llama")}\n'
        f'- route.needs_web: {routing.get("needs_web", False)}\n'
        f'- route.needs_browser: {routing.get("needs_browser", False)}\n'
        f'- route.needs_shell: {routing.get("needs_shell", False)}\n'
        f'- question.preview: {(question or "").strip()[:140]}'
    )


def _guess_kind(filename: str, mime_type: str) -> str:
    name = (filename or '').lower()
    mime = (mime_type or '').lower()
    if mime.startswith('image/') or name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
        return 'image'
    if mime == 'application/pdf' or name.endswith('.pdf'):
        return 'pdf'
    if name.endswith('.docx') or mime in (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
    ):
        return 'docx'
    if mime.startswith('text/') or name.endswith(('.txt', '.md', '.csv')):
        return 'text'
    return 'unknown'


async def _download_telegram_file(bot, file_id):
    """Download a Telegram file as bytes with API compatibility across PTB versions."""
    tg_file = await bot.get_file(file_id)
    try:
        data = await tg_file.download_as_bytearray()
        return bytes(data)
    except Exception:
        buf = io.BytesIO()
        await tg_file.download_to_memory(out=buf)
        return buf.getvalue()


async def _extract_telegram_attachment_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract textual context from Telegram photo/document attachments."""
    msg = update.message
    if not msg:
        return '', None

    from email_handler import _describe_image_with_gemma, _extract_text_from_pdf, _extract_text_from_docx

    try:
        # Photo: use highest-resolution variant.
        if msg.photo:
            photo = msg.photo[-1]
            data = await _download_telegram_file(context.bot, photo.file_id)
            text = _describe_image_with_gemma(data, 'telegram-photo.jpg')
            return (text or '').strip(), {
                'kind': 'image',
                'name': 'telegram-photo.jpg',
                'mime': 'image/jpeg',
                'size': getattr(photo, 'file_size', None),
            }

        # Generic file/document.
        if msg.document:
            doc = msg.document
            data = await _download_telegram_file(context.bot, doc.file_id)
            filename = doc.file_name or 'telegram-document'
            mime = doc.mime_type or ''
            kind = _guess_kind(filename, mime)

            if kind == 'image':
                text = _describe_image_with_gemma(data, filename)
            elif kind == 'pdf':
                text = _extract_text_from_pdf(data)
            elif kind == 'docx':
                text = _extract_text_from_docx(data)
            elif kind == 'text':
                text = data.decode('utf-8', errors='replace')
            else:
                text = f'(Unsupported Telegram attachment type: {mime or filename})'

            return (text or '').strip(), {
                'kind': kind,
                'name': filename,
                'mime': mime,
                'size': getattr(doc, 'file_size', None),
            }
    except Exception as e:
        logger.exception('[Telegram] Attachment extraction failed')
        return f'(Attachment extraction failed: {e})', None

    return '', None

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


def _build_sender_context(sender: str, question: str, limit: int = 3) -> str:
    """
    Inject recent Q&A pairs for this sender so agents have conversation memory.
    Returns the question prefixed with up to `limit` prior closed exchanges.
    Only applies if closed tickets with final answers exist for this sender.
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT question, final_answer, closed_at
               FROM tickets
               WHERE sender_email=? AND status='closed'
                     AND final_answer IS NOT NULL AND final_answer != ''
               ORDER BY id DESC LIMIT ?""",
            (sender, limit)
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f'[Telegram] Could not load sender history for {sender}: {e}')
        return question

    if not rows:
        return question

    history = list(reversed(rows))
    lines = ['=== Recent conversation context (for agent awareness only) ===']
    for r in history:
        lines.append(f'[{r["closed_at"]}]')
        lines.append(f'User asked: {r["question"][:300]}')
        lines.append(f'Swarm answered: {r["final_answer"][:400]}')
        lines.append('')
    lines.append('=== Current question ===')
    lines.append(question)
    return '\n'.join(lines)


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
            ok = send_reply(
                to_address=mod,
                subject=f'[Swarm] Unknown sender: {key}',
                body=plain,
                html_body=html,
            )
            if ok:
                logger.info(f'[Telegram] Notified {mod} about unknown user {chat_id}')
                log_activity('telegram', 'notify_sent', f'chat_id={chat_id} → {mod}')
            else:
                logger.error(f'[Telegram] Notification send returned False for {mod} (chat_id={chat_id})')
                log_activity('telegram', 'notify_failed', f'chat_id={chat_id} → {mod} | send_reply=False')
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

    # Build augmented question: inject prior Q&A for this sender so agents have memory.
    # Raw question is preserved for all storage (queue, ticket, logs).
    augmented_question = _build_sender_context(sender, question)

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

    try:
        # Stage 1 — augmented question for context-aware routing + agent prompts
        log_activity('telegram', 'pipeline_start', f'{ticket_number} | @{username}')
        web_results, llama_answer, shared_context, routing = consult_stage1(augmented_question)
        ticket_set_routing(ticket_number, routing)
        log_activity('telegram', 'stage1_done', f'{ticket_number} | routing: {routing.get("agents","?")} sap={routing.get("is_sap",False)}')

        if routing.get('is_sap'):
            await update.message.reply_text(
                'Eight has picked up your SAP question. The specialist pipeline is deliberating — give it a few minutes.'
            )
        else:
            log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')
            trace = _llama_action_trace(question, routing)
            # Send stage1 result immediately — before stage2 starts — to keep Telegram happy
            try:
                await update.message.reply_text(f'[LLaMA]\n{trace}\n\n{llama_answer[:3600]}')
                await update.effective_chat.send_action(ChatAction.TYPING)
            except Exception as send_err:
                logger.warning(f'[Telegram] Could not send stage1 result: {send_err}')

        # Stage 2 — augmented question keeps context alive through full pipeline
        try:
            qwen_answer, gemma_answer, debate = consult_stage2(
                augmented_question, web_results, llama_answer, shared_context, conv_id, routing
            )
        except Exception as s2_err:
            # Stage 2 failed (often a timeout). Stage 1 result already sent — close ticket with that.
            mark_failed(queue_id, reason=f'stage2: {s2_err}')
            log_activity('telegram', 'pipeline_failed', f'{ticket_number} | stage2: {s2_err}')
            try:
                await update.message.reply_text(
                    f'⚠️ Stage 2 could not complete ({s2_err}). LLaMA stage 1 result above is the best answer available right now.'
                )
            except Exception:
                pass
            librarian_close(ticket_number, question, llama_answer,
                            queue_id=queue_id, sender_email=sender)
            return

        # Build full response
        parts = []
        if qwen_answer and not routing.get('is_sap'):
            parts.append(f'[Mistral]\n{qwen_answer[:4000]}')
        if debate.get('fired'):
            parts.append('[Debate — challenge round fired]')
        parts.append(f'[Gemma — verdict] {ticket_ref}\n{gemma_answer[:4000]}')

        for part in parts:
            try:
                await update.message.reply_text(part)
            except Exception as send_err:
                logger.warning(f'[Telegram] Could not send reply part: {send_err}')
        log_activity('telegram', 'stage2_done', f'{ticket_number} | reply sent to @{username}')

        # Close ticket
        librarian_close(ticket_number, question, gemma_answer,
                        queue_id=queue_id, sender_email=sender)
        log_activity('telegram', 'ticket_closed', f'{ticket_number} | reply sent to @{username}')

        # Queue clear check
        if get_queue_depth() == 0:
            on_queue_clear()
    except Exception as e:
        mark_failed(queue_id, reason=str(e))
        log_activity('telegram', 'pipeline_failed', f'{ticket_number} | {e}')
        raise


async def _run_direct_agent_pipeline(update: Update, target_agent: str, question: str):
    """Direct-to-agent mode with ticket traceability retained.

    This keeps a lightweight ticket/queue log while bypassing multi-stage triage.
    """
    chat_id = update.effective_chat.id
    username = update.effective_user.username or str(chat_id)
    sender = _telegram_key(chat_id)
    target = (target_agent or '').strip().lower()

    if target not in _DIRECT_AGENTS:
        await update.message.reply_text(
            f'Unknown direct agent `{target}`. Supported: {", ".join(sorted(_DIRECT_AGENTS))}'
        )
        return

    queue_id, position, tags = queue_intake(sender, f'Telegram: {username}', question, priority=5)
    conv_id = new_conversation(question, source='telegram', sender=sender)
    ticket_number = f'TG-{conv_id}'
    ticket_create(ticket_number, sender, question, tags=(tags + ',direct-agent,' + target), queue_id=queue_id)
    mark_processing(queue_id)
    log_message(conv_id, 'Ghost', question, to_agent=target.capitalize(), message_type='chat')

    await update.message.reply_text(
        f'Direct mode: routing to {target} (ticket {ticket_number}, queue #{position}).'
    )
    await update.effective_chat.send_action(ChatAction.TYPING)

    try:
        augmented = _build_sender_context(sender, question)
        prompt = augmented
        if target == 'llama':
            prompt = (
                augmented
                + '\n\nBefore your answer, include a short "Action Trace" section listing what you checked and why.'
            )
        answer = ask_agent(target, prompt)
        if target == 'llama':
            answer = _llama_action_trace(question, {'agents': 'llama'}) + '\n\n' + answer

        log_message(conv_id, target.capitalize(), answer, to_agent='Ghost', message_type='chat')
        librarian_close(ticket_number, question, answer, queue_id=queue_id, sender_email=sender)
        await update.message.reply_text(f'[{target.capitalize()} — direct]\n{answer[:4000]}')
        log_activity('telegram', 'direct_agent_done', f'{ticket_number} | @{username} -> {target}')

        if get_queue_depth() == 0:
            on_queue_clear()
    except Exception as e:
        mark_failed(queue_id, reason=str(e))
        log_activity('telegram', 'direct_agent_failed', f'{ticket_number} | {target} | {e}')
        await update.message.reply_text(f'Direct run failed: {e}')


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
    if not update.message:
        return

    chat_id  = update.effective_chat.id
    username = update.effective_user.username or str(chat_id)
    raw_text = (update.message.text or update.message.caption or '').strip()

    attachment_text, attachment_meta = await _extract_telegram_attachment_text(update, context)
    if attachment_meta:
        log_activity(
            'telegram',
            'attachment_received',
            f'@{username} | {attachment_meta.get("kind")} | {attachment_meta.get("name")} | bytes={attachment_meta.get("size")}'
        )

    if raw_text and attachment_text:
        text = (
            raw_text
            + '\n\n--- Attachment interpretation ---\n'
            + attachment_text[:12000]
            + '\n--- End attachment interpretation ---'
        )
    elif raw_text:
        text = raw_text
    elif attachment_text:
        text = (
            'Please process this attachment and answer based on its content.\n\n'
            + attachment_text[:12000]
        )
    else:
        await update.message.reply_text('I could not read any text or supported attachment from that message.')
        return

    logger.info(f'[Telegram] Message from {chat_id} (@{username}): {text[:80]}')

    classification = _classify(chat_id)

    if classification == 'trusted':
        upper = text.upper()

        # ── Direct-to-agent commands (hybrid model) ─────────
        direct = _parse_direct_agent_command(text)
        if direct:
            target_agent, direct_question = direct
            await _run_direct_agent_pipeline(update, target_agent, direct_question)
            return

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
        # Unknown Telegram user — hold message, notify Ghost for TRUST/NOTIFY/IGNORE decision.
        logger.info(f'[Telegram] Unknown user {chat_id} (@{username}) — holding for Ghost review')
        log_activity('telegram', 'unknown_sender_held', f'chat_id={chat_id} @{username} | held pending review')
        try:
            await _notify_ghost(context.application, chat_id, username, text[:200])
            await update.message.reply_text(
                'Thanks for reaching out. Your message has been flagged for review by the operator. '
                'You will hear back once access is confirmed.'
            )
        except Exception as e:
            logger.error(f'[Telegram] Failed to notify Ghost about unknown user {chat_id}: {e}')


# ── Entry point ───────────────────────────────────────────────────────────────

async def _handle_polling_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global Telegram error hook to absorb transient transport failures."""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f'[Telegram] transient network error: {err}')
        return
    logger.exception(f'[Telegram] unhandled error: {err}')

def run():
    print(f'\n=== {TELEGRAM_BOT_NAME} Telegram Bot ===')
    print(f'Bot: @Seven_FridaysBot')
    print('Polling for messages...\n')

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_error_handler(_handle_polling_error)
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
            handle_message,
        )
    )
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    run()
