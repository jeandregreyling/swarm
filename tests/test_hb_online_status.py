"""Practice 26 (owner 14 Nov): online agents' status is known before JD sends anything.

"In the popup their status should be known before firing off any messages because HB should have already checked their status and
availability at startup; if they are not available they shouldn't be in the list; the teams register should reflect this with
Auto / On / Off so the APEX models can't call them for no reason and say they tried but the model isn't available."
"""
import sqlite3
import time

from core import hb_online


def _conn():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT);
        CREATE TABLE hb_peer_work(request_id INTEGER, state TEXT, stage TEXT, updated_at REAL);
        CREATE TABLE hb_peer_workers(principal TEXT PRIMARY KEY, state TEXT, detail TEXT, updated_at REAL);''')
    return conn


def test_practice_26_modes_default_off_and_follow_the_old_authorisation():
    conn = _conn()
    assert hb_online.mode(conn, 'gemini') == 'off'
    hb_online.authorise(conn, 'gemini', True, 'jd')                      # the older /online gemini on
    assert hb_online.mode(conn, 'gemini') == 'auto'
    hb_online.set_mode(conn, 'gemini', 'on', 'jd')
    assert hb_online.mode(conn, 'gemini') == 'on' and hb_online.status(conn, 'gemini')['authorised']
    hb_online.set_mode(conn, 'gemini', 'off', 'jd')
    assert not hb_online.status(conn, 'gemini')['authorised']


def test_practice_26_a_fresh_check_decides_availability_not_an_old_failure():
    conn = _conn()
    conn.execute("INSERT INTO peer_messages VALUES(1,'gemini-advisor')")
    conn.execute("INSERT INTO hb_peer_work VALUES(1,'failed','Gemini relay failure: ValueError',?)", (time.time() - 3 * 86400,))
    conn.execute("INSERT INTO hb_peer_workers VALUES('gemini-advisor','running','',?)", (time.time(),))
    assert not hb_online.status(conn, 'gemini')['available']                # the old failure, before any check
    hb_online.probe(conn, 'gemini', checker=lambda: (True, 'gemini-2.5-flash answers'))
    s = hb_online.status(conn, 'gemini')
    assert s['available'] and s['reason'].startswith('checked') and 'gemini-2.5-flash answers' in s['reason']
    hb_online.probe(conn, 'gemini', checker=lambda: (False, 'API key rejected'))
    assert not hb_online.status(conn, 'gemini')['available'] and 'API key rejected' in hb_online.status(conn, 'gemini')['reason']


def test_practice_26_the_mention_list_offers_only_available_agents_that_are_not_off():
    conn = _conn()
    for p in ('gemini', 'codex', 'claude'):
        conn.execute("INSERT INTO hb_peer_workers VALUES(?,'running','',?)", (hb_online.PROVIDERS[p], time.time()))
    hb_online.set_mode(conn, 'gemini', 'auto', 'jd')
    hb_online.set_mode(conn, 'codex', 'auto', 'jd')
    hb_online.probe(conn, 'gemini', checker=lambda: (True, 'ok'))
    hb_online.probe(conn, 'codex', checker=lambda: (False, 'usage limit reached'))
    hb_online.probe(conn, 'claude', checker=lambda: (True, 'ok'))
    keys = [i['key'] for i in hb_online.mention_items(conn)]
    assert keys == ['gemini']                                               # codex unavailable, claude switched Off
    assert hb_online.mention_items(conn)[0]['label'] == 'Gemini (Flash)'


def test_practice_26_automatic_calls_respect_the_switch_and_the_check():
    conn = _conn()
    conn.execute("INSERT INTO hb_peer_workers VALUES('gemini-advisor','running','',?)", (time.time(),))
    assert hb_online.may_dispatch(conn, 'gemini-advisor', 'apex')[0] is False                 # Off by default
    hb_online.set_mode(conn, 'gemini', 'auto', 'jd')
    hb_online.probe(conn, 'gemini', checker=lambda: (False, 'down'))
    allowed, why = hb_online.may_dispatch(conn, 'gemini-advisor', 'apex')
    assert not allowed and 'down' in why                                    # APEX is told before it tries
    hb_online.probe(conn, 'gemini', checker=lambda: (True, 'ok'))
    assert hb_online.may_dispatch(conn, 'gemini-advisor', 'apex')[0] is True
    assert hb_online.may_dispatch(conn, 'gemini-advisor', 'user')[0] is True                  # JD's own @mention always goes


def test_practice_26_the_models_card_lists_online_agents_with_their_switch():
    conn = _conn()
    hb_online.set_mode(conn, 'gemini', 'auto', 'jd')
    hb_online.probe(conn, 'gemini', checker=lambda: (True, 'ok'))
    rows = {r['model']: r for r in hb_online.catalogue(conn)}
    assert rows['gemini']['where'] == 'online' and rows['gemini']['loaded'] and rows['gemini']['mode'] == 'auto'
    assert rows['codex']['mode'] == 'off'
