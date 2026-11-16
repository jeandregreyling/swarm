"""Practice 102 (owner 16 Nov 2026): "I still can't see these downloads in HB". HB's download lines went to chat 2834, which JD no longer
uses, and after a restart the tablet link was called "enx12d050f6667f". Lines now go to the chat JD uses, and any enx... link is the tablet."""
import sqlite3

from core import hb_downloads as d


def test_practice_102_lines_go_where_jd_is(tmp_path):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2845, 'user', 'I still cannot see these downloads')")
    f = tmp_path / 'model.gguf'
    f.write_bytes(b'x' * 10)
    d.register(c, 'Test model', f, 100, interface='enx12d050f6667f', now=1000.0)
    chat, text = c.execute("SELECT conversation_id, content FROM messages WHERE from_agent='hummingbird'").fetchone()
    assert chat == 2845 and 'tablet USB tethering (mobile data)' in text
    assert 'tablet USB tethering' in d.status_text(c)


def test_practice_102_connection_names():
    assert d.connection('enp5s0') == 'home line (Orbi)'
    assert d.connection('enx12d050f6667f') == 'tablet USB tethering (mobile data)'
    assert d.connection(None) == 'default connection'
