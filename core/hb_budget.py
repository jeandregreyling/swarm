"""Online agents cost JD real money per token (owner 14 Nov 2026: "it's not a charity"). HB manages each online agent's daily budget
(core/capability_packs/hb.agent.budget.v1.json - data, JD sets the numbers):

  check(conn, agent, sender)  automatic (HB/APEX) requests stop once the automatic share of the day's budget is used, so the rest stays for
                              JD's own questions and for checks. JD's own requests always go through (his money, his call).
  text_for(agent)             what an online agent is told at onboarding: what a token means here, its budget, its habits.
  line(conn, agent)           usage today for /agents.
Usage = tokens recorded on the agent's replies in the last 24 hours (messages.tokens_used).
"""
import json
from pathlib import Path

PACK = Path(__file__).resolve().parent / 'capability_packs' / 'hb.agent.budget.v1.json'
OWNER_SENDERS = ('user', 'ghost', 'owner', 'jd')


def load():
    return json.loads(PACK.read_text())


def for_agent(agent_id):
    pack = load()
    return {**pack['default_online'], **pack['agents'].get(agent_id, {})}


def used_24h(conn, agent_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'").fetchone():
        return 0
    row = conn.execute("SELECT COALESCE(SUM(tokens_used),0) FROM messages WHERE from_agent=? AND created_at>=datetime('now','-1 day')",
                       (agent_id,)).fetchone()
    return int(row[0] or 0)


def check(conn, agent_id, sender):
    """(allowed, reason) for a request to an online agent."""
    b = for_agent(agent_id)
    if not b.get('metered', True) or not b.get('daily_tokens') or str(sender or '').lower() in OWNER_SENDERS:
        return True, ''
    used, limit = used_24h(conn, agent_id), int(b['daily_tokens'] * b.get('automatic_share', 1.0))
    if used >= limit:
        return False, (f"{agent_id} has used {used:,} of its {b['daily_tokens']:,} tokens today; HB keeps the rest for JD's own questions "
                       f"and checks, so automatic requests wait until tomorrow (budget: hb.agent.budget.v1.json)")
    return True, ''


def text_for(agent_id):
    pack, b = load(), for_agent(agent_id)
    if b.get('metered', True) and b.get('daily_tokens'):
        budget = (f"Your budget: {b['daily_tokens']:,} tokens a day. HB stops automatic requests to you at "
                  f"{int(b.get('automatic_share', 1) * 100)}% so the rest is kept for JD's own questions and checks. ")
    else:
        budget = f"{b.get('note', 'HB cannot measure your token use')} "
    return (f"What tokens mean here: {pack['meaning']} {budget}Habits: " + ' '.join(pack['habits']))


def line(conn, agent_id):
    b = for_agent(agent_id)
    if not b.get('metered', True) or not b.get('daily_tokens'):
        return 'tokens: not metered'
    return f"tokens today: {used_24h(conn, agent_id):,} of {b['daily_tokens']:,}"
