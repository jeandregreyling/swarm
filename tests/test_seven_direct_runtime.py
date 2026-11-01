from __future__ import annotations

import os

from core import model_runtime_gateway as gw
from core.seven_llm import registry
from core.seven_llm import llama_server
from core.seven_llm.registry import ModelEntry
from core.seven_llm.driver_llamacpp import _extract_cli_answer, _messages_to_prompt
from core.seven_llm.inventory import scan_gguf
from core.seven_llm.prompt_profiles import get_profile


def test_direct_chat_reserves_tokens_for_a_final_answer():
    payload = llama_server._chat_payload('apex-direct:7b', [], temperature=0, options={})
    assert payload['max_tokens'] == 2048


def test_direct_chat_uses_registry_profile_and_rejects_reasoning_only(monkeypatch):
    import pytest
    from types import SimpleNamespace

    entry = ModelEntry(name='test-direct', driver='llamacpp', options={'profile': 'llama3'})
    monkeypatch.setattr(registry, 'get', lambda _model: entry)
    monkeypatch.setattr(llama_server, 'ensure', lambda *_args, **_kwargs: SimpleNamespace(endpoint='http://direct-test'))
    posted = {}

    def fake_post(url, json, timeout):
        posted.update(json)
        return SimpleNamespace(status_code=200, json=lambda: {
            'choices': [{'message': {'content': '', 'reasoning_content': 'SKILL fs_write do-not-execute'}}],
            'usage': {'completion_tokens': 10},
        })

    monkeypatch.setattr(llama_server.requests, 'post', fake_post)
    with pytest.raises(RuntimeError, match='no final answer'):
        llama_server.chat('test-direct', [{'role': 'user', 'content': 'hello'}])
    assert posted['stop'] == get_profile('llama3').stops or posted['stop'] == list(get_profile('llama3').stops)


def test_direct_registry_discovers_repo_local_seven_model():
    names = {m.name for m in registry.list_models()}
    assert "seven-direct:daily" in names
    assert "seven-direct:q8" in names
    daily = registry.get("seven-direct:daily")
    assert daily is not None
    assert daily.driver == "llamacpp"
    assert daily.path and daily.path.endswith("qwen2.5-0.5b-instruct-q4_k_m.gguf")
    assert daily.ram_gb <= 1.5
    entry = registry.get("seven-direct:q8")
    assert entry is not None
    assert entry.driver == "llamacpp"
    assert entry.path and entry.path.endswith("seven-7b-q8_0.gguf")


def test_server_environment_loads_adjacent_llama_cpp_libraries(monkeypatch, tmp_path):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing/lib")
    binary = tmp_path / "bin" / "llama-server"
    env = llama_server._server_environment(str(binary))
    assert env["LD_LIBRARY_PATH"].split(os.pathsep) == [
        str(binary.parent),
        "/existing/lib",
    ]


def test_inventory_reports_mounted_root_and_repo_ggufs():
    snap = scan_gguf(roots=["/mnt/llm", "agents/seven/models"], limit=20)
    roots = {r["path"]: r for r in snap["roots"]}
    assert os.path.abspath("agents/seven/models") in roots
    assert any(m["name"] == "seven-7b-q8_0" for m in snap["models"])
    if "/mnt/llm" in roots:
        assert isinstance(roots["/mnt/llm"]["exists"], bool)
        assert isinstance(roots["/mnt/llm"]["mounted"], bool)


def test_llamacpp_cli_prompt_and_output_parser():
    prompt = _messages_to_prompt([
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Reply OK"},
    ])
    assert prompt.endswith("Assistant:")
    raw = """
Loading model...

available commands:
  /exit or Ctrl+C     stop or exit

> System: Be brief.
User: Reply OK
Assistant:

OK.
User:

[ Prompt: 5.2 t/s | Generation: 2.0 t/s ]

Exiting...
"""
    assert _extract_cli_answer(raw, prompt) == "OK."


def test_prompt_profile_infers_seven_chatml():
    profile = get_profile("seven-direct:daily")
    prompt = profile.format_messages([
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Reply OK"},
    ])
    assert profile.name == "chatml"
    assert "<|im_start|>user" in prompt
    assert prompt.endswith("<|im_start|>assistant:")
    assert profile.trim_response("OK<|im_end|>\nnoise") == "OK"


def test_gateway_routes_registered_direct_model_by_name(monkeypatch):
    class FakeDriver:
        def chat(self, model, messages, **kwargs):
            assert model == "seven-direct:q8"
            kwargs["on_token"]("direct")
            kwargs["on_token"](" ok")
            return "direct ok", 2

    monkeypatch.setattr("core.seven_llm.driver_llamacpp.LlamaCppDriver", lambda *a, **k: FakeDriver())
    events = []
    tokens = []
    res = gw.chat(
        "seven-direct:q8",
        [{"role": "user", "content": "hi"}],
        on_event=lambda event: events.append(event["stage"]),
        on_token=tokens.append,
    )
    assert res.ok is True
    assert res.content == "direct ok"
    assert res.tokens == 2
    assert "direct_dispatch" in events
    assert tokens == ["direct", " ok"]


def test_llama_server_chat_uses_openai_endpoint(monkeypatch):
    class FakeProc:
        pid = 12345

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    posted = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "warm ok"}}],
                "usage": {"completion_tokens": 2},
            }

    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server, "_port_for", lambda model: 18123)
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: FakeProc())

    def fake_post(url, json=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        return FakeResponse()

    monkeypatch.setattr(llama_server.requests, "post", fake_post)
    llama_server.stop("seven-direct:q8")
    text, tokens = llama_server.chat(
        "seven-direct:q8",
        [{"role": "user", "content": "hi"}],
        temperature=0,
        options={"num_predict": 8, "timeout": 5},
    )
    assert text == "warm ok"
    assert tokens == 2
    assert posted["url"] == "http://127.0.0.1:18123/v1/chat/completions"
    assert posted["json"]["model"] == "seven-direct:q8"
    assert posted["json"]["max_tokens"] == 8
    llama_server.stop("seven-direct:q8")


def test_llama_server_chat_streams_openai_chunks(monkeypatch):
    class FakeProc:
        pid = 12346

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    class FakeStreamResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=False):
            yield 'data: {"choices":[{"delta":{"content":"warm"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" ok"}}],"usage":{"completion_tokens":2}}'
            yield "data: [DONE]"

    posted = {}
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server, "_port_for", lambda model: 18124)
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: FakeProc())

    def fake_post(url, json=None, stream=None, timeout=None):
        posted["stream"] = stream
        posted["json"] = json
        return FakeStreamResponse()

    monkeypatch.setattr(llama_server.requests, "post", fake_post)
    llama_server.stop("seven-direct:q8")
    chunks = []
    text, tokens = llama_server.chat(
        "seven-direct:q8",
        [{"role": "user", "content": "hi"}],
        options={"num_predict": 8, "timeout": 5},
        on_token=chunks.append,
    )
    assert text == "warm ok"
    assert tokens == 2
    assert chunks == ["warm", " ok"]
    assert posted["stream"] is True
    assert posted["json"]["stream"] is True
    llama_server.stop("seven-direct:q8")


def test_llama_server_resource_guard_blocks_oversized_model(monkeypatch, tmp_path):
    model_path = tmp_path / "too-big.gguf"
    model_path.write_bytes(b"GGUF")
    registry.register(ModelEntry(
        name="pytest-too-big-direct",
        driver="llamacpp",
        role="general",
        path=str(model_path),
        ram_gb=64.0,
    ))
    monkeypatch.setattr(llama_server, "_meminfo_gb", lambda: {
        "total_gb": 16.0,
        "available_gb": 12.0,
        "reserve_gb": 3.0,
        "single_resident": True,
    })
    try:
        llama_server.ensure("pytest-too-big-direct", timeout_s=1)
    except RuntimeError as exc:
        assert "resource guard blocked pytest-too-big-direct" in str(exc)
    else:
        raise AssertionError("oversized direct model should be blocked")


def test_llama_server_single_resident_stops_previous_model(monkeypatch):
    class OldProc:
        pid = 111
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    class NewProc:
        pid = 222

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    old = OldProc()
    llama_server.stop()
    monkeypatch.setattr(llama_server, "SINGLE_RESIDENT", True)
    llama_server._PROCS["seven-direct:q8"] = old
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server, "_port_for", lambda model: 18125)
    monkeypatch.setattr(llama_server, "_meminfo_gb", lambda: {
        "total_gb": 32.0,
        "available_gb": 24.0,
        "reserve_gb": 3.0,
        "single_resident": True,
    })
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: NewProc())
    handle = llama_server.ensure("seven-direct:fp16", timeout_s=1)
    assert handle.pid == 222
    assert old.terminated is True
    assert "seven-direct:q8" not in llama_server._PROCS
    assert "seven-direct:fp16" in llama_server._PROCS
    llama_server.stop()


def _register_direct(tmp_path, name, **kwargs):
    model_path = tmp_path / f"{name.replace(':', '_')}.gguf"
    model_path.write_bytes(b"GGUF")
    registry.register(ModelEntry(name=name, driver="llamacpp", role="general", path=str(model_path), **kwargs))


def test_llama_server_reuses_same_model_started_by_another_process(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-shared-direct", ram_gb=2.0)
    llama_server.stop()
    monkeypatch.setattr(llama_server, "_foreign_servers", lambda: [
        {"pid": 4242, "model": "pytest-shared-direct", "port": 18999},
    ])
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: endpoint.endswith(":18999"))

    def no_spawn(*_a, **_k):
        raise AssertionError("must reuse the existing server, not spawn a duplicate")

    monkeypatch.setattr(llama_server.subprocess, "Popen", no_spawn)
    handle = llama_server.ensure("pytest-shared-direct", timeout_s=1)
    assert (handle.pid, handle.port) == (4242, 18999)
    assert "pytest-shared-direct" not in llama_server._PROCS


def test_llama_server_single_resident_stops_other_processes_servers(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-new-direct", ram_gb=2.0)

    class NewProc:
        pid = 333

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

    killed = []
    llama_server.stop()
    monkeypatch.setattr(llama_server, "SINGLE_RESIDENT", True)
    monkeypatch.setattr(llama_server, "_foreign_servers", lambda: [
        {"pid": 5151, "model": "pytest-old-direct", "port": 18998},
    ])
    monkeypatch.setattr(llama_server, "_kill_pid", lambda pid, **_k: killed.append(pid))
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server, "_port_for", lambda model: 18126)
    monkeypatch.setattr(llama_server, "_meminfo_gb", lambda: {
        "total_gb": 32.0, "available_gb": 24.0, "reserve_gb": 3.0, "single_resident": True,
    })
    monkeypatch.setattr(llama_server, "default_binary", lambda: __file__)
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: NewProc())
    handle = llama_server.ensure("pytest-new-direct", timeout_s=1)
    assert handle.pid == 333
    assert killed == [5151]
    llama_server.stop()


def test_llama_server_guard_charges_vram_overflow_to_system_ram(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-gpu-direct", ram_gb=12.0, options={"ngl": 999})
    llama_server.stop()
    monkeypatch.setattr(llama_server, "_vram_free_gb", lambda: 2.0)
    monkeypatch.setattr(llama_server, "_meminfo_gb", lambda: {
        "total_gb": 64.0, "available_gb": 8.0, "reserve_gb": 3.0, "single_resident": True,
    })
    try:
        llama_server.ensure("pytest-gpu-direct", timeout_s=1)
    except RuntimeError as exc:
        assert "requires 10.0GB" in str(exc)
    else:
        raise AssertionError("VRAM overflow into GTT must be charged against system RAM")


class _LiveProc:
    def __init__(self, pid):
        self.pid = pid
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def _budget_env(monkeypatch, *, available_gb, vram_free=None, budget=60.0):
    llama_server.stop()
    monkeypatch.setattr(llama_server, "SINGLE_RESIDENT", False)
    monkeypatch.setattr(llama_server, "RAM_BUDGET_GB", budget)
    monkeypatch.setattr(llama_server, "_vram_free_gb", lambda: vram_free)
    monkeypatch.setattr(llama_server, "_server_alive", lambda endpoint: True)
    monkeypatch.setattr(llama_server, "default_binary", lambda: __file__)
    mem = {"available_gb": available_gb}
    monkeypatch.setattr(llama_server, "_meminfo_gb", lambda: {
        "total_gb": 62.0, "available_gb": mem["available_gb"], "reserve_gb": 3.0,
    })
    return mem


def test_llama_server_budget_keeps_models_resident_while_they_fit(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-a", ram_gb=4.0, options={"ngl": 0})
    _register_direct(tmp_path, "pytest-b", ram_gb=4.0, options={"ngl": 0})
    _budget_env(monkeypatch, available_gb=40.0)
    procs = iter([_LiveProc(401), _LiveProc(402)])
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: next(procs))
    llama_server.ensure("pytest-a", timeout_s=1)
    llama_server.ensure("pytest-b", timeout_s=1)
    assert {"pytest-a", "pytest-b"} <= set(llama_server._PROCS)
    llama_server.stop()


def test_llama_server_budget_evicts_least_recently_used(monkeypatch, tmp_path):
    for name in ("pytest-old", "pytest-recent", "pytest-next"):
        _register_direct(tmp_path, name, ram_gb=10.0, options={"ngl": 0})
    mem = _budget_env(monkeypatch, available_gb=40.0, budget=25.0)
    procs = {401: _LiveProc(401), 402: _LiveProc(402), 403: _LiveProc(403)}
    order = iter(procs.values())
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: next(order))
    llama_server.ensure("pytest-old", timeout_s=1)
    llama_server.ensure("pytest-recent", timeout_s=1)
    llama_server.ensure("pytest-old", timeout_s=1)  # reuse refreshes its LRU stamp
    mem["available_gb"] = 20.0
    llama_server.ensure("pytest-next", timeout_s=1)
    assert procs[402].terminated is True
    assert procs[401].terminated is False
    assert set(llama_server._PROCS) == {"pytest-old", "pytest-next"}
    llama_server.stop()


def test_llama_server_gpu_spill_prefers_evicting_gpu_residents(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-cpu", ram_gb=5.0, options={"ngl": 0})
    _register_direct(tmp_path, "pytest-gpu-old", ram_gb=9.0)
    _register_direct(tmp_path, "pytest-gpu-new", ram_gb=9.0)
    mem = _budget_env(monkeypatch, available_gb=10.0, vram_free=15.0)
    procs = {501: _LiveProc(501), 502: _LiveProc(502), 503: _LiveProc(503)}
    order = iter(procs.values())
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: next(order))
    llama_server.ensure("pytest-gpu-old", timeout_s=1)
    llama_server.ensure("pytest-cpu", timeout_s=1)
    vram = {"free": 6.0}
    monkeypatch.setattr(llama_server, "_vram_free_gb", lambda: vram["free"])
    real_stop = llama_server._stop_locked

    def stop_and_free(name, **kw):
        if name == "pytest-gpu-old":
            vram["free"] = 15.0
        return real_stop(name, **kw)

    monkeypatch.setattr(llama_server, "_stop_locked", stop_and_free)
    mem["available_gb"] = 6.0
    llama_server.ensure("pytest-gpu-new", timeout_s=1)
    assert procs[501].terminated is True  # older GPU model made room in VRAM
    assert procs[502].terminated is False  # the more recent CPU model is untouched
    llama_server.stop()


def test_llama_server_reaps_servers_idle_past_ttl(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-idle", ram_gb=2.0, ttl_seconds=60, options={"ngl": 0})
    _register_direct(tmp_path, "pytest-fresh", ram_gb=2.0, options={"ngl": 0})
    _budget_env(monkeypatch, available_gb=40.0)
    procs = iter([_LiveProc(601), _LiveProc(602)])
    monkeypatch.setattr(llama_server.subprocess, "Popen", lambda *a, **k: next(procs))
    llama_server.ensure("pytest-idle", timeout_s=1)
    state = llama_server._load_state()
    state["pytest-idle"]["last_used"] -= 120
    llama_server._save_state(state)
    llama_server.ensure("pytest-fresh", timeout_s=1)
    assert set(llama_server._PROCS) == {"pytest-fresh"}
    llama_server.stop()


def test_llama_server_launch_flags_avoid_hidden_host_memory(monkeypatch, tmp_path):
    _register_direct(tmp_path, "pytest-flags", ram_gb=2.0)
    _budget_env(monkeypatch, available_gb=40.0, vram_free=15.0)
    seen = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return _LiveProc(701)

    monkeypatch.setattr(llama_server.subprocess, "Popen", fake_popen)
    llama_server.ensure("pytest-flags", timeout_s=1)
    cmd = seen["cmd"]
    assert cmd[cmd.index("--load-mode") + 1] == "none"
    assert cmd[cmd.index("--cache-ram") + 1] == str(llama_server.CACHE_RAM_MIB)
    assert "--n-gpu-layers" not in cmd  # llama-server auto-fit decides the split
    assert seen["kwargs"]["start_new_session"] is True
    llama_server.stop()


def test_llama_server_chat_applies_modelfile_defaults_and_retries_evicted(monkeypatch):
    from types import SimpleNamespace

    import requests

    entry = ModelEntry(name="pytest-mf:latest", driver="llamacpp",
                       options={"default_system": "You are Fred.", "temperature": 0.15})
    monkeypatch.setattr(registry, "get", lambda name: entry if name in {"pytest-mf", "pytest-mf:latest"} else None)
    ensured = []
    monkeypatch.setattr(llama_server, "ensure", lambda model, **_k: ensured.append(model) or SimpleNamespace(
        endpoint=f"http://direct-{len(ensured)}"))
    posted = []

    def fake_post(url, json, timeout):
        posted.append((url, json))
        if len(posted) == 1:
            raise requests.ConnectionError("server evicted")
        return SimpleNamespace(status_code=200, json=lambda: {
            "choices": [{"message": {"content": "ok"}}], "usage": {"completion_tokens": 1}})

    monkeypatch.setattr(llama_server.requests, "post", fake_post)
    assert llama_server.chat("pytest-mf", [{"role": "user", "content": "hi"}]) == ("ok", 1)
    assert ensured == ["pytest-mf:latest", "pytest-mf:latest"]
    url, payload = posted[-1]
    assert url.startswith("http://direct-2")
    assert payload["model"] == "pytest-mf:latest"
    assert payload["temperature"] == 0.15
    assert payload["messages"][0] == {"role": "system", "content": "You are Fred."}


def _write_ollama_store(root):
    import hashlib
    import json

    blobs = root / "blobs"
    blobs.mkdir(parents=True)

    def blob(data: bytes) -> str:
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        (blobs / digest.replace(":", "-")).write_bytes(data)
        return digest

    def manifest(layers):
        return json.dumps({"layers": [
            {"mediaType": f"application/vnd.ollama.image.{kind}", "digest": digest, "size": size}
            for kind, digest, size in layers
        ]}).encode()

    weights = blob(b"GGUF-weights")
    params = blob(json.dumps({"num_ctx": 4096, "num_gpu": 0, "num_thread": 6, "temperature": 0.15}).encode())
    system = blob(b"You are Mistral Small.")
    v2 = root / "manifests-v2" / "ollama.com" / "library" / "fred-cpu"
    v2.mkdir(parents=True)
    fred = blob(manifest([("model", weights, 2 * 1024 ** 3), ("params", params, 1), ("system", system, 1)]))
    (v2 / "24b").symlink_to(blobs / fred.replace(":", "-"))
    v1 = root / "manifests" / "registry.ollama.ai" / "library" / "nomic-embed-text"
    v1.mkdir(parents=True)
    (v1 / "latest").write_bytes(manifest([("model", blob(b"GGUF-embed"), 300 * 1024 ** 2)]))


def test_registry_serves_ollama_store_models_directly(monkeypatch, tmp_path):
    from utils.local_runtime_policy import is_direct_runtime_model

    _write_ollama_store(tmp_path)
    monkeypatch.setenv("SWARM_OLLAMA_STORE", str(tmp_path))
    try:
        registry.reload()
        fred = registry.get("fred-cpu:24b")
        assert fred.driver == "llamacpp" and fred.path.startswith(str(tmp_path / "blobs"))
        assert fred.ctx == 4096
        assert fred.options["ngl"] == 0 and fred.options["threads"] == 6
        assert fred.options["temperature"] == 0.15
        assert fred.options["default_system"] == "You are Mistral Small."
        embed = registry.get("nomic-embed-text")  # bare name resolves like Ollama's ':latest'
        assert embed.name == "nomic-embed-text:latest"
        assert embed.role == "embed" and embed.options["embedding"] is True
        assert is_direct_runtime_model("fred-cpu:24b")
    finally:
        monkeypatch.setenv("SWARM_OLLAMA_STORE", "")
        registry.reload()


def test_direct_chat_translates_ollama_format_to_openai_response_format():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    as_schema = llama_server._chat_payload("m", [], temperature=0, options={"response_format": schema})
    assert as_schema["response_format"] == {"type": "json_object", "schema": schema}
    as_json = llama_server._chat_payload("m", [], temperature=0, options={"response_format": "json"})
    assert as_json["response_format"] == {"type": "json_object"}
    openai = {"type": "json_schema", "json_schema": {"name": "x", "schema": schema}}
    assert llama_server._chat_payload("m", [], temperature=0, options={"response_format": openai})["response_format"] == openai


def test_core_llm_routes_registered_models_to_llama_server(monkeypatch, tmp_path):
    from core import llm

    _register_direct(tmp_path, "pytest-llm-direct", ram_gb=2.0)
    calls = {}

    def fake_chat(model, messages, **kwargs):
        calls.update(model=model, **kwargs)
        kwargs["on_token"] and kwargs["on_token"]("hi")
        return "hi", 1

    monkeypatch.setattr(llama_server, "chat", fake_chat)
    monkeypatch.setattr(llm, "_get_ollama", lambda: (_ for _ in ()).throw(AssertionError("must not use Ollama")))
    chunks = []
    assert llm.chat("pytest-llm-direct", [{"role": "user", "content": "x"}], stream=True,
                    temperature=0.2, on_chunk=chunks.append) == ("hi", 1)
    assert calls["model"] == "pytest-llm-direct" and calls["temperature"] == 0.2
    assert chunks == ["hi"]
    monkeypatch.setattr(llm, "_ollama_list", lambda: (_ for _ in ()).throw(ConnectionError("ollama down")))
    names = [m.model for m in llm.list_models().models]
    assert "pytest-llm-direct" in names


def test_direct_chat_converts_ollama_images_to_content_parts():
    payload = llama_server._chat_payload(
        "m", [{"role": "user", "content": "describe", "images": ["QUJD"]}], temperature=0, options={})
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
    assert "images" not in payload["messages"][0]


def test_direct_runtime_ttl_override_is_persisted_and_used_for_reaping(tmp_path, monkeypatch):
    _register_direct(tmp_path, "pytest-ttl-direct", ram_gb=2.0, ttl_seconds=30)
    state_path = tmp_path / "llama-state.json"
    monkeypatch.setattr(llama_server, "STATE_PATH", str(state_path))
    assert llama_server.set_ttl("pytest-ttl-direct", 5) == 5
    state = llama_server._load_state()
    state["pytest-ttl-direct"]["last_used"] = 1.0
    stopped = []
    monkeypatch.setattr(llama_server, "_load_state", lambda: state)
    monkeypatch.setattr(llama_server, "_residents", lambda: [{"model": "pytest-ttl-direct", "pid": 42, "own": False}])
    monkeypatch.setattr(llama_server, "_stop_resident", lambda resident: stopped.append(resident["model"]))

    llama_server._reap_idle(state, keep="")

    assert stopped == ["pytest-ttl-direct"]


def test_chat_payload_alternates_roles_for_strict_templates():
    payload = llama_server._chat_payload('gemma3:12b', [
        {'role': 'system', 'content': 'sys a'},
        {'role': 'system', 'content': 'sys b'},
        {'role': 'assistant', 'content': 'qwen: hi'},
        {'role': 'assistant', 'content': 'llama: hey'},
        {'role': 'system', 'content': 'relay note'},
        {'role': 'user', 'content': 'go', 'images': ['AAAA']},
    ], temperature=0, options={})
    msgs = payload['messages']
    assert [m['role'] for m in msgs] == ['system', 'user', 'assistant', 'user']
    assert msgs[0]['content'] == 'sys a\n\nsys b'
    assert msgs[2]['content'] == 'qwen: hi\n\nllama: hey'
    assert msgs[3]['content'][0] == {'type': 'text', 'text': 'relay note\n\ngo'}
    assert msgs[3]['content'][1]['type'] == 'image_url'
