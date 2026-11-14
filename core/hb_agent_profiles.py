"""Agent profiles (owner 14 Nov 2026): onboarding a new agent means giving it a profile, not writing code for its name.

core/capability_packs/hb.agent.profiles.v1.json lists profiles (tools + rules) and which agent has which profile. HB's tool grants add the
profile's tools for an agent that may read HB at all; the agent's worker reads its instructions from the profile.
"""
import json
from pathlib import Path

PACK = Path(__file__).resolve().parent / 'capability_packs' / 'hb.agent.profiles.v1.json'


def _pack():
    try:
        return json.loads(PACK.read_text())
    except (OSError, ValueError):
        return {'profiles': {}, 'agents': {}}


def _registered_profile(agent, conn=None):
    """Onboarded agents (hb_agents, core/hb_agents.py) carry their profile in HB's database."""
    try:
        if conn is None:
            from contextlib import closing
            from utils.db._connection import get_connection
            with closing(get_connection()) as c:
                return _registered_profile(agent, c)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_agents'").fetchone():
            return None
        row = conn.execute("SELECT profile, status FROM hb_agents WHERE agent_id=? AND status IN ('active','provisional')", (agent,)).fetchone()
        return (row[0] if row[1] == 'active' else 'provisional') if row else None   # owner 14 Nov: no pass, no work
    except Exception:
        return None


def profile_for(agent, conn=None):
    pack = _pack()
    name = _registered_profile(agent, conn) or pack.get('agents', {}).get(agent)
    return {'name': name, **pack['profiles'][name]} if name in pack.get('profiles', {}) else None


def tools_for(agent, conn=None):
    p = profile_for(agent, conn)
    return list(p.get('tools') or []) if p else []


def instructions_for(agent, conn=None):
    p = profile_for(agent, conn)
    return str(p.get('instructions') or '') if p else ''
