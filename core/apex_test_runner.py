"""Bounded pytest runner so APEX can verify approved fixes without a shell."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time

from core.recovery_supervisor import ROOT

MAX_TEST_FILES = 5
TEST_TIMEOUT_S = 150
MAX_TEST_OUTPUT = 6000
_KEYWORD = re.compile(r"[A-Za-z0-9_\[\]\- ]{1,100}")
_LOCK = threading.Lock()
_SUMMARY = re.compile(r"^=*\s*(\d+ (?:passed|failed|error|errors|skipped|deselected).*?)\s*=*$")


def _tracked_tests(root: Path, tests: object) -> list[str]:
    if (not isinstance(tests, list) or not 1 <= len(tests) <= MAX_TEST_FILES
            or len(set(map(str, tests))) != len(tests)):
        raise ValueError(f"tests must list 1-{MAX_TEST_FILES} unique files")
    tracked = set(subprocess.run(
        ["git", "--no-pager", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "tests"],
        capture_output=True, text=True, timeout=10, check=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).stdout.split("\0"))
    for value in tests:
        if isinstance(value, str) and "::" in value:
            path, _, name = value.partition("::")
            raise ValueError(f"tests lists files only, not pytest node IDs; to run one function send "
                             f'{{"tests":["{path}"],"keyword":"{name.split("::")[-1]}"}}')
        if (not isinstance(value, str) or not re.fullmatch(r"tests/(?:[\w-]+/)*test_[\w-]+\.py", value)
                or value not in tracked):
            raise PermissionError(f"Not a tracked or non-ignored tests/test_*.py file: {value!r}")
        path = root / value
        if any(part.is_symlink() for part in (path, *path.parents) if part != root):
            raise PermissionError("Symlinked test paths are unavailable")
        if not path.resolve().is_relative_to(root.resolve()):
            raise PermissionError("Test path escapes the repository")
        if not path.is_file() or path.stat().st_size>1_000_000:
            raise PermissionError("Test must be a bounded regular source file")
    return tests


NOT_RUN = " NOT RUN: no pytest started, so there is no exit code, verdict or ALM run."


def _keyword_error(keyword: object) -> str:
    if isinstance(keyword, str) and ("<" in keyword or ">" in keyword):
        return (f"keyword {keyword!r} is a placeholder, not a test name. Calls in one batch cannot see "
                "each other's receipts: call grep_repo alone, then copy a function name from its receipt.")
    if isinstance(keyword, str) and not keyword.strip("\"' "):
        return (f"keyword {keyword!r} is only quotes; a keyword is plain text such as a test function "
                "name (letters, digits, spaces, _, -, [ or ]).")
    return "keyword must be 1-100 letters, digits, spaces, _, -, [ or ]"


def validate_test_args(args: dict, root: Path = ROOT) -> tuple[list[str], str | None]:
    try:
        return _validate_test_args(args, root)
    except (ValueError, PermissionError) as exc:
        raise type(exc)(f"{exc}{NOT_RUN}") from None


def _validate_test_args(args: dict, root: Path) -> tuple[list[str], str | None]:
    if not isinstance(args, dict) or set(args) - {"tests", "keyword"} or "tests" not in args:
        raise ValueError("run_tests accepts only tests and optional keyword")
    tests = _tracked_tests(root, args["tests"])
    keyword = args.get("keyword")
    if keyword is not None and (not isinstance(keyword, str) or not _KEYWORD.fullmatch(keyword)):
        raise ValueError(_keyword_error(keyword))
    if keyword is not None and len(keyword.strip()) < 3:
        # "case A" is an ALM case letter, not a pytest name; -k A silently matches nearly everything.
        letter = keyword.strip()
        raise ValueError(f"keyword {keyword!r} is not a test name. To run these tests against ALM case "
                         f"{letter}, resend them without keyword and with case_id: the C- id of the "
                         f"test case titled \"{letter}: ...\" in your alm_step_get receipt")
    return tests, keyword


def _verdict(exit_code: int, summary: str | None) -> str:
    # One plain line the model can quote instead of inferring the outcome from raw fields.
    if exit_code == 0:
        return f"PASS: {summary or 'all selected tests passed'}"
    if exit_code == 5:
        return ("NOT A PASS: no tests ran (pytest exit 5, 0 selected); "
                "the file or keyword matched no test")
    if exit_code == 1:
        return f"FAIL: {summary or 'tests failed'}; read output_tail for the failing test names"
    return f"ERROR: pytest exit {exit_code}; {summary or 'tests did not complete'}"


def run_tests(args: dict, root: Path = ROOT) -> dict:
    tests, keyword = validate_test_args(args, root)
    if not _LOCK.acquire(blocking=False):
        return {"verdict": "UNKNOWN: another test run is active; no tests started",
                "status": "busy", "detail": "Another APEX test run is active; no tests started."}
    try:
        with tempfile.TemporaryDirectory(prefix="apex-tests-") as scratch:
            # Isolate state: tests get a scratch HOME/DB, never live credentials or databases.
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": scratch,
                   "LANG": "C.UTF-8", "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
                   "SWARM_DB": str(Path(scratch) / "swarm.sqlite"), "TMPDIR": scratch}
            command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                       "--no-header", "-o", "addopts=", *tests]
            if keyword:
                command += ["-k", keyword]
            started = time.monotonic()
            try:
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True,
                                        timeout=TEST_TIMEOUT_S, stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                return {"verdict": f"UNKNOWN: pytest timed out after {TEST_TIMEOUT_S}s",
                        "status": "timeout", "tests": tests, "keyword": keyword,
                        "detail": f"pytest exceeded {TEST_TIMEOUT_S}s and was stopped; result unknown."}
            output = (result.stdout + result.stderr).strip()
            summary = next((match.group(1) for line in reversed(output.splitlines())
                            if (match := _SUMMARY.match(line.strip()))), None)
            return {"verdict": _verdict(result.returncode, summary),
                    "status": "passed" if result.returncode == 0 else "failed",
                    "exit_code": result.returncode, "tests": tests, "keyword": keyword,
                    "summary": summary, "seconds": round(time.monotonic() - started, 1),
                    "output_tail": output[-MAX_TEST_OUTPUT:],
                    "output_truncated": len(output) > MAX_TEST_OUTPUT}
    finally:
        _LOCK.release()


def run_tests_json(args: dict, root: Path = ROOT) -> str:
    return json.dumps(run_tests(args, root))
