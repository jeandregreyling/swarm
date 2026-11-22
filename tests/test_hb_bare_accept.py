"""Bare /accept from Telegram or main chat approves a single pending step or lists pending step IDs instead of /help."""
import sqlite3

from core import hb_commands as hc


def test_bare_accept_parses_cleanly():
    assert hc.parse('accept') == ('accept', [])
    assert hc.parse('accept S-0123456789') == ('accept', ['S-0123456789'])
    assert hc.parse('reject') is None


def test_bare_accept_handles_zero_one_and_many_pending(monkeypatch):
    conn = sqlite3.connect(':memory:')
    # 0 pending
    monkeypatch.setattr(hc, 'waiting_items', lambda c, conv=None: [])
    assert 'Nothing is waiting for /accept' in hc.run(conn, 2845, 'accept', [], 'JD')

    # 1 pending -> calls accept_step directly
    called = []
    monkeypatch.setattr(hc, 'waiting_items', lambda c, conv=None: [{'kind': 'accept', 'step_id': 'S-AAAABBBBCC', 'title': 'One step'}])
    monkeypatch.setattr(hc, 'accept_step', lambda c, sid, actor, comment='': called.append((sid, actor)) or f'Accepted {sid}')
    assert hc.run(conn, 2845, 'accept', [], 'JD') == 'Accepted S-AAAABBBBCC'
    assert called == [('S-AAAABBBBCC', 'JD')]

    # >1 pending -> lists exact /accept S-... commands cleanly
    monkeypatch.setattr(hc, 'waiting_items', lambda c, conv=None: [
        {'kind': 'accept', 'step_id': 'S-AAAABBBBCC', 'title': 'First step'},
        {'kind': 'accept', 'step_id': 'S-DDDD111122', 'title': 'Second step'},
    ])
    out = hc.run(conn, 2845, 'accept', [], 'JD')
    assert '/accept S-AAAABBBBCC' in out and '/accept S-DDDD111122' in out
