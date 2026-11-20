"""Practice 193: Telegram and email talk to HB; main chat and Needs-you are mirrored to the owner's phone."""
import email
import json
import sqlite3
from types import SimpleNamespace

import pytest

from core import hb_channels as ch


@pytest.fixture
def conn(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    c.execute('CREATE TABLE trusted_senders(id INTEGER PRIMARY KEY, email TEXT, added_by TEXT, added_at TEXT, notes TEXT)')
    rows = [('jd@example.com', 'Jeandre - Ghost, swarm owner'), ('telegram:111', 'Approved by moderator'), ('discord:222', 'Ghost - Jeandre Discord user ID'),
            ('friend@example.org', 'Approved by moderator'), ('sevenpotato9@gmail.com', 'Seven - swarm address')]
    c.executemany('INSERT INTO trusted_senders(email, notes) VALUES (?,?)', rows)
    monkeypatch.setattr('core.hb_chat.owner_chat', lambda conn: 7)
    ch.seed(c, SimpleNamespace(GHOST_TELEGRAM_CHAT_ID=999, GHOST_EMAIL='JD@example.com'))
    while not ch.JOBS.empty():
        ch.JOBS.get()
    return c


def test_identities(conn):
    assert ch.role(conn, 'telegram:999') == 'owner' and ch.role(conn, 'email:jd@example.com') == 'owner'
    assert ch.role(conn, 'discord:222') == 'owner' and ch.role(conn, 'email:friend@example.org') == 'user'
    assert ch.role(conn, 'telegram:111') == 'user' and ch.role(conn, 'email:sevenpotato9@gmail.com') is None


def test_unknown_sender_runs_nothing_and_jd_is_told(conn):
    said = ch.inbound(conn, 'telegram', 'telegram:5', 'stranger', '/stop')
    assert 'does not know you' in said
    note = conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird'").fetchone()[0]
    assert '/channels trust telegram:5' in note and 'Nothing was run' in note


def test_owner_command_runs_through_hb_and_is_not_mirrored_twice(conn):
    ran = []
    said = ch.inbound(conn, 'telegram', 'telegram:999', 'jd', '/status', commands=lambda c, conv, verb, args, actor, after: ran.append((verb, actor)) or 'all good')
    assert said == 'all good' and ran == [('status', 'JD via Telegram')]
    ch.set_cursor(conn, 'mirror_last_id', 0)
    ch.set_cursor(conn, 'needs_seen', '[]')
    sent = []
    ch.mirror_once(conn, lambda t: sent.append(t) or True)
    assert sent == []                                   # the echo and the delivered reply are both skipped


def test_machine_commands_need_the_screen_and_users_only_ask(conn):
    assert 'needs the screen' in ch.inbound(conn, 'telegram', 'telegram:999', 'jd', '/admin approve A-1')
    assert 'commands are for the owner' in ch.inbound(conn, 'telegram', 'telegram:111', 'mate', '/status')


def test_questions_queue_an_answer_requests_become_tasks(conn):
    assert 'APEX is on it' in ch.inbound(conn, 'telegram', 'telegram:999', 'jd', 'What is wage type /XQE?')
    job = ch.JOBS.get_nowait()
    assert job['question'] == 'What is wage type /XQE?' and job['channel'] == 'telegram'
    sent = []
    said = ch.inbound(conn, 'telegram', 'telegram:999', 'jd', 'fix the scroll arrow in main chat',
                      enqueue=lambda c, conv, mid, body, to, sender: sent.append((to, sender)) or [42])
    assert sent == [(['apex'], 'user')] and 'request 42' in said
    assert 'APEX is on it' in ch.inbound(conn, 'telegram', 'telegram:111', 'mate', 'build me a website')   # users only ask


def test_answer_is_posted_and_emailed_back(conn):
    mails = []
    job = {'channel': 'email', 'key': 'email:jd@example.com', 'question': 'q?', 'message_id': 1,
           'reply': {'to': 'jd@example.com', 'subject': 'MCB cap', 'message_id': '<m1>'}}
    out = ch.work_one(job, connect=lambda: _Shared(conn), answer=lambda q, h: 'The MCB is an annual cap.',
                      mail=lambda to, subject, body, **kw: mails.append((to, subject, body)))
    assert out == 'The MCB is an annual cap.' and mails == [('jd@example.com', 'Re: MCB cap', 'The MCB is an annual cap.')]
    assert conn.execute("SELECT from_agent FROM messages ORDER BY id DESC LIMIT 1").fetchone()[0] == 'apex'


class _Shared:
    def __init__(self, conn):
        self.c = conn

    def __getattr__(self, name):
        return getattr(self.c, name)

    def close(self):
        pass


def test_mirror_sends_new_posts_filters_noise_and_splits(conn, monkeypatch):
    monkeypatch.setattr('core.hb_commands.waiting_items', lambda conn: [{'key': 'accept:S-1', 'kind': 'accept', 'step_id': 'S-1', 'label': 'Approve S-1'}])
    sent = []
    assert ch.mirror_once(conn, lambda t: sent.append(t) or True) == 0          # first start: nothing from history
    for sender, content, kind in (('apex', '**Hi** see [note](http://x)', 'response'), ('apex', '[tool:read_file] ok', 'response'),
                                  ('hummingbird', '{"task_type": "x"}', 'response'), ('hummingbird', 'x' * 9000, 'response')):
        conn.execute("INSERT INTO messages(conversation_id, from_agent, content, message_type) VALUES (7,?,?,?)", (sender, content, kind))
    monkeypatch.setattr('core.hb_commands.waiting_items', lambda conn: [{'key': 'accept:S-1', 'kind': 'accept', 'step_id': 'S-1', 'label': 'Approve S-1'},
                                                                         {'key': 'halt:T-2', 'kind': 'halted', 'task_id': 'T-2', 'label': 'Stuck task', 'why': 'APEX is stuck'}])
    ch.mirror_once(conn, lambda t: sent.append(t) or True)
    assert sent[0] == 'APEX: Hi see note' and sent[1].startswith('HB: xxx') and len(sent[1]) <= ch.TELEGRAM_CHUNK
    assert len(sent) == 5 and not any(s.startswith(('APEX: [tool', 'HB: {')) for s in sent)   # 1 + 3 parts of the long post + Needs you
    needs = [s for s in sent if s.startswith('⚑')]
    assert needs == ['⚑ Needs you: Stuck task\nAPEX is stuck\nReply: /continue T-2 · /cancel T-2']


def test_telegram_poll_hands_messages_to_inbound_and_answers(conn):
    calls = []

    def call(method, payload=None, timeout=0):
        calls.append((method, payload))
        if method == 'getUpdates':
            return {'ok': True, 'result': [{'update_id': 10, 'message': {'chat': {'id': 999}, 'from': {'username': 'jd'}, 'text': '/help'}}]}
        return {'ok': True}
    seen = []
    n = ch.telegram_poll_once(conn, call=call, handle=lambda c, channel, key, name, text: seen.append((channel, key, text)) or 'here is help')
    assert n == 1 and seen == [('telegram', 'telegram:999', '/help')] and ch.cursor(conn, 'telegram_offset') == '11'
    assert calls[-1] == ('sendMessage', {'chat_id': 999, 'text': 'here is help', 'disable_web_page_preview': 'true'})


def _mail(auth, body='Is the MCB cap annual?', subject='Question'):
    msg = email.message_from_string(f'From: JD <jd@example.com>\nSubject: {subject}\nAuthentication-Results: mx.google.com; {auth}\n\n{body}\n\nOn Mon, X wrote:\n> old')
    return msg


def test_email_requests_need_dkim_or_spf_and_strip_quotes(conn):
    handled = []
    h = lambda c, channel, key, name, text, reply: handled.append((key, text)) or 'ok'
    assert ch.from_email(conn, _mail('dkim=fail spf=fail'), 'jd@example.com', 'Question', 'Is the MCB cap annual?', '<m>', handle=h) == 'unverified'
    assert handled == []
    ch.from_email(conn, _mail('dkim=pass header.i=@example.com'), 'jd@example.com', 'Question', 'Is the MCB cap annual?\n\nOn Mon, X wrote:\n> old', '<m>', handle=h)
    assert handled == [('email:jd@example.com', 'Question\nIs the MCB cap annual?')]
    assert ch.from_email(conn, _mail('dkim=pass'), 'jd@example.com', 'Sheet', 'here you go', '<m2>', handle=h, has_files=True) is None
    assert ch.from_email(conn, _mail('dkim=pass'), 'sevenpotato9@gmail.com', 'x', 'loop?', '<m3>', handle=h) is None


def test_channels_command(conn):
    assert 'enrolled as user' in ch.command(conn, ['trust', 'telegram:77'], 'JD')
    assert ch.role(conn, 'telegram:77') == 'user'
    assert 'enrolled as owner' in ch.command(conn, ['trust', 'email:me@x.org', 'owner'], 'JD')
    assert 'no longer' in ch.command(conn, ['untrust', 'telegram:77'], 'JD') and ch.role(conn, 'telegram:77') is None
    assert 'Channels:' in ch.command(conn, [], 'JD')
