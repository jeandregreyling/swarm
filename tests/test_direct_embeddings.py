from __future__ import annotations

from types import SimpleNamespace


def test_legacy_nomic_embedding_name_routes_to_direct(monkeypatch):
    from core import llm

    calls = {}

    def fake_get(name):
        if name == "nomic-embed-text":
            return SimpleNamespace(name=name, driver="ollama", role="embed", path=None)
        if name == "nomic-embed-text-direct":
            return SimpleNamespace(
                name=name,
                driver="llamacpp",
                role="embed",
                path="/tmp/nomic-embed-text-direct.gguf",
            )
        return None

    monkeypatch.setattr("core.seven_llm.registry.get", fake_get)
    monkeypatch.setattr(llm.os.path, "isfile", lambda path: True)
    def fake_embeddings(model, prompt):
        calls["args"] = (model, prompt)
        return [0.1]

    monkeypatch.setattr("core.seven_llm.llama_server.embeddings", fake_embeddings)

    assert llm.embeddings("nomic-embed-text", "hello") == [0.1]
    assert calls["args"] == ("nomic-embed-text-direct", "hello")


def test_direct_embedding_model_bypasses_ollama(monkeypatch):
    from core import llm

    calls = {}

    monkeypatch.setattr(
        "core.seven_llm.registry.get",
        lambda name: SimpleNamespace(name=name, driver="llamacpp", role="embed", path="/tmp/embed.gguf")
        if name == "nomic-embed-text-direct"
        else None,
    )
    def fake_embeddings(model, prompt):
        calls["args"] = (model, prompt)
        return [0.2]

    monkeypatch.setattr("core.seven_llm.llama_server.embeddings", fake_embeddings)

    assert llm.embeddings("nomic-embed-text-direct", "hello") == [0.2]
    assert calls["args"] == ("nomic-embed-text-direct", "hello")
