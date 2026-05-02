"""Lock the chat_smoke_probe → spine CHAT emission contract.

Regression for MD-FEATURE-B13F80E2C988. The probe must:
  1. Be registered as a periodic task.
  2. Emit a spine CHAT event (info on success, warn on failure) so Traced
     surfaces historical latency.
  3. Never crash the caller if spine import fails.
"""
import sqlite3
import sys
import types

import pytest


def _install_fake_orch(monkeypatch, ask_agent_impl):
    """Mirror the trick used by tests/test_session28_batch11.py — replace
    fridays.orchestrator in sys.modules AND on the fridays package, since
    the probe does `from fridays import orchestrator`."""
    fake = types.ModuleType("fridays.orchestrator")
    fake.ask_agent = ask_agent_impl
    monkeypatch.setitem(sys.modules, "fridays.orchestrator", fake)
    try:
        import fridays as _frpkg
        monkeypatch.setattr(_frpkg, "orchestrator", fake, raising=False)
    except ImportError:
        pass


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm_memory.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE task_run_log (
            id INTEGER PRIMARY KEY,
            task_name TEXT,
            status TEXT,
            output TEXT,
            run_at TEXT,
            duration_ms INTEGER
        );
        """
    )
    con.commit()
    con.close()

    from utils.db import _connection
    monkeypatch.setattr(_connection, "DB_PATH", str(db_path))
    return db_path


class TestChatSmokeProbeRegistration:
    def test_registered_in_task_registry(self):
        from fridays.task_runner import TASK_REGISTRY
        assert "chat_smoke_probe" in TASK_REGISTRY
        entry = TASK_REGISTRY["chat_smoke_probe"]
        assert callable(entry["fn"])
        assert entry.get("category") == "monitoring"

    def test_description_mentions_chat_round_trip(self):
        from fridays.task_runner import TASK_REGISTRY
        desc = TASK_REGISTRY["chat_smoke_probe"]["description"].lower()
        assert "chat" in desc and "round-trip" in desc


class TestChatSmokeProbeSpineEmission:
    def test_success_emits_info_chat_event(self, fresh_db, monkeypatch):
        from core import spine
        from fridays.task_runner import TASK_REGISTRY

        spine.clear_ring()
        _install_fake_orch(monkeypatch, lambda *a, **kw: "OK")

        out = TASK_REGISTRY["chat_smoke_probe"]["fn"]()

        assert "ok" in out.lower() and "FAILED" not in out
        events = [e for e in spine.get_recent()
                  if e.kind == spine.EventKind.CHAT and e.source == "chat_smoke_probe"]
        assert len(events) == 1
        ev = events[0]
        assert ev.severity == spine.Severity.INFO
        assert ev.payload.get("ok") is True
        assert isinstance(ev.payload.get("latency_ms"), int)
        assert ev.payload.get("agent") == "llama"

    def test_failure_emits_warn_chat_event(self, fresh_db, monkeypatch):
        from core import spine
        from fridays.task_runner import TASK_REGISTRY

        spine.clear_ring()

        def _boom(*a, **kw):
            raise RuntimeError("backend offline")

        _install_fake_orch(monkeypatch, _boom)

        out = TASK_REGISTRY["chat_smoke_probe"]["fn"]()

        assert "FAILED" in out
        events = [e for e in spine.get_recent()
                  if e.kind == spine.EventKind.CHAT and e.source == "chat_smoke_probe"]
        assert len(events) == 1
        ev = events[0]
        assert ev.severity == spine.Severity.WARN
        assert ev.payload.get("ok") is False
        assert "backend offline" in (ev.payload.get("err") or "")

    def test_empty_reply_emits_warn(self, fresh_db, monkeypatch):
        from core import spine
        from fridays.task_runner import TASK_REGISTRY

        spine.clear_ring()
        _install_fake_orch(monkeypatch, lambda *a, **kw: "   ")

        out = TASK_REGISTRY["chat_smoke_probe"]["fn"]()

        assert "FAILED" in out
        events = [e for e in spine.get_recent() if e.source == "chat_smoke_probe"]
        assert events and events[-1].severity == spine.Severity.WARN

    def test_payload_includes_latency_and_reply_len(self, fresh_db, monkeypatch):
        from core import spine
        from fridays.task_runner import TASK_REGISTRY

        spine.clear_ring()
        _install_fake_orch(monkeypatch, lambda *a, **kw: "OK ack")

        TASK_REGISTRY["chat_smoke_probe"]["fn"]()

        ev = [e for e in spine.get_recent() if e.source == "chat_smoke_probe"][-1]
        assert ev.payload["reply_len"] == len("OK ack")
        assert ev.payload["latency_ms"] >= 0

    def test_spine_failure_does_not_break_probe(self, fresh_db, monkeypatch):
        """If spine.log raises, the probe still returns its status string."""
        from fridays.task_runner import TASK_REGISTRY
        from core import spine as _spine

        _install_fake_orch(monkeypatch, lambda *a, **kw: "OK")

        def _boom(*a, **kw):
            raise RuntimeError("spine on fire")
        monkeypatch.setattr(_spine, "log", _boom)

        out = TASK_REGISTRY["chat_smoke_probe"]["fn"]()
        assert "ok" in out.lower() and "FAILED" not in out


class TestProbeArguments:
    def test_custom_agent_passed_through(self, fresh_db, monkeypatch):
        from core import spine
        from fridays.task_runner import TASK_REGISTRY

        spine.clear_ring()
        seen = {}

        def _ask(agent, prompt, *a, **kw):
            seen["agent"] = agent
            seen["prompt"] = prompt
            return "ack"

        _install_fake_orch(monkeypatch, _ask)
        TASK_REGISTRY["chat_smoke_probe"]["fn"](agent="gemma")

        assert seen.get("agent") == "gemma"
        ev = [e for e in spine.get_recent() if e.source == "chat_smoke_probe"][-1]
        assert ev.payload["agent"] == "gemma"

    def test_custom_prompt_passed_through(self, fresh_db, monkeypatch):
        from fridays.task_runner import TASK_REGISTRY
        seen = {}

        def _ask(agent, prompt, *a, **kw):
            seen["prompt"] = prompt
            return "ack"

        _install_fake_orch(monkeypatch, _ask)
        TASK_REGISTRY["chat_smoke_probe"]["fn"](prompt="hi")

        assert seen.get("prompt") == "hi"

    def test_invalid_timeout_does_not_raise(self, fresh_db, monkeypatch):
        from fridays.task_runner import TASK_REGISTRY
        _install_fake_orch(monkeypatch, lambda *a, **kw: "ack")
        out = TASK_REGISTRY["chat_smoke_probe"]["fn"](timeout="not-a-number")
        assert "ok" in out.lower()
