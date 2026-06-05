from types import SimpleNamespace


def test_library_model_status_prefers_direct_embedding(monkeypatch):
    from flask import Flask
    from frontend.blueprints.library import library_bp

    app = Flask(__name__)
    app.register_blueprint(library_bp)

    import core.llm as llm

    monkeypatch.setattr(llm, "_direct_embedding_model", lambda model: "nomic-embed-text-direct")
    monkeypatch.setattr(llm, "list_models", lambda: SimpleNamespace(models=[]))

    data = app.test_client().get("/api/library/model-status").get_json()

    assert data["ok"] is True
    assert data["ready"] is True
    assert data["runtime"] == "seven-direct"
    assert data["direct_model"] == "nomic-embed-text-direct"


def test_library_pull_model_noops_when_direct_embedding_exists(monkeypatch):
    from flask import Flask
    from frontend.blueprints.library import library_bp

    app = Flask(__name__)
    app.register_blueprint(library_bp)

    import core.llm as llm

    monkeypatch.setattr(llm, "_direct_embedding_model", lambda model: "nomic-embed-text-direct")

    data = app.test_client().post("/api/library/pull-model").get_json()

    assert data["ok"] is True
    assert data["ready"] is True
    assert data["runtime"] == "seven-direct"
    assert "no Ollama pull needed" in data["message"]


def test_knowledge_batch_embeddings_use_shared_llm_path(monkeypatch):
    from lib.knowledge import ingest

    calls = []

    def fake_embeddings(model, prompt):
        calls.append((model, prompt))
        return [float(len(prompt))]

    monkeypatch.setattr("core.llm.embeddings", fake_embeddings)

    assert ingest.embed_batch(["alpha", "beta"]) == [[5.0], [4.0]]
    assert calls == [
        ("nomic-embed-text", "alpha"),
        ("nomic-embed-text", "beta"),
    ]
