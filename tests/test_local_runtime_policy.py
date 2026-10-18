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


def test_qwen_preferred_model_is_fast_cpu_default():
    assert preferred_model_for_agent("qwen", "qwen2.5:latest") == "qwen2.5:7b-instruct"
    assert preferred_model_for_agent("gemma", "gemma3:latest") == "qwen2.5:7b-instruct"
    assert preferred_model_for_agent("duck", "qwen2.5:latest") == "qwen:latest"
    assert preferred_model_for_agent("llama", "llama3.2:latest") == "llama3.2:latest"


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
