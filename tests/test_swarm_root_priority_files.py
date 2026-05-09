"""
test_swarm_root_priority_files.py

Verify the three priority hardcoded-path files no longer embed
/home/seven/swarm and instead resolve via SWARM_ROOT env or __file__.

Targets (from audit/hardcoded_paths_audit.md):
  - fridays/task_runner.py
  - fridays/scheduler.py
  - lib/system/file_versioning.py
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

HARD_CODED = "/home/seven/swarm"
PRIORITY_FILES = [
    Path("fridays/task_runner.py"),
    Path("fridays/scheduler.py"),
    Path("lib/system/file_versioning.py"),
]


def _file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("py_file", PRIORITY_FILES)
def test_no_hardcoded_swarm_root_literal(py_file: Path):
    """Each file must not contain the literal /home/seven/swarm string."""
    text = _file_text(py_file)
    assert HARD_CODED not in text, (
        f"{py_file} still contains hard-coded path {HARD_CODED!r}"
    )


@pytest.mark.parametrize("py_file", PRIORITY_FILES)
def test_uses_swarm_root_env_or_file_derive(py_file: Path):
    """Each file must reference SWARM_ROOT or derive from __file__."""
    text = _file_text(py_file)
    has_swarm_root = "SWARM_ROOT" in text
    has_file_derive = "__file__" in text
    assert has_swarm_root or has_file_derive, (
        f"{py_file} must use SWARM_ROOT or __file__ for path resolution"
    )


def test_task_runner_uses_swarm_root_env(tmp_path, monkeypatch):
    """When SWARM_ROOT is set, task_runner should insert that path."""
    fake_root = str(tmp_path / "swarm")
    os.makedirs(fake_root, exist_ok=True)
    monkeypatch.setenv("SWARM_ROOT", fake_root)

    # Remove module from cache so re-import picks up the new env.
    for key in list(sys.modules):
        if key in ("fridays.task_runner", "fridays"):
            del sys.modules[key]

    import fridays.task_runner as tr

    assert fake_root in sys.path
    # The module-level _SWARM_ROOT should match the env.
    assert tr._SWARM_ROOT == fake_root


def test_scheduler_uses_swarm_root_env(tmp_path, monkeypatch):
    """When SWARM_ROOT is set, scheduler should insert that path and utils subpath."""
    fake_root = str(tmp_path / "swarm")
    os.makedirs(fake_root, exist_ok=True)
    monkeypatch.setenv("SWARM_ROOT", fake_root)

    for key in list(sys.modules):
        if key in ("fridays.scheduler", "fridays"):
            del sys.modules[key]

    # Ensure repo root + utils are findable so scheduler's top-level imports resolve.
    repo_root = str(Path(__file__).resolve().parents[1])
    for p in (repo_root, os.path.join(repo_root, "utils")):
        if p not in sys.path:
            sys.path.insert(0, p)

    import fridays.scheduler as sched

    assert fake_root in sys.path
    assert str(tmp_path / "swarm" / "utils") in sys.path
    assert sched._SWARM_ROOT == fake_root


def test_file_versioning_uses_swarm_root_env(tmp_path, monkeypatch):
    """When SWARM_ROOT is set, file_versioning dirs should be under that root."""
    fake_root = str(tmp_path / "swarm")
    os.makedirs(fake_root, exist_ok=True)
    monkeypatch.setenv("SWARM_ROOT", fake_root)

    for key in list(sys.modules):
        if key in ("lib.system.file_versioning", "lib", "lib.system"):
            del sys.modules[key]

    # Ensure lib/system is findable so file_versioning's top-level imports resolve.
    repo_root = str(Path(__file__).resolve().parents[1])
    lib_system = os.path.join(repo_root, "lib", "system")
    for p in (repo_root, lib_system):
        if p not in sys.path:
            sys.path.insert(0, p)

    import lib.system.file_versioning as fv

    assert fv.VERSIONS_DIR == os.path.join(fake_root, ".swarm_versions")
    assert fv.RESTORE_BIN_DIR == os.path.join(fake_root, ".restore_bin")
