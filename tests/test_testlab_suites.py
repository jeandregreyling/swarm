"""Pin the new Test Lab suites (P-00221285D1).

Covers:
  * S-53B7D03A12 — Tasker suite
  * S-2E9343FB8F — Research watcher suite
  * S-F7FB61FF05 — Studio projects suite
"""
from __future__ import annotations

from pathlib import Path

from core import testlab_registry as tlr


REPO = Path(__file__).resolve().parents[1]


def test_registry_has_three_new_suites():
    ids = {e["id"] for e in tlr.get_registry()}
    for sid in ("suite-tasker", "suite-research-watcher", "suite-studio-projects"):
        assert sid in ids, f"missing Test Lab suite: {sid}"


def test_suites_have_grouping_and_command():
    for sid in ("suite-tasker", "suite-research-watcher", "suite-studio-projects"):
        entry = tlr.get_entry(sid)
        assert entry is not None
        assert entry["group"] == "Suites"
        cmd = str(entry["command"])
        assert "pytest" in cmd, f"{sid} should run pytest"
        assert "--tb=line" in cmd


def test_suites_only_reference_real_test_files():
    for sid in ("suite-tasker", "suite-research-watcher", "suite-studio-projects"):
        entry = tlr.get_entry(sid)
        cmd = str(entry["command"])
        for token in cmd.split():
            if token.endswith(".py") and "test_" in token:
                rel = REPO / token
                assert rel.exists(), f"{sid} references missing file {token}"


def test_registry_get_entry_returns_none_for_unknown():
    assert tlr.get_entry("does-not-exist") is None


def test_registry_get_returns_a_copy():
    a = tlr.get_registry()
    a[0]["label"] = "MUTATED"
    b = tlr.get_registry()
    assert b[0]["label"] != "MUTATED"
