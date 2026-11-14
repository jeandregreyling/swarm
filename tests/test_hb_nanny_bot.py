"""Nanny bot: deterministic facts and rules, a small model only for wording, posts only on change."""
import sqlite3

import pytest

from core import hb_nanny_bot as nanny, hb_commands as hc


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,'
              ' message_type TEXT, tokens_used INT, created_at TEXT)')
    c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(2834,'user','apex','hi','chat')")
    yield c
    c.close()


BUSY = {'gpu': {'vram_percent': 93.0}, 'ram': {'total_gb': 64, 'available_gb': 5, 'swap_total_gb': 0},
        'models': [{'model': 'apex-direct:7b', 'kind': 'managed', 'vram_gb': 2.4, 'ram_gb': 0.9, 'placement': 'gpu', 'idle_min': 40},
                   {'model': 'apex-server', 'kind': 'service', 'vram_gb': 10.9, 'ram_gb': 0.3, 'placement': 'gpu', 'idle_min': None}],
        'queue': {'queued': 2, 'oldest_hours': 30, 'running': 0}, 'workers_down': ['gemini-advisor'],
        'spinning': [{'task_id': 'T-AAAAAAAAAAAA', 'reason': '9 checkpoints since the last passing check'}],
        'needs_owner': ['T-BBBBBBBBBBBB'], 'kc_lag': 0, 'db_gb': 2.4}
QUIET = {**BUSY, 'gpu': {'vram_percent': 50.0}, 'ram': {'total_gb': 64, 'available_gb': 40, 'swap_total_gb': 0},
         'queue': {'queued': 0, 'oldest_hours': None, 'running': 0}, 'workers_down': [], 'spinning': [], 'needs_owner': []}


def test_rules_find_what_matters_with_the_fixing_command():
    items = {i['key']: i for i in nanny.findings(BUSY)}
    assert items['idle-gpu:apex-direct:7b']['command'] == '/unload apex-direct:7b'     # managed, idle, GPU full
    assert not any(k.startswith('idle-gpu:apex-server') for k in items)                # the APEX service is never auto-suggested
    assert items['ram-low']['severity'] == 'warn' and items['queue-old']['command'] == '/queue'
    assert 'worker:gemini-advisor' in items and items['spin:T-AAAAAAAAAAAA']['command'] == '/clipboard T-AAAAAAAAAAAA'
    assert items['needs-owner']['command'] == '/approvals'
    assert nanny.findings(QUIET) == []


def test_posts_only_when_findings_change_and_the_model_only_writes_the_note(conn, monkeypatch):
    state = {'f': BUSY}
    monkeypatch.setattr(nanny, 'facts', lambda c, now=None: state['f'])
    calls = []
    mid = nanny.run_once(conn, now=1000, model_call=lambda prompt: calls.append(prompt) or 'GPU memory is nearly full; unload the idle model first.')
    text = conn.execute('SELECT content FROM messages WHERE id=?', (mid,)).fetchone()[0]
    assert text.startswith('Nanny (seven-direct:daily, small model in RAM, summary): GPU memory is nearly full')
    assert 'Checked facts:' in text and '/unload apex-direct:7b' in text
    assert 'do not invent' in calls[0]
    assert nanny.run_once(conn, now=1200, model_call=lambda p: 'x' * 30) is None            # same findings: quiet
    assert nanny.run_once(conn, now=1000 + nanny.REPOST_AFTER + 1, model_call=lambda p: 'Still busy: unload the idle model.')
    state['f'] = QUIET
    assert nanny.run_once(conn, now=9000, model_call=lambda p: pytest.fail('no model for an empty report')) is None


def test_slow_or_missing_model_falls_back_to_hbs_own_note(conn, monkeypatch):
    monkeypatch.setattr(nanny, 'facts', lambda c, now=None: BUSY)
    def broken(prompt):
        raise TimeoutError('model busy')
    mid = nanny.run_once(conn, now=1000, model_call=broken)
    row = conn.execute('SELECT note_source FROM hb_nanny_reports WHERE message_id=?', (mid,)).fetchone()
    assert row[0] == 'hb'


def test_off_by_default_and_commands(conn, monkeypatch):
    assert nanny.settings(conn)['enabled'] is False and nanny.tick(conn, now=10_000) is False
    assert 'every 10 min' in hc.handle(conn, 2834, '/nanny on 10', 'jd')
    assert nanny.settings(conn)['enabled'] is True
    monkeypatch.setattr(nanny, 'facts', lambda c, now=None: BUSY)
    assert '/unload apex-direct:7b' in hc.handle(conn, 2834, '/nanny report', 'jd')
    assert hc.handle(conn, 2834, '/nanny off', 'jd') == 'Nanny off.'
    with pytest.raises(ValueError):
        nanny.configure(conn, True, 1)
    monkeypatch.setattr('core.hb_hardware.model_processes', lambda: [{'model': 'apex-server', 'kind': 'service', 'vram_gb': 10.9, 'ram_gb': 0.3}])
    assert 'system service' in hc.handle(conn, 2834, '/unload apex-server', 'jd')
    assert 'not loaded' in hc.handle(conn, 2834, '/unload gemma3:12b', 'jd')


def test_model_note_with_ids_numbers_or_alarm_words_is_replaced_by_hbs_note():
    items = nanny.findings(BUSY)
    for bad in ('Three machines failed 15 checkpoints.', 'T-AAAAAAAAAAAA has a critical system failure, act now.',
                'Five out of six tasks are failing, look at the models.'):
        note, source = nanny.model_note(items, model_call=lambda prompt, bad=bad: bad)
        assert source == 'hb' and note == nanny.plain_note(items)
    note, source = nanny.model_note(items, model_call=lambda p: 'Some tasks keep failing and GPU memory is tight; look at the stuck tasks first.')
    assert source == nanny.NANNY_MODEL
