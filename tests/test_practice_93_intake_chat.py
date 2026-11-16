"""Practice 93 (owner 16 Nov 2026): HB looked at JD's spreadsheet in the inbox folder and said it could not read it (company protection
label) - in chat 2834, which JD no longer uses, so he never saw it. Inbox-folder and email-intake messages now go to the chat JD last typed in."""
import sqlite3

from core import hb_email_intake as e


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    e.ensure_schema(c)
    return c


def test_practice_93_the_chat_jd_uses():
    c = _db()
    assert e.jd_chat(c) == e.MAIN_CHAT                       # JD has typed nowhere yet
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2834, 'user', 'old')")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'download all the notes')")
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2834, 'hummingbird', 'notice')")
    assert e.jd_chat(c) == 2845


def test_practice_93_an_unreadable_inbox_file_is_reported_where_jd_is(tmp_path):
    c = _db()
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'go')")
    f = tmp_path / 'SAPKE608F9 - G4.xlsx'
    f.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1') + b'protected' * 10)
    import os
    os.utime(f, (1, 1))
    e.folder_check(c, tmp_path, keep=lambda *a: 1, now=1000.0)
    said = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert said and said[-1][0] == 2845 and 'SAPKE608F9 - G4.xlsx' in said[-1][1]
