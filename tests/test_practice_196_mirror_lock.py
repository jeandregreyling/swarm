"""Practice 196: the mirror talks to Telegram only after HB's database is released."""
import sqlite3
from types import SimpleNamespace

from core import hb_channels as ch


def test_no_write_lock_is_held_while_sending(monkeypatch, tmp_path):
    path = tmp_path / 'hb.db'
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute('CREATE TABLE trusted_senders(id INTEGER PRIMARY KEY, email TEXT, added_by TEXT, added_at TEXT, notes TEXT)')
    monkeypatch.setattr('core.hb_chat.owner_chat', lambda conn: 7)
    monkeypatch.setattr('core.hb_commands.waiting_items', lambda conn: [])
    ch.seed(c, SimpleNamespace(GHOST_TELEGRAM_CHAT_ID=999, GHOST_EMAIL='jd@example.com'))
    ch.mirror_once(c, lambda t: True)
    c.commit()
    for n in range(3):
        c.execute("INSERT INTO messages(conversation_id, from_agent, content, message_type) VALUES (7,'apex',?,'response')", (f'answer {n}',))
    c.commit()
    other = sqlite3.connect(path, timeout=0.2)
    seen = []

    def send(text):
        assert not c.in_transaction                      # nothing of ours is open while Telegram is called
        other.execute("INSERT INTO messages(conversation_id, from_agent, content, message_type) VALUES (8,'x','y','z')")   # another writer gets in
        other.commit()
        seen.append(text)
        return True
    assert ch.mirror_once(c, send) == 3 and seen == ['APEX: answer 0', 'APEX: answer 1', 'APEX: answer 2']
    assert ch.cursor(c, 'mirror_last_id') == str(c.execute('SELECT MAX(id) FROM messages WHERE conversation_id=7').fetchone()[0])
