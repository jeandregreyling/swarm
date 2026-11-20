"""Practice 212: guests get a welcome, guest commands, and only their own questions."""
import sqlite3

from core import hb_channels as ch, hb_guest as g


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    ch.ensure(c)
    return c


def test_trust_as_user_sends_a_welcome(monkeypatch):
    sent = []
    monkeypatch.setattr(ch, 'telegram_send', lambda chat, text, call=None: sent.append((chat, text)))
    class T:
        def __init__(self, target, args, **kw): self.f, self.a = target, args
        def start(self): self.f(*self.a)
    monkeypatch.setattr(ch.threading, 'Thread', T)
    monkeypatch.setattr(ch, 'WELCOME_IN_TESTS', True)
    c = db()
    said = ch.command(c, ['trust', 'telegram:555'], 'JD')
    assert 'guest' in said and 'welcome' in said and ch.role(c, 'telegram:555') == 'user'
    assert sent[0][0] == '555' and "You're set up as a guest" in sent[0][1] and '/mine' in sent[0][1]
    sent.clear()
    ch.command(c, ['trust', 'telegram:777', 'owner'], 'JD')
    assert sent == []                                   # owners get no guest welcome


def test_guest_commands_never_reach_owner_commands(monkeypatch):
    c = db()
    c.execute("INSERT INTO hb_channel_identities VALUES ('telegram:555','user','telegram:555','JD',0)")
    monkeypatch.setattr(ch, '_chat', lambda conn: 7)
    assert 'What you can do' in ch.inbound(c, 'telegram', 'telegram:555', 'Sam', '/help')
    assert 'APEX - the main model' in ch.inbound(c, 'telegram', 'telegram:555', 'Sam', '/about')
    assert 'commands are for the owner' in ch.inbound(c, 'telegram', 'telegram:555', 'Sam', '/stop')


def test_mine_pairs_his_questions_with_answers():
    c = db()
    ch._log(c, 'telegram', 'in', 'telegram:555', 1, 'what is MCB?')
    ch._log(c, 'telegram', 'out', 'apex', 2, 'The Maximum Contribution Base.')
    ch._log(c, 'telegram', 'in', 'telegram:999', 3, 'someone else')
    text = g.mine(c, 'telegram:555')
    assert 'what is MCB?' in text and 'Maximum Contribution Base' in text and 'someone else' not in text
