"""Practice 270: APEX asks owners for access; only an owner command grants it; a grant is one tool on one task."""
import sqlite3

import pytest

from core import hb_access, hb_commands


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute('CREATE TABLE hb_channel_identities(key TEXT, role TEXT)')
    return c


def test_ask_grant_and_attach():
    c = _db()
    r = hb_access.request(c, 'apex', 'studio_proposal', 'T-0000000000AA', 'submit the overclock-control change for JD to review')
    assert r['state'] == 'pending' and r['request_id'].startswith('A-')
    msg = c.execute('SELECT content FROM messages').fetchone()[0]
    assert '/grant ' + r['request_id'] in msg and 'studio_proposal' in msg
    assert hb_access.granted_tools(c, 'T-0000000000AA') == []
    assert 'granted' in hb_access.decide(c, r['request_id'], True, 'JD')
    assert hb_access.granted_tools(c, 'T-0000000000AA') == ['studio_proposal']
    assert hb_access.granted_tools(c, 'T-0000000000BB') == []


def test_unknown_tools_and_empty_reasons_are_refused():
    with pytest.raises(ValueError):
        hb_access.request(_db(), 'apex', 'sudo', 'T-1', 'I want root access to everything')
    with pytest.raises(ValueError):
        hb_access.request(_db(), 'apex', 'run_tests', 'T-1', 'pls')


def test_owner_commands_parse():
    assert hb_commands.parse('grant A-ABC123') == ('grant', ['A-ABC123'])
    assert hb_commands.parse('deny a-abc123') == ('deny', ['A-ABC123'])
    assert hb_commands.parse('permissions granted to request A-ABC123') == ('grant', ['A-ABC123'])
