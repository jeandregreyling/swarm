"""Step residual_risk + owner_route + project status automation
+ no-network integration profile + concurrency probe.

Covers (P-00221285D1):
  * S-64552DDFEA — residual_risk field on project_steps
  * S-58C4823367 — owner_route slug for steps
  * S-7BA9955A6D — project status automation (auto-archive)
  * S-D277FF5AFC — CI-friendly no-network integration profile
  * S-941A9C1A0A — concurrency probe for Tasker run-now
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def kc(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_DB_PATH", str(tmp_path / "swarm.db"))
    monkeypatch.setenv("SWARM_ROOT", str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from utils.db import _connection
    importlib.reload(_connection)
    from utils.db import _schema
    importlib.reload(_schema)
    _schema.initialise_database()
    from core.knowledge import projects as _kc
    importlib.reload(_kc)
    return _kc


# ── S-64552DDFEA: residual_risk ─────────────────────────────────────────────

def test_residual_risk_can_be_set_and_cleared(kc):
    pid = kc.create_project("rr")
    sid = kc.add_step(pid, "step")
    assert kc.update_step(sid, residual_risk="acceptable; monitored by alarm")
    s = [s for s in kc.list_steps(pid) if s["step_id"] == sid][0]
    assert s["residual_risk"] == "acceptable; monitored by alarm"
    # clear
    assert kc.update_step(sid, residual_risk="")
    s = [s for s in kc.list_steps(pid) if s["step_id"] == sid][0]
    assert s["residual_risk"] is None


def test_residual_risk_is_capped(kc):
    pid = kc.create_project("rr2")
    sid = kc.add_step(pid, "step")
    big = "X" * 1000
    kc.update_step(sid, residual_risk=big)
    s = [s for s in kc.list_steps(pid) if s["step_id"] == sid][0]
    assert len(s["residual_risk"]) == 240


# ── S-58C4823367: owner_route ───────────────────────────────────────────────

def test_owner_route_slugifies_input(kc):
    pid = kc.create_project("orr")
    sid = kc.add_step(pid, "step")
    kc.update_step(sid, owner_route="Backend!Team / mistral$$")
    s = [s for s in kc.list_steps(pid) if s["step_id"] == sid][0]
    assert s["owner_route"] == "backendteam_mistral"


def test_owner_route_can_be_cleared(kc):
    pid = kc.create_project("orr2")
    sid = kc.add_step(pid, "step")
    kc.update_step(sid, owner_route="qa")
    kc.update_step(sid, owner_route="")
    s = [s for s in kc.list_steps(pid) if s["step_id"] == sid][0]
    assert s["owner_route"] is None


# ── S-7BA9955A6D: project status automation ────────────────────────────────

def test_project_auto_archives_when_all_steps_done(kc):
    pid = kc.create_project("auto")
    s1 = kc.add_step(pid, "a")
    s2 = kc.add_step(pid, "b")
    kc.update_step_status(s1, "done")
    # not yet — s2 still todo
    proj = kc.get_project(pid)["project"]
    assert proj["status"] == "active"
    kc.update_step_status(s2, "done")
    proj = kc.get_project(pid)["project"]
    assert proj["status"] == "archived"


def test_project_does_not_auto_archive_with_blocked(kc):
    pid = kc.create_project("noauto")
    s1 = kc.add_step(pid, "a")
    s2 = kc.add_step(pid, "b")
    kc.update_step_status(s1, "done")
    kc.update_step_status(s2, "blocked")
    proj = kc.get_project(pid)["project"]
    assert proj["status"] == "active"


def test_project_auto_archive_respects_skipped(kc):
    pid = kc.create_project("skip")
    s1 = kc.add_step(pid, "a")
    s2 = kc.add_step(pid, "b")
    kc.update_step_status(s1, "done")
    kc.update_step_status(s2, "skipped")
    proj = kc.get_project(pid)["project"]
    assert proj["status"] == "archived"


def test_project_auto_archive_does_not_revive_manual_archive(kc):
    pid = kc.create_project("manual")
    s1 = kc.add_step(pid, "a")
    kc.update_project(pid, status="on_hold")
    kc.update_step_status(s1, "done")
    proj = kc.get_project(pid)["project"]
    # Only flips active→archived; on_hold projects stay put.
    assert proj["status"] == "on_hold"


# ── S-D277FF5AFC: no-network integration profile ───────────────────────────

def test_ci_no_network_profile_blocks_outbound_http():
    from utils import ci_profile
    importlib.reload(ci_profile)
    ci_profile.enable_no_network()
    try:
        # Use an IP literal so DNS doesn't intercept before our socket
        # patch fires. 192.0.2.1 is TEST-NET-1 (RFC 5737) — guaranteed
        # not to route to a real host even if the patch leaks.
        import socket
        s = socket.socket()
        s.settimeout(0.05)
        with pytest.raises(ci_profile.NetworkBlocked):
            s.connect(("192.0.2.1", 80))
        s.close()
    finally:
        ci_profile.disable_no_network()


def test_ci_no_network_profile_allows_loopback():
    from utils import ci_profile
    importlib.reload(ci_profile)
    ci_profile.enable_no_network()
    try:
        # 127.0.0.1 hits should not raise NetworkBlocked at the patch
        # layer (they may still fail to connect — that's fine; we only
        # care that the profile didn't pre-emptively block them).
        import socket
        s = socket.socket()
        s.settimeout(0.05)
        try:
            s.connect(("127.0.0.1", 1))  # arbitrary closed port
        except (ConnectionRefusedError, OSError):
            pass
        finally:
            s.close()
    finally:
        from utils import ci_profile
        ci_profile.disable_no_network()


def test_ci_no_network_idempotent():
    from utils import ci_profile
    importlib.reload(ci_profile)
    ci_profile.enable_no_network()
    ci_profile.enable_no_network()  # no double-patching, no error
    ci_profile.disable_no_network()
    ci_profile.disable_no_network()  # safe to disable twice


# ── S-941A9C1A0A: Tasker run-now concurrency probe ─────────────────────────

def test_tasker_run_now_lock_serialises_concurrent_calls():
    from utils import tasker_run_lock
    importlib.reload(tasker_run_lock)
    tasker_run_lock.reset()
    fired = []
    blocked = []

    def attempt(tag):
        with tasker_run_lock.try_run("task-1") as got:
            if got:
                fired.append(tag)
                # hold long enough that other threads land on the lock
                import time as _t
                _t.sleep(0.05)
            else:
                blocked.append(tag)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # exactly one acquired
    assert len(fired) == 1
    assert len(blocked) == 7


def test_tasker_run_now_lock_is_per_task_id():
    from utils import tasker_run_lock
    importlib.reload(tasker_run_lock)
    tasker_run_lock.reset()
    with tasker_run_lock.try_run("task-A") as got_a:
        assert got_a
        with tasker_run_lock.try_run("task-B") as got_b:
            assert got_b
        with tasker_run_lock.try_run("task-A") as got_a2:
            assert got_a2 is False
