"""Practice 192: the Ghost reserve keeps 2 GB+ of the GPU for JD's desktop; email goes from sevenpotato9; restarts wait for turns."""
import sqlite3
import time

from core import hb_apex_swap as s
from core import hb_gpu_guard as g
from core import hb_plan_workflow as wf
from core import hb_task_manager as tm

DROPIN = """[Service]
ExecStart=
ExecStart=/x/llama-server -m /m/swift.gguf --device ROCm0 --fit on -fitt 2048 -fitc 16384 --jinja --flash-attn on -b 512 -ub 256 --no-webui
"""


def test_render_floors_the_margin_and_quantizes_the_27b_kv_cache():
    out = s.render(DROPIN, {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None})
    assert '-fitt 3584' in out and '-ctk q8_0' in out and '-ctv q8_0' in out
    higher = s.render(DROPIN.replace('-fitt 2048', '-fitt 4096'), {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None})
    assert '-fitt 4096' in higher
    other = s.render(DROPIN, {'name': 'gpt-oss:20b', 'path': '/m/oss.gguf', 'template': None})
    assert '-ctk q8_0' in other and '-fitt 3584' in other   # Practice 286: every APEX model gets the 8-bit KV cache


def _calls():
    seen = []
    return seen, (lambda: seen.append('reload') or True), (lambda: seen.append('restart') or True), (lambda: True)


def test_three_low_readings_raise_the_margin_when_apex_is_idle(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN.replace('2048', '3584'))
    c, said = sqlite3.connect(':memory:'), []
    seen, reload, restart, answers = _calls()
    for i, free in enumerate((1.2, 1.1, 1.0)):
        out = g.ghost_tick(c, now=1000 + i * 60, free=free, path=p, idle=lambda: True, reload=reload, restart=restart, answers=answers, say=said.append)
    assert '-fitt 4096' in p.read_text() and seen == ['reload', 'restart'] and 'more of the GPU' in said[0]
    assert g.ghost_tick(c, now=1300, free=0.9, path=p, idle=lambda: True, reload=reload, restart=restart, answers=answers, say=said.append) is None


def test_no_change_while_apex_works_or_when_there_is_room(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN)
    c = sqlite3.connect(':memory:')
    for i in range(3):
        assert g.ghost_tick(c, now=1000 + i * 60, free=1.0, path=p, idle=lambda: False, say=lambda m: None) is None
    assert '-fitt 2048' in p.read_text()
    c2 = sqlite3.connect(':memory:')
    for i, free in enumerate((1.0, 2.5, 1.0)):
        assert g.ghost_tick(c2, now=1000 + i * 60, free=free, path=p, idle=lambda: True, say=lambda m: None) is None


def test_at_the_maximum_margin_hb_only_hints_once(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN.replace('2048', str(g.MARGIN_MAX_MIB)))
    c, said = sqlite3.connect(':memory:'), []
    for i in range(5):
        g.ghost_tick(c, now=1000 + i * 60, free=1.0, path=p, idle=lambda: True, say=said.append)
    assert len(said) == 1 and 'Closing a GPU-heavy program' in said[0]


def test_owner_email_goes_through_sevenpotato9(monkeypatch):
    sent = []
    import lib.email.email_handler as eh
    monkeypatch.setattr(eh, 'send_reply', lambda to, subject, body, **kw: sent.append((subject, kw.get('sender_name'))) or True)
    tm._send_owner_email('HB needs you: x', 'body')
    assert sent == [('HB needs you: x', 'Hummingbird')]


def test_restart_waits_for_a_running_turn():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_restart_queue(task_id TEXT PRIMARY KEY, scope TEXT, reason TEXT, at REAL)')
    c.execute("INSERT INTO hb_restart_queue VALUES ('T-1','ui','x',0)")
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    c.execute("INSERT INTO hb_peer_work VALUES (1,'apex','running','turn',0)")
    launched = []
    assert wf.restart_tick(c, now=time.time(), run=launched.append) is None and launched == []
