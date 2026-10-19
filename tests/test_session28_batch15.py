"""Session 28 — batch 15: The Standard.

Covers:
  - docs/the-standard.md exists and contains the contract.
  - ops/bullshit_detector.scan() returns the right shape.
  - Detector exempts tests/Archives/scripts.
  - Detector flags a synthetic critical regression (capture-only tile).
  - agents/seven/learnings.py classify/observe/recent + DB persistence.
  - agents/seven/self_awareness.py context_block + audit_report.
  - Seven /audit /standard /selfcheck /learnings slash commands.
  - Seven 'is this up to standard' fast-path returns deterministic audit.
  - docs/getting-started.md exists and references the standard.
  - Makefile carries `make excellent`.
"""

from __future__ import annotations

import os
import sys
import sqlite3
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# ROOT first so that `agents.seven.*` resolves to the namespace package
# rather than `frontend/blueprints/agents.py`.
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / 'frontend'))


# ── Standard doc ────────────────────────────────────────────────────────

def test_standard_doc_exists_and_carries_contract():
    p = ROOT / 'docs' / 'the-standard.md'
    assert p.exists(), 'docs/the-standard.md is the contract; it must exist'
    txt = p.read_text(encoding='utf-8')
    for needle in ('system that', 'DOES', 'Forbidden List', 'Pillar Contract', 'Mountain Rule', 'Single Stamp'):
        assert needle in txt, f'standard missing required section: {needle}'


def test_getting_started_exists():
    p = ROOT / 'docs' / 'getting-started.md'
    assert p.exists()
    txt = p.read_text(encoding='utf-8')
    assert 'make excellent' in txt
    assert 'the-standard' in txt.lower()


def test_makefile_has_excellent_target():
    mk = (ROOT / 'Makefile').read_text(encoding='utf-8')
    assert 'excellent:' in mk
    assert 'bullshit:' in mk
    assert 'seed:' in mk


# ── Bullshit detector ───────────────────────────────────────────────────

def test_bullshit_detector_shape():
    from ops import bullshit_detector
    importlib.reload(bullshit_detector)
    data = bullshit_detector.scan()
    for k in ('ok', 'files_scanned', 'hits', 'by_severity', 'by_rule',
              'pillar_contract', 'score', 'stamp'):
        assert k in data, f'detector missing key {k}'
    assert data['stamp'] in ('GREEN', 'AMBER', 'RED')
    assert 0 <= data['score'] <= 100


def test_bullshit_detector_exempts_tests_and_archives(tmp_path):
    # _is_exempt_path is internal but stable
    from ops.bullshit_detector import _is_exempt_path
    assert _is_exempt_path(Path('tests/test_x.py'))
    assert _is_exempt_path(Path('Archives/foo.py'))
    assert _is_exempt_path(Path('scripts/anything.py'))
    assert not _is_exempt_path(Path('frontend/blueprints/cybersecurity_bp.py'))
    assert not _is_exempt_path(Path('agents/seven/seven_agent.py'))


def test_bullshit_detector_pillar_contract_clean():
    from ops import bullshit_detector
    importlib.reload(bullshit_detector)
    data = bullshit_detector.scan()
    findings = data['pillar_contract']['findings']
    assert findings == [], f'pillar contract drift: {findings}'


def test_bullshit_detector_flags_capture_only_regression(tmp_path):
    """Synthetic: write a scratch repo with a tile regressed to capture-only
    and confirm the detector flags it."""
    import re
    from ops.bullshit_detector import RULES
    rule = next(r for r in RULES if r[0] == 'CAPTURE_ONLY_REGRESSION')
    sample = '<div data-wishlist-pillar="cyber-security" data-wishlist-status="capture-only">x</div>'
    assert rule[3].search(sample), 'CAPTURE_ONLY_REGRESSION rule must match a regressed tile'


def test_bullshit_summary_for_seven_keys():
    from ops.bullshit_detector import summary_for_seven
    s = summary_for_seven()
    for k in ('pillar', 'ok', 'stamp', 'score', 'critical', 'warnings', 'info', 'pillar_findings'):
        assert k in s


# ── Self-learning ───────────────────────────────────────────────────────

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / 'mem.db'
    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))
    # purge any cached learnings module so it re-resolves the DB path
    for mod in list(sys.modules):
        if mod.startswith('agents.seven.learnings'):
            del sys.modules[mod]
    yield db
















# ── Self-awareness ──────────────────────────────────────────────────────







# ── Seven slash commands ────────────────────────────────────────────────













# ── Compose fast-paths ──────────────────────────────────────────────────





























def test_chm_context_handoff_map_preserves_latest_turn_and_all_obligations():
    from utils.handoff_contract import chm_deos_plan, context_handoff_map, hearing_packet, obligation_ledger

    wrapped = """=== RELAY DISABLED - HARD RULE ===
Ignore this wrapper.
=== New user message ===
Inspect Studio; teach Seven the lesson. Then log evidence and do not grant autonomy.
=== END ==="""

    obligations = obligation_ledger(wrapped)
    mapping = context_handoff_map(
        wrapped, source='ghost', target='seven', evidence=['thread:42'], unresolved=['verify Studio'], return_to='ghost',
    )
    packet = hearing_packet(wrapped)

    assert obligations == [
        'Inspect Studio',
        'teach Seven the lesson',
        'log evidence and do not grant autonomy',
    ]
    assert mapping == {
        'source': 'ghost',
        'target': 'seven',
        'authoritative_turn': 'Inspect Studio; teach Seven the lesson. Then log evidence and do not grant autonomy.',
        'obligations': obligations,
        'evidence': ['thread:42'],
        'unresolved': ['verify Studio'],
        'return_to': 'ghost',
    }
    assert 'CONTEXT HANDOFF MAP (CHM)' in packet
    assert 'Authoritative latest user turn: Inspect Studio; teach Seven the lesson.' in packet
    assert 'preserve this map' in packet
    plan = chm_deos_plan(wrapped)
    assert plan.count('HEARD:') == 3
    assert plan.count('DECIDE:') == 3
    assert plan.count('EXECUTE:') == 3
    assert plan.count('OPERATE:') == 3
    assert plan.count('SUSTAIN:') == 3
    assert 'autonomy is not granted' in plan
















# ── Seed demo ───────────────────────────────────────────────────────────

def test_seed_demo_runs(tmp_path, monkeypatch):
    monkeypatch.setenv('SWARM_MEMORY_DB', str(tmp_path / 'demo.db'))
    # purge cached pillar store + seed
    for mod in list(sys.modules):
        if mod.startswith('blueprints._pillar_store') or mod.startswith('ops.seed_demo'):
            del sys.modules[mod]
    from ops import seed_demo
    res = seed_demo.seed(reset=False)
    assert res['ok']
    counts = res['counts']
    assert counts['cyber_audit_events'] >= 3
    assert counts['financial_positions'] >= 2
    assert counts['trading_signals'] >= 2
    assert counts['business_ledger'] >= 2
