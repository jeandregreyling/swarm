"""Practice 160 (owner 18 Nov 2026: "shouldn't HB check and review questions before automatically assigning an agent unless I manually pick
one"): JD's pick (@model, a model switched On) wins; a model switched Off is never swapped in; otherwise HB reviews the question and says what
it decided before APEX starts; /apex model reloads a playing model whose settings changed."""
import sqlite3

from core import hb_apex_swap as s

QR = 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'
QC = 'Fix the failing test in core/hb_rename.py'
ROWS = [{'name': 'gpt-oss:20b', 'path': '/b/g', 'template': None, 'size_gb': 13.8, 'fits': True},
        {'name': 'swift-qwen3.8-27b', 'path': '/m/s', 'template': None, 'size_gb': 12.1, 'fits': True}]
NONE = {'matches': ['SAP Note 3606625: [document_id 1] 3606625 - Documentation for overruling wage types | x']}


def db():
    return sqlite3.connect(':memory:')


def test_practice_160_manual_pick():
    assert s.manual_pick('@gpt-oss:20b what is /001?', {}, ROWS) == ('gpt-oss:20b', 'you named gpt-oss:20b with @')
    assert s.manual_pick('what is /001?', {'swift-qwen3.8-27b': 'on'}, ROWS)[0] == 'swift-qwen3.8-27b'
    assert s.manual_pick('what is /001?', {}, ROWS) == (None, '')


def test_practice_160_at_model_wins_over_hb(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    monkeypatch.setattr(s, 'candidates', lambda: ROWS)
    calls, said = [], []
    s.route_for(db(), '@gpt-oss:20b ' + QR, said.append, idle=lambda: True, modes={},
                swapper=lambda n, say: (calls.append(n) or (True, 'ok')), search=lambda q: NONE)
    assert calls == ['gpt-oss:20b'] and 'you named gpt-oss:20b with @' in said[0]


def test_practice_160_review_line_then_swap(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    monkeypatch.setattr(s, 'candidates', lambda: ROWS)
    calls, said = [], []
    s.route_for(db(), QR, said.append, idle=lambda: True, modes={}, swapper=lambda n, say: (calls.append(n) or (True, 'ok')),
                search=lambda q: NONE)
    assert calls == ['swift-qwen3.8-27b']
    assert said[0].startswith('HB review: research question (') and 'no strong match' in said[0] and 'swaps APEX first' in said[0]


def test_practice_160_switched_off_is_never_swapped_in(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    monkeypatch.setattr(s, 'candidates', lambda: ROWS)
    calls = []
    s.route_for(db(), QR, print, idle=lambda: True, modes={'swift-qwen3.8-27b': 'off'},
                swapper=lambda n, say: (calls.append(n) or (True, 'ok')), search=lambda q: NONE)
    assert calls == []


def test_practice_160_other_work_is_not_reviewed_or_swapped(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    monkeypatch.setattr(s, 'candidates', lambda: ROWS)
    said = []
    assert s.route_for(db(), QC, said.append, idle=lambda: True, modes={}, search=lambda q: NONE) == '' and said == []


def test_practice_160_same_model_new_settings_reloads(tmp_path, monkeypatch):
    monkeypatch.setattr(s, '_record', lambda name: None)
    p = tmp_path / 'gpu-offload.conf'
    p.write_text('Description=APEX swift-qwen3.8-27b Vulkan llama-server\nExecStart=/x -m /m/s --jinja -b 2048 -ub 1024 --no-webui\n')
    ok, msg = s.swap('swift-qwen3.8-27b', print, p, reload=lambda: True, restart=lambda: True, answers=lambda: True, rows=ROWS)
    assert ok and '-b 512 -ub 256' in p.read_text() and 'already' not in msg
    ok, msg = s.swap('swift-qwen3.8-27b', print, p, reload=lambda: True, restart=lambda: True, answers=lambda: True, rows=ROWS)
    assert 'already' in msg
