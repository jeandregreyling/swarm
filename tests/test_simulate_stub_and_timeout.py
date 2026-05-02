"""Tests for utils/simulate.py deterministic stub mode + per-stage timeout.

Regression for MD-BUG-83465630DE9B (BUG-025).
"""
import importlib
import os
import sys

import pytest


def _fresh_simulate(monkeypatch, **env):
    """Reload utils.simulate with the given env vars so the module-level
    flags (STUB_MODE, STAGE_TIMEOUT_SECONDS) re-evaluate."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    # Drop any cached module so the env-driven branches re-run.
    sys.modules.pop("utils.simulate", None)
    sys.modules.pop("simulate", None)
    return importlib.import_module("utils.simulate")


class TestStubMode:
    def test_stub_mode_off_by_default(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB=None)
        assert sim.STUB_MODE is False

    def test_stub_mode_on_with_1(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        assert sim.STUB_MODE is True

    def test_stub_mode_on_with_true(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="true")
        assert sim.STUB_MODE is True

    def test_stub_mode_on_with_yes(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="yes")
        assert sim.STUB_MODE is True

    def test_stub_mode_off_for_garbage(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="maybe")
        assert sim.STUB_MODE is False


class TestStubReturns:
    def test_stub_stage1_shape(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        web, llama, shared, routing = sim._stub_stage1("hello world")
        assert isinstance(web, list) and web
        assert isinstance(llama, str) and "stub" in llama.lower()
        assert isinstance(shared, dict)
        for k in ("needs_web", "agents", "is_sap", "is_system",
                  "is_identity", "mode", "search_engines"):
            assert k in routing

    def test_stub_stage1_detects_sap_keyword(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        _, _, _, r = sim._stub_stage1("SAP HCM payroll question")
        assert r["is_sap"] is True

    def test_stub_stage1_detects_system_keyword(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        _, _, _, r = sim._stub_stage1("how much RAM are we using")
        assert r["is_system"] is True

    def test_stub_stage1_returns_quickly(self, monkeypatch):
        import time
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        start = time.time()
        sim._stub_stage1("x" * 200)
        assert time.time() - start < 0.5

    def test_stub_stage2_shape(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        qwen, gemma, debate = sim._stub_stage2("q", [], "llama", {}, 1, {})
        assert "stub" in qwen.lower()
        assert "stub" in gemma.lower()
        assert debate["fired"] is False
        assert debate["rounds"] == 0

    def test_stub_stage_eight_shape(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        out = sim._stub_stage_eight("q", [], {}, 1)
        for k in ("functional", "technical", "devil", "gemma_verdict"):
            assert k in out
            assert "stub" in out[k].lower()

    def test_stub_swap_takes_effect(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB="1")
        # When STUB_MODE is on, the module-level names point at the stubs.
        assert sim.consult_stage1 is sim._stub_stage1
        assert sim.consult_stage2 is sim._stub_stage2
        assert sim.consult_stage_eight is sim._stub_stage_eight

    def test_no_stub_swap_when_off(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STUB=None)
        # When off, the real orchestrator functions are bound (not the stubs).
        assert sim.consult_stage1 is not sim._stub_stage1


class TestStageTimeout:
    def test_default_timeout_is_60s(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT=None)
        assert sim.STAGE_TIMEOUT_SECONDS == 60

    def test_custom_timeout_parsed(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="5")
        assert sim.STAGE_TIMEOUT_SECONDS == 5

    def test_garbage_timeout_falls_back_to_default(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="not-a-number")
        assert sim.STAGE_TIMEOUT_SECONDS == 60

    def test_zero_timeout_clamped_to_one(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="0")
        assert sim.STAGE_TIMEOUT_SECONDS == 1

    def test_with_timeout_passes_through_result(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="5")
        assert sim._with_timeout("noop", lambda: 42) == 42

    def test_with_timeout_propagates_exception(self, monkeypatch):
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="5")

        def _boom():
            raise ValueError("inner")

        with pytest.raises(ValueError, match="inner"):
            sim._with_timeout("inner-fn", _boom)

    @pytest.mark.skipif(not hasattr(__import__("signal"), "SIGALRM"),
                        reason="Platform without SIGALRM")
    def test_with_timeout_kills_runaway(self, monkeypatch):
        import time
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="1")
        with pytest.raises(sim.StageTimeout):
            sim._with_timeout("sleeper", lambda: time.sleep(3))

    def test_with_timeout_cleans_up_alarm(self, monkeypatch):
        # After a normal call, no alarm should remain pending.
        import signal as _sig
        sim = _fresh_simulate(monkeypatch, SWARM_SIMULATE_STAGE_TIMEOUT="5")
        sim._with_timeout("noop", lambda: 1)
        if hasattr(_sig, "SIGALRM"):
            # alarm(0) returns the seconds remaining on the previous alarm
            remaining = _sig.alarm(0)
            assert remaining == 0
