"""Practice 153 (owner 18 Nov 2026: "HB should be the one orchestrating this by knowing what the question is about and which model to
use"): research questions go to the preferred research model, swapped in while APEX is idle; HB never swaps back by itself; each model
has its own turn time."""
import sqlite3

from core import hb_apex_swap as s

QR = 'What do the SAP notes say about the MCB cap, what does it mean and how is it paid?'
QC = 'Fix the failing test in core/hb_rename.py'


def db():
    return sqlite3.connect(':memory:')


def test_practice_153_research_swaps_to_the_preferred_model(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    calls, said = [], []
    out = s.route_for(db(), QR, said.append, idle=lambda: True, swapper=lambda name, say: (calls.append(name) or (True, f'APEX is now {name}')))
    assert calls == ['swift-qwen3.8-27b'] and 'research question' in said[0] and out == 'APEX is now swift-qwen3.8-27b'


def test_practice_153_no_swap_when_playing_busy_or_other_work(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    swapper = lambda name, say: (_ for _ in ()).throw(AssertionError('no swap'))
    assert s.route_for(db(), QR, print, idle=lambda: True, swapper=swapper) == ''
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    assert s.route_for(db(), QR, print, idle=lambda: False, swapper=swapper) == ''
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    assert s.route_for(db(), QC, print, idle=lambda: True, swapper=swapper) == ''     # never swaps back by itself


def test_practice_153_failed_swap_answers_with_the_loaded_model(monkeypatch):
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    out = s.route_for(db(), QR, print, idle=lambda: True, swapper=lambda name, say: (False, 'did not start.'))
    assert out.endswith('HB answers with gpt-oss:20b.')


def test_practice_153_prefer_and_turn_time(monkeypatch):
    c = db()
    monkeypatch.setattr(s, 'find', lambda m: {'name': m} if m in ('gpt-oss:20b', 'swift-qwen3.8-27b') else None)
    assert 'go to gpt-oss:20b' in s.prefer(c, 'research', 'gpt-oss:20b')
    assert s.prefs(c)['research'] == 'gpt-oss:20b'
    assert 'whatever model' in s.prefer(c, 'research', 'none') and not s.prefs(c)['research']
    monkeypatch.setattr(s, 'playing', lambda: 'swift-qwen3.8-27b')
    assert s.turn_seconds(360) == 600
    monkeypatch.setattr(s, 'playing', lambda: 'gpt-oss:20b')
    assert s.turn_seconds(360) == 360
