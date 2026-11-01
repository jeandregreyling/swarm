import json
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "utils")]

from core.chat_continuity import ContinuityChat, NOTICE, storage_fault

AGENTS = [{"name": "qwen", "model": "qwen2.5-coder:7b", "tier": "local"}]


def corrupt_connection():
    raise sqlite3.DatabaseError("database disk image is malformed")


def test_detects_real_conversation_failure_and_does_not_hide_unrelated_errors():
    assert "malformed" in storage_fault(corrupt_connection)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        storage_fault(lambda: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")))


def test_separate_durable_history_survives_new_instance_without_primary(tmp_path):
    chat = ContinuityChat(tmp_path)
    observed = []

    def model(model, messages):
        observed.append(messages)
        assert model == AGENTS[0]["model"]
        return "Actual local reply.", 4

    first = chat.send({"message": "hello"}, AGENTS, "ghost", "malformed", model)
    assert first["mode"] == "local_recovery"
    assert NOTICE in first["response"]
    second = ContinuityChat(tmp_path).send(
        {"message": "continue", "conversation_id": first["conversation_id"]},
        AGENTS, "ghost", "malformed", model)
    assert second["conversation_id"] == first["conversation_id"]
    assert any(message["content"] == "hello" for message in observed[-1])
    thread = chat.read(first["conversation_id"], "ghost")
    assert len(thread["messages"]) == 4
    assert thread["source"] == "local-recovery-chat"
    with pytest.raises(PermissionError):
        chat.read(first["conversation_id"], "another-user")
    assert chat.recent("another-user") == []


def test_runner_failure_preserves_input_and_exact_error(tmp_path):
    chat = ContinuityChat(tmp_path)
    with pytest.raises(RuntimeError, match="runner unavailable"):
        chat.send({"message": "keep this"}, AGENTS, "ghost", "malformed",
                  lambda *_: ("[local runtime error: runner unavailable]", 0))
    thread = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert thread["messages"][0]["content"] == "keep this"
    assert "runner unavailable" in thread["last_error"]["error"]


def test_wrapper_notice_is_not_reinforced_in_model_history(tmp_path):
    chat = ContinuityChat(tmp_path)
    observed = []

    def model(_, messages):
        observed.append(messages)
        return NOTICE + "\n\n" + NOTICE + "\n\nI coordinate JD's local work.", 12

    first = chat.send({"message": "hello"}, AGENTS, "ghost", "malformed", model)
    assert first["response"].count(NOTICE) == 1
    second = chat.send(
        {"message": "what do you coordinate?", "conversation_id": first["conversation_id"]},
        AGENTS, "ghost", "malformed", model)
    assert second["response"].count(NOTICE) == 1
    assistants = [message for message in observed[-1] if message["role"] == "assistant"]
    assert assistants and all(NOTICE not in message["content"] for message in assistants)


def test_duplicate_old_notice_readback_does_not_rewrite_original_journal(tmp_path):
    chat = ContinuityChat(tmp_path)
    first = chat.send({"message": "hello"}, AGENTS, "ghost", "malformed",
                      lambda *_: ("A useful answer.", 4))
    path = chat.path(first["conversation_id"])
    thread = json.loads(path.read_text())
    thread["messages"][-1]["content"] = NOTICE + "\n\n" + NOTICE + "\n\nA useful answer."
    path.write_text(json.dumps(thread))
    original = path.read_bytes()
    readback = chat.read(first["conversation_id"], "ghost")
    assert readback["messages"][-1]["content"].count(NOTICE) == 1
    assert path.read_bytes() == original


def test_wrapper_does_not_strip_user_quotes_or_mid_answer_evidence(tmp_path):
    chat = ContinuityChat(tmp_path)
    quoted = "A log quoted this banner: " + NOTICE
    observed = []

    def model(_, messages):
        observed.append(messages)
        return quoted, 5

    first = chat.send({"message": NOTICE}, AGENTS, "ghost", "malformed", model)
    assert observed[0][-1]["content"] == NOTICE
    assert first["response"] == NOTICE + "\n\n" + quoted


def test_banner_only_generation_is_not_accepted_as_useful_answer(tmp_path):
    chat = ContinuityChat(tmp_path)
    with pytest.raises(RuntimeError):
        chat.send({"message": "hello"}, AGENTS, "ghost", "malformed",
                  lambda *_: (NOTICE + "\n\n" + NOTICE, 8))


def test_saved_lesson_is_loaded_in_fresh_context_without_wrapper_banner(tmp_path):
    observed = []

    def model(_, messages):
        observed.append(messages)
        return "What specific error are you investigating?", 8

    ContinuityChat(tmp_path).send({"message": "Help diagnose this"}, AGENTS, "ghost", "malformed", model)
    prompt = observed[0][0]["content"]
    assert '"id": "conversation.coordinator"' in prompt
    assert '"version": "1.0.0"' in prompt
    assert "Gemma coordinates JD's local work" in prompt
    assert "The current recovery thread is available" in prompt
    assert NOTICE not in prompt


@pytest.fixture
def live_route(tmp_path, monkeypatch):
    from frontend.blueprints import chat, conversations
    import core.chat_continuity
    from core import llm

    store = ContinuityChat(tmp_path)
    monkeypatch.setattr(core.chat_continuity, "ContinuityChat", lambda: store)
    monkeypatch.setattr(chat, "_reg_routable", lambda: AGENTS)
    monkeypatch.setattr(chat, "_resolve_identity_or_response",
                        lambda _: ({"effective_user": "ghost"}, None))
    monkeypatch.setattr(chat, "get_current_user", lambda: None)
    monkeypatch.setattr(chat, "get_connection", corrupt_connection)
    monkeypatch.setattr(chat, "new_conversation", lambda *_args, **_kwargs: pytest.fail("Primary write"))
    monkeypatch.setattr(chat, "log_message", lambda *_args, **_kwargs: pytest.fail("Primary write"))
    monkeypatch.setattr(conversations, "get_connection", corrupt_connection)
    monkeypatch.setattr(conversations, "_resolve_identity_or_response",
                        lambda _: ({"effective_user": "ghost"}, None))
    monkeypatch.setattr(llm, "chat_via_gateway", lambda *_args, **_kwargs: ("Local reply", 3))
    app = Flask(__name__)
    app.register_blueprint(chat.chat_bp)
    app.register_blueprint(conversations.conversations_bp)
    return app.test_client(), store


def test_actual_chat_route_automatically_recovers_and_readback_works(live_route):
    client, store = live_route
    response = client.post("/api/chat", json={
        "message": "hello", "agents": ["qwen"], "local_only": True,
        "auto_relay": False, "new_thread": True,
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["storage_degraded"] is True
    assert data["responses"][0]["model"] == AGENTS[0]["model"]
    conversation_id = data["conversation_id"]
    readback = client.get(f"/api/conversations/{conversation_id}/messages")
    assert readback.status_code == 200
    assert readback.get_json()["messages"][-1]["content"].endswith("Local reply")
    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert listing.get_json()[0]["id"] == conversation_id
    assert listing.headers["X-Fridays-Storage-Status"].startswith("degraded")
    followup = client.post("/api/chat", json={
        "message": "continue", "agents": ["qwen"], "local_only": True,
        "auto_relay": False, "conversation_id": conversation_id,
    })
    assert followup.status_code == 200
    assert len(store.read(conversation_id, "ghost")["messages"]) == 4


def test_recovery_mode_does_not_silently_dispatch_nonlocal_requests(live_route):
    client, _ = live_route
    response = client.post("/api/chat", json={
        "message": "hello", "agents": ["qwen"], "auto_relay": False,
    })
    assert response.status_code == 503
    assert response.get_json()["storage_degraded"] is True
