from utils.local_runtime_policy import (
    configured_ollama_models,
    is_chat_capable_model,
    is_local_ollama_agent,
    preferred_model_for_agent,
    unused_chat_models,
)


def test_configured_models_ignore_disabled_and_non_ollama_agents():
    agents = [
        {"name": "qwen", "tier": "local", "model": "qwen:latest", "enabled": 1},
        {"name": "sniffles", "tier": "local", "model": "deepseek-r1:7b", "enabled": 0},
        {"name": "seven", "tier": "local", "model": "local-algorithm", "enabled": 1},
        {"name": "nine", "tier": "paid", "model": "external", "enabled": 1},
    ]

    assert configured_ollama_models(agents) == {"qwen:latest"}


def test_agents_keep_their_own_registry_models(monkeypatch):
    from utils import local_runtime_policy as policy

    monkeypatch.setattr(policy, 'PREFERRED_AGENT_MODELS', {'apex': 'apex-direct:20b'})
    monkeypatch.setattr('utils.db.registry.get_agent_models', lambda: {})
    for name in ("qwen", "gemma", "duck", "llama", "mistral"):
        assert preferred_model_for_agent(name, "other:latest") == "other:latest"
    assert preferred_model_for_agent('apex', 'other:latest') == 'apex-direct:20b'
    assert preferred_model_for_agent("eight", "gemma3:latest") == "gemma3:latest"


def test_agent_registry_model_is_used_without_a_global_override(monkeypatch):
    from utils import local_runtime_policy as policy

    monkeypatch.setattr(policy, 'PREFERRED_AGENT_MODELS', {})
    monkeypatch.setattr('utils.db.registry.get_agent_models', lambda: {'qwen': 'qwen2.5:14b-instruct'})
    assert preferred_model_for_agent('qwen', 'qwen:latest') == 'qwen2.5:14b-instruct'


def test_unused_chat_models_excludes_embedding_and_avoided_defaults():
    installed = ["qwen:latest", "qwen2.5:latest", "nomic-embed-text:latest", "mistral:latest"]
    assigned = ["qwen:latest"]

    assert is_chat_capable_model("nomic-embed-text:latest") is False
    assert unused_chat_models(installed, assigned) == ["mistral:latest"]


def test_direct_gguf_is_chat_capable_but_not_ollama():
    agent = {"name": "seven", "tier": "local", "model": "seven-direct:daily", "enabled": 1}

    assert is_local_ollama_agent(agent) is False
    assert configured_ollama_models([agent]) == set()
    assert is_chat_capable_model("seven-direct:daily") is True


def test_registered_apex_direct_model_is_not_ollama(monkeypatch):
    from core.seven_llm import registry
    from core.seven_llm.registry import ModelEntry

    monkeypatch.setattr(registry, 'get', lambda name: ModelEntry(name=name, driver='llamacpp'))
    agent = {'name': 'apex', 'tier': 'local', 'model': 'apex-direct:7b', 'enabled': 1}
    assert is_local_ollama_agent(agent) is False
    assert configured_ollama_models([agent]) == set()
