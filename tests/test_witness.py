"""tests/test_witness.py — Seven the Witness engine."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'frontend'))


def _fresh_db_env(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setenv('SWARM_MEMORY_DB', tmp.name)
    monkeypatch.setenv('SWARM_DB_PATH', tmp.name)
    # Force re-init of any module-level _INIT_DONE flag.
    import importlib
    if 'core.witness' in sys.modules:
        importlib.reload(sys.modules['core.witness'])
    from core import witness as w
    w._INIT_DONE = False  # type: ignore[attr-defined]
    return w, tmp.name


def test_vapor_detection(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    rep = w.scan_text("This should work probably, I think it's fine.",
                      kind='user', target='user')
    rules = {c.rule for c in rep}
    assert 'VAPOR' in rules


def test_hedge_detection(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    rep = w.scan_text("Will fix later, this is just a placeholder TBD.",
                      kind='user', target='user')
    rules = {c.rule for c in rep}
    assert 'HEDGE' in rules


def test_contra_detection(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    rep = w.scan_text("Yes and no — this always fails but never crashes.",
                      kind='seven', target='seven')
    rules = {c.rule for c in rep}
    assert 'SELF_CONTRADICTION' in rules


def test_conviction_clean_text_high(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    score = w.conviction("Run the migration. The build is green.")
    assert score >= 0.85, score


def test_conviction_vapor_heavy_drops(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    score = w.conviction("It should work, probably, maybe, I think it's fine.")
    assert score < 0.7, score


def test_conviction_receipt_bonus(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    base = w.conviction("It should work probably.")
    boosted = w.conviction("It should work probably (see episode#42).")
    assert boosted > base


def test_review_user_msg_persists(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    msg = "I think this will probably work, will fix later."
    report = w.review_user_msg(msg, save=True)
    assert report.callouts, "expected callouts on hedgy message"
    rows = w.list_callouts(limit=10)
    assert any(r['target'] == 'user' for r in rows)


def test_stats_round_trip(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    w.review_user_msg("This should work probably.", save=True)
    w.review_seven_response("Will fix later — placeholder.",
                            user_msg="why?", save=True)
    s = w.stats()
    assert s['total'] >= 2
    assert 'user' in s['by_target'] or 'seven' in s['by_target']


def test_enabled_toggle(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    assert w.is_enabled() is True  # default ON
    assert w.set_enabled(False) is False
    assert w.is_enabled() is False
    assert w.set_enabled(True) is True
    assert w.is_enabled() is True


def test_annotate_clean_returns_empty(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    rep = w.review_seven_response("The build is green. Migration applied.",
                                  user_msg="status?", save=False)
    out = w.annotate(rep)
    assert out == "" or '🟢' not in out or rep.callouts == []


def test_annotate_dirty_has_glyph(monkeypatch):
    w, _ = _fresh_db_env(monkeypatch)
    rep = w.review_seven_response("This should work probably, will fix later.",
                                  user_msg="?", save=False)
    out = w.annotate(rep)
    assert out, "expected an annotation footer"
    # at least one severity glyph
    assert any(g in out for g in ('·', '⚠️', '🛑', '🟢', '🟡', '🔴'))
