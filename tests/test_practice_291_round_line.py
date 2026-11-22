"""Practice 291 (JD 22 Nov: "'APEX thinking' what the actual fuck does that even mean? thinking without DOING is fucking wild mate"): every
model round is announced with what APEX has actually done this turn - changes, checks and reads - instead of 'thinking'."""
from pathlib import Path

from core.apex_tools import round_line

ROOT = Path(__file__).resolve().parents[1]


def test_the_round_line_counts_what_was_done():
    assert round_line(1, []) == 'APEX round 1: 0 changes, 0 checks, 0 reads so far'
    receipts = [{'tool': 'read_file', 'status': 'succeeded'}, {'tool': 'grep_repo', 'status': 'succeeded'},
                {'tool': 'propose_patch', 'status': 'succeeded'}, {'tool': 'run_tests', 'status': 'succeeded'}, {'tool': 'propose_patch', 'status': 'failed'}]
    assert round_line(4, receipts) == 'APEX round 4: 1 change, 1 check, 2 reads so far'
    assert round_line(5, receipts, final=True).startswith('APEX round 5: writing the answer - 1 change')


def test_thinking_is_gone_from_apexs_turn():
    assert "APEX thinking - round" not in (ROOT / 'core/apex_tools.py').read_text()



def test_change_set_inspection_is_a_read_and_not_repeat_progress():
    from core.apex_tools import made_progress

    receipts = [{'tool': 'change_set', 'status': 'succeeded', 'arguments': {'action': action}}
                for action in ('show', 'status')]
    assert round_line(2, receipts) == 'APEX round 2: 0 changes, 0 checks, 2 reads so far'
    for receipt in receipts:
        seen = set()
        assert made_progress(receipt, seen)
        assert not made_progress(receipt, seen)


def test_change_set_apply_counts_only_recorded_changed_files():
    from core.apex_tools import made_progress

    changed = {'tool': 'change_set', 'status': 'succeeded', 'arguments': {'action': 'apply'},
               'output': '{"state": "applied", "files": ["core/hb_lights.py"]}'}
    unchanged = {**changed, 'output': '{"state": "ALREADY APPLIED", "next": "run_tests"}'}
    assert round_line(3, [changed]).startswith('APEX round 3: 1 change,')
    assert round_line(4, [unchanged]).startswith('APEX round 4: 0 changes,')
    seen = set()
    assert made_progress(unchanged, seen)
    assert not made_progress(unchanged, seen)
