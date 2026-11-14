"""Bounded Studio ALM access for APEX: read a step, record its own pytest runs."""
from __future__ import annotations

import json
import re

MAX_ALM_OUTPUT = 6000
_STEP_ID = re.compile(r"S-[0-9A-F]{10}")
_CASE_ID = re.compile(r"C-[0-9A-F]{10}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _assigned(step: dict) -> bool:
    return "apex" in {str(step.get("owner") or "").lower(), str(step.get("owner_route") or "").lower()}


def read_step(step_id: object) -> dict:
    from core.knowledge import projects
    if not isinstance(step_id, str) or not _STEP_ID.fullmatch(step_id):
        raise ValueError("step_id must look like S- followed by 10 uppercase hex characters")
    step = projects.get_step(step_id)
    if not step:
        return {"status": "not_found", "step_id": step_id}
    if not _assigned(step):
        return {"status": "not_assigned", "step_id": step_id,
                "detail": "This step is not assigned to APEX; its content is not available."}
    result = {
        "status": "found", "step_id": step_id, "project_id": step.get("project_id"),
        "title": step.get("title"), "step_status": step.get("status"),
        "owner": step.get("owner"),
        # Numbered items keep a small model on every part of a multi-sentence step.
        "checklist": [f"{index}. {sentence}" for index, sentence in enumerate(
            _SENTENCE.split(str(step.get("description") or "")[:2500].strip()), 1) if sentence],
        "checklist_note": "Do every item, using the exact paths and words it names; report each result.",
        "test_cases": [{key: case.get(key) for key in ("case_id", "title", "status")}
                       for case in step.get("test_cases", [])[:15]],
        "earlier_runs_note": ("history from previous turns, not results of this turn; "
                              "a retest needs a new run_tests call"),
        "earlier_runs": [{key: run.get(key) for key in ("run_id", "case_id", "status", "exit_code")}
                         for run in step.get("test_runs", [])[:8]],
    }
    while len(json.dumps(result).encode()) > MAX_ALM_OUTPUT and result["checklist"]:
        result["checklist"].pop()
        result["checklist_truncated"] = True
    return result


def _apex_case(case_id: object) -> dict:
    from core.knowledge import projects
    if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
        raise ValueError("case_id must look like C- followed by 10 uppercase hex characters")
    case = projects.get_test_case(case_id)
    step = projects.get_step(case["step_id"]) if case and case.get("step_id") else None
    if not case or not step or not _assigned(step):
        raise PermissionError("case_id is not a test case on an ALM step assigned to APEX")
    return case


def run_recorded_tests(args: dict, runner, validate=None) -> dict:
    """Run pytest via ``runner`` and record the real outcome as an ALM test run."""
    from core.knowledge import test_runs
    from core.apex_test_runner import NOT_RUN
    if validate is None:
        from core.apex_test_runner import validate_test_args as validate
    try:
        case = _apex_case(args.get("case_id"))
    except (ValueError, PermissionError) as exc:
        raise type(exc)(f"{exc}{NOT_RUN}") from None
    test_args = {key: value for key, value in args.items() if key != "case_id"}
    note = None
    keyword = test_args.get("keyword")
    title = str(case.get("title") or "").strip()
    if isinstance(keyword,str) and _CASE_ID.fullmatch(keyword.strip()):
        if keyword.strip()!=case['case_id']:
            raise ValueError(f"keyword is another ALM case ID, not a pytest test name. Use case_id for the assigned case and omit keyword.{NOT_RUN}")
        test_args.pop('keyword')
        note=f"keyword {keyword!r} was dropped: case_id already selects this ALM record. All requested test files ran; use keyword only for an actual pytest name."
    if isinstance(keyword, str) and len(keyword.strip()) >= 3 and keyword.strip().casefold() == title.casefold():
        raise ValueError(f"keyword {keyword!r} is the title of case {case['case_id']}, not a test name; "
                         "case_id already selects the case. Put the test function name copied from your "
                         f"grep_repo receipt in keyword, or omit keyword to run the whole file.{NOT_RUN}")
    if (isinstance(keyword, str) and 0 < len(keyword.strip()) < 3
            and title.upper().startswith(keyword.strip().upper() + ":")):
        # The case letter duplicates case_id; dropping it saves a round the 8K window cannot spare.
        test_args.pop("keyword")
        note = (f"keyword {keyword!r} was dropped: it is the letter of case {case['case_id']}, which "
                "case_id already selects, so the whole file ran for that case. Next time omit keyword.")
    validate(test_args)
    command = "pytest " + " ".join(test_args.get("tests") or [])
    if test_args.get("keyword"):
        command += f" -k {test_args['keyword']!r}"
    run_id = test_runs.start_run("apex:pytest", command=command, triggered_by="apex",
                                 project_id=case["project_id"], step_id=case["step_id"],
                                 case_id=case["case_id"])
    if not run_id:
        raise RuntimeError("ALM test run could not be recorded; no tests started")
    try:
        result = runner(test_args)
    except BaseException as exc:
        test_runs.abort_run(run_id, f"runner error: {exc}"[:500])
        raise
    status = {"passed": test_runs.STATUS_PASS, "failed": test_runs.STATUS_FAIL}.get(
        result.get("status"), test_runs.STATUS_ABORTED)
    tail = f"{result.get('summary') or result.get('detail') or ''}\n{result.get('output_tail') or ''}"
    if not test_runs.finish_run(run_id, status=status, exit_code=result.get("exit_code"),
                                stdout_tail=tail.strip()):
        raise RuntimeError(f"ALM test run {run_id} started but its result could not be saved")
    # Lead with the verdict and run handles so archived 600-character excerpts keep them.
    return {"verdict": result.get("verdict"), "alm_run_id": run_id, "alm_run_status": status,
            "alm_case_id": case["case_id"], **({"note": note} if note else {}), **result}
