"""Practice 105 (owner 16 Nov 2026): HB's benchmark, onboarding, exam, GPU-guard, proposal and lesson lines went to chat 2834, which JD no
longer uses - he never saw MiniCPM5 pass its benchmark or Copilot pass its exam. Every module now asks core.hb_chat.owner_chat, and this
test fails if code posts to chat 2834 directly again."""
import re
import sqlite3
from pathlib import Path

from core import hb_agents, hb_chat, hb_model_bench

ROOT = Path(__file__).resolve().parents[1]


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    return c


def test_practice_105_the_chat_jd_uses():
    c = _db()
    assert hb_chat.owner_chat(c) == 2834 and hb_chat.owner_chat(None) == 2834
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2834, 'user', 'old')")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'yes please go')")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2834, 'hummingbird', 'notice')")
    assert hb_chat.owner_chat(c) == 2845


def test_practice_105_benchmark_and_onboarding_lines_reach_jd():
    c = _db()
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'yes please go')")
    hb_model_bench._post(c, '🧪 minicpm5-cpu:2b done')
    hb_agents._post(c, '✅ copilot-instructor passed')
    assert [r[0] for r in c.execute("SELECT conversation_id FROM messages WHERE from_agent='hummingbird'")] == [2845, 2845]


def test_practice_105_nobody_posts_to_2834_directly():
    found = []
    for path in list((ROOT / 'core').glob('*.py')) + list((ROOT / 'frontend' / 'blueprints').glob('*.py')):
        src = path.read_text(encoding='utf-8', errors='replace')
        if re.search(r"VALUES \(2834,", src) or re.search(r"\(MAIN_CHAT,\s*(?:message\(|f'|f\"|text\b)", src) or re.search(r"run\(conn,\s*2834,", src):
            found.append(path.name)
    assert found == [], found
