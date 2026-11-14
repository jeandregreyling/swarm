import json
import sqlite3
import time

import pytest

from core import hb_commands as hc, hb_tasks, hb_online


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT,'
              ' content TEXT, message_type TEXT, tokens_used INT, created_at TEXT)')
    c.execute('CREATE TABLE hb_peer_workers(principal TEXT, state TEXT, detail TEXT)')
    c.execute('CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT, sender TEXT, delivered_at REAL)')
    c.execute('CREATE TABLE hb_peer_work(request_id INT, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, status TEXT, residual_risk TEXT, updated_at REAL)')
    hb_tasks.ensure_schema(c)
    from core import hb_task_manager
    hb_task_manager.ensure_schema(c)
    yield c
    c.close()


def test_slash_and_legacy_prefix_but_not_paths():
    assert hc.is_hb('/status') and hc.is_hb('  /cancel T-14AEA38BF295') and hc.is_hb('@hb tasks')
    assert not hc.is_hb('/home/jd/file.py') and not hc.is_hb('see /status') and not hc.is_hb('hello')


def test_fixed_grammar():
    assert hc.parse('status') == ('status', [])
    assert hc.parse('') == ('help', [])
    assert hc.parse('cancel t-14aea38bf295') == ('cancel', ['T-14AEA38BF295'])
    assert hc.parse('cancel') is None
    assert hc.parse('online codex on') == ('online', ['codex', 'on'])
    assert hc.parse('online claude on') == ('online', ['claude', 'on'])   # 12 Nov: @claude is a provider
    assert hc.parse('online chatgpt on') is None
    assert hc.parse('dream on 1800') == ('dream', ['on', '1800'])
    assert hc.parse('stop') is None                         # existing Stop path owns it


def test_catalogue_drives_popup_and_help():
    names = [c['name'] for c in hc.catalogue()]
    for n in ('status', 'tasks', 'cancel', 'online', 'approvals', 'yes', 'no', 'stop'):
        assert n in names and '/' + n in hc.HELP
    assert next(c for c in hc.catalogue() if c['name'] == 'cancel')['confirm'] is True


def test_typo_suggestion_waits_for_yes(conn):
    reply = hc.handle(conn, 1, '/queu', 'jd', interpreter=lambda *a: pytest.fail('no model for typos'))
    assert '"/queue"' in reply
    assert 'Queue is empty' in hc.handle(conn, 1, '/yes', 'jd')
    assert 'Nothing is waiting' in hc.handle(conn, 1, '/yes', 'jd')
    hc.handle(conn, 1, '/stauts', 'jd')
    assert hc.handle(conn, 1, '/no', 'jd') == 'OK, not running /status.'


def _task(conn, tid='T-AAAAAAAAAAAA'):
    conn.execute("INSERT INTO hb_tasks(task_id,conversation_id,root_message_id,title,objective,state,created_at,updated_at,version)"
                 " VALUES(?,1,1,'old idea','x','active',0,0,1)", (tid,))
    return tid


def test_cancel_halts_and_asks_then_cancels_everything(conn, monkeypatch):
    tid = _task(conn)
    conn.execute("INSERT INTO peer_messages(id,recipient,sender) VALUES(7,'apex','hummingbird')")
    conn.execute("INSERT INTO hb_peer_work VALUES(7,'apex','queued','waiting',0)")
    conn.execute("INSERT INTO hb_task_requests(task_id,request_id) VALUES(?,7)", (tid,))
    import hashlib
    step = 'S-' + hashlib.sha256(tid.encode()).hexdigest()[:10].upper()
    conn.execute("INSERT INTO project_steps VALUES(?,'todo','',0)", (step,))
    monkeypatch.setattr(hc, '_set_mode', lambda *a, **k: 'off')
    ask = hc.handle(conn, 1, f'/cancel {tid}', 'jd')
    assert 'old idea' in ask and '/yes' in ask
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'active'   # nothing yet
    after = []
    done = hc.handle(conn, 1, '/yes', 'jd', after=after)
    assert 'cancelled' in done and len(after) == 1
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'cancelled'
    assert conn.execute('SELECT state FROM hb_peer_work WHERE request_id=7').fetchone()[0] == 'cancelled'
    assert conn.execute('SELECT status FROM project_steps WHERE step_id=?', (step,)).fetchone()[0] == 'skipped'
    assert 'already cancelled' in hc.cancel_task(conn, tid, 'jd')


def test_no_declines_cancel(conn):
    tid = _task(conn)
    hc.handle(conn, 1, f'/cancel {tid}', 'jd')
    assert 'not running /cancel' in hc.handle(conn, 1, '/no', 'jd')
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'active'


def test_plain_english_only_suggests_and_cancel_still_asks(conn):
    tid = _task(conn)
    reply = hc.handle(conn, 1, '/drop that old idea task please', 'jd', interpreter=lambda body, tasks: f'cancel {tid}')
    assert 'nothing has run' in reply and '/yes' in reply
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'active'


def test_model_cannot_invent_a_task_id(monkeypatch):
    monkeypatch.setattr(hc, '_llama_idle', lambda base=None: True)

    class R:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(hc.urllib.request, 'urlopen', lambda *a, **k: R(json.dumps(
        {'choices': [{'message': {'content': '{"command": "cancel T-AAAAAAAAAAAA"}'}}]}).encode()))
    assert hc.interpret('drop it', [{'task_id': 'T-BBBBBBBBBBBB', 'title': 'x'}]) is None
    assert hc.interpret('drop it', [{'task_id': 'T-AAAAAAAAAAAA', 'title': 'x'}]) == 'cancel T-AAAAAAAAAAAA'


def test_busy_model_is_not_queued(monkeypatch):
    monkeypatch.setattr(hc, '_llama_idle', lambda base=None: False)
    assert hc.interpret('anything at all', []) is None


def test_dream_commands(conn):
    assert 'DREAM off' in hc.handle(conn, 1, '/dream status', 'jd')
    assert 'after 1800s' in hc.handle(conn, 1, '/dream on 1800', 'jd')
    assert hc.handle(conn, 1, '/dream off', 'jd') == 'DREAM off.'


# ------------------------------------------------------------------ online providers
def test_online_needs_authorisation_and_availability(conn):
    s = hb_online.status(conn, 'codex')
    assert not s['authorised'] and not s['usable']
    hc.handle(conn, 1, '/online codex on', 'jd')
    assert hb_online.usable(conn, 'codex')
    conn.execute("INSERT INTO peer_messages(id,recipient,sender) VALUES(1,'codex-instructor','apex')")
    conn.execute("INSERT INTO hb_peer_work VALUES(1,'codex-instructor','failed','You have hit your usage limit',?)", (time.time(),))
    s = hb_online.status(conn, 'codex')
    assert s['authorised'] and not s['available'] and 'usage limit' in s['reason']
    conn.execute("INSERT INTO peer_messages(id,recipient,sender) VALUES(2,'codex-instructor','ghost')")
    conn.execute("INSERT INTO hb_peer_work VALUES(2,'codex-instructor','completed','ok',?)", (time.time() + 1,))
    assert hb_online.usable(conn, 'codex')                 # a later success means it is back


def test_automatic_requests_held_but_owner_requests_pass(conn):
    assert hb_online.may_dispatch(conn, 'codex-instructor', 'hummingbird')[0] is False
    assert 'not authorised' in hb_online.may_dispatch(conn, 'codex-instructor', 'apex')[1]
    assert hb_online.may_dispatch(conn, 'codex-instructor', 'ghost')[0] is True    # owner asked directly
    assert hb_online.may_dispatch(conn, 'apex', 'hummingbird')[0] is True          # local is never gated
    hb_online.authorise(conn, 'gemini', True, 'jd')
    conn.execute("INSERT INTO hb_peer_workers VALUES('gemini-advisor','stopped','')")
    ok, why = hb_online.may_dispatch(conn, 'gemini-advisor', 'apex')
    assert not ok and 'worker is stopped' in why


def test_codex_probe_overrides_older_failure(conn):
    hb_online.authorise(conn, 'codex', True, 'jd')
    conn.execute("INSERT INTO peer_messages(id,recipient,sender) VALUES(1,'codex-instructor','apex')")
    conn.execute("INSERT INTO hb_peer_work VALUES(1,'codex-instructor','failed','usage limit',100)")
    conn.execute('CREATE TABLE hb_provider_probes(provider TEXT PRIMARY KEY, last_probe REAL, observed TEXT, accepted TEXT, outcome TEXT, detail TEXT)')
    conn.execute("INSERT INTO hb_provider_probes VALUES('codex',200,NULL,NULL,'verified_available','')")
    assert hb_online.usable(conn, 'codex')


def test_review_gate_halts_and_asks_owner(conn):
    from core import hb_task_manager as m
    tid = _task(conn)
    task = hb_tasks.get(conn, tid)
    mid = m.ask_owner(conn, task, 'T is ready for review, but Codex is not authorised.', '/online codex on')
    row = conn.execute('SELECT from_agent, content FROM messages WHERE id=?', (mid,)).fetchone()
    assert row[0] == 'hummingbird' and '\nDetails: ' in row[1] and '/online codex on' in row[1]


def test_accept_and_reject_studio_steps_through_hb(conn):
    conn.execute("INSERT INTO project_steps VALUES('S-ABCDEF0123','partial','Built; awaiting owner acceptance',0)")
    conn.execute("ALTER TABLE project_steps ADD COLUMN title TEXT")
    conn.execute("UPDATE project_steps SET title='@HB commands' WHERE step_id='S-ABCDEF0123'")
    tid = _task(conn)
    conn.execute("UPDATE hb_tasks SET step_id='S-ABCDEF0123' WHERE task_id=?", (tid,))
    assert '/accept S-ABCDEF0123' in hc.handle(conn, 1, '/approvals', 'jd')
    assert hc.parse('reject S-ABCDEF0123') is None                  # a reason is required
    assert 'back to todo' in hc.handle(conn, 1, '/reject S-ABCDEF0123 popup missing in full chat', 'jd')
    assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-ABCDEF0123'").fetchone()[0] == 'todo'
    assert 'step S-ABCDEF0123' in hc.handle(conn, 1, '/accept s-abcdef0123', 'jd')
    assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-ABCDEF0123'").fetchone()[0] == 'done'
    assert conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0] == 'completed'
    assert 'already accepted' in hc.handle(conn, 1, '/accept S-ABCDEF0123', 'jd')


def test_done_and_clipboard_commands(conn):
    tid = _task(conn)
    assert hc.parse(f'done {tid}') is None                                  # criteria required
    assert hc.parse(f'done {tid} VRAM matches sysfs; switches work') == ('done', [tid, 'VRAM matches sysfs', 'switches work'])
    reply = hc.handle(conn, 1, f'/done {tid} VRAM matches sysfs; switches unload a model', 'jd')
    assert 'saved' in reply and 'switches unload a model' in reply
    card = hc.handle(conn, 1, f'/clipboard {tid}', 'jd')
    assert card.startswith('DREAM CLIPBOARD for ' + tid) and 'Done when (owner): VRAM matches sysfs' in card
    names = [c['name'] for c in hc.catalogue()]
    assert 'done' in names and 'clipboard' in names
