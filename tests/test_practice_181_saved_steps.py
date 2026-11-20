"""Practice 181: APEX's steps are saved with the reply and shown under it."""
import sqlite3
from pathlib import Path

from core import hb_turn_steps

ROOT = Path(__file__).resolve().parents[1]


def test_save_and_read_steps():
    c = sqlite3.connect(':memory:')
    steps = [{'t': 0.1, 'text': 'APEX thinking - round 1'}, {'t': 2.5, 'text': 'searching our notes: "MCB"'}, {'t': 3, 'text': ' '}]
    assert hb_turn_steps.save(c, 1, 42, steps)
    assert hb_turn_steps.for_messages(c, ['42', '43', 'x']) == {42: steps[:2]}
    assert not hb_turn_steps.save(c, 1, None, steps) and not hb_turn_steps.save(c, 1, 44, [])


def test_chat_records_and_page_shows_steps():
    chat = (ROOT / 'frontend/blueprints/chat.py').read_text()
    assert 'turn_steps.append(' in chat and 'hb_turn_steps.save(steps_conn, conv_id, reply_id, turn_steps)' in chat
    assert "/api/peer/v1/hb/turn-steps" in (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    js = (ROOT / 'frontend/static/js/hb-turn-steps.js').read_text()
    assert 'How APEX got here' in js and "'<details" not in js and "createElement('details')" in js
    assert 'hb-turn-steps.js' in (ROOT / 'frontend/templates/terminal_base.html').read_text()
