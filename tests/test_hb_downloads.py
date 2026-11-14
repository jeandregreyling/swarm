"""Owner 14 Nov: "these downloads should be showing in main chat because they're related to tasks in Studio"."""
import sqlite3

from core import hb_downloads as dl, hb_commands as hc


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, '
                 'message_type TEXT, tokens_used INT)')
    return conn


def test_progress_steps_done_and_stall_reach_main_chat(tmp_path):
    conn = _conn()
    f = tmp_path / 'model.gguf'
    f.write_bytes(b'x' * 10)
    dl.register(conn, 'Mixtral 8x7B', f, 1000, interface='enp5s0', step_id='S-B4C07AFD21', now=0)
    said = lambda: [r[0] for r in conn.execute('SELECT content FROM messages ORDER BY id')]
    assert said()[0].startswith('⬇ Download started: Mixtral 8x7B (0.0 GB) over the home line (Orbi)') and 'S-B4C07AFD21' in said()[0]
    f.write_bytes(b'x' * 300)
    dl.tick(conn, now=60)
    assert '⬇ Mixtral 8x7B: 25% (0.0 of 0.0 GB) over the home line (Orbi), about 1 min left.' in said()[-1]
    dl.tick(conn, now=70)
    assert len(said()) == 2                                                    # nothing new to say
    dl.tick(conn, now=70 + dl.STALL_S + 1)
    assert said()[-1].startswith('⚠ Download stalled: Mixtral 8x7B')
    dl.tick(conn, now=70 + 2 * dl.STALL_S)
    assert len(said()) == 3                                                    # warned once
    f.write_bytes(b'x' * 1000)
    dl.tick(conn, now=2000)
    assert said()[-1].startswith('✅ Downloaded: Mixtral 8x7B')
    dl.tick(conn, now=3000)
    assert len(said()) == 4
    assert 'Mixtral 8x7B: done, 100%' in hc.handle(conn, 2834, '/downloads', 'jd')
