"""Owner 14 Nov: online agents cost real money per token. HB keeps each one inside its daily budget (data in hb.agent.budget.v1.json),
keeps the last part of it for JD's own questions and checks, and tells every online agent at onboarding what tokens mean here."""
import sqlite3

from core import hb_budget


def _db(tokens):
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, from_agent TEXT, tokens_used INT, created_at TEXT DEFAULT (datetime('now')))")
    conn.execute("INSERT INTO messages(from_agent, tokens_used) VALUES ('codex-instructor', ?)", (tokens,))
    conn.execute("INSERT INTO messages(from_agent, tokens_used, created_at) VALUES ('codex-instructor', 9999999, datetime('now','-2 days'))")
    return conn


def test_automatic_requests_stop_at_the_automatic_share_and_jd_still_gets_through():
    b = hb_budget.for_agent('codex-instructor')
    limit = int(b['daily_tokens'] * b['automatic_share'])
    assert hb_budget.check(_db(limit - 1), 'codex-instructor', 'apex') == (True, '')
    ok, why = hb_budget.check(_db(limit), 'codex-instructor', 'apex')
    assert not ok and 'automatic requests wait until tomorrow' in why
    assert hb_budget.check(_db(limit * 5), 'codex-instructor', 'user')[0]          # JD's own question always goes through
    assert hb_budget.line(_db(1234), 'codex-instructor').startswith('tokens today: 1,234 of')   # yesterday's use does not count


def test_unmetered_agents_are_not_gated_but_still_learn_the_habits():
    assert hb_budget.check(_db(10 ** 9), 'copilot-instructor', 'apex')[0]
    t = hb_budget.text_for('copilot-instructor')
    assert 'paid for by JD' in t and 'Be brief' in t and 'subscription' in t
    assert 'tokens a day' in hb_budget.text_for('gemini-advisor')


def test_online_onboarding_memory_states_access_limits_and_cost(monkeypatch):
    from core import hb_agents
    text = hb_agents._online_terms('gemini-advisor', ['read_file', 'studio_proposal'])
    assert 'cannot change HB' in text and 'Studio proposals' in text and 'paid for by JD' in text and 'keys' in text
