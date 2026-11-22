"""Phone & email follow-up continuity: execution-time history includes prior replies posted after follow-up arrived, and shares Carry Forward."""
import sqlite3

from core import hb_carry_forward as cf, hb_channels as ch


def _db():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, '
        'from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)'
    )
    ch.ensure(conn)
    conn.execute("INSERT INTO hb_channel_identities VALUES ('telegram:1','owner','JD','test',0)")
    conn.execute("INSERT INTO hb_channel_identities VALUES ('telegram:2','user','Guest','test',0)")
    return conn


def test_phone_followup_includes_reply_posted_after_followup_and_carry_forward(monkeypatch):
    conn = _db()
    monkeypatch.setattr(ch, '_work_task', lambda j: None)
    m1 = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'user','apex','Check roses in Melbourne','chat',0)").lastrowid
    m2 = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'user','apex','Which one delivers today?','chat',0)").lastrowid
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'apex','user','Flowers Vasette and Botanics are freshest.','response',0)")
    cf.record(conn, 2845, 'Check roses in Melbourne', 'Flowers Vasette and Botanics are freshest.', [{'tool': 'web_search', 'status': 'succeeded'}])
    conn.commit()

    seen_history = []
    class FakeConn:
        def __init__(self, inner): self._c = inner
        def __getattr__(self, name): return getattr(self._c, name)
        def close(self): pass

    def fake_answer(q, hist):
        seen_history.extend(hist)
        return 'Flowers Vasette offers same-day delivery today.'

    job = {'channel': 'telegram', 'key': 'telegram:1', 'question': 'Which one delivers today?', 'message_id': m2, 'reply': {}}
    out = ch.work_one(job, connect=lambda: FakeConn(conn), answer=fake_answer)
    assert 'same-day delivery' in out
    combined = '\n'.join(str(h.get('content', '')) for h in seen_history)
    assert 'Flowers Vasette and Botanics are freshest.' in combined
    assert 'CARRY FORWARD' in combined
    assert 'Which one delivers today?' in cf.card(conn, 2845)


def test_guest_phone_turn_never_receives_owner_carry_forward(monkeypatch):
    conn = _db()
    monkeypatch.setattr(ch, '_work_task', lambda j: None)
    monkeypatch.setattr(ch, 'telegram_send', lambda *a, **k: None)
    cf.record(conn, 2845, 'Private owner payroll note', 'Confidential owner answer', [])
    m = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'user','apex','Hi APEX','chat',0)").lastrowid
    conn.commit()
    seen_history = []
    class FakeConn:
        def __init__(self, inner): self._c = inner
        def __getattr__(self, name): return getattr(self._c, name)
        def close(self): pass
    job = {'channel': 'telegram', 'key': 'telegram:2', 'question': 'Hi APEX', 'message_id': m, 'reply': {}}
    ch.work_one(job, connect=lambda: FakeConn(conn), answer=lambda q, h: seen_history.extend(h) or 'Hi there!')
    assert seen_history == []
