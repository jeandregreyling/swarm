"""Practice 294 (JD 22 Nov: the BA's spec "just doesn't look right"): it invented ui/status_drawer.py and core/hb_status.py because it was
never shown the real files. Its facts now start with the step's Done-when test and the real files that test references, and HB rejects an
invented path in the scope or design as well as in the plan."""
from pathlib import Path

from core import hb_homework as hw

ROOT = Path(__file__).resolve().parents[1]


def test_the_ba_is_shown_the_files_the_test_names():
    files = hw.test_files('Done when: tests/test_practice_287_status_tokens_scroll.py passes')
    assert 'tests/test_practice_287_status_tokens_scroll.py' in files
    assert 'frontend/static/js/hb-live.js' in files and 'frontend/static/js/views/chat.js' in files


def test_invented_paths_in_scope_or_design_are_rejected():
    card = {'scope_in': ['ui/status_drawer.py'], 'design': ['core/hb_status.py renders the drawer', 'frontend/static/js/hb-live.js renderStatus']}
    probs = hw.plan_problems([], {'frontend/static/js/hb-live.js'}, {'done_when': []}, card)
    assert any('scope names ui/status_drawer.py' in p for p in probs) and any('design names core/hb_status.py' in p for p in probs)
    assert not any('hb-live.js' in p for p in probs)
