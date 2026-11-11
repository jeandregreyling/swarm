import pytest
from types import SimpleNamespace

from core.seven_llm import llama_server, registry
from core.seven_llm.driver_llamacpp import LlamaCppDriver


@pytest.fixture
def external_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("External APEX must never load, admit, evict, or stop a model")

    for name in ("_admit", "_reap_idle", "_foreign_servers", "_load_state", "_stop_locked"):
        monkeypatch.setattr(llama_server, name, forbidden)
    monkeypatch.setattr(llama_server.subprocess, "Popen", forbidden)
    monkeypatch.setattr(LlamaCppDriver, "_load", forbidden)
    monkeypatch.setattr(LlamaCppDriver, "_chat_cli", forbidden)
    monkeypatch.setattr(llama_server.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": [{"id": "gpt-oss:20B"}, {"id": "qwen2.5:14b-instruct"}]},
    ))


def test_external_model_mismatch_never_mislabels_or_loads(monkeypatch, external_only):
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": [{"id": "qwen2.5:14b-instruct"}]},
    ))
    with pytest.raises(RuntimeError, match="does not serve 'gpt-oss:20B'; no fallback"):
        LlamaCppDriver().chat("gpt-oss:20b", [{"role": "user", "content": "Hello"}])


@pytest.mark.parametrize("name,api_model", [
    ("apex-direct:20b", "gpt-oss:20B"),
    ("gpt-oss:20b", "gpt-oss:20B"),
    ("qwen2.5:14b-instruct", "qwen2.5:14b-instruct"),
])
def test_external_registry_routes_without_spawning(monkeypatch, external_only, name, api_model):
    entry = registry.get(name)
    assert entry.endpoint == "http://127.0.0.1:8080"
    assert entry.options["api_model"] == api_model
    assert entry.options["raw_completion"] is False
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: endpoint == entry.endpoint)
    stages = []
    handle = llama_server.ensure(name, progress=stages.append)
    assert (handle.endpoint, handle.port, handle.pid) == (entry.endpoint, 8080, 0)
    assert stages[0]["external"] is True

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "APEX"}}], "usage": {"completion_tokens": 1}}

    def post(url, *, json, timeout):
        assert url == entry.endpoint + "/v1/chat/completions"
        assert json["model"] == api_model
        assert json["messages"][0] == {"role": "system", "content": "You are APEX."}
        return Response()

    monkeypatch.setattr(llama_server.requests, "post", post)
    # Caller mode overrides must not bypass the external service.
    assert LlamaCppDriver().chat(
        name, [{"role": "system", "content": "You are APEX."}, {"role": "user", "content": "Identity?"}],
        options={"mode": "cli", "api_model": "wrong-model", "max_tokens": 32},
    ) == ("APEX", 1)
    assert llama_server.stop(name) == 0


@pytest.mark.parametrize("name", ["apex-direct:20b", "gpt-oss:20b", "qwen2.5:14b-instruct"])
def test_external_server_offline_never_falls_back(monkeypatch, external_only, name):
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: False)
    with pytest.raises(RuntimeError, match="External llama-server unavailable"):
        LlamaCppDriver().chat(name, [{"role": "user", "content": "Hello"}])


def test_external_connection_retry_never_loads(monkeypatch, external_only):
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    attempts = []

    def disconnected(handle):
        attempts.append(handle.endpoint)
        raise llama_server.requests.ConnectionError("service disconnected")

    with pytest.raises(llama_server.requests.ConnectionError):
        llama_server._retry_if_evicted("apex-direct:20b", {}, disconnected)
    assert attempts == ["http://127.0.0.1:8080"] * 2
