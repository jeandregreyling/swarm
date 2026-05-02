"""Pin listener-hygiene artefacts (P-00221285D1).

Covers:
  * S-2753E6750B — listener email vs scheduler responsibility split
  * S-D504258E73 — systemd unit for scheduler main_loop
  * S-398A356904 — graceful listener restart command
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_scheduler_unit_present():
    unit = REPO / "swarm-scheduler.service"
    assert unit.exists(), "swarm-scheduler.service must exist at repo root"
    text = unit.read_text(encoding="utf-8")
    assert "ExecStart=" in text
    assert "utils/scheduler.py" in text, "unit must invoke utils/scheduler.py main_loop"
    assert "Restart=on-failure" in text
    assert "WantedBy=multi-user.target" in text


def test_scheduler_unit_uses_venv_python():
    text = (REPO / "swarm-scheduler.service").read_text(encoding="utf-8")
    # The terminal unit uses the venv binary; the scheduler should follow
    # that pattern so deps (e.g. apscheduler-style) resolve correctly.
    assert "/home/seven/swarm/.venv/bin/python3" in text


def test_listener_restart_script_present_and_executable():
    p = REPO / "scripts" / "swarm-listener-restart.sh"
    assert p.exists()
    mode = os.stat(p).st_mode
    assert mode & stat.S_IXUSR, "script must be user-executable"


def test_listener_restart_script_passes_bash_n():
    p = REPO / "scripts" / "swarm-listener-restart.sh"
    res = subprocess.run(
        ["bash", "-n", str(p)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr


def test_listener_restart_script_drain_contract():
    text = (REPO / "scripts" / "swarm-listener-restart.sh").read_text(encoding="utf-8")
    # Drain marker file approach
    assert "DRAIN_FILE" in text
    # Configurable timeout
    assert "LISTENER_DRAIN_TIMEOUT" in text
    # Verifies state after restart
    assert "is-active" in text


def test_scheduler_main_loop_still_callable():
    # Scheduler must still expose main_loop() so the systemd unit ExecStart works.
    import importlib
    spec = importlib.util.spec_from_file_location(
        "_swarm_scheduler", REPO / "utils" / "scheduler.py"
    )
    assert spec is not None and spec.loader is not None
    # Don't actually exec the module — main_loop has side effects + DB reads.
    # Just confirm the symbol is defined by reading the source.
    src = (REPO / "utils" / "scheduler.py").read_text(encoding="utf-8")
    assert "def main_loop()" in src
    assert "if __name__ == '__main__':" in src
