"""
discord_notify.py — Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Pushes swarm events to a configured Discord channel as rich embeds.
Used by swarm_tasks.py, listener.py, and anywhere Ghost needs a ping.

All functions are fire-and-forget safe — they catch and log all exceptions
so a Discord failure never breaks the main pipeline.

Requires DISCORD_TOKEN and DISCORD_CHANNEL_ID in config.py.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import asyncio
import logging
import threading

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.discord_notify')

# ── Colour palette (matches dashboard theme) ──────────────────────────────────
COLOUR_INFO    = 0x3B82F6   # blue   — general / ticket opened
COLOUR_OK      = 0x22C55E   # green  — ticket closed / digest
COLOUR_WARN    = 0xF59E0B   # amber  — SLA warning / snooze
COLOUR_URGENT  = 0xEF4444   # red    — URGENT / unknown sender
COLOUR_GHOST   = 0x10B981   # teal   — Ghost Circle / Claude


def _get_config():
    try:
        from config import DISCORD_TOKEN, DISCORD_CHANNEL_ID
        return DISCORD_TOKEN, int(DISCORD_CHANNEL_ID) if DISCORD_CHANNEL_ID else None
    except (ImportError, ValueError, AttributeError):
        return '', None


def _is_configured():
    token, channel_id = _get_config()
    return bool(token and channel_id)


# ── Async core ────────────────────────────────────────────────────────────────

async def _send_async(embed, view=None):
    """Open a throwaway Discord client, send one message, close."""
    import discord

    token, channel_id = _get_config()
    if not token or not channel_id:
        return

    intents = discord.Intents.default()
    client  = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            await channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f'[Discord notify] send failed: {e}')
        finally:
            await client.close()

    await client.start(token, reconnect=False)


def _send(embed, view=None):
    """
    Fire-and-forget: runs the async send in a daemon thread so it never
    blocks the caller (listener loop, task runner, etc).
    """
    if not _is_configured():
        return

    def _thread():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send_async(embed, view))
            loop.close()
        except Exception as e:
            logger.error(f'[Discord notify] thread error: {e}')

    t = threading.Thread(target=_thread, daemon=True)
    t.start()


# ── Button views ──────────────────────────────────────────────────────────────
# Views are UI-only — no callbacks here.
# Interactions are dispatched to discord_bot.py via on_interaction,
# which parses the custom_id and runs the action there.

def _make_trust_view(sender_key: str):
    """TRUST / NOTIFY / IGNORE buttons for unknown-sender notifications."""
    import discord
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label='TRUST',  style=discord.ButtonStyle.success,
                                    custom_id=f'swarm:trust:{sender_key}'))
    view.add_item(discord.ui.Button(label='NOTIFY', style=discord.ButtonStyle.primary,
                                    custom_id=f'swarm:notify:{sender_key}'))
    view.add_item(discord.ui.Button(label='IGNORE', style=discord.ButtonStyle.danger,
                                    custom_id=f'swarm:ignore:{sender_key}'))
    return view


def _make_ticket_view(ticket_number: str):
    """Force Close / Resend buttons for SLA / snooze alerts."""
    import discord
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label='Force Close', style=discord.ButtonStyle.danger,
                                    custom_id=f'swarm:close:{ticket_number}'))
    view.add_item(discord.ui.Button(label='Resend',      style=discord.ButtonStyle.secondary,
                                    custom_id=f'swarm:resend:{ticket_number}'))
    return view


# ── Public notification functions ─────────────────────────────────────────────

def notify_unknown_sender(from_addr: str, subject: str, preview: str, source: str = 'email'):
    """Ghost gets pinged about an unknown sender — with TRUST/NOTIFY/IGNORE buttons."""
    if not _is_configured():
        return
    import discord

    display = from_addr
    embed = discord.Embed(
        title='Unknown sender',
        description=f'**{display}** sent a message to Seven.',
        colour=COLOUR_URGENT
    )
    embed.add_field(name='Source',   value=source.upper(), inline=True)
    embed.add_field(name='Subject',  value=subject[:100] or '(no subject)', inline=True)
    embed.add_field(name='Preview',  value=preview[:300], inline=False)
    embed.set_footer(text="Seven's Swarm")

    view = _make_trust_view(from_addr)
    _send(embed, view)
    logger.info(f'[Discord notify] unknown sender: {from_addr}')


def notify_sla_warning(ticket_number: str, sender_email: str, created_at: str,
                       question: str, hours: int):
    """SLA breach alert with Force Close / Resend buttons."""
    if not _is_configured():
        return
    import discord

    embed = discord.Embed(
        title=f'⏱ SLA Warning — {ticket_number}',
        description=f'This ticket has been open for more than **{hours} hours**.',
        colour=COLOUR_WARN
    )
    embed.add_field(name='From',    value=sender_email, inline=True)
    embed.add_field(name='Opened',  value=created_at[:16], inline=True)
    embed.add_field(name='Question', value=(question or '')[:200], inline=False)
    embed.set_footer(text="Seven's Swarm — SLA monitor")

    view = _make_ticket_view(ticket_number)
    _send(embed, view)
    logger.info(f'[Discord notify] SLA warning: {ticket_number}')


def notify_snooze_fired(ticket_number: str, note: str):
    """Snooze reminder ping."""
    if not _is_configured():
        return
    import discord

    embed = discord.Embed(
        title=f'💤 Snooze expired — {ticket_number}',
        description=f'This ticket is back on your radar.',
        colour=COLOUR_WARN
    )
    if note and note != '(no note)':
        embed.add_field(name='Note', value=note[:300], inline=False)
    embed.set_footer(text="Seven's Swarm — Snooze")

    view = _make_ticket_view(ticket_number)
    _send(embed, view)


def notify_ticket_opened(ticket_number: str, sender_email: str, question: str,
                         is_urgent: bool = False, source: str = 'email'):
    """New ticket opened — informational ping."""
    if not _is_configured():
        return
    import discord

    title  = f'⚡ URGENT ticket — {ticket_number}' if is_urgent else f'New ticket — {ticket_number}'
    colour = COLOUR_URGENT if is_urgent else COLOUR_INFO

    embed = discord.Embed(title=title, colour=colour)
    embed.add_field(name='From',    value=sender_email, inline=True)
    embed.add_field(name='Source',  value=source.upper(), inline=True)
    embed.add_field(name='Question', value=(question or '')[:300], inline=False)
    embed.set_footer(text="Seven's Swarm")

    _send(embed)


def notify_ticket_closed(ticket_number: str, duck_result: str):
    """Ticket closed — green tick."""
    if not _is_configured():
        return
    import discord

    is_yes = (duck_result or '').upper().startswith('YES')
    colour = COLOUR_OK if is_yes else COLOUR_WARN
    duck_icon = '✓' if is_yes else '⚠'

    embed = discord.Embed(
        title=f'{duck_icon} Closed — {ticket_number}',
        description=f'Duck: **{duck_result or "—"}**',
        colour=colour
    )
    embed.set_footer(text="Seven's Swarm")
    _send(embed)


def send_digest(stats: dict, date_str: str):
    """Daily digest as a rich embed instead of (or alongside) email."""
    if not _is_configured():
        return
    import discord

    duck_total = stats['duck_yes'] + stats['duck_no']
    duck_rate  = f"{100 * stats['duck_yes'] // duck_total}%" if duck_total else 'n/a'

    embed = discord.Embed(
        title=f"📊 Daily Digest — {date_str}",
        colour=COLOUR_OK
    )
    embed.add_field(name='Opened',    value=str(stats['opened']),  inline=True)
    embed.add_field(name='Closed',    value=str(stats['closed']),  inline=True)
    embed.add_field(name='Open now',  value=str(stats['open']),    inline=True)
    embed.add_field(
        name='Duck pass rate',
        value=f"{duck_rate}  ({stats['duck_yes']} yes / {stats['duck_no']} no)",
        inline=False
    )
    if stats.get('top_tags'):
        tag_str = ', '.join(f'`{t}` {c}' for t, c in stats['top_tags'])
        embed.add_field(name='Top tags (7 days)', value=tag_str, inline=False)
    embed.set_footer(text="Seven's Swarm — Daily Digest")

    _send(embed)


def notify_ghost_circle(problem_type: str, ticket_number: str, tokens: int):
    """Ghost Circle was called — audit trail in Discord."""
    if not _is_configured():
        return
    import discord

    embed = discord.Embed(
        title='👁 Ghost Circle consulted',
        colour=COLOUR_GHOST
    )
    embed.add_field(name='Problem type', value=problem_type, inline=True)
    embed.add_field(name='Ticket',       value=ticket_number or '—', inline=True)
    embed.add_field(name='Tokens used',  value=str(tokens), inline=True)
    embed.set_footer(text="Seven's Swarm — Claude advisory")

    _send(embed)


def notify_brief_ready(brief_summary: str, trigger: str = 'scheduled', tokens: int = 0,
                       open_proposals: int = 0, duck_flags: int = 0, open_tickets: int = 0):
    """Ping Ghost when a new Ghost Brief has been generated."""
    if not _is_configured():
        return
    import discord

    lines = []
    if open_tickets:
        lines.append(f'📬 **{open_tickets}** open ticket{"s" if open_tickets != 1 else ""}')
    if open_proposals:
        lines.append(f'🗂 **{open_proposals}** active proposal{"s" if open_proposals != 1 else ""}')
    if duck_flags:
        lines.append(f'⚠️ **{duck_flags}** Duck flag{"s" if duck_flags != 1 else ""}')
    if tokens:
        lines.append(f'🪙 {tokens:,} tokens')

    desc = '\n'.join(lines) if lines else 'Brief generated.'
    if brief_summary:
        desc += f'\n\n_{brief_summary[:300]}_'

    embed = discord.Embed(
        title='📋 Ghost Brief Ready',
        description=desc,
        colour=COLOUR_GHOST,
    )
    embed.set_footer(text=f"Seven's Swarm · trigger: {trigger}")
    _send(embed)


def post_raw(title: str, body: str, colour: int = COLOUR_INFO):
    """Generic one-off message — for manual pings or future use."""
    if not _is_configured():
        return
    import discord

    embed = discord.Embed(title=title, description=body[:4000], colour=colour)
    embed.set_footer(text="Seven's Swarm")
    _send(embed)
