import json
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "utils")]

from core.chat_continuity import (
    APEX_AGENT, ApexOffline, ContinuityChat, NOTICE, STATE_OFFLINE, STATE_OK, STATE_RECOVERY,
    apex_roster, classify_runtime_error, recovery_roster, storage_fault,
)

AGENTS = [{"name": "apex", "model": "gpt-oss:20b", "tier": "local", "label": "APEX"}]


def corrupt_connection():
    raise sqlite3.DatabaseError("database disk image is malformed")


def test_apex_is_the_only_roster_entry_without_touching_the_database():
    for roster in (apex_roster(), recovery_roster()):
        assert [row["name"] for row in roster] == ["apex"]
        assert roster[0]["model"] == APEX_AGENT["model"] == "gpt-oss:20b"
        assert roster[0]["tier"] == "local"
    assert recovery_roster()[0]["storage_degraded"] is True
    assert apex_roster()[0]["storage_degraded"] is False


@pytest.mark.parametrize("error,expected", [
    ("External llama-server unavailable at http://127.0.0.1:8080", STATE_OFFLINE),
    ("absolute timeout after 180s", STATE_OFFLINE),
    ("HTTPConnectionPool: Max retries exceeded", STATE_OFFLINE),
    ("Connection refused", STATE_OFFLINE),
    ("parser has no reverse mapping", "error"),
    ("", "error"),
])
def test_transport_and_timeout_failures_classify_as_offline(error, expected):
    assert classify_runtime_error(error) == expected


def test_recovery_dispatch_rejects_any_non_apex_model(tmp_path):
    with pytest.raises(ValueError, match="only the APEX model"):
        ContinuityChat(tmp_path).send(
            {"message": "hello"}, [{"name": "qwen", "model": "qwen2.5-coder:7b", "tier": "local"}],
            "ghost", "malformed", lambda *_: pytest.fail("must not call a non-APEX model"))


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
    assert first["state"] == STATE_RECOVERY
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
    with pytest.raises(ApexOffline, match="runner unavailable"):
        chat.send({"message": "keep this"}, AGENTS, "ghost", "malformed",
                  lambda *_: ("[local runtime error: runner unavailable]", 0))
    thread = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert thread["messages"][0]["content"] == "keep this"
    assert "runner unavailable" in thread["last_error"]["error"]
    assert thread["last_error"]["state"] == STATE_OFFLINE


def test_network_exception_from_gateway_is_offline_not_generic(tmp_path):
    chat = ContinuityChat(tmp_path)

    def model(*_):
        raise ConnectionError("HTTPConnectionPool(host='127.0.0.1', port=8080): Max retries exceeded")

    with pytest.raises(ApexOffline, match="Max retries"):
        chat.send({"message": "ping"}, AGENTS, "ghost", "malformed", model)
    thread = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert thread["last_error"]["state"] == STATE_OFFLINE


def test_non_transport_runtime_error_is_not_mislabelled_offline(tmp_path):
    chat = ContinuityChat(tmp_path)
    with pytest.raises(RuntimeError, match="reverse mapping") as info:
        chat.send({"message": "ping"}, AGENTS, "ghost", "malformed",
                  lambda *_: ("[local runtime error: parser has no reverse mapping]", 0))
    assert not isinstance(info.value, ApexOffline)
    thread = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert thread["last_error"]["state"] == "error"


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
    assert '"version": "1.1.0"' in prompt
    assert "APEX coordinates JD's local work" in prompt
    assert "Gemma" not in prompt
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
    assert data["state"] == STATE_RECOVERY
    # The UI asked for Qwen; the backend owns routing and answers through APEX.
    assert data["agent"] == "apex"
    assert data["routed_from"] == ["qwen"]
    assert data["responses"][0]["model"] == AGENTS[0]["model"] == "gpt-oss:20b"
    conversation_id = data["conversation_id"]
    readback = client.get(f"/api/conversations/{conversation_id}/messages")
    assert readback.status_code == 200
    assert readback.get_json()["messages"][-1]["content"].endswith("Local reply")
    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert listing.get_json()[0]["id"] == conversation_id
    assert listing.headers["X-Fridays-Storage-Status"].startswith("degraded")
    followup = client.post("/api/chat", json={
        "message": "continue", "agents": ["gemma", "llama"], "local_only": True,
        "auto_relay": False, "conversation_id": conversation_id,
    })
    assert followup.status_code == 200
    assert followup.get_json()["agents"] == ["apex"]
    assert len(store.read(conversation_id, "ghost")["messages"]) == 4


def test_recovery_mode_does_not_silently_dispatch_nonlocal_requests(live_route):
    client, _ = live_route
    response = client.post("/api/chat", json={
        "message": "hello", "agents": ["qwen"], "auto_relay": False,
    })
    assert response.status_code == 503
    body = response.get_json()
    assert body["storage_degraded"] is True
    assert body["state"] == STATE_RECOVERY


def test_recovery_route_reports_offline_when_apex_endpoint_is_unreachable(live_route, monkeypatch):
    from core import llm

    client, store = live_route
    calls = []

    def unreachable(model, *_args, **_kwargs):
        calls.append(model)
        return ("[local runtime error: External llama-server unavailable at http://127.0.0.1:8080]", 0)

    monkeypatch.setattr(llm, "chat_via_gateway", unreachable)
    response = client.post("/api/chat", json={
        "message": "anyone there?", "agents": ["qwen"], "local_only": True,
        "auto_relay": False, "new_thread": True,
    })
    assert response.status_code == 503
    body = response.get_json()
    assert body["ok"] is False
    assert body["state"] == STATE_OFFLINE
    assert body["storage_degraded"] is True
    assert body["model"] == "gpt-oss:20b"
    assert "unavailable" in body["response"]
    assert calls == ["gpt-oss:20b"]
    thread = json.loads(next(store.root.glob("*.json")).read_text())
    assert thread["messages"][0]["content"] == "anyone there?"
    assert thread["last_error"]["state"] == STATE_OFFLINE


def test_relay_requests_are_refused_on_the_apex_lane(live_route):
    client, _ = live_route
    response = client.post("/api/chat", json={
        "message": "hello", "agents": ["qwen"], "local_only": True,
        "relay_from": "gemma", "auto_relay": False,
    })
    assert response.status_code == 400
    assert "APEX is the only local routing target" in response.get_json()["response"]


@pytest.fixture
def healthy_route(tmp_path, monkeypatch):
    """Disposable primary SQLite; the live swarm_memory.db is never opened."""
    from frontend.blueprints import chat
    from frontend.services import chat_history
    from utils.db import _connection
    from core import llm

    db_path = tmp_path / "disposable_primary.db"
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, source TEXT DEFAULT 'email',
                sender TEXT, created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER, from_agent TEXT NOT NULL,
                to_agent TEXT, content TEXT NOT NULL, message_type TEXT DEFAULT 'response',
                tokens_used INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
            """
        )

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(_connection, "DB_PATH", str(db_path))
    monkeypatch.setattr(chat, "get_connection", connect)
    monkeypatch.setattr(chat_history, "get_connection", connect)
    monkeypatch.setattr(chat_history, "_display_chat_participant_local", lambda name: str(name or "").upper())
    monkeypatch.setattr(chat, "_resolve_identity_or_response",
                        lambda _: ({"effective_user": "ghost", "acting_user": "ghost", "proxy_as": None}, None))
    monkeypatch.setattr(chat, "get_current_user", lambda: None)
    monkeypatch.setattr(chat, "_log_human_ghost_thought", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_reg_routable", lambda: pytest.fail("APEX lane must not read the agents table"))
    gateway_calls = []

    def gateway(model, messages, **_kwargs):
        gateway_calls.append((model, messages))
        return "APEX answer", 7

    monkeypatch.setattr(llm, "chat_via_gateway", gateway)
    app = Flask(__name__)
    app.register_blueprint(chat.chat_bp)
    return app.test_client(), connect, gateway_calls


def test_healthy_storage_routes_every_local_request_to_apex_and_persists_primary(healthy_route):
    client, connect, gateway_calls = healthy_route
    response = client.post("/api/chat", json={
        "message": "hello apex", "agents": ["gemma", "qwen"], "local_only": True,
        "auto_relay": False, "new_thread": True,
    })
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert data["ok"] is True
    assert data["state"] == STATE_OK
    assert data["storage_degraded"] is False
    assert data["agent"] == "apex" and data["agents"] == ["apex"]
    assert data["routed_from"] == ["gemma", "qwen"]
    assert data["responses"][0]["model"] == "gpt-oss:20b"
    assert data["pending_jobs"] == []
    assert [model for model, _ in gateway_calls] == ["gpt-oss:20b"]
    assert gateway_calls[0][1][-1]["role"] == "user" and "hello apex" in gateway_calls[0][1][-1]["content"]
    with connect() as con:
        rows = con.execute("SELECT from_agent, to_agent, content FROM messages ORDER BY id").fetchall()
    assert [(r["from_agent"], r["to_agent"]) for r in rows] == [("user", "apex"), ("apex", "user")]
    assert rows[-1]["content"] == "APEX answer"


def test_healthy_storage_offline_apex_returns_offline_state_and_keeps_user_message(healthy_route, monkeypatch):
    from core import llm

    client, connect, _ = healthy_route
    monkeypatch.setattr(llm, "chat_via_gateway",
                        lambda *_a, **_k: ("[local runtime error: absolute timeout after 180s]", 0))
    response = client.post("/api/chat", json={
        "message": "still there?", "agents": ["qwen"], "local_only": True,
        "auto_relay": False, "new_thread": True,
    })
    assert response.status_code == 503
    body = response.get_json()
    assert body["state"] == STATE_OFFLINE
    assert body["storage_degraded"] is False
    assert body["conversation_id"]
    with connect() as con:
        rows = con.execute("SELECT from_agent, content FROM messages ORDER BY id").fetchall()
    assert [(r["from_agent"], r["content"]) for r in rows] == [("user", "still there?")]


def test_sse_chat_events_reach_the_registered_blueprint_instance(healthy_route):
    """terminal.py registers `blueprints.sse`; chat.py must publish to that instance.

    Without polling, the UIs refresh only on these events, so publishing to a
    second `frontend.blueprints.sse` module (separate subscriber list) would
    silently reach nobody.
    """
    import importlib
    import queue

    client, _connect, _ = healthy_route
    production_sse = importlib.import_module("blueprints.sse")
    test_sse = importlib.import_module("frontend.blueprints.sse")
    assert production_sse is not test_sse
    client.application.register_blueprint(production_sse.sse_bp)
    subscriber = queue.Queue()
    with production_sse._sub_lock:
        production_sse._subscribers.append(subscriber)
    try:
        response = client.post("/api/chat", json={
            "message": "ping", "agents": ["gemma"], "local_only": True,
            "auto_relay": False, "new_thread": True,
        })
        assert response.status_code == 200
        events = []
        while not subscriber.empty():
            raw = subscriber.get_nowait()
            assert raw.startswith("event: chat\n")
            events.append(json.loads(raw.split("data: ", 1)[1].strip()))
    finally:
        with production_sse._sub_lock:
            production_sse._subscribers.remove(subscriber)
    statuses = [(e["agent"], e["status"]) for e in events]
    assert statuses == [("apex", "running"), ("apex", "completed")]
    assert events[-1]["state"] == STATE_OK
    assert events[-1]["conversation_id"] == response.get_json()["conversation_id"]
    assert test_sse._subscribers == []
