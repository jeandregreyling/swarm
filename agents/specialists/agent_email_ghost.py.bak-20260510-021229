"""
agent_email_ghost.py — Seven's Swarm / Phase 6 Agent Agency
═══════════════════════════════════════════════════════════════════════════════
Any agent can send Ghost an email + Discord notification via this module.
Primary use: proposal ready for review.

Ghost reviews in the KB tab — Proposals section.
Approve → proposal imported to KB + agent memory updated.
Reject  → optional feedback written to agent's private sandpit.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

from email_handler import send_reply
from config import GHOST_EMAIL
from database import log_activity
import discord_notify


def agent_email_ghost(agent, subject, body, ticket_number=None, proposal_filename=None):
    """
    Send Ghost an email from the swarm on behalf of an agent.
    Also posts a Discord notification to the notification channel.

    agent:               Agent name (e.g. 'gemma', 'qwen')
    subject:             Email subject line
    body:                Email body text
    ticket_number:       Optional — link to a ticket
    proposal_filename:   Optional — links to the review queue in the KB tab
    """
    full_subject = f'[{agent.capitalize()}] {subject}'
    dashboard_link = ''
    if proposal_filename:
        dashboard_link = (
            f'\r\n\r\nReview in dashboard → Docs tab → Proposals:\r\n'
            f'http://seven-potato:5050/ (Docs → scroll to Proposals)\r\n'
        )

    full_body = (
        f'Message from {agent.capitalize()} (Seven\'s Swarm)\r\n'
        f'{"=" * 50}\r\n\r\n'
        f'{body}'
        f'{dashboard_link}'
        f'\r\n\r\n— Seven\'s Swarm'
    )

    try:
        send_reply(
            to_address=GHOST_EMAIL,
            subject=full_subject,
            body=full_body
        )
        log_activity(agent, 'email_ghost', subject[:100])
        print(f'[AgentEmail] {agent} → Ghost: {subject[:60]}')
    except Exception as e:
        print(f'[AgentEmail] Email failed: {e}')

    # Discord notification
    try:
        preview = body[:600] + ('…' if len(body) > 600 else '')
        discord_notify.post_raw(
            title=f'[{agent.capitalize()}] {subject[:80]}',
            body=preview,
            colour=discord_notify.COLOUR_INFO,
        )
    except Exception as e:
        print(f'[AgentEmail] Discord notification failed: {e}')


def notify_proposal_ready(agent, proposal_filename, proposal_preview):
    """
    Convenience wrapper: notify Ghost that a proposal is ready for review.
    """
    agent_email_ghost(
        agent=agent,
        subject=f'Proposal ready for review: {proposal_filename}',
        body=(
            f'I\'ve drafted a proposal during my idle time. It has passed Sniffles audit.\r\n\r\n'
            f'Preview:\r\n{"-" * 40}\r\n{proposal_preview[:600]}\r\n{"-" * 40}\r\n\r\n'
            f'To review: open the Dashboard → Docs tab → scroll to Proposals.\r\n'
            f'You can Approve (adds to KB + updates my memory) or Reject (optional feedback).'
        ),
        proposal_filename=proposal_filename
    )


if __name__ == '__main__':
    # Quick test
    agent_email_ghost(
        agent='qwen',
        subject='Test message from Qwen',
        body='This is a test. The proposal system is working.'
    )
    print('Done.')
