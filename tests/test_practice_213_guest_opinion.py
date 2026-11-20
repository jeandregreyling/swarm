"""Practice 213: a guest's answer turn carries the opinion-not-notes rule; the owner's does not."""
import sqlite3

from core import hb_channels as ch, hb_guest as g


def run(role):
    c = sqlite3.connect(':memory:', check_same_thread=False)
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    ch.ensure(c)
    c.execute("INSERT INTO hb_channel_identities VALUES ('telegram:1',?,'telegram:1','JD',0)", (role,))

    class Keep:
        def __getattr__(self, n): return getattr(c, n)
        def close(self): pass
    seen = []
    ch.work_one({'channel': 'telegram', 'key': 'telegram:1', 'message_id': 1, 'question': 'what is /XQE?', 'reply': {}},
                connect=Keep, answer=lambda q, h: seen.append(g.GUEST_TURN.get()) or 'ok')
    return seen[0], g.GUEST_TURN.get()


def test_guest_turn_is_flagged_and_reset(monkeypatch):
    monkeypatch.setattr(ch, '_chat', lambda conn: 7)
    monkeypatch.setattr(ch, 'telegram_send', lambda *a, **k: True)
    monkeypatch.setattr(ch, '_owner_task_state', lambda conn, job: '')
    assert run('user') == (True, False)
    assert run('owner') == (False, False)


def test_rule_says_opinion_not_notes():
    r = g.ANSWER_RULE
    assert 'own words' in r and 'Do not quote SAP note text' in r and 'note number' in r
    assert 'hb_guest.ANSWER_RULE' in open(ch.__file__).read()
