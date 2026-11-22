"""Practice 292 (JD 22 Nov: "Thinking round 1 through 10 without any results it quite a waste of time ... fucking nothing happening mate"):
APEX spent rounds 4-10 flipping an accepted step doing/blocked and repeating a broken run_tests. Three rounds without progress end the
tool rounds; an accepted step's status cannot be changed by APEX."""
from pathlib import Path

from core.apex_tools import STALL_ROUNDS, STALL_NOTICE, made_progress

ROOT = Path(__file__).resolve().parents[1]


def test_status_flips_plans_failures_and_repeat_reads_are_not_progress():
    seen = set()
    read = {'tool': 'read_file', 'status': 'succeeded', 'arguments': {'path': 'core/x.py'}}
    assert made_progress(read, seen) and not made_progress(dict(read), seen)
    for r in ({'tool': 'studio_status', 'status': 'succeeded', 'arguments': {'status': 'doing'}},
              {'tool': 'task_plan', 'status': 'succeeded', 'arguments': {}}, {'tool': 'run_tests', 'status': '', 'arguments': {}}):
        assert not made_progress(r, seen), r
    assert made_progress({'tool': 'propose_patch', 'status': 'succeeded', 'arguments': {}}, seen)
    assert made_progress({'tool': 'run_tests', 'status': 'succeeded', 'arguments': {}}, seen)


def test_the_turn_stops_after_three_idle_rounds_and_status_of_a_done_step_is_locked():
    src = (ROOT / 'core/apex_tools.py').read_text()
    assert STALL_ROUNDS == 3 and 'no further tool runs this turn' in STALL_NOTICE
    assert 'if stall_rounds >= STALL_ROUNDS and receipts:' in src
    assert 'This step is already done (accepted)' in (ROOT / 'core/hb_tasks.py').read_text()
