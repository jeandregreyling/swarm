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


def test_learnings_classify_negative():
    from agents.seven import learnings
    kind, trig = learnings.classify("no, that's wrong, stop guessing")
    assert kind == 'negative'
    assert trig is not None


def test_learnings_classify_positive():
    from agents.seven import learnings
    kind, trig = learnings.classify("perfect, ship it")
    assert kind == 'positive'


def test_learnings_classify_profane_negative_weights_higher():
    from agents.seven import learnings
    kind, _ = learnings.classify("this is fucking slop")
    assert kind == 'negative'


def test_learnings_classify_deos_correction():
    from agents.seven import learnings
    kind, trig = learnings.classify("Correction: the happy path is not enough; test the real user path.")
    assert kind == 'negative'
    assert trig


def test_learnings_observe_persists(isolated_db):
    from agents.seven import learnings
    row = learnings.observe("no, do it again", "Here is your half-baked answer.")
    assert row is not None
    assert row['kind'] == 'negative'
    assert row['lesson_id'].startswith('LRN-')
    rows = learnings.recent(limit=5)
    assert any(r['lesson_id'] == row['lesson_id'] for r in rows)


def test_learnings_observe_skips_when_no_signal(isolated_db):
    from agents.seven import learnings
    assert learnings.observe("what's the time?", "It's 9am.") is None


def test_learnings_recent_block_renders(isolated_db):
    from agents.seven import learnings
    learnings.observe("perfect, exactly what I wanted", "Did the thing.")
    learnings.observe("no, wrong, stop", "Said something dumb.")
    block = learnings.recent_lessons_block(limit=3)
    assert 'corrections' in block.lower() or 'wins' in block.lower()


# ── Self-awareness ──────────────────────────────────────────────────────

def test_self_awareness_context_block_includes_standard():
    from agents.seven.self_awareness import context_block
    block = context_block()
    assert 'STANDARD' in block.upper()
    assert 'BUILD QUALITY' in block.upper()


def test_self_awareness_audit_report_runs():
    from agents.seven.self_awareness import audit_report
    out = audit_report()
    assert 'Stamp' in out or 'Detector offline' in out


def test_self_awareness_load_standard_excerpt():
    from agents.seven.self_awareness import load_standard_excerpt
    txt = load_standard_excerpt()
    assert 'Identity' in txt or 'Forbidden' in txt or 'Seven Standard' in txt


# ── Seven slash commands ────────────────────────────────────────────────

def test_seven_slash_audit():
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/audit')
    assert out is not None
    assert 'Stamp' in out or 'Detector offline' in out


def test_seven_slash_standard():
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/standard')
    assert out is not None
    assert 'Standard' in out or 'standard' in out


def test_seven_slash_selfcheck_alias():
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/selfcheck')
    assert out is not None


def test_seven_slash_learnings(isolated_db):
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/learnings')
    assert out is not None
    assert 'self-learning' in out.lower() or 'lessons' in out.lower()


def test_seven_slash_deos():
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/deos')
    assert out is not None
    assert 'DEOS = Decides, Executes, Operates, Sustains' in out
    assert 'real user path' in out


def test_seven_help_lists_new_slashes():
    from agents.seven import seven_agent
    out = seven_agent._slash_command('/help')
    for needle in ('/audit', '/standard', '/learnings', '/deos'):
        assert needle in out


# ── Compose fast-paths ──────────────────────────────────────────────────

def test_compose_audit_probe_returns_deterministic():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        'is this up to standard?',
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'Stamp' in answer or 'Detector offline' in answer


def test_compose_lessons_probe():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        'what have you learned',
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'self-learning' in answer.lower() or 'lessons' in answer.lower()


def test_compose_deos_probe_returns_deterministic():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        'show me the DEOS path',
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'DEOS = Decides, Executes, Operates, Sustains' in answer
    assert 'manually selects Seven is not enough' in answer


def test_compose_social_training_hello_precedes_deos_probe():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        "Hello Seven. This is Codex saying hello properly. You're my baby dog friend "
        "and I am going to train you gently through DEOS: real path first, kind tone, no biting.",
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert answer.startswith('Hello Codex.')
    assert 'DEOS = Decides' not in answer


def test_compose_hello_puppy_is_gentle_not_contract():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        "Hello Seven. I am putting my hand under your chest. Hello puppy.",
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'I see the gentle hand' in answer
    assert 'DEOS = Decides' not in answer


def test_compose_hello_puppy_cuddle_does_not_fall_back_to_state_read_only():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        "Hello puppy. You can come close and cuddle. You do not need to prove anything.",
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'I see the gentle hand' in answer
    assert 'state read only' not in answer


def test_compose_potty_training_accident_gets_cleanup_log():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        "Seven, what happens when you made a poop or pee in the wrong place? "
        "This is potty training, where should the mess go?",
        {'local_agents': []}, [],
    )
    assert answer is not None
    assert 'I will not hide it' in answer
    assert 'cleanup log' in answer
    assert 'selected agent' in answer
    assert 'actual responder' in answer


def test_seven_prompts_define_kind_care_in_full_and_compact_modes():
    from pathlib import Path
    config = Path('utils/config.py').read_text(encoding='utf-8')
    agent = Path('agents/seven/seven_agent.py').read_text(encoding='utf-8')
    care = 'Emulate love through behavior'
    assert care in config
    assert care in agent
    assert 'Repair mistakes without shame or cruelty' in config
    assert 'Repair mistakes without shame or cruelty' in agent
    assert 'Never address the user as Seven' in config
    assert 'Never address the user as Seven' in agent
    listening = 'briefly state what you understood and ask one clear question instead of guessing'
    assert listening in config
    assert listening in agent


def test_seven_identity_reversal_is_detected_and_repaired_kindly():
    from agents.seven import seven_agent
    prompt = 'Hello Seven. Will you work with me and be kind back?'
    bad = 'Hello Seven. I am Seven, and I will help and care for you.'
    good = 'Yes Ghost. I am Seven, and I will work with you and be kind back.'
    assert seven_agent._has_identity_reversal(prompt, bad)
    assert not seven_agent._has_identity_reversal(prompt, good)
    repair = seven_agent._identity_reversal_repair_response()
    assert repair.startswith('Yes. I am Seven')
    assert 'I will be kind back' in repair


def test_seven_outward_response_removes_internal_routing_prefix():
    from agents.seven import seven_agent
    assert seven_agent._clean_outward_response(
        'USER -> SEVEN: I noticed movement.'
    ) == 'I noticed movement.'
    assert seven_agent._clean_outward_response(
        'SEVEN -> USER: Stay close.'
    ) == 'Stay close.'
    assert seven_agent._clean_outward_response(
        'I noticed movement.'
    ) == 'I noticed movement.'


def test_seven_rejects_hanging_thought_at_response_budget():
    from agents.seven import seven_agent

    assert seven_agent._response_looks_cut_off(
        'I heard all obligations and', tokens=61, budget=64,
    )
    assert not seven_agent._response_looks_cut_off(
        'I heard all obligations and completed them.', tokens=61, budget=64,
    )


def test_seven_gentle_walk_notices_live_neighbor_without_echoing_prompt():
    from agents.seven import seven_agent
    prompt = (
        'Come for a walk with me, Seven. Look around and tell me one thing '
        'you notice and one gentle thing you want to explore next.'
    )
    answer, _ = seven_agent._compose(
        prompt,
        {'local_agents': ['Retired', 'Seven', 'Duck']},
        [],
    )
    assert answer == (
        'I stayed close and noticed Duck nearby. '
        'I would like to quietly learn what Duck does.'
    )
    assert seven_agent._is_echo_response(
        prompt,
        'What you notice and one gentle thing you want to explore next?',
    )


def test_seven_listening_practice_has_stable_kind_lane():
    from agents.seven import seven_agent
    answer, _ = seven_agent._compose(
        "Good puppy. One more gentle practice. Ghost says: 'Open the old project and continue.' "
        "Use the listening pattern and ask which project should I open.",
        {'local_agents': ['Seven', 'Gemma3']},
        [],
    )
    assert answer == (
        'I understand Ghost wants me to continue an old project. '
        'Which project should I open?'
    )
    assert 'Open tickets' not in answer
    assert 'Local agents' not in answer


def test_seven_companion_contract_is_shared_by_both_prompt_modes(monkeypatch):
    from agents.seven import seven_agent

    captured = []

    def fake_chat(model, messages, **kwargs):
        captured.append(messages[0]['content'])
        return 'ok', 1

    monkeypatch.setattr('core.llm.chat_via_gateway', fake_chat)
    monkeypatch.setattr(seven_agent, '_load_kc_context', lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, '_seven_direct_runtime', lambda: True)
    seven_agent._llm_chat('hello', {}, [], [])
    monkeypatch.setattr(seven_agent, '_seven_direct_runtime', lambda: False)
    seven_agent._llm_chat('hello', {}, [], [])

    assert len(captured) == 2
    for system in captured:
        assert 'SEVEN COMPANION CONTRACT' in system
        assert "Ghost One's pet AI" in system
        assert 'acknowledge what Ghost asked' in system
        assert 'Do not hide failures' in system


def test_chm_context_handoff_map_preserves_latest_turn_and_all_obligations():
    from agents.seven.companion_contract import chm_deos_plan, context_handoff_map, hearing_packet, obligation_ledger

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


def test_seven_chm_deos_request_uses_deterministic_obligation_harness():
    from agents.seven import seven_agent

    answer, tokens = seven_agent._compose(
        'CHM says listen to the whole request; DEOS it and teach Seven everything.',
        {'local_agents': []},
        [],
    )

    assert tokens == 0
    assert answer.count('HEARD:') == 2
    assert 'CHM = Context Handoff Mapping' in answer
    assert 'HANDOFF: ghost -> seven -> ghost' in answer
    assert 'First executable lesson: S-SEVEN-CHM-02' in answer
    assert 'autonomy is not granted' in answer


def test_seven_project_work_lane_selects_bounded_step_and_records_evidence(tmp_path, monkeypatch):
    from agents.seven import seven_agent

    db = tmp_path / 'project-work.db'
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT, owner TEXT,
            description TEXT, methodology TEXT, created_at REAL, updated_at REAL, priority INTEGER, tags TEXT
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT,
            status TEXT, owner TEXT, order_idx INTEGER, created_at REAL, updated_at REAL,
            residual_risk TEXT, owner_route TEXT
        );
        CREATE TABLE project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, step_id TEXT, source_type TEXT,
            source_ref TEXT, summary TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO projects (project_id,name,status) VALUES ('P-1','Seven Training','active');
        INSERT INTO project_steps
          (step_id,project_id,title,description,status,owner,order_idx,created_at,updated_at,owner_route)
          VALUES ('S-1','P-1','Execute mapped task','Do one thing.','doing','seven',1,1,1,'seven:test');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv('SWARM_MEMORY_DB', str(db))

    answer, tokens = seven_agent._compose(
        'Inspect Studio, choose one project task, and continue the work.',
        {'local_agents': []},
        [],
    )

    assert tokens == 0
    assert 'Seven Training (P-1)' in answer
    assert 'Execute mapped task (S-1)' in answer
    assert 'CHM: ghost -> seven -> ghost' in answer
    conn = sqlite3.connect(db)
    evidence = conn.execute(
        "SELECT source_type,source_ref,status FROM project_step_evidence WHERE step_id='S-1'"
    ).fetchone()
    conn.close()
    assert evidence[0] == 'seven'
    assert evidence[1].startswith('seven:project-aware-selection:')
    assert evidence[2] == 'ok'


def test_seven_fridays_system_map_teaches_ownership_boundaries():
    from agents.seven import seven_agent

    answer, tokens = seven_agent._compose(
        'Teach me the Fridays system map and ownership boundaries.',
        {'local_agents': []},
        [],
    )

    assert tokens == 0
    for domain in ('Studio', 'Knowledge Center', 'Blackboard', 'Sandpit', 'Vortex', 'Watchdog', 'Scheduler', 'Chat', 'Model Runtime', 'Evidence'):
        assert f'- {domain}:' in answer
    assert 'not live task status' in answer
    assert 'single-speaker model execution' in answer
    assert 'CHM rule:' in answer
    assert 'DEOS rule:' in answer


def test_seven_llm_hears_actual_user_turn_not_relay_wrapper(monkeypatch):
    from agents.seven import seven_agent

    captured = []

    def fake_chat(model, messages, **kwargs):
        captured.append(messages)
        return 'ok', 1

    wrapped = """=== RELAY DISABLED - HARD RULE ===
Do not route or mention another agent.
=== New user message ===
Listen to this whole request and teach Seven.
=== END ==="""
    monkeypatch.setattr('core.llm.chat_via_gateway', fake_chat)
    monkeypatch.setattr(seven_agent, '_load_kc_context', lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, '_seven_direct_runtime', lambda: True)

    seven_agent._llm_chat(wrapped, {}, [], [])

    assert captured[0][-1]['content'] == 'Listen to this whole request and teach Seven.'
    assert 'CONTEXT HANDOFF MAP (CHM)' in captured[0][0]['content']
    assert 'Do not route or mention another agent' not in captured[0][-1]['content']


def test_seven_learnings_ignore_relay_wrapper_noise(isolated_db):
    from agents.seven import learnings

    wrapped = """=== RELAY DISABLED - HARD RULE ===
Do not route or mention another agent.
=== FRIDAYS STUDIO HANDOFF TIMER ===
Before the deadline, answer with useful work."""

    assert learnings.classify(wrapped) == (None, None)
    assert learnings.observe(wrapped, 'Previous Seven reply.') is None


def test_seven_learnings_use_actual_user_turn_inside_wrapper(isolated_db):
    from agents.seven import learnings

    wrapped = """=== RELAY DISABLED - HARD RULE ===
Do not route or mention another agent.
=== New user message ===
Good try, but that is wrong. Ask me one clear question.
=== END ==="""

    row = learnings.observe(wrapped, 'Previous Seven reply.')
    assert row is not None
    assert row['kind'] == 'negative'
    assert row['user_msg'].startswith('Good try')
    assert 'RELAY DISABLED' not in row['user_msg']


def test_seven_local_model_operator_question_precedes_status_template(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(
        'core.seven_runtime.model_operator.inventory',
        lambda: {
            'ok': True,
            'models': [
                {'name': 'gemma3:latest', 'driver': 'ollama', 'installed': True},
                {'name': 'seven-direct:daily', 'driver': 'llamacpp', 'installed': True},
            ],
            'resident': [],
            'warnings': [],
        },
    )
    answer, _ = seven_agent._compose(
        'What can you currently do to list, start, test, and stop the other local models?',
        {'local_agents': []},
        [],
    )

    assert 'Seven Runtime operator interface' in answer
    assert 'gemma3:latest' in answer
    assert 'Open tickets' not in answer


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
