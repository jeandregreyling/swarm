import sqlite3

import pytest

from core import peer_bridge as peers


def test_codex_is_a_separate_scoped_principal_with_real_thread_roundtrip():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE conversations (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER,
            from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT,
            tokens_used INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO conversations VALUES (1, 'Shared recovery');
    ''')
    peers.ensure_schema(conn)
    assert conn.execute("SELECT enabled FROM service_principals WHERE id='codex-instructor'").fetchone()[0] == 0
    token = peers.issue_token(conn, 'codex-instructor')
    principal = peers.authenticate(conn, token)
    assert principal['id'] == 'codex-instructor'
    assert principal['scopes'] == {'peer.read', 'peer.post', 'peer.memory'}
    assert peers.mentioned_peers('@codex @Codex @instructor') == ['codex-instructor', 'copilot-instructor']
    assert peers.mentioned_peers('mail@codex.com @codexElse @@codex') == []
    assert peers.parse_dispatch('[DISPATCH: @codex] Review this receipt') == [('codex-instructor', 'Review this receipt')]
    ids = peers.enqueue(conn, 1, None, 'Please review recovery', ['codex-instructor'], sender='ghost')
    assert [row['id'] for row in peers.inbox(conn, principal)] == ids
    posted = peers.post(conn, principal, 1, 'Codex has reviewed the recovery receipts.')
    assert posted['from_agent'] == 'codex-instructor'
    assert peers.thread(conn, principal, 1)[-1]['content'] == 'Codex has reviewed the recovery receipts.'
    with pytest.raises(peers.PeerError):
        peers.post(conn, principal, 1, 'I am the instructor', 'copilot-instructor')
    assert any(p['id'] == 'codex-instructor' for p in peers.conversation_activity(conn, 1)['participants'])
    peers.set_enabled(conn, 'codex-instructor', False, 'ghost')
    assert peers.authenticate(conn, token) is None
    conn.close()
