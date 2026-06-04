from __future__ import annotations

import os

from core import model_runtime_gateway as gw
from core.seven_llm import registry
from core.seven_llm import llama_server
from core.seven_llm.registry import ModelEntry
from core.seven_llm.driver_llamacpp import _extract_cli_answer, _messages_to_prompt
from core.seven_llm.inventory import scan_gguf
from core.seven_llm.prompt_profiles import get_profile


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


def test_inventory_reports_mounted_root_and_repo_ggufs():
    snap = scan_gguf(roots=["/mnt/llm", "agents/seven/models"], limit=20)
    roots = {r["path"]: r for r in snap["roots"]}
    assert os.path.abspath("agents/seven/models") in roots
    assert any(m["name"] == "seven-7b-q8_0" for m in snap["models"])
    if "/mnt/llm" in roots:
        assert roots["/mnt/llm"]["exists"] is True
        assert roots["/mnt/llm"]["mounted"] in {True, False}


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
