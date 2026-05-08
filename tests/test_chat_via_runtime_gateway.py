"""Tests for routing local agents through the runtime gateway.

Covers PACKET-07 STEP-ROUTE-CHAT-THROUGH-RUNTIME-GATEWAY-20260430:
- core.llm.chat_via_gateway exists, returns (content, tokens)
- gateway events surface as stage_cb labels
- model_runtime_gateway.chat fires on_token / on_event callbacks
- local streaming agents reference the gateway helper, not the legacy
  on_chunk-only path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import llm
from core import model_runtime_gateway as gw


class _FakePostResp:
    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line


def _stream_lines():
    import json as _json
    return [
        _json.dumps({"message": {"content": "Hello"}, "done": False}),
        _json.dumps({"message": {"content": " world"}, "done": False}),
        _json.dumps({"message": {"content": "."}, "done": True, "eval_count": 7}),
    ]


def test_gateway_chat_fires_event_and_token_callbacks(monkeypatch):
    sent = {"posts": 0}

    def fake_post(url, json=None, stream=None, timeout=None):
        sent["posts"] += 1
        return _FakePostResp(_stream_lines())

    monkeypatch.setattr(gw.requests, "post", fake_post)

    tokens_seen = []
    events_seen = []

    res = gw.chat(
        "llama3.2",
        [{"role": "user", "content": "hi"}],
        on_token=lambda piece: tokens_seen.append(piece),
        on_event=lambda evt: events_seen.append(evt["stage"]),
    )
    assert res.ok is True
    assert res.content == "Hello world."
    assert res.tokens == 7
    assert tokens_seen == ["Hello", " world", "."]
    # Must include lifecycle markers in order.
    assert "queued" in events_seen
    assert "dispatch" in events_seen
    assert "first_token" in events_seen
    assert "completed" == events_seen[-1]


def test_chat_via_gateway_translates_events_to_stage_cb(monkeypatch):
    def fake_post(url, json=None, stream=None, timeout=None):
        return _FakePostResp(_stream_lines())

    monkeypatch.setattr(gw.requests, "post", fake_post)

    stages = []

    def stage_cb(text, _extra=None):
        stages.append(text)

    chunks = []
    content, tokens = llm.chat_via_gateway(
        "llama3.2",
        [{"role": "user", "content": "hi"}],
        stage_cb=stage_cb,
        on_chunk=chunks.append,
        temperature=0.6,
    )
    assert content == "Hello world."
    assert tokens == 7
    assert chunks == ["Hello", " world", "."]
    # The translator must produce human-readable stage labels.
    joined = " | ".join(stages)
    assert "gateway: queued" in joined
    assert "gateway: dispatch" in joined
    assert "gateway: first token" in joined
    assert "gateway: completed" in joined


def test_chat_via_gateway_returns_partial_on_failure(monkeypatch):
    def fake_post(url, json=None, stream=None, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(gw.requests, "post", fake_post)

    stages = []
    content, tokens = llm.chat_via_gateway(
        "llama3.2",
        [{"role": "user", "content": "hi"}],
        stage_cb=lambda text, _extra=None: stages.append(text),
    )
    assert content == ""
    assert tokens == 0
    assert any("gateway: failed" in s for s in stages)


def test_chat_via_gateway_tolerates_single_arg_stage_cb(monkeypatch):
    def fake_post(url, json=None, stream=None, timeout=None):
        return _FakePostResp(_stream_lines())

    monkeypatch.setattr(gw.requests, "post", fake_post)

    stages = []
    # Single-arg callback to confirm the helper falls back gracefully.
    content, _ = llm.chat_via_gateway(
        "llama3.2",
        [{"role": "user", "content": "hi"}],
        stage_cb=lambda text: stages.append(text),
    )
    assert content == "Hello world."
    assert any("gateway: dispatch" in s for s in stages)


@pytest.mark.parametrize(
    "path",
    [
        "agents/llama/llama_agent.py",
        "agents/gemma/gemma_agent.py",
        "agents/qwen/qwen_agent.py",
        "agents/mistral/mistral_agent.py",
        "agents/deepseek_local/deepseek_local_agent.py",
        "agents/phi3/phi3_agent.py",
        "agents/twenty/twenty_agent.py",
    ],
)
def test_local_agents_use_gateway_helper(path):
    src = Path(path).read_text(encoding="utf-8")
    assert "_llm.chat_via_gateway(" in src, f"{path} must route through chat_via_gateway"
    # The legacy stream call site must be gone for these agents.
    assert "_llm.chat(MODEL" not in src and "_llm.chat(model_name" not in src, (
        f"{path} still has a direct _llm.chat stream call"
    )
