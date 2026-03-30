"""
fridays/discord_bot.py — Seven's Swarm (RL-023)
═══════════════════════════════════════════════════════════════════════════════
Discord front door for Fridays. Same trusted sender model as email + Telegram.

Flow for trusted users:
    Message received → queue intake → read receipt
    → Stage 1 (LLaMA fast) → Stage 2 (Qwen + Gemma full verdict)
    → Librarian closes ticket → Duck check

Unknown users: Ghost notified, reply TRUST/NOTIFY/IGNORE.

Trusted senders stored as 'discord:<user_id>' in trusted_senders table.
Commands (trusted only): URGENT, NOTE, TAG, SNOOZE, SKILL, SCHEDULE,
                         QUEUE, QUEUE LIST, TICKET <n>, TICKETS, CLOSE <n>,
                         VORTEX, VORTEX CHECKPOINT <label>, VORTEX HISTORY
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import asyncio
import logging

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')
sys.path.insert(0, '/home/seven/swarm/agents/ghost')

import discord
from discord.ext import commands

from config import GHOST_EMAIL
try:
    from config import DISCORD_TOKEN, DISCORD_BOT_NAME
except ImportError:
    DISCORD_TOKEN    = ''
    DISCORD_BOT_NAME = 'Fridays'

from database import log_activity
from database import (get_all_email_lists, add_trusted_sender,
                      add_notification_sender, new_conversation,
                      log_message, get_connection)
from queue_manager import intake as queue_intake, get_queue_depth, mark_processing, mark_failed
from ticket import create as ticket_create, librarian_close, set_routing as ticket_set_routing
from orchestrator import consult_stage1, consult_stage2
from duck import on_queue_clear

try:
    from time_machine import time_wizard as _tw
except Exception:
    _tw = None

logger = logging.getLogger('seven.discord')


# ── Vortex helpers ────────────────────────────────────────────────────────────

def _vortex_event(agent: str, action: str, event_type: str = 'discord',
                  target: str = '', details: dict = None):
    """Record a Vortex event. Silent — never raises."""
    if not _tw:
        return
    try:
        _tw.record_event(agent=agent, action=action, event_type=event_type,
                         target=target, details=details or {})
    except Exception as e:
        logger.debug(f'[Discord] Vortex event failed: {e}')


def _vortex_checkpoint(label: str, agent: str = 'discord', description: str = ''):
    """Create a Vortex checkpoint. Silent — never raises."""
    if not _tw:
        return None
    try:
        return _tw.create_workflow_checkpoint(label=label, agent=agent, description=description)
    except Exception as e:
        logger.debug(f'[Discord] Vortex checkpoint failed: {e}')
        return None

# ── Sender classification ─────────────────────────────────────────────────────

def _discord_key(user_id):
    return f'discord:{user_id}'


def _classify(user_id):
    trusted, moderators, notification = get_all_email_lists()
    key = _discord_key(user_id)
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


# ── Notify Ghost about unknown Discord user ───────────────────────────────────

async def _notify_ghost(user_id, username, preview):
    """Send Ghost an email about an unknown Discord user."""
    from email_handler import send_reply
    from urllib.parse import quote

    key     = _discord_key(user_id)
    display = f'@{username}' if username else str(user_id)

    _subj_enc   = quote(f'[Swarm] Unknown sender: {key}', safe='')
    trust_link  = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=TRUST'
    notify_link = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=NOTIFY'
    ignore_link = f'mailto:{GHOST_EMAIL}?subject={_subj_enc}&body=IGNORE'

    plain = (
        f'Fridays received a Discord message from an unknown user.\n\n'
        f'User:    {display}\n'
        f'User ID: {user_id}\n'
        f'Preview: {preview[:200]}\n\n'
        f'Action links:\n\n'
        f'TRUST   {trust_link}\n\n'
        f'NOTIFY  {notify_link}\n\n'
        f'IGNORE  {ignore_link}\n'
    )
    html = f"""<!DOCTYPE html>
<html><body style="background:#0f0f0f;color:#e0e0e0;font-family:monospace;padding:20px;max-width:600px">
<p style="color:#888;font-size:13px">Fridays received a Discord message from an unknown user.</p>
<table style="margin:14px 0;font-size:13px;border-collapse:collapse">
  <tr><td style="color:#555;padding:3px 12px 3px 0">User</td><td style="color:#e0e0e0">{display}</td></tr>
  <tr><td style="color:#555;padding:3px 12px 3px 0">User ID</td><td style="color:#e0e0e0">{user_id}</td></tr>
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
        logger.warning(f'[Discord] No moderators — cannot notify about {user_id}')
        log_activity('discord', 'notify_failed', f'user_id={user_id} — no moderators')
        return
    for mod in mods:
        try:
            send_reply(to_address=mod,
                       subject=f'[Swarm] Unknown sender: {key}',
                       body=plain,
                       html_body=html)
            logger.info(f'[Discord] Notified {mod} about unknown user {user_id}')
            log_activity('discord', 'notify_sent', f'user_id={user_id} → {mod}')
        except Exception as e:
            logger.error(f'[Discord] Failed to notify {mod}: {e}')


# ── Moderator commands ────────────────────────────────────────────────────────

def _handle_mod_command(text, ticket_number, sender):
    """
    Handle NOTE / TAG / SNOOZE / TRUST DOMAIN commands.
    Returns reply string or None if not a mod command.
    """
    upper = text.strip().upper()

    if upper.startswith('NOTE:'):
        note_text = text[5:].strip()
        from database import add_ticket_note_by_number
        add_ticket_note_by_number(ticket_number, 'ghost', note_text, note_type='manual')
        log_activity('discord', 'note_added', f'{ticket_number} | {note_text[:80]}')
        return f'📝 Note added to {ticket_number}.'

    if upper.startswith('TAG:'):
        tags_raw = text[4:].strip()
        new_tags = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]
        from database import update_ticket_tags
        update_ticket_tags(ticket_number, new_tags)
        log_activity('discord', 'tag_added', f'{ticket_number} | {", ".join(new_tags)}')
        return f'🏷 Tags added to {ticket_number}: {", ".join(new_tags)}'

    if upper.startswith('SNOOZE:'):
        raw = text[7:].strip()
        from listener import _parse_snooze_time
        wake_at = _parse_snooze_time(raw)
        if not wake_at:
            return f'⚠️ Could not parse snooze time: "{raw}"\nFormats: 30m, 2h, 2d, 2026-04-01, 2026-04-01 09:00'
        from database import snooze_ticket
        snooze_ticket(ticket_number, sender, wake_at, note=f'Discord snooze: {raw}')
        log_activity('discord', 'snooze_set', f'{ticket_number} | wake={wake_at}')
        return f'💤 {ticket_number} snoozed until {wake_at}.'

    if upper.startswith('TRUST DOMAIN '):
        domain = text.split(None, 2)[2].strip().lower()
        from database import add_trusted_domain
        add_trusted_domain(domain, added_by=sender, note='Added via Discord', channel='discord')
        log_activity('discord', 'domain_trusted', domain)
        return f'✓ Domain {domain} added to trusted domains.'

    return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(message: discord.Message, question: str, is_urgent=False):
    """Full swarm pipeline for a trusted Discord message."""
    user_id  = message.author.id
    username = message.author.name
    sender   = _discord_key(user_id)
    priority = 1 if is_urgent else 5

    # Queue intake
    queue_id, position, tags = queue_intake(sender, f'Discord: @{username}', question,
                                             priority=priority)
    log_activity('discord', 'message_received', f'@{username} | {question[:80]}')

    # Read receipt
    urgent_line = '\n⚡ Marked **URGENT** — jumped to front of queue.' if is_urgent else ''
    await message.reply(f'Got it. You are #{position} in queue.{urgent_line}\nThe swarm is on it — full response coming shortly.')
    async with message.channel.typing():
        pass

    # Ticket
    conv_id = new_conversation(question, source='discord', sender=sender)
    ticket_number = f'DC-{conv_id}'
    ticket_create(ticket_number, sender, question, tags=tags, queue_id=queue_id)
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')
    mark_processing(queue_id)

    try:
        # Stage 1
        log_activity('discord', 'pipeline_start', f'{ticket_number} | @{username}')
        web_results, llama_answer, shared_context, routing = consult_stage1(question)
        ticket_set_routing(ticket_number, routing)

        if routing.get('is_sap'):
            await message.reply('Eight has picked up your SAP question. The specialist pipeline is deliberating — give it a few minutes.')
        else:
            # Send LLaMA response in chunks (Discord 2000 char limit)
            llama_chunks = [llama_answer[i:i+1900] for i in range(0, len(llama_answer), 1900)]
            await message.reply(f'**[LLaMA]**\n{llama_chunks[0]}')
            for chunk in llama_chunks[1:]:
                await message.channel.send(chunk)

        # Stage 2
        qwen_answer, gemma_answer, debate = consult_stage2(
            question, web_results, llama_answer, shared_context, conv_id, routing
        )

        # Send full response
        if qwen_answer and not routing.get('is_sap'):
            qwen_chunks = [qwen_answer[i:i+1900] for i in range(0, len(qwen_answer), 1900)]
            await message.channel.send(f'**[Qwen]**\n{qwen_chunks[0]}')
            for chunk in qwen_chunks[1:]:
                await message.channel.send(chunk)

        if debate.get('fired'):
            await message.channel.send('*[Debate — challenge round fired]*')

        gemma_chunks = [gemma_answer[i:i+1900] for i in range(0, len(gemma_answer), 1900)]
        await message.channel.send(f'**[Gemma — verdict]** `[Swarm #{conv_id}]`\n{gemma_chunks[0]}')
        for chunk in gemma_chunks[1:]:
            await message.channel.send(chunk)

        log_activity('discord', 'stage2_done', f'{ticket_number} | reply sent to @{username}')

        # Close ticket
        librarian_close(ticket_number, question, gemma_answer,
                        queue_id=queue_id, sender_email=sender)
        log_activity('discord', 'ticket_closed', f'{ticket_number}')

        if get_queue_depth() == 0:
            on_queue_clear()
    except Exception as e:
        mark_failed(queue_id, reason=str(e))
        log_activity('discord', 'pipeline_failed', f'{ticket_number} | {e}')
        raise


# ── Skill command handler ─────────────────────────────────────────────────────

async def _handle_skill_command(message: discord.Message, text: str):
    from fridays.skills import parse_skill_command, call as skill_call, list_skills

    sender = _discord_key(message.author.id)
    parsed = parse_skill_command(text)

    if not parsed:
        skills = list_skills()
        lines = ['**Available skills:**\n']
        for s in skills:
            lines.append(f'`{s["name"]}` — {s["description"]}')
            lines.append(f'  {s["usage"]}\n')
        await message.reply('\n'.join(lines)[:1900])
        return

    skill_name, args = parsed
    async with message.channel.typing():
        pass
    ok, output = skill_call(skill_name, args=args, agent=sender)
    prefix = '✓' if ok else '✗'
    reply = f'{prefix} **[{skill_name}]**\n\n{output}'
    await message.reply(reply[:1900])


# ── Schedule command handler ──────────────────────────────────────────────────

async def _handle_schedule_command(message: discord.Message, text: str):
    from fridays.scheduler import parse_schedule_command, add_task, list_tasks, disable_task

    upper = text.strip().upper()

    if upper in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
        tasks = list_tasks()
        if tasks:
            rows = '\n'.join(
                f'`#{t["id"]}` {t["schedule"]} | {t["action_type"]} | {t["action_data"][:30]} | next: {t["next_run"]}'
                for t in tasks
            )
            await message.reply(f'**Scheduled tasks ({len(tasks)}):**\n\n{rows}')
        else:
            await message.reply('No scheduled tasks.')
        return

    if upper.startswith('SCHEDULE CANCEL '):
        try:
            task_id = int(text.strip().split()[-1])
            disable_task(task_id)
            await message.reply(f'Task #{task_id} disabled.')
        except Exception as e:
            await message.reply(f'Error: {e}')
        return

    parsed = parse_schedule_command(text)
    if parsed:
        name, schedule, action_type, action_data = parsed
        sender = _discord_key(message.author.id)
        task_id = add_task(name, schedule, action_type, action_data, created_by=sender)
        await message.reply(
            f'Task #{task_id} scheduled.\n'
            f'Schedule: `{schedule}`\n'
            f'Action:   `{action_type}`\n'
            f'Data:     `{action_data[:80]}`\n\n'
            f'Send `SCHEDULE LIST` to see all tasks.\n'
            f'Send `SCHEDULE CANCEL {task_id}` to disable it.'
        )
    else:
        await message.reply(
            'Could not parse schedule command.\n\n'
            '**Format:** `SCHEDULE <schedule> <action> <data>`\n\n'
            '**Examples:**\n'
            '```\n'
            'SCHEDULE daily 09:00 QUESTION What is today\'s news?\n'
            'SCHEDULE weekly mon 08:00 SHELL df -h\n'
            'SCHEDULE once 2026-04-01 09:00 REMIND Check lease renewal\n'
            'SCHEDULE interval 30 SHELL free -h\n'
            '```'
        )


# ── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    logger.info(f'[Discord] Logged in as {bot.user} (ID: {bot.user.id})')
    print(f'\n=== {DISCORD_BOT_NAME} Discord Bot ===')
    print(f'Bot: {bot.user}')
    print('Listening for messages...\n')


# ── Button interaction handler ────────────────────────────────────────────────
# Handles all swarm:action:data custom_ids from discord_notify.py embeds.

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get('custom_id', '')
    if not custom_id.startswith('swarm:'):
        return

    parts  = custom_id.split(':', 2)   # ['swarm', 'action', 'data']
    action = parts[1] if len(parts) > 1 else ''
    data   = parts[2] if len(parts) > 2 else ''

    try:
        if action == 'trust':
            from database import add_trusted_sender, log_activity
            add_trusted_sender(data, added_by='ghost-discord', note='Discord button')
            log_activity('discord', 'sender_trusted', data)
            await interaction.response.edit_message(
                content=f'✓ **{data}** added to trusted senders.', embed=None, view=None
            )

        elif action == 'notify':
            from database import add_notification_sender, log_activity
            add_notification_sender(data, added_by='ghost-discord', note='Discord button')
            log_activity('discord', 'sender_notify', data)
            await interaction.response.edit_message(
                content=f'🔔 **{data}** added to notification senders.', embed=None, view=None
            )

        elif action == 'ignore':
            from database import log_activity
            log_activity('discord', 'sender_ignored', data)
            await interaction.response.edit_message(
                content=f'🚫 **{data}** marked as ignored.', embed=None, view=None
            )

        elif action == 'close':
            ticket_number = data
            from database import get_connection, log_activity
            conn = get_connection()
            ticket = conn.execute(
                'SELECT question, sender_email FROM tickets WHERE ticket_number=?',
                (ticket_number,)
            ).fetchone()
            conn.close()
            if ticket:
                from ticket import librarian_close
                librarian_close(ticket_number, ticket['question'],
                                '[Force closed by Ghost via Discord]',
                                sender_email=ticket['sender_email'])
            log_activity('discord', 'ticket_force_closed', ticket_number)
            await interaction.response.edit_message(
                content=f'⊠ **{ticket_number}** force closed.', embed=None, view=None
            )

        elif action == 'resend':
            ticket_number = data
            from database import get_connection, log_activity
            conn = get_connection()
            ticket = conn.execute(
                'SELECT final_answer, sender_email FROM tickets WHERE ticket_number=?',
                (ticket_number,)
            ).fetchone()
            conn.close()
            if ticket and ticket['final_answer']:
                from email_handler import send_reply
                send_reply(
                    to_address=ticket['sender_email'],
                    subject=f'Re: [{ticket_number}] — follow-up',
                    body=ticket['final_answer']
                )
                log_activity('discord', 'ticket_resent', ticket_number)
                await interaction.response.edit_message(
                    content=f'↩ **{ticket_number}** response resent.', embed=None, view=None
                )
            else:
                await interaction.response.send_message('No answer to resend.', ephemeral=True)

        else:
            await interaction.response.send_message(f'Unknown action: {action}', ephemeral=True)

    except Exception as e:
        logger.error(f'[Discord] Interaction error ({custom_id}): {e}')
        try:
            await interaction.response.send_message(f'Error: {e}', ephemeral=True)
        except Exception:
            pass


@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Only handle DMs (privacy — don't process public channel messages unless configured)
    if message.channel.type != discord.ChannelType.private:
        return

    user_id  = message.author.id
    username = message.author.name
    text     = message.content.strip()

    if not text:
        return

    logger.info(f'[Discord] DM from {user_id} (@{username}): {text[:80]}')

    classification = _classify(user_id)

    if classification == 'trusted':
        upper = text.upper()

        # ── Skill commands ────────────────────────────────────
        if upper.startswith('SKILL'):
            await _handle_skill_command(message, text)
            return

        # ── Scheduler commands ────────────────────────────────
        if upper.startswith('SCHEDULE ') or upper in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
            await _handle_schedule_command(message, text)
            return

        # ── URGENT flag ───────────────────────────────────────
        is_urgent = upper.startswith('URGENT:') or upper.startswith('URGENT ')
        question  = text[7:].strip() if is_urgent else text

        # ── Moderator commands (NOTE/TAG/SNOOZE/TRUST DOMAIN) ─
        # These require a ticket context — if the user types NOTE: <text>,
        # we look up their most recent open ticket
        if any(upper.startswith(cmd) for cmd in ('NOTE:', 'TAG:', 'SNOOZE:', 'TRUST DOMAIN ')):
            sender = _discord_key(user_id)
            conn = get_connection()
            latest = conn.execute(
                "SELECT ticket_number FROM tickets WHERE sender_email=? ORDER BY id DESC LIMIT 1",
                (sender,)
            ).fetchone()
            conn.close()
            if latest:
                reply = _handle_mod_command(text, latest['ticket_number'], sender)
                if reply:
                    await message.reply(reply)
                    return
            else:
                await message.reply('No ticket found to attach this command to.')
                return

        try:
            await _run_pipeline(message, question, is_urgent=is_urgent)
        except Exception as e:
            logger.error(f'[Discord] Pipeline error: {e}')
            await message.reply(f'Something went wrong in the swarm: {e}')

    elif classification == 'notification':
        logger.info(f'[Discord] Notification user {user_id} — silent.')

    else:
        # Unknown Discord user — notify Ghost, auto-answer
        log_activity('discord', 'unknown_sender', f'user_id={user_id} @{username}')
        await _notify_ghost(user_id, username, text)
        try:
            await _run_pipeline(message, text)
        except Exception as e:
            logger.error(f'[Discord] Pipeline error for unknown user: {e}')
            await message.reply(f'Something went wrong: {e}')


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    if not DISCORD_TOKEN:
        print('[Discord] ERROR: DISCORD_TOKEN not set in config.py')
        print('  1. Go to https://discord.com/developers/applications')
        print('  2. Create application → Bot → copy token')
        print('  3. Add to config.py: DISCORD_TOKEN = "your-token"')
        print('  4. Enable "Message Content Intent" under Bot settings')
        print('  5. Invite bot with DM permissions')
        return

    print(f'\n=== {DISCORD_BOT_NAME} Discord Bot ===')
    print('Starting...\n')
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s')
    run()
