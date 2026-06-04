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


def test_twenty_gateway_uses_long_local_timeouts(monkeypatch):
    from agents.twenty import twenty_agent

    monkeypatch.setattr(twenty_agent, "_build_context", lambda _message: "")
    monkeypatch.setattr(twenty_agent, "_resolve_model", lambda: "qwen3.6:latest")
    monkeypatch.setattr("database.save_agent_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr("coding_bible.inject", lambda prompt: prompt)

    called = {}

    def _fake_gateway(model, messages, **kwargs):
        called["model"] = model
        called["kwargs"] = kwargs
        return "twenty ok", 12

    monkeypatch.setattr("core.llm.chat_via_gateway", _fake_gateway)

    answer, tokens = twenty_agent.chat("hello")

    assert answer == "twenty ok"
    assert tokens == 12
    assert called["model"] == "qwen3.6:latest"
    assert called["kwargs"]["idle_timeout_s"] == twenty_agent.GATEWAY_IDLE_TIMEOUT_S
    assert called["kwargs"]["absolute_timeout_s"] == twenty_agent.GATEWAY_ABSOLUTE_TIMEOUT_S


def test_eight_uses_runtime_gateway_path(monkeypatch):
    from agents.eight import eight_agent

    monkeypatch.setattr(eight_agent, "_build_context", lambda _message: "context")
    monkeypatch.setattr(eight_agent, "_resolve_model", lambda: "gemma4:26b")

    called = {}

    def _fake_gateway(model, messages, **kwargs):
        called["model"] = model
        called["messages"] = messages
        called["kwargs"] = kwargs
        return "eight ok", 42

    monkeypatch.setattr("core.llm.chat_via_gateway", _fake_gateway)
    monkeypatch.setattr("database.save_agent_memory", lambda **kwargs: None)

    answer, tokens = eight_agent.chat("hello", conversation_history=[{"role": "assistant", "content": "prior"}])

    assert answer == "eight ok"
    assert tokens == 42
    assert called["model"] == "gemma4:26b"
    assert callable(called["kwargs"]["stage_cb"]) or called["kwargs"]["stage_cb"] is None
    assert callable(called["kwargs"]["on_chunk"])
    assert called["messages"][-1]["content"] == "hello"


def test_seven_uses_direct_runtime_gateway(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "SEVEN_MODEL", "seven-direct:daily")
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])
    monkeypatch.setattr(seven_agent, "_load_kc_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_open_curiosity", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_pillars_context", lambda: {})
    monkeypatch.setattr(seven_agent, "_compose", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr("database.save_agent_memory", lambda *args, **kwargs: None)

    called = {}

    def _fake_gateway(model, messages, **kwargs):
        called["model"] = model
        called["messages"] = messages
        called["kwargs"] = kwargs
        return "seven ok", 7

    monkeypatch.setattr("core.llm.chat_via_gateway", _fake_gateway)

    stages = []
    answer, tokens = seven_agent.chat("hello", stage_cb=lambda text, _eta=None: stages.append(text))

    assert answer == "seven ok"
    assert tokens == 7
    assert called["model"] == "seven-direct:daily"
    assert called["kwargs"]["keep_alive"] == 0
    assert called["messages"][-1]["content"] == "hello"
    assert "thinking · seven merged model" in stages


def test_seven_direct_runtime_failure_falls_back_to_state(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(seven_agent, "SEVEN_MODEL", "seven-direct:daily")
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"queued": 0, "running": 0, "failed": 0, "tickets": 0, "proposals": 0, "local_agents": ["Seven"]})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda _message: [])
    monkeypatch.setattr(seven_agent, "_load_kc_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_identity_beliefs", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_open_curiosity", lambda *args, **kwargs: [])
    monkeypatch.setattr(seven_agent, "_load_pillars_context", lambda: {})
    monkeypatch.setattr(seven_agent, "_compose", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr("database.save_agent_memory", lambda *args, **kwargs: None)

    stopped = []
    monkeypatch.setattr("core.seven_llm.llama_server.stop", lambda model: stopped.append(model) or 1)
    monkeypatch.setattr(
        "core.llm.chat_via_gateway",
        lambda *args, **kwargs: ("[local runtime error: timeout]", 0),
    )

    answer, tokens = seven_agent.chat("hello")

    assert tokens == 0
    assert "My model is offline right now" in answer
    assert stopped == ["seven-direct:daily"]


def test_mistral_uses_shorter_gateway_no_token_timeout(monkeypatch):
    from agents.mistral import mistral_agent

    monkeypatch.setattr(mistral_agent, "_build_context", lambda _message: "context")
    monkeypatch.setattr("coding_bible.inject", lambda prompt: prompt)
    monkeypatch.setattr("database.save_agent_memory", lambda **kwargs: None)

    called = {}

    def _fake_gateway(model, messages, **kwargs):
        called["model"] = model
        called["kwargs"] = kwargs
        return "mistral ok", 9

    def _fake_skill_loop(agent_name, call_fn, messages, emit_fn, **kwargs):
        return call_fn(messages)

    monkeypatch.setattr("core.llm.chat_via_gateway", _fake_gateway)
    monkeypatch.setattr("agents.skills_loop.run_skill_loop", _fake_skill_loop)

    answer, tokens = mistral_agent.chat("hello")

    assert answer == "mistral ok"
    assert tokens == 9
    assert called["model"] == "mistral:latest"
    assert called["kwargs"]["idle_timeout_s"] == mistral_agent.GATEWAY_IDLE_TIMEOUT_S
    assert called["kwargs"]["absolute_timeout_s"] == mistral_agent.GATEWAY_ABSOLUTE_TIMEOUT_S


def test_schema_seeds_twenty_with_qwen36_alias():
    src = (ROOT / "utils" / "db" / "_schema.py").read_text(encoding="utf-8")
    assert "'twenty'" in src
    assert "qwen3.6:latest" in src
