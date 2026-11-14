"""Practice 32 (owner 14 Nov): "@git" reaches the onboarded git agent - its handles route to its inbox and appear in the @ list."""
from core import hb_agents, hb_online
from test_hb_agents import world  # noqa: F401
from test_peer_turns import flow, reply  # noqa: F401
from pathlib import Path


def _git(conn):
    hb_agents.onboard(conn, 'copilot-instructor', kind='online', profile='advisor', about='VS Code instructor.', say=lambda t: None,
                      handles=['git', 'github', 'copilot'])


def test_practice_32_inbox_handles_reach_the_agent(world):
    conn = world
    _git(conn)
    assert hb_agents.inbox_route(conn, 2834, 99, '@git please continue your audit', 'user') == ['copilot-instructor']
    got = conn.execute("SELECT sender, body FROM peer_messages WHERE recipient='copilot-instructor' AND message_id=99").fetchone()
    assert got == ('user', '@git please continue your audit')
    assert hb_agents.inbox_route(conn, 2834, 100, '@nobody hello', 'user') == []


def test_practice_32_inbox_agents_with_their_own_route_are_left_alone(world):
    conn = world
    hb_agents.onboard(conn, 'gemini-advisor', kind='online', profile='advisor', about='Online advisor.', say=lambda t: None, handles=['gemini'])
    assert hb_agents.inbox_route(conn, 2834, 101, '@gemini what do you think', 'user') == []


def test_practice_32_inbox_handles_are_in_the_mention_list(world):
    conn = world
    _git(conn)
    keys = [m['key'] for m in hb_agents.mention_items(conn)]
    assert keys == ['copilot', 'git', 'github']


def test_practice_32_inbox_chat_hands_handles_to_the_inbox_not_to_apex():
    src = (Path(hb_agents.__file__).resolve().parents[1] / 'frontend/blueprints/chat.py').read_text()
    assert 'hb_agents.inbox_route(' in src and "mode': 'inbox'" in src
