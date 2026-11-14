"""Practice 33 (owner 14 Nov): "@Claude your handle is still not processed" - inbox agents' handles are in the @ list; HB confirms delivery."""
from pathlib import Path
from core import hb_agents, hb_online
from test_hb_agents import world  # noqa: F401
from test_peer_turns import flow, reply  # noqa: F401


def test_practice_33_handles_offered_for_every_inbox_agent(world):
    conn = world
    hb_agents.onboard(conn, 'claude-code', kind='online', profile='advisor', about='Claude Code.', say=lambda t: None, handles=['claude', 'claude-code'])
    assert [m['key'] for m in hb_agents.mention_items(conn)] == ['claude', 'claude-code']
    assert 'hb_agents.mention_items(conn)' in Path(hb_online.__file__).read_text()


def test_practice_33_delivery_is_confirmed_in_main_chat_at_once():
    src = (Path(hb_agents.__file__).resolve().parents[1] / 'frontend/blueprints/chat.py').read_text()
    i = src.index('g.hb_inbox_routed = (')
    assert 'INSERT INTO messages' in src[i:i + 600]
