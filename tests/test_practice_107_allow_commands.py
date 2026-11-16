"""Practice 107 (owner 16 Nov 2026): "it should ask to add commands to whitelist if they aren't in it". A command that is not on main chat's
list is offered ("Allow and run" or /sh allow <command>); JD adds that exact command and it runs. Never sudo, never destructive, never chained."""
import sqlite3
import time
from pathlib import Path

from core import hb_chat_terminal as t

ROOT = Path(__file__).resolve().parents[1]


def _db(tmp_path):
    path = tmp_path / 'm.db'
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.commit()
    c.close()
    return lambda: sqlite3.connect(path, timeout=10)


def _wait(command_id, connect):
    end = time.time() + 20
    while time.time() < end:
        s = t.status(command_id, connect)
        if s and s['state'] != 'running':
            return s
        time.sleep(0.2)


def test_practice_107_ask_then_add_then_run(tmp_path):
    connect = _db(tmp_path)
    first = t.start(2845, 'nproc', connect=connect)
    assert first['state'] == 'refused' and first['can_allow'] is True
    assert 'Allow and run' in t.status(first['command_id'], connect)['content']
    assert t.allow('nproc', 'jd', connect=connect) == {'ok': True, 'command': 'nproc'}
    second = t.start(2845, 'nproc', connect=connect)
    assert second['ok']
    s = _wait(second['command_id'], connect)
    assert s['state'] == 'completed' and s['output'].strip().isdigit()
    assert t.start(2845, 'nproc --all', connect=connect)['state'] == 'refused'      # only the exact command was added


def test_practice_107_never_privileged_destructive_or_chained(tmp_path):
    connect = _db(tmp_path)
    for cmd in ('sudo ls', 'su -', 'rm -rf build', 'shutdown now', 'nproc;id', 'no-such-program-xyz'):
        assert t.can_allow(cmd)[0] is False, cmd
        assert t.allow(cmd, 'jd', connect=connect)['ok'] is False, cmd
    assert t.start(2845, 'sudo ls', connect=connect).get('can_allow') is False


def test_practice_107_main_chat_offers_it():
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    assert '/api/chat-terminal/allow' in js and 'Allow and run' in js and 'else if (data && data.can_allow) _hcTerminalOffer' in js
    assert "/api/chat-terminal/allow" in (ROOT / 'frontend/blueprints/shell.py').read_text()
