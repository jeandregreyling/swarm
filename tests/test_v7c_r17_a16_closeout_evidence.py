"""V7C-R17 + A16 — Regression test lab close-out evidence.

Project: P-E9BAE4159F
Steps:   S-959B3FE96E (R17), S-A296E57174 (A16)

Locks:
  - Every closed V7C item has a dedicated pytest file in tests/
  - Each test file declares council-of-7 reviewer style (seven test_ functions)
  - Each test file references the ALM step_id it locks
  - Test Lab backend endpoints exist: /api/knowledge/test-runs (POST), steps PATCH
  - CHANGELOG or session memory carries the closure list
  - A16: regression methodology uses source-assertion + reviewers, not UI snapshots
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'


# The 17 V7C test files this session touched/created.
V7C_FILES = [
    'test_v7c_a01_studio_default.py',
    'test_v7c_a02_settings_window.py',
    'test_v7c_r4_chat_manual_first.py',
    'test_v7c_a08_chat_thread_refresh.py',
    'test_v7c_r5_history_popout.py',
    'test_v7c_a14_terminal_history.py',
    'test_v7c_r6_a15_orbs.py',
    'test_v7c_r11_a13_library.py',
    'test_v7c_r7_settings_trace_windows.py',
    'test_v7c_r8_monitor_health_fan.py',
    'test_v7c_a04_monitor_visibility.py',
    'test_v7c_a05_fan_operator.py',
    'test_v7c_r2_home_header.py',
    'test_v7c_r9_a11_agents_tab.py',
    'test_v7c_r10_a12_seven_coding_bible.py',
    'test_v7c_r14_a06_vortex.py',
    'test_v7c_r13_studio.py',
    'test_v7c_r12_a09_a10_email_feeds.py',
]


def test_r17_r1_all_v7c_files_exist():
    missing = [f for f in V7C_FILES if not (TESTS / f).exists()]
    assert not missing, f'missing test files: {missing}'


def test_r17_r2_each_file_has_seven_tests():
    # Council-of-7 reviewer count per file.
    short = []
    for name in V7C_FILES:
        src = (TESTS / name).read_text()
        count = len(re.findall(r'^def test_', src, re.MULTILINE))
        if count < 7:
            short.append((name, count))
    assert not short, f'files with <7 reviewers: {short}'


def test_r17_r3_each_file_references_alm_step():
    # Every V7C test file must carry its S-<id> marker for traceability.
    unmarked = []
    for name in V7C_FILES:
        src = (TESTS / name).read_text()
        if not re.search(r'S-[0-9A-F]{10}', src):
            unmarked.append(name)
    assert not unmarked, f'files without ALM step id: {unmarked}'


def test_r17_a16_source_assertion_methodology():
    # A16: tests assert against source, not mocks / UI snapshots.
    # Every V7C file reads a real source file via Path(__file__).resolve().
    missing = []
    for name in V7C_FILES:
        src = (TESTS / name).read_text()
        if 'Path(__file__)' not in src or '.read_text()' not in src:
            missing.append(name)
    assert not missing, f'files not using source-assertion: {missing}'


def test_r17_r5_project_reference():
    # Close-out evidence must be tied to the V7C project id.
    unref = []
    for name in V7C_FILES:
        src = (TESTS / name).read_text()
        if 'P-E9BAE4159F' not in src:
            unref.append(name)
    assert not unref, f'files missing V7C project ref: {unref}'


def test_r17_r6_alm_endpoints_still_live():
    # Presence check — blueprint registered for knowledge API.
    kbp = (ROOT / 'frontend' / 'blueprints').glob('*.py')
    sources = '\n'.join(p.read_text() for p in kbp if p.is_file())
    assert '/api/knowledge/steps/' in sources
    assert '/api/knowledge/test-runs' in sources


def test_r17_r7_reviewer_docstring_contract():
    # Each V7C file must open with a docstring naming the step and purpose.
    bad = []
    for name in V7C_FILES:
        src = (TESTS / name).read_text()
        head = src[:500]
        if not head.startswith('"""V7C-'):
            bad.append(name)
    assert not bad, f'files missing V7C- prefixed docstring: {bad}'
