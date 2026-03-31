"""
UAT gate runner for Fridays.

Runs the critical regression suites in sequence and exits non-zero if any fail.

Usage:
    python3 tests/run_uat_gate.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GateResult:
    name: str
    command: list[str]
    returncode: int
    duration_sec: float


def _run_case(name: str, command: list[str]) -> GateResult:
    start = time.time()
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    duration = time.time() - start

    # Print condensed output so this can be used in CI/local quickly.
    print(f"\n[{name}] command: {' '.join(command)}")
    print(f"[{name}] exit: {proc.returncode} | duration: {duration:.2f}s")

    # Keep output bounded but useful.
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        print(f"[{name}] stdout:\n{out[-2500:]}")
    if err:
        print(f"[{name}] stderr:\n{err[-1500:]}")

    return GateResult(name=name, command=command, returncode=proc.returncode, duration_sec=duration)


def main() -> int:
    print("=" * 70)
    print("FRIDAYS UAT GATE")
    print("=" * 70)

    cases = [
        ("compile", [sys.executable, "-m", "py_compile", "frontend/terminal.py", "fridays/telegram_bot.py", "tests/test_telegram_trust.py", "tests/test_manager_onboarding_api.py"]),
        ("e2e", [sys.executable, "tests/test_e2e_fridays.py"]),
        ("telegram_trust", [sys.executable, "tests/test_telegram_trust.py"]),
        ("manager_onboarding", [sys.executable, "tests/test_manager_onboarding_api.py"]),
    ]

    results: list[GateResult] = []
    for name, command in cases:
        results.append(_run_case(name, command))

    failed = [r for r in results if r.returncode != 0]

    print("\n" + "-" * 70)
    for r in results:
        status = "PASS" if r.returncode == 0 else "FAIL"
        print(f"{status:4}  {r.name:18}  {r.duration_sec:7.2f}s")
    print("-" * 70)

    if failed:
        print(f"UAT GATE: FAIL ({len(failed)} failing suite(s))")
        return 1

    print("UAT GATE: PASS (all critical suites green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
