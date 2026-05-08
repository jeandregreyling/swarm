from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "utils"))


def test_twenty_repairs_legacy_qwen_alias(monkeypatch):
    from agents.twenty import twenty_agent

    monkeypatch.setattr(
        "utils.db.registry.get_agent_models",
        lambda: {"twenty": "qwen3:latest"},
    )

    assert twenty_agent._resolve_model() == "qwen3.6:latest"


def test_eight_uses_local_llm_path(monkeypatch):
    from agents.eight import eight_agent

    monkeypatch.setattr(eight_agent, "_build_context", lambda _message: "context")
    monkeypatch.setattr(eight_agent, "_resolve_model", lambda: "gemma4:26b")

    called = {}

    def _fake_chat(model, messages, **kwargs):
        called["model"] = model
        called["messages"] = messages
        called["kwargs"] = kwargs
        return "eight ok", 42

    monkeypatch.setattr("core.llm.chat", _fake_chat)
    monkeypatch.setattr("database.save_agent_memory", lambda **kwargs: None)

    answer, tokens = eight_agent.chat("hello", conversation_history=[{"role": "assistant", "content": "prior"}])

    assert answer == "eight ok"
    assert tokens == 42
    assert called["model"] == "gemma4:26b"
    assert called["kwargs"]["stream"] is False
    assert called["messages"][-1]["content"] == "hello"


def test_schema_seeds_twenty_with_qwen36_alias():
    src = (ROOT / "utils" / "db" / "_schema.py").read_text(encoding="utf-8")
    assert "'twenty'" in src
    assert "qwen3.6:latest" in src
