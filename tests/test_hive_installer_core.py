"""Tests for the click-through installer's headless core."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.install import hive_installer_core as core


# ---- detect_platform / default_stage_dir ---------------------------------

def test_detect_platform_returns_known_value():
    p = core.detect_platform()
    assert p in ("linux", "macos", "windows", "unknown")


def test_default_stage_dir_per_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sd = core.default_stage_dir("linux")
    assert sd == tmp_path / "swarm-hive"
    sd2 = core.default_stage_dir("macos")
    assert "Library" in str(sd2)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AL"))
    sd3 = core.default_stage_dir("windows")
    assert sd3 == tmp_path / "AL" / "swarm-hive"


# ---- plan_install --------------------------------------------------------

def test_plan_install_linux():
    plan = core.plan_install("http://leader:5050/", plat="linux", node_id="n1")
    assert plan.leader == "http://leader:5050"
    assert plan.platform == "linux"
    assert plan.node_id == "n1"
    assert plan.installer_filename == "install_linux.sh"
    assert plan.agent_url.endswith("/api/hive/install/agent.py")
    assert plan.installer_url.endswith("/api/hive/install/install_linux.sh")


def test_plan_install_windows():
    plan = core.plan_install("http://leader", plat="windows")
    assert plan.installer_filename == "install_windows.ps1"


def test_plan_install_rejects_empty_leader():
    with pytest.raises(core.InstallerError):
        core.plan_install("", plat="linux")


def test_plan_install_rejects_unknown_platform():
    with pytest.raises(core.InstallerError):
        core.plan_install("http://leader", plat="haiku")


# ---- probe_leader (mocked) -----------------------------------------------

class _FakeResponse:
    def __init__(self, payload, headers=None):
        self._b = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_probe_leader_empty():
    r = core.probe_leader("")
    assert r.ok is False
    assert "empty" in r.reason


def test_probe_leader_adds_scheme(monkeypatch):
    captured = {}

    def fake_open(url, **kw):
        captured["url"] = url
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(core, "_open", fake_open)
    r = core.probe_leader("leader.local:5050")
    assert r.ok is True
    assert captured["url"].startswith("http://leader.local:5050")


def test_probe_leader_handles_manifest(monkeypatch):
    calls = []
    def fake_open(url, **kw):
        calls.append(url)
        if url.endswith("/api/hive/install/"):
            return _FakeResponse({"ok": True, "version": "v0"})
        if url.endswith("/api/hive/nodes"):
            return _FakeResponse({"ok": True, "count": 3, "nodes": []})
        raise core.InstallerError(f"unexpected {url}")
    monkeypatch.setattr(core, "_open", fake_open)
    r = core.probe_leader("http://x:5050")
    assert r.ok is True
    assert r.node_count == 3


def test_probe_leader_unreachable(monkeypatch):
    def fake_open(url, **kw):
        raise core.InstallerError("boom")
    monkeypatch.setattr(core, "_open", fake_open)
    r = core.probe_leader("http://nope:5050")
    assert r.ok is False
    assert "boom" in r.reason


def test_probe_leader_rejects_non_hive_response(monkeypatch):
    monkeypatch.setattr(core, "_open", lambda url, **kw: _FakeResponse({"ok": False}))
    r = core.probe_leader("http://x")
    assert r.ok is False
    assert "manifest" in r.reason


# ---- download_to ---------------------------------------------------------

def test_download_to_writes_file_atomically(monkeypatch, tmp_path):
    payload = b"hello-agent\n"
    class FakeR:
        def __init__(self):
            self.headers = {"Content-Length": str(len(payload))}
            self._buf = io.BytesIO(payload)
        def read(self, n=-1):
            return self._buf.read(n)
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(core, "_open", lambda url, **kw: FakeR())
    progress_calls = []
    dest = tmp_path / "sub" / "agent.py"
    out = core.download_to("http://x/agent.py", dest, progress=lambda r,t: progress_calls.append((r,t)))
    assert out == dest
    assert dest.read_bytes() == payload
    assert not (tmp_path / "sub" / "agent.py.part").exists()
    assert progress_calls and progress_calls[-1][0] == len(payload)


# ---- run_platform_installer (mocked subprocess) --------------------------

def test_run_platform_installer_missing_file(tmp_path):
    plan = core.plan_install("http://leader", plat="linux")
    res = core.run_platform_installer(plan, tmp_path / "missing.sh")
    assert res.ok is False
    assert "not staged" in res.detail


def test_run_platform_installer_streams_log(tmp_path, monkeypatch):
    plan = core.plan_install("http://leader", plat="linux")
    fake = tmp_path / "i.sh"
    fake.write_text("#!/bin/sh\necho hi\n")
    fake.chmod(0o755)

    class FakeProc:
        def __init__(self):
            self.stdout = iter(["line-one\n", "line-two\n"])
        def wait(self):
            return 0

    monkeypatch.setattr(core.shutil, "which", lambda x: "/bin/bash" if x == "bash" else None)
    def fake_popen(cmd, **kw):
        return FakeProc()
    monkeypatch.setattr(core.subprocess, "Popen", fake_popen)

    captured = []
    res = core.run_platform_installer(plan, fake, on_log=captured.append)
    assert res.ok is True
    assert any("line-one" in c for c in captured)
    assert any("line-two" in c for c in captured)


def test_run_platform_installer_nonzero(tmp_path, monkeypatch):
    plan = core.plan_install("http://leader", plat="linux")
    fake = tmp_path / "i.sh"
    fake.write_text("#!/bin/sh\nexit 7\n")

    class FakeProc:
        def __init__(self):
            self.stdout = iter([])
        def wait(self): return 7

    monkeypatch.setattr(core.shutil, "which", lambda x: "/bin/bash" if x == "bash" else None)
    monkeypatch.setattr(core.subprocess, "Popen", lambda *a, **kw: FakeProc())
    res = core.run_platform_installer(plan, fake)
    assert res.ok is False
    assert "code 7" in res.detail
