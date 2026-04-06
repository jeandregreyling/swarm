"""
fridays/discord_bot.py — Seven's Swarm (RL-023)
═══════════════════════════════════════════════════════════════════════════════
Discord front door for Fridays. Same trusted sender model as email + Telegram.

Flow for trusted users:
    Message received → queue intake → read receipt
    → Stage 1 (LLaMA fast) → Stage 2 (Mistral + Gemma full verdict)
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
from orchestrator import consult_stage1, consult_stage2, ask_agent
from duck import on_queue_clear

try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('_tw_core', '/home/seven/swarm/core/time_machine.py')
    _tm_core = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_tm_core)
    _tw = _tm_core.time_wizard
except Exception:
    _tw = None

logger = logging.getLogger('seven.discord')

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
            ok = send_reply(
                to_address=mod,
                subject=f'[Swarm] Unknown sender: {key}',
                body=plain,
                html_body=html,
            )
            if ok:
                logger.info(f'[Discord] Notified {mod} about unknown user {user_id}')
                log_activity('discord', 'notify_sent', f'user_id={user_id} → {mod}')
            else:
                logger.error(f'[Discord] Notification send returned False for {mod} (user_id={user_id})')
                log_activity('discord', 'notify_failed', f'user_id={user_id} → {mod} | send_reply=False')
        except Exception as e:
            logger.error(f'[Discord] Failed to notify {mod}: {e}')
            log_activity('discord', 'notify_failed', f'user_id={user_id} → {mod} | {e}')


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
    _vortex_event('discord', f'message_received:@{username}', target=sender,
                  details={'queue_id': queue_id, 'position': position, 'tags': tags})

    # Read receipt
    urgent_line = '\n⚡ Marked **URGENT** — jumped to front of queue.' if is_urgent else ''
    await message.reply(f'Got it. You are #{position} in queue.{urgent_line}\nThe swarm is on it — full response coming shortly.')
    async with message.channel.typing():
        pass

    # Ticket
    conv_id = new_conversation(question, source='discord', sender=sender)
    ticket_number = f'DC-{conv_id}'
    ticket_create(ticket_number, sender, question, tags=tags, queue_id=queue_id)
    _vortex_event('discord', f'ticket_created:{ticket_number}', target=sender,
                  details={'queue_id': queue_id, 'tags': tags, 'username': username})
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
            llama_payload = _llama_action_trace(question, routing) + '\n\n' + llama_answer
            llama_chunks = [llama_payload[i:i+1900] for i in range(0, len(llama_payload), 1900)]
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
            await message.channel.send(f'**[Mistral]**\n{qwen_chunks[0]}')
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
        _vortex_event('discord', f'ticket_closed:{ticket_number}', target=sender,
                      details={'username': username, 'queue_id': queue_id})
        _vortex_checkpoint(
            label=f'discord-ticket-{ticket_number}',
            agent='discord',
            description=f'Ticket {ticket_number} closed for @{username}'
        )

        if get_queue_depth() == 0:
            on_queue_clear()
    except Exception as e:
        mark_failed(queue_id, reason=str(e))
        log_activity('discord', 'pipeline_failed', f'{ticket_number} | {e}')
        raise


async def _run_direct_agent_pipeline(message: discord.Message, target_agent: str, question: str):
    """Direct-to-agent mode with ticket traceability retained."""
    user_id = message.author.id
    username = message.author.name
    sender = _discord_key(user_id)
    target = (target_agent or '').strip().lower()

    if target not in _DIRECT_AGENTS:
        await message.reply(f'Unknown direct agent `{target}`. Supported: {", ".join(sorted(_DIRECT_AGENTS))}')
        return

    queue_id, position, tags = queue_intake(sender, f'Discord: @{username}', question, priority=5)
    conv_id = new_conversation(question, source='discord', sender=sender)
    ticket_number = f'DC-{conv_id}'
    ticket_create(ticket_number, sender, question, tags=(tags + ',direct-agent,' + target), queue_id=queue_id)
    mark_processing(queue_id)
    log_message(conv_id, 'Ghost', question, to_agent=target.capitalize(), message_type='chat')

    await message.reply(f'Direct mode: routing to **{target}** (ticket `{ticket_number}`, queue #{position}).')
    async with message.channel.typing():
        pass

    try:
        prompt = question
        if target == 'llama':
            prompt = (
                question
                + '\n\nBefore your answer, include a short "Action Trace" section listing what you checked and why.'
            )
        answer = ask_agent(target, prompt)
        if target == 'llama':
            answer = _llama_action_trace(question, {'agents': 'llama'}) + '\n\n' + answer

        log_message(conv_id, target.capitalize(), answer, to_agent='Ghost', message_type='chat')
        librarian_close(ticket_number, question, answer, queue_id=queue_id, sender_email=sender)
        chunks = [answer[i:i+1900] for i in range(0, len(answer), 1900)]
        await message.channel.send(f'**[{target.capitalize()} — direct]**\n{chunks[0]}')
        for chunk in chunks[1:]:
            await message.channel.send(chunk)
        log_activity('discord', 'direct_agent_done', f'{ticket_number} | @{username} -> {target}')

        if get_queue_depth() == 0:
            on_queue_clear()
    except Exception as e:
        mark_failed(queue_id, reason=str(e))
        log_activity('discord', 'direct_agent_failed', f'{ticket_number} | {target} | {e}')
        await message.reply(f'Direct run failed: {e}')


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


# ── Queue / ticket / Vortex management handlers ──────────────────────────────

async def _handle_queue_command(message: discord.Message, _text: str):
    """QUEUE / QUEUE STATUS / QUEUE LIST — current queue depth and active items."""
    from database import get_connection
    depth = get_queue_depth()
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, from_addr, subject, status, priority, created_at
           FROM queue
           WHERE status IN ('queued', 'processing')
           ORDER BY priority ASC, created_at ASC
           LIMIT 20"""
    ).fetchall()
    conn.close()

    if not rows:
        await message.reply(f'Queue is empty. Total depth: **{depth}**')
        return

    lines = [f'**Queue — {depth} active item(s):**\n']
    for r in rows:
        ago = r['created_at'][:16] if r['created_at'] else '?'
        prio = '⚡' if r['priority'] == 1 else '·'
        lines.append(f'{prio} `#{r["id"]}` [{r["status"]}] {r["subject"][:40]} — {r["from_addr"][:30]} @ {ago}')
    await message.reply('\n'.join(lines)[:1900])


async def _handle_tickets_command(message: discord.Message, mode: str):
    """TICKETS / TICKETS OPEN / TICKETS ALL — list tickets."""
    from database import get_connection
    conn = get_connection()
    if mode == 'open':
        rows = conn.execute(
            """SELECT ticket_number, sender_email, status, created_at, question
               FROM tickets WHERE status = 'open'
               ORDER BY created_at DESC LIMIT 25"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT ticket_number, sender_email, status, created_at, question
               FROM tickets
               ORDER BY created_at DESC LIMIT 25"""
        ).fetchall()
    conn.close()

    if not rows:
        await message.reply('No tickets found.')
        return

    lines = [f'**Tickets ({mode}) — {len(rows)} shown:**\n']
    status_icon = {'open': '🟡', 'closed': '✅', 'failed': '🔴'}
    for r in rows:
        icon = status_icon.get(r['status'], '·')
        q = (r['question'] or '')[:40]
        when = (r['created_at'] or '')[:16]
        lines.append(f'{icon} `{r["ticket_number"]}` [{r["status"]}] {q} — {r["sender_email"][:25]} @ {when}')
    await message.reply('\n'.join(lines)[:1900])


async def _handle_ticket_detail_command(message: discord.Message, ticket_ref: str):
    """TICKET <number> — show full ticket details."""
    from database import get_connection
    conn = get_connection()
    ticket = conn.execute(
        """SELECT t.*, q.status AS queue_status, q.priority
           FROM tickets t
           LEFT JOIN queue q ON q.id = t.queue_id
           WHERE t.ticket_number = ?""",
        (ticket_ref,)
    ).fetchone()
    notes = []
    if ticket:
        notes = conn.execute(
            "SELECT agent, note_type, content, created_at FROM ticket_notes WHERE ticket_id=? ORDER BY created_at ASC",
            (ticket['id'],)
        ).fetchall()
    conn.close()

    if not ticket:
        await message.reply(f'Ticket `{ticket_ref}` not found.')
        return

    lines = [
        f'**Ticket `{ticket["ticket_number"]}`**',
        f'Status:  {ticket["status"]}',
        f'From:    {ticket["sender_email"]}',
        f'Opened:  {(ticket["created_at"] or "")[:16]}',
        f'Tags:    {ticket["tags"] or "(none)"}',
        f'Question: {(ticket["question"] or "")[:200]}',
    ]
    if ticket['final_answer']:
        lines.append(f'Answer:  {ticket["final_answer"][:300]}')
    if ticket['duck_result']:
        lines.append(f'Duck:    {ticket["duck_result"]}')
    if notes:
        lines.append(f'\n**Notes ({len(notes)}):**')
        for n in notes[-5:]:
            lines.append(f'  [{n["agent"]}·{n["note_type"]}] {(n["content"] or "")[:120]}')
    await message.reply('\n'.join(lines)[:1900])


async def _handle_close_command(message: discord.Message, ticket_ref: str, sender: str):
    """CLOSE <ticket> — force-close a ticket via Librarian."""
    from database import get_connection
    conn = get_connection()
    ticket = conn.execute(
        'SELECT question, sender_email, status, queue_id FROM tickets WHERE ticket_number=?',
        (ticket_ref,)
    ).fetchone()
    conn.close()

    if not ticket:
        await message.reply(f'Ticket `{ticket_ref}` not found.')
        return
    if ticket['status'] == 'closed':
        await message.reply(f'`{ticket_ref}` is already closed.')
        return

    from ticket import librarian_close
    librarian_close(ticket_ref, ticket['question'],
                    f'[Force closed by {sender} via Discord CLOSE command]',
                    queue_id=ticket['queue_id'],
                    sender_email=ticket['sender_email'])
    log_activity('discord', 'ticket_force_closed', f'{ticket_ref} by {sender}')
    _vortex_event('discord', f'ticket_force_closed:{ticket_ref}', target=ticket_ref,
                  details={'actor': sender, 'method': 'CLOSE command'})
    _vortex_checkpoint(
        label=f'discord-close-{ticket_ref}',
        agent='discord',
        description=f'{ticket_ref} force-closed by {sender} via Discord command'
    )
    await message.reply(f'✓ `{ticket_ref}` closed.')


async def _handle_vortex_status(message: discord.Message):
    """VORTEX / VORTEX STATUS — recent checkpoints and event count."""
    if not _tw:
        await message.reply('Vortex is not active.')
        return

    try:
        checkpoints = _tw.list_checkpoints(limit=5)
        events_raw  = _tw.get_timeline(limit=10) if hasattr(_tw, 'get_timeline') else []
    except Exception as e:
        await message.reply(f'Vortex error: {e}')
        return

    lines = ['**Vortex status**\n']
    if checkpoints:
        lines.append(f'**Recent checkpoints ({len(checkpoints)} shown):**')
        for cp in checkpoints:
            ts = (cp.get('timestamp') or cp.get('created_at') or '')[:16]
            lines.append(f'  · `{cp.get("checkpoint_name", "?")}` — {cp.get("description", "")}  @ {ts}')
    else:
        lines.append('No checkpoints yet.')

    if events_raw:
        lines.append(f'\n**Recent events ({len(events_raw)} shown):**')
        for ev in events_raw[:5]:
            ts = (ev.get('timestamp') or ev.get('created_at') or '')[:16]
            lines.append(f'  · [{ev.get("agent","?")}] {ev.get("action","")} @ {ts}')

    await message.reply('\n'.join(lines)[:1900])


async def _handle_vortex_history(message: discord.Message):
    """VORTEX HISTORY — last 20 Vortex events."""
    if not _tw:
        await message.reply('Vortex is not active.')
        return
    try:
        if hasattr(_tw, 'get_timeline'):
            events = _tw.get_timeline(limit=20)
        else:
            from time_machine import DB_PATH
            import sqlite3, json
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            events = [dict(r) for r in conn.execute(
                "SELECT * FROM time_events ORDER BY timestamp DESC LIMIT 20"
            ).fetchall()]
            conn.close()
    except Exception as e:
        await message.reply(f'Vortex history error: {e}')
        return

    if not events:
        await message.reply('No Vortex events yet.')
        return

    lines = [f'**Vortex history — {len(events)} events:**\n']
    for ev in events:
        ts = (ev.get('timestamp') or ev.get('created_at') or '')[:16]
        lines.append(f'`{ts}` [{ev.get("agent","?")}] {ev.get("action","")[:60]}')
    await message.reply('\n'.join(lines)[:1900])


async def _handle_vortex_checkpoint(message: discord.Message, label: str):
    """VORTEX CHECKPOINT <label> — create a manual Vortex checkpoint."""
    sender = f'discord:{message.author.id}'
    cp = _vortex_checkpoint(
        label=label,
        agent='discord',
        description=f'Manual checkpoint by @{message.author.name} via Discord'
    )
    log_activity('discord', 'vortex_checkpoint', label)
    if cp:
        name = cp.get('checkpoint_name') if isinstance(cp, dict) else str(cp)
        await message.reply(f'✓ Vortex checkpoint created: `{name}`')
    else:
        await message.reply('Vortex checkpoint could not be created (Vortex not active).')


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
            _vortex_event('discord', f'sender_trusted:{data}', target=data,
                          details={'action': 'button_trust', 'actor': 'ghost'})
            await interaction.response.edit_message(
                content=f'✓ **{data}** added to trusted senders.', embed=None, view=None
            )

        elif action == 'notify':
            from database import add_notification_sender, log_activity
            add_notification_sender(data, added_by='ghost-discord', note='Discord button')
            log_activity('discord', 'sender_notify', data)
            _vortex_event('discord', f'sender_notify:{data}', target=data,
                          details={'action': 'button_notify', 'actor': 'ghost'})
            await interaction.response.edit_message(
                content=f'🔔 **{data}** added to notification senders.', embed=None, view=None
            )

        elif action == 'ignore':
            from database import add_notification_sender, log_activity
            add_notification_sender(data, added_by='ghost-discord', note='Discord button — ignored')
            log_activity('discord', 'sender_ignored', data)
            _vortex_event('discord', f'sender_ignored:{data}', target=data,
                          details={'action': 'button_ignore', 'actor': 'ghost'})
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
            _vortex_event('discord', f'ticket_force_closed:{ticket_number}',
                          target=ticket_number,
                          details={'action': 'button_close', 'actor': 'ghost'})
            _vortex_checkpoint(
                label=f'discord-force-close-{ticket_number}',
                agent='discord',
                description=f'Ghost force-closed {ticket_number} via Discord button'
            )
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
                _vortex_event('discord', f'ticket_resent:{ticket_number}',
                              target=ticket_number,
                              details={'action': 'button_resend', 'actor': 'ghost'})
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

        # ── Direct-to-agent commands (hybrid model) ─────────
        direct = _parse_direct_agent_command(text)
        if direct:
            target_agent, direct_question = direct
            await _run_direct_agent_pipeline(message, target_agent, direct_question)
            return

        # ── Skill commands ────────────────────────────────────
        if upper.startswith('SKILL'):
            await _handle_skill_command(message, text)
            return

        # ── Scheduler commands ────────────────────────────────
        if upper.startswith('SCHEDULE ') or upper in ('SCHEDULE LIST', 'LIST TASKS', 'TASKS'):
            await _handle_schedule_command(message, text)
            return

        # ── Queue management commands ─────────────────────────
        if upper in ('QUEUE', 'QUEUE STATUS', 'QUEUE LIST', 'Q'):
            await _handle_queue_command(message, text)
            return

        if upper in ('TICKETS', 'TICKETS OPEN', 'OPEN TICKETS'):
            await _handle_tickets_command(message, 'open')
            return

        if upper == 'TICKETS ALL':
            await _handle_tickets_command(message, 'all')
            return

        if upper.startswith('TICKET '):
            ticket_ref = text.split(None, 1)[1].strip().upper()
            await _handle_ticket_detail_command(message, ticket_ref)
            return

        if upper.startswith('CLOSE '):
            ticket_ref = text.split(None, 1)[1].strip().upper()
            await _handle_close_command(message, ticket_ref, sender=_discord_key(user_id))
            return

        # ── Vortex commands ───────────────────────────────────
        if upper in ('VORTEX', 'VORTEX STATUS'):
            await _handle_vortex_status(message)
            return

        if upper == 'VORTEX HISTORY':
            await _handle_vortex_history(message)
            return

        if upper.startswith('VORTEX CHECKPOINT'):
            label = text[len('VORTEX CHECKPOINT'):].strip() or 'discord-manual'
            await _handle_vortex_checkpoint(message, label)
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
