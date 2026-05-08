"""Session 28 batch 12 — three closures.

Covered:
- S-2838647C35: .gitignore covers runtime artifacts (thinking_tree, media_center,
  ledger offsets, sandpit shared state) and previously-tracked log files have
  been untracked.
- S-7C7ED96F5B: a curated list of repo scripts/utilities no longer hard-codes
  ``/home/seven/swarm`` as a ``sys.path`` target. They derive SWARM_ROOT from
  ``__file__`` (with env override) so they work in worktrees and dev checkouts.
- S-1C55C2826A and S-A4249B4159 already have a dedicated regression suite
  (``tests/test_tasker_dry_run.py``) — this batch only certifies the path
  audit + .gitignore coverage.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


# ---- S-2838647C35 -----------------------------------------------------------

GITIGNORE_REQUIRED_ENTRIES = [
    "fridays/thinking_tree_log.json",
    "runtime/seven/heartbeat.json",
    "runtime/seven/ledger.offset",
    "runtime/backups/log.jsonl",
    "sandpits/shared/CURRENT_FOCUS.md",
    "sandpits/shared/STALE_PROPOSALS.md",
    "sandpits/shared/media_center_state.json",
    "sandpits/studio/DISPATCHED_WORK.md",
    "swarm_docs/SYSTEM_INDEX.md",
    "swarm_docs/SYSTEM_LANDSCAPE.json",
    "artifacts/media_center/",
]


def test_gitignore_covers_runtime_artifacts():
    body = (REPO / ".gitignore").read_text(encoding="utf-8")
    missing = [entry for entry in GITIGNORE_REQUIRED_ENTRIES if entry not in body]
    assert not missing, f"missing .gitignore entries: {missing}"


def test_runtime_log_no_longer_tracked():
    """runtime/backups/log.jsonl was previously tracked; it must now be ignored."""
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.check_output(
        ["git", "ls-files", "runtime/backups/log.jsonl"],
        cwd=REPO,
        text=True,
    ).strip()
    assert out == "", f"runtime/backups/log.jsonl is still tracked: {out!r}"


# ---- S-7C7ED96F5B -----------------------------------------------------------

PATH_AUDIT_TARGETS = [
    "scripts/_log_packet10a_milestone.py",
    "scripts/_log_wishlist_milestone.py",
    "utils/scheduler.py",
    "utils/app_launcher.py",
    "utils/seven_fridays.py",
]

# Matches sys.path.insert(..., "/home/seven/swarm...") regardless of quote style.
HARDCODED_SYSPATH = re.compile(
    r"""sys\.path\.insert\s*\([^)]*['"]/home/seven/swarm[^'"]*['"]"""
)


@pytest.mark.parametrize("rel_path", PATH_AUDIT_TARGETS)
def test_no_hardcoded_syspath_insert(rel_path):
    src = (REPO / rel_path).read_text(encoding="utf-8")
    match = HARDCODED_SYSPATH.search(src)
    assert match is None, (
        f"{rel_path} still hard-codes a sys.path absolute: {match.group(0)!r}"
    )


@pytest.mark.parametrize("rel_path", PATH_AUDIT_TARGETS)
def test_uses_swarm_root_pattern(rel_path):
    src = (REPO / rel_path).read_text(encoding="utf-8")
    assert "SWARM_ROOT" in src, f"{rel_path} should reference SWARM_ROOT"
    # Either env-var lookup or relative-to-__file__ derivation must be present.
    has_env = "os.environ.get('SWARM_ROOT'" in src or 'os.environ.get("SWARM_ROOT"' in src
    has_relative = "os.path.abspath(__file__)" in src or "Path(__file__)" in src
    assert has_env or has_relative, (
        f"{rel_path} must derive SWARM_ROOT from env or __file__"
    )


def test_swarm_root_helper_module_exists():
    helper = REPO / "utils" / "swarm_root.py"
    assert helper.exists()
    body = helper.read_text(encoding="utf-8")
    assert "SWARM_ROOT" in body
    assert "os.environ" in body


def test_seven_fridays_no_remaining_absolute_paths_in_repl_logic():
    """The interactive read/write/list paths in seven_fridays.py must not
    reference /home/seven/swarm directly — they must use SWARM_ROOT."""
    src = (REPO / "utils" / "seven_fridays.py").read_text(encoding="utf-8")
    bad_lines = [
        ln for ln in src.splitlines()
        if "/home/seven/swarm" in ln and "SWARM_ROOT" not in ln and not ln.lstrip().startswith("#")
    ]
    assert not bad_lines, "absolute paths remain:\n" + "\n".join(bad_lines)
