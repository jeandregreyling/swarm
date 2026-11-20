"""Prepare Practice 195: a focused test run (-k keyword) is evidence, never the step's check - HB auto-approved Seven runtime on one
selected test passing while the step's file still failed 6 tests."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
AL, TM = 'core/apex_alm.py', 'core/hb_task_manager.py'
edits = [
    {'path': AL, 'old': '''    run_id = test_runs.start_run("apex:pytest", command=command, triggered_by="apex",
                                 project_id=case["project_id"], step_id=case["step_id"],
                                 case_id=case["case_id"])''', 'new': '''    # Practice 195 (20 Nov 2026): at 19:07 HB auto-approved "Bug: seven direct runtime" because a run of ONE selected test passed
    # ("1 passed, 33 deselected") and that run was rolled up onto the step's own case - the file still failed 6 tests. A focused run
    # (-k keyword) is evidence while working; it is not linked to the case, so only the whole check can mark the step's case passed.
    focused = bool(test_args.get("keyword"))
    run_id = test_runs.start_run("apex:pytest", command=command, triggered_by="apex",
                                 project_id=case["project_id"], step_id=case["step_id"],
                                 case_id=None if focused else case["case_id"])'''},
    {'path': AL, 'old': '''    return {"verdict": result.get("verdict"), "alm_run_id": run_id, "alm_run_status": status,
            "alm_case_id": case["case_id"], **({"note": note} if note else {}), **result}''', 'new': '''    out = {"verdict": result.get("verdict"), "alm_run_id": run_id, "alm_run_status": status,
           "alm_case_id": case["case_id"], **({"note": note} if note else {}), **result}
    if focused:                                        # Practice 195: never counts as the step's check
        out["alm_run_status"] = "focused"
        out["note"] = ((out.get("note") + " ") if out.get("note") else "") + (
            f"This run used keyword {test_args['keyword']!r}, so it checked only part of the step; it does not count as the step's "
            "check. Run the step's whole check (no keyword) before saying the step is done.")
    return out'''},
    {'path': 'tests/test_apex_alm.py', 'old': '''        {"tests": ["tests/test_x.py"], "keyword": "truncated", "case_id": alm["case"]},
        passing, validate=accept)''', 'new': '''        {"tests": ["tests/test_x.py"], "case_id": alm["case"]},     # Practice 195: a -k run is focused, not the case's check
        passing, validate=accept)'''},
    {'path': 'tests/test_apex_alm.py', 'old': '''    assert "2 passed" in run["stdout_tail"] and "-k 'truncated'" in run["command"]''',
     'new': '''    assert "2 passed" in run["stdout_tail"] and "-k" not in run["command"]'''},
    {'path': TM, 'old': '''        passed=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass'",(task['task_id'],)).fetchone()[0]''',
     'new': '''        passed=conn.execute("SELECT MAX(created_at) FROM hb_task_events WHERE task_id=? AND kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass' "
                            "AND COALESCE(json_extract(payload,'$.verdict'),'') NOT LIKE '%deselected%'",(task['task_id'],)).fetchone()[0]   # Practice 195'''},
]

test = r'''"""Practice 195: a focused test run (-k) never counts as the step's check."""
from core import apex_alm


def _setup(monkeypatch):
    starts = []
    from core.knowledge import test_runs
    monkeypatch.setattr(apex_alm, '_apex_case', lambda case_id: {'case_id': 'C-1', 'project_id': 'P', 'step_id': 'S-1', 'title': 'Guarded checks'})
    monkeypatch.setattr(test_runs, 'start_run', lambda *a, **kw: starts.append(kw.get('case_id')) or 'R-1')
    monkeypatch.setattr(test_runs, 'finish_run', lambda *a, **kw: True)
    return starts


def test_focused_run_is_not_the_steps_check(monkeypatch):
    starts = _setup(monkeypatch)
    out = apex_alm.run_recorded_tests({'tests': ['tests/test_x.py'], 'keyword': 'test_one'},
                                      lambda a: {'status': 'passed', 'verdict': 'PASS: 1 passed, 33 deselected', 'exit_code': 0},
                                      validate=lambda a: a)
    assert starts == [None] and out['alm_run_status'] == 'focused' and "does not count as the step's check" in out['note']


def test_whole_check_still_rolls_up(monkeypatch):
    starts = _setup(monkeypatch)
    out = apex_alm.run_recorded_tests({'tests': ['tests/test_x.py']},
                                      lambda a: {'status': 'passed', 'verdict': 'PASS: 34 passed', 'exit_code': 0}, validate=lambda a: a)
    assert starts == ['C-1'] and out['alm_run_status'] == 'pass'


def test_ready_ignores_deselected_passes():
    src = open('core/hb_task_manager.py').read()
    assert "NOT LIKE '%deselected%'" in src
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("Found 20 Nov: at 19:07 (Auto on) HB auto-approved 'Bug: seven direct runtime' - APEX ran ONE selected test "
                            "(\"1 passed, 33 deselected\"), core/apex_alm rolled that run onto the step's own case, the task manager saw the case "
                            "passed after the last change and accepted the step; the file still fails 6 tests and APEX changed nothing. "
                            "apex_alm.run_recorded_tests: a focused run (-k) is not linked to the case and reports alm_run_status 'focused' with "
                            "a note to run the whole check; hb_task_manager's ready check ignores passes whose verdict says 'deselected'."),
                 edits=edits, new_files={'tests/test_practice_195_focused_runs.py': test},
                 test={'tests': ['tests/test_practice_195_focused_runs.py', 'tests/test_apex_alm.py', 'tests/test_hb_task_manager.py',
                                 'tests/test_practice_168_placeholder_case.py'], 'keyword': ''}, run=run)
print(out['verified'])
