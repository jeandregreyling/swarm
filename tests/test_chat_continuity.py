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
    apex_request_history,
)

AGENTS = [dict(APEX_AGENT)]


def test_current_request_cannot_be_replaced_by_concurrent_shared_thread_message():
    history = [{"role": "user", "content": "another request", "studio_archived": True}]
    result = apex_request_history(history, "this request")
    assert result[-1] == {"role": "user", "content": "this request"}
    assert result[0] == history[0] and result[0] is not history[0]
    assert apex_request_history(result, "this request") == result
    assert apex_request_history([], "this request") == [result[-1]]


@pytest.fixture(autouse=True)
def isolated_apex_lifecycle(tmp_path, monkeypatch):
    from core import apex_context
    from utils import thread_memory
    monkeypatch.setattr(thread_memory, "MIND_DB_PATH", str(tmp_path / "mind.db"))
    monkeypatch.setattr(apex_context, "server_prompt_tokens",
                        lambda messages: sum(len(m["content"].encode("utf-8")) for m in messages) // 3 + 128)


def corrupt_connection():
    raise sqlite3.DatabaseError("database disk image is malformed")


def test_apex_is_the_only_roster_entry_without_touching_the_database():
    for roster in (apex_roster(), recovery_roster()):
        assert [row["name"] for row in roster] == ["apex"]
        assert roster[0]["model"] == APEX_AGENT["model"] == "qwen2.5:14b-instruct"
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
    assert '"version": "1.2.0"' in prompt
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
    assert data["responses"][0]["model"] == AGENTS[0]["model"] == "qwen2.5:14b-instruct"
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


def test_main_chat_defaults_to_local_even_during_storage_recovery(live_route):
    client, _ = live_route
    response = client.post("/api/chat", json={
        "message": "hello", "agents": ["qwen"], "auto_relay": False,
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["storage_degraded"] is True
    assert body["state"] == STATE_RECOVERY
    assert body["agent"] == "apex"


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
    assert body["model"] == "qwen2.5:14b-instruct"
    assert "unavailable" in body["response"]
    assert calls == ["qwen2.5:14b-instruct"]
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
    from core.knowledge import projects
    from core import apex_studio
    from core import apex_routing
    monkeypatch.setattr(apex_routing, 'choose_local_model', lambda message:
                        apex_routing.LocalRoute(APEX_AGENT['model'], 'voice', 16384, 'test catalogue'))

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
    monkeypatch.setattr(projects, "_SCHEMA_READY", False)
    monkeypatch.setattr(apex_studio, "get_connection", connect)
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


_KC_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_sources(source_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'text', source_ref TEXT, raw_text TEXT, domain_tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active', added_by TEXT NOT NULL DEFAULT 'ghost', chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now')), updated_at DATETIME DEFAULT (datetime('now')),
    category TEXT NOT NULL DEFAULT 'general', subcategory TEXT, content_hash TEXT);
CREATE TABLE IF NOT EXISTS knowledge_chunks(chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INT, chunk_index INT,
    chunk_text TEXT, embedding TEXT, created_at DATETIME DEFAULT (datetime('now')));
"""


def _kc_transcript(conn, conversation_id):
    """DOES: index the chat into the KC the way the HB coordinator does, then return the transcript text."""
    from core import hb_kc_records
    conn.executescript(_KC_DDL)
    hb_kc_records.tick(conn)
    row = conn.execute("SELECT raw_text FROM knowledge_sources WHERE source_ref=?", (f"hb-chat:{conversation_id}",)).fetchone()
    return row[0] if row else ""


def test_apex_route_compacts_long_history_and_reloads_same_thread_checkpoint(healthy_route):
    # Since 9 Nov every message belongs to a task and a turn carries only that task's history;
    # DOES (12 Nov) saves every chat and task in the KC and tells the model where to read it again.
    from core import hb_tasks
    client, connect, calls = healthy_route
    raw = '[tool:read_file] succeeded (receipt archived-real)\n{"path":"source.py"}\n' + "evidence\n" * 3000
    with connect() as conn:
        hb_tasks.ensure_schema(conn)
        cid = conn.execute("INSERT INTO conversations (title) VALUES ('Long thread')").lastrowid
        ids = [conn.execute(
            "INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type) "
            "VALUES (?, 'apex', 'user', ?, 'tool_result')", (cid, raw)).lastrowid for _ in range(10)]
        owner_mid = conn.execute("INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type) "
                                 "VALUES (?, 'user', 'apex', 'Inspect source.py and report', 'chat')", (cid,)).lastrowid
        task = hb_tasks.bind(conn, cid, owner_mid)
        for mid in ids:
            hb_tasks.bind(conn, cid, mid, task_id=task["task_id"], kind="reply")
        _kc_transcript(conn, cid)
    first = client.post("/api/chat", json={
        "message": "Continue inspection; preserve unrelated files.", "conversation_id": cid, "task_id": task["task_id"],
        "agents": ["apex"], "local_only": True, "auto_relay": False, "history_mode": "full",
    })
    assert first.status_code == 200, first.get_json()
    prompt = str(calls[-1][1])
    assert "evidence\n" * 100 not in prompt                      # long tool output compacted to receipts
    assert "archived-real" in prompt                              # ...that keep the real receipt handle
    assert "HISTORY POINTER" in prompt and task["task_id"] in prompt and f"chat:{cid}" in prompt
    with connect() as conn:
        stored = conn.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND message_type='tool_result'", (cid,)
        ).fetchall()
        transcript = _kc_transcript(conn, cid)
    assert len(stored) == 10 and all(row["content"] == raw for row in stored)   # nothing durable was deleted
    assert "Continue inspection; preserve unrelated files." in transcript and "archived-real" in transcript
    second = client.post("/api/chat", json={
        "message": "What remains?", "conversation_id": cid, "agents": ["apex"],
        "local_only": True, "auto_relay": False, "history_mode": "recent",
    })
    assert second.status_code == 200
    # A separate new task in the same chat still knows where the earlier work is saved.
    assert "HISTORY POINTER" in str(calls[-1][1]) and f"chat:{cid}" in str(calls[-1][1])


def test_healthy_tool_loop_persists_receipts_and_publishes_sanitized_sse(healthy_route, monkeypatch):
    from frontend.blueprints import chat, sse
    from core import llm
    from core.apex_tools import ReadOnlyRepository
    import queue

    client, connect, _ = healthy_route
    # Publish to the same SSE blueprint this test observes, even when both
    # production and package import paths were loaded during collection.
    client.application.register_blueprint(sse.sse_bp)
    monkeypatch.setattr(chat, "can_user_invoke_skill", lambda *_args, **_kw: True)
    monkeypatch.setattr(ReadOnlyRepository, "call", lambda _self, name, args: "actual backend output")
    outputs = iter([
        json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}}]}),
        "The backend inspected the workspace.",
    ])
    monkeypatch.setattr(llm, "chat_via_gateway", lambda *_args, **_kw: (next(outputs), 3))
    events = queue.Queue()
    with sse._sub_lock:
        sse._subscribers.append(events)
    try:
        response = client.post("/api/chat", json={
            "message": "Inspect the workspace", "local_only": True, "new_thread": True,
        })
    finally:
        with sse._sub_lock:
            sse._subscribers.remove(events)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    receipt = body["tool_receipts"][0]
    assert receipt["output"] == "actual backend output" and receipt["status"] == "succeeded"
    with connect() as conn:
        row = conn.execute("SELECT content FROM messages WHERE message_type='tool_result'").fetchone()
    assert receipt["id"] in row["content"] and "actual backend output" in row["content"]
    published = []
    while not events.empty():
        published.append(events.get_nowait())
    tool_events = [event for event in published if '"status": "tool_receipt"' in event]
    assert len(tool_events) == 1
    assert receipt["id"] in tool_events[0]
    assert "actual backend output" not in tool_events[0]
    assert f'"conversation_id": {body["conversation_id"]}' in tool_events[0]


def test_browser_gateway_closes_tools_after_repeated_reads_and_saves_the_answer(healthy_route, monkeypatch):
    from frontend.blueprints import chat
    from core import llm
    from core.apex_tools import ReadOnlyRepository, TURN_FORMAT, response_format_for_turn

    client, connect, _ = healthy_route
    backend_calls, formats = [], []
    monkeypatch.setattr(chat, 'can_user_invoke_skill', lambda *_a, **_k: True)

    def read(_self, name, args):
        backend_calls.append(name)
        return 'value = 9'

    def gateway(_model, _messages, **kwargs):
        schema = kwargs['response_format']['json_schema']['schema']
        formats.append(schema)
        if len(formats) <= 3:
            assert 'oneOf' in schema
            return json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}], 'answer': ''}), 1
        assert schema['properties']['tool_calls']['maxItems'] == 0
        return json.dumps({'tool_calls': [], 'answer': 'example.py contains value = 9; no tests were run.'}), 1

    monkeypatch.setattr(ReadOnlyRepository, 'call', read)
    monkeypatch.setattr(llm, 'chat_via_gateway', gateway)
    response = client.post('/api/chat', json={'message': 'Inspect example.py', 'local_only': True, 'new_thread': True})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body['response'] == 'example.py contains value = 9; no tests were run.'
    assert len(formats) == 4 and backend_calls == ['read_file']
    assert len(body['tool_receipts']) == 1
    with connect() as conn:
        assert conn.execute("SELECT content FROM messages WHERE message_type='response' ORDER BY id DESC LIMIT 1").fetchone()[0] == body['response']
    assert response_format_for_turn() is TURN_FORMAT


def test_healthy_tool_authorization_database_failure_stops_execution(healthy_route, monkeypatch):
    from frontend.blueprints import chat
    from core import llm
    from core.apex_tools import ReadOnlyRepository

    client, _, _ = healthy_route

    def denied(*_args, **_kw):
        raise sqlite3.DatabaseError("permission storage malformed")

    monkeypatch.setattr(chat, "can_user_invoke_skill", denied)
    monkeypatch.setattr(ReadOnlyRepository, "call", lambda *_args: pytest.fail("Unauthorized read"))
    monkeypatch.setattr(llm, "chat_via_gateway", lambda *_args, **_kw: (
        json.dumps({"tool_calls": [{"name": "git_status", "arguments": {}}]}), 1))
    response = client.post("/api/chat", json={
        "message": "Inspect", "local_only": True, "new_thread": True,
    })
    assert response.status_code == 500
    assert "authorization storage is unavailable" in response.get_json()["response"]


@pytest.mark.parametrize("allowed", [True, False, "database_error"])
def test_authenticated_apex_web_dispatch_checks_permission_and_persists(healthy_route, monkeypatch, allowed):
    from frontend.blueprints import chat
    from core import llm
    from lib.search import internet

    client, connect, _ = healthy_route
    monkeypatch.setattr(chat, "_tool_operator", lambda: ("ghost", "session-web"))

    def permission(_user, skill, **_kwargs):
        assert skill == "web_search"
        if allowed == "database_error":
            raise sqlite3.DatabaseError("permission database unavailable")
        return allowed

    monkeypatch.setattr(chat, "can_user_invoke_skill", permission)
    calls = []

    def provider(query, name):
        calls.append((query, name))
        return {"provider": name, "sources": ["https://docs.python.org/"], "text": "Public docs"}

    monkeypatch.setattr(internet, "search_provider", provider)
    outputs = iter([
        json.dumps({"tool_calls": [{"name": "web_search", "arguments": {
            "query": "Python documentation", "provider": "serper"}}], "answer": ""}),
        '{"tool_calls":[],"answer":"Search complete or denied, as recorded."}',
    ])
    monkeypatch.setattr(llm, "chat_via_gateway", lambda *_args, **_kw: (next(outputs), 1))
    response = client.post("/api/chat", json={
        "message": "Search public Python documentation", "local_only": True, "new_thread": True,
    })
    if allowed == "database_error":
        assert response.status_code == 500
        assert "Web search authorization storage is unavailable" in response.get_json()["response"]
    else:
        assert response.status_code == 200, response.get_json()
        receipt = response.get_json()["tool_receipts"][0]
        assert receipt["status"] == ("succeeded" if allowed else "denied")
        with connect() as conn:
            row = conn.execute("SELECT content FROM messages WHERE message_type='tool_result'").fetchone()
        assert receipt["id"] in row["content"]
    assert len(calls) == (1 if allowed is True else 0)


def test_apex_legacy_skill_execution_is_disabled(healthy_route, monkeypatch):
    from frontend.blueprints import chat

    client, _, calls = healthy_route
    monkeypatch.setattr(chat, "_parse_chat_skill_command", lambda _: ("shell", "touch forbidden"))
    response = client.post("/api/chat", json={
        "message": "SKILL shell touch forbidden", "local_only": True, "new_thread": True,
    })
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("decision", [True, False])
def test_chat_suspends_then_approval_route_resumes_same_thread(healthy_route, monkeypatch, tmp_path, decision):
    from frontend.blueprints import chat
    from core import llm, tool_approval
    from core.apex_tools import ReadOnlyRepository
    import subprocess
    import threading
    import time

    client, connect, _ = healthy_route
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "probe.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(root), "add", "--", "probe.py"], check=True)
    repository = ReadOnlyRepository(root)
    store = tool_approval.ApprovalStore()
    monkeypatch.setattr(tool_approval, "APPROVALS", store)
    monkeypatch.setattr(chat, "get_current_user", lambda: {"username": "ghost", "role": "owner"})
    monkeypatch.setattr(chat, "can_user_invoke_skill", lambda *_args, **_kw: True)
    monkeypatch.setattr("core.apex_tools.ReadOnlyRepository", lambda: repository)
    published = threading.Event()

    class Publisher:
        def publish(self, name, payload, **kwargs):
            if name == "tool_approval_pending":
                published.set()

        def publish_chat_update(self, *args, **kwargs):
            pass

    monkeypatch.setattr(chat, "_sse_module", lambda: Publisher())
    models = []
    outputs = iter([
        json.dumps({"tool_calls": [{"name": "propose_write_file",
                                   "arguments": {"path": "probe.py", "content": "# comment\nvalue = 1\n"}}],
                    "answer": ""}),
        json.dumps({"tool_calls": [], "answer": "The backend decision is recorded."}),
    ])

    def model(name, messages, **kwargs):
        models.append((name, list(messages)))
        return next(outputs), 2

    monkeypatch.setattr(llm, "chat_via_gateway", model)
    results = []

    def send():
        with client.application.test_client() as sender:
            sender.set_cookie("friday_session", "session-cookie")
            response = sender.post("/api/chat", json={
                "message": "Propose adding a comment", "local_only": True, "new_thread": True,
            })
            results.append((response.status_code, response.get_json()))

    thread = threading.Thread(target=send)
    thread.start()
    try:
        assert published.wait(5), "No pending proposal event"
        time.sleep(0.05)
        assert len(models) == 1 and not results
        assert (root / "probe.py").read_text() == "value = 1\n"
        client.set_cookie("friday_session", "session-cookie")
        pending = client.get("/api/tool-approval").get_json()["pending"][0]
        response = client.post("/api/tool-approval", json={
            "transaction_id": pending["transaction_id"], "decision": decision,
        }, headers={"X-Tool-Approval-CSRF": pending["csrf_token"]})
        assert response.status_code == 200
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert results[0][0] == 200, results
        body = results[0][1]
        assert len(models) == (2 if decision else 1)
        assert body["tool_receipts"][0]["status"] == ("succeeded" if decision else "denied")
        if decision:
            assert "Approved write completed" in models[1][1][-1]["content"]
        else:
            assert "User Denied Execution" in body["response"]
            assert "new operator instruction" in body["response"]
        with connect() as conn:
            row = conn.execute("SELECT content FROM messages WHERE message_type='tool_result'").fetchone()
        assert pending["transaction_id"] in row["content"]
        assert (root / "probe.py").read_text() == ("# comment\nvalue = 1\n" if decision else "value = 1\n")
    finally:
        for transaction in list(store._pending.values()):
            store.cancel(transaction, "test cleanup")
        thread.join(timeout=5)


def test_healthy_storage_routes_every_local_request_to_apex_and_persists_primary(healthy_route, monkeypatch):
    from core import llm
    from core.apex_context import APEX_REASONING_EFFORT

    client, connect, gateway_calls = healthy_route
    original_gateway = llm.chat_via_gateway

    def gateway(model, messages, **kwargs):
        assert kwargs["options"]["reasoning_effort"] == APEX_REASONING_EFFORT == "low"
        return original_gateway(model, messages, **kwargs)

    monkeypatch.setattr(llm, "chat_via_gateway", gateway)
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
    assert data["responses"][0]["model"] == "qwen2.5:14b-instruct"
    assert data["pending_jobs"] == []
    assert [model for model, _ in gateway_calls] == ["qwen2.5:14b-instruct"]
    assert gateway_calls[0][1][-1]["role"] == "user" and "hello apex" in gateway_calls[0][1][-1]["content"]
    with connect() as con:
        rows = con.execute("SELECT from_agent, to_agent, content FROM messages ORDER BY id").fetchall()
    assert [(r["from_agent"], r["to_agent"]) for r in rows] == [("user", "apex"), ("apex", "user")]
    assert rows[-1]["content"] == "APEX answer"


def test_wrapper_records_normal_turn_and_evicts_old_user_history_without_manual_handoff(
        healthy_route, monkeypatch):
    from frontend.blueprints import chat
    from core import apex_studio
    client, connect, calls = healthy_route
    monkeypatch.setattr(chat, "get_current_user", lambda: {"username": "ghost", "role": "owner"})
    client.set_cookie("friday_session", "wrapper-test")
    with connect() as conn:
        cid = conn.execute("INSERT INTO conversations(title) VALUES ('Automatic task')").lastrowid
        for index in range(20):
            conn.execute(
                "INSERT INTO messages(conversation_id,from_agent,to_agent,content) VALUES (?,'user','apex',?)",
                (cid, f"Historical requirement {index}: " + "reference " * 1000))
    response = client.post("/api/chat", json={
        "message": "Inspect the current task, do not modify files", "conversation_id": cid,
        "local_only": True, "history_mode": "full",
    })
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["studio"]["project_id"]
    assert "Inspect the current task, do not modify files" in calls[-1][1][-1]["content"]
    # Main chat stays small: a new message is a new task and does not drag 20 old messages into the prompt...
    assert "Historical requirement 0" not in str(calls[-1][1])
    with connect() as conn:
        _, text = apex_studio._snapshot(conn, body["studio"]["project_id"])
        saved = json.loads(text)
        assert saved["outcome"]["state"] == "completed"
        assert saved["outcome"]["response"] == "APEX answer"
        assert saved["outcome"]["completion_tokens"] == 7
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE from_agent='user'").fetchone()[0] == 21
        transcript = _kc_transcript(conn, cid)
    # ...while the whole history is saved and searchable in the KC (DOES).
    assert "Historical requirement 0" in transcript and "Historical requirement 19" in transcript
    assert "Inspect the current task, do not modify files" in transcript


def test_message_sent_during_a_turn_is_queued_then_answered_with_that_turn_in_context(healthy_route, monkeypatch):
    import threading
    import time as _time
    from frontend.blueprints import chat
    from core import llm

    client, connect, _ = healthy_route
    monkeypatch.setattr(chat, "_APEX_TURNS", chat._TurnQueue())
    with connect() as conn:
        cid = conn.execute("INSERT INTO conversations(title) VALUES ('Queued turns')").lastrowid
    release_first, queued, calls, results = threading.Event(), threading.Event(), [], {}
    monkeypatch.setattr(chat, "_sse_chat",
                        lambda _cid, _agent, status, **_kw: queued.set() if status == "queued" else None)

    def gateway(model, messages, **_kwargs):
        calls.append(messages)
        if "first request" in messages[-1]["content"]:
            assert release_first.wait(5)
            return "first answer", 3
        return "second answer", 3

    monkeypatch.setattr(llm, "chat_via_gateway", gateway)

    def send(name, task_id=None):
        # The second message is sent as a follow-up in the first message's task (the UI task picker).
        results[name] = client.application.test_client().post("/api/chat", json={
            "message": f"{name} request", "conversation_id": cid, "local_only": True,
            "auto_relay": False, "history_mode": "full", "task_id": task_id,
        })

    first = threading.Thread(target=send, args=("first",))
    first.start()
    for _ in range(200):
        if calls:
            break
        _time.sleep(0.01)
    with connect() as conn:
        first_task = conn.execute("SELECT task_id FROM hb_tasks WHERE conversation_id=? ORDER BY created_at LIMIT 1",
                                  (cid,)).fetchone()[0]
    second = threading.Thread(target=send, args=("second", first_task))
    second.start()
    assert queued.wait(5), "the second message must wait for the running turn, not fail as model busy"
    assert len(calls) == 1
    release_first.set()
    first.join(10)
    second.join(10)
    assert results["first"].status_code == 200 and results["second"].status_code == 200
    assert results["second"].get_json()["response"] == "second answer"
    assert len(calls) == 2 and "first answer" in str(calls[1])


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
    assert statuses == [("apex", "running"), ("apex", "measurement"), ("apex", "completed")]
    assert events[-1]["state"] == STATE_OK
    assert events[-1]["conversation_id"] == response.get_json()["conversation_id"]
    assert test_sse._subscribers == []


def test_explicit_codex_address_bypasses_local_model_even_from_local_ui(healthy_route, monkeypatch):
    from flask import jsonify
    from frontend.blueprints import chat
    import types
    client, _, gateway_calls = healthy_route
    selected = []
    def dispatch(data, message, targets):
        selected.append((message, targets))
        return jsonify({'ok': True, 'mode': 'peer', 'conversation_id': 1})
    name = chat._sse_module().__name__.replace('.sse', '.peer_bridge')
    monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(dispatch_operator_message=dispatch))
    response = client.post('/api/chat', json={'message': '@codex read the response and make corrections', 'local_only': True})
    assert response.status_code == 200 and response.get_json()['mode'] == 'peer'
    assert selected[0][1] == ['codex-instructor']
    assert gateway_calls == []


def test_apex_prompt_teaches_verified_does_and_bounded_instructor_requests():
    from core.chat_continuity import apex_system_prompt
    prompt = apex_system_prompt(AGENTS[0], recovery=False, proposals=True)
    assert 'Do, Operate, Execute, Sustain' in prompt
    assert 'utils/does_teaching.py' in prompt
    assert 'ask_instructor' in prompt
    assert 'Clarify only a specific unresolved detail' in prompt
    assert 'grants no extra tool permissions' in prompt


@pytest.mark.parametrize("recovering", [False, True])
def test_owner_workspace_grant_applies_writes_without_waiting_and_restores_recovery_tools(
        healthy_route, tmp_path, monkeypatch, recovering):
    from core import apex_permissions, apex_tools, llm, tool_approval
    from frontend.blueprints import chat
    import subprocess

    client, connect, _ = healthy_route
    repository_root = tmp_path / 'editable'
    repository_root.mkdir()
    subprocess.run(['git', 'init', '-q', str(repository_root)], check=True)
    (repository_root / 'example.py').write_text('value = 1\n')
    subprocess.run(['git', '-C', str(repository_root), 'add', 'example.py'], check=True)
    repository = apex_tools.ReadOnlyRepository(repository_root)
    monkeypatch.setattr(apex_tools, 'ReadOnlyRepository', lambda: repository)
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'owner': 'ghost', 'workspace': str(repository_root), 'autonomous_writes': True}))
    policy.chmod(0o600)
    monkeypatch.setattr(apex_permissions, 'POLICY_PATH', policy)
    monkeypatch.setattr(apex_permissions, 'ROOT', repository_root)
    monkeypatch.setattr(chat, '_tool_operator', lambda: ('ghost', 'session-write'))
    monkeypatch.setattr(chat, 'can_user_invoke_skill', lambda *_a, **_k: True)
    store = tool_approval.ApprovalStore()
    monkeypatch.setattr(tool_approval, 'APPROVALS', store)
    monkeypatch.setattr(store, 'wait', lambda *_: pytest.fail('Autonomous edit waited for approval'))
    request_data = {'message': '@apex Edit example.py to set value = 2', 'local_only': True}
    journal_before = None
    if recovering:
        continuity = ContinuityChat(tmp_path / 'recovery')
        original = continuity.send({'message': 'An earlier task'}, AGENTS, 'ghost', 'storage was offline',
                                   lambda *_: ('Old recovery answer', 1))
        recovery_id = original['conversation_id']
        journal_before = continuity.path(recovery_id).read_bytes()
        monkeypatch.setattr(sys.modules['core.chat_continuity'], 'ContinuityChat', lambda: continuity)
        request_data['conversation_id'] = recovery_id
    else:
        request_data['new_thread'] = True
    outputs = iter([
        json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}], 'answer': ''}),
        json.dumps({'tool_calls': [{'name': 'propose_patch', 'arguments': {
            'file_path': 'example.py', 'exact_old_text': 'value = 1', 'new_text': 'value = 2'}}], 'answer': ''}),
        json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}], 'answer': ''}),
        json.dumps({'tool_calls': [], 'answer': 'Updated example.py and read back value = 2.'}),
    ])
    seen = []

    def gateway(_model, messages, **_kwargs):
        seen.append(messages)
        return next(outputs), 1

    monkeypatch.setattr(llm, 'chat_via_gateway', gateway)
    response = client.post('/api/chat', json=request_data)
    assert response.status_code == 200, response.get_json()
    result = response.get_json()
    assert (repository_root / 'example.py').read_text() == 'value = 2\n'
    assert [row['status'] for row in result['tool_receipts']] == ['succeeded'] * 3
    assert result['tool_receipts'][1]['authorization'] == 'owner_workspace_grant'
    assert 'execute immediately' in seen[0][0]['content']
    with connect() as conn:
        records = conn.execute("SELECT content FROM messages WHERE message_type='tool_result'").fetchall()
    assert any(result['tool_receipts'][1]['id'] in row[0] for row in records)
    assert store.list_for('ghost', 'session-write') == []
    if recovering:
        assert result['conversation_id'] != recovery_id
        assert continuity.path(recovery_id).read_bytes() == journal_before
        with connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM recovery_thread_imports').fetchone()[0] == 1


def test_apex_chat_logs_in_as_itself_loads_own_memory_and_records_owner_separately(
        healthy_route, tmp_path, monkeypatch):
    from core import agent_identity, apex_tools, llm
    from frontend.blueprints import chat
    from services import auth
    import subprocess

    client, connect, _ = healthy_route
    from core import apex_routing
    monkeypatch.setattr(apex_routing,'choose_local_model', lambda message:
                        apex_routing.LocalRoute('apex-direct:7b','coder',16384,'test local routing'))
    monkeypatch.setattr(agent_identity, 'STATE', tmp_path / 'agent-state')
    with connect() as conn:
        conn.executescript("CREATE TABLE agents(name TEXT PRIMARY KEY,tier TEXT); INSERT INTO agents VALUES ('apex','local');")
        agent_identity.provision(conn, activate=True)
    owner = {'username': 'ghost', 'role': 'owner'}
    monkeypatch.setattr(auth, 'get_current_user', lambda: owner)
    monkeypatch.setattr(chat, '_tool_operator', lambda: ('ghost', 'owner-session'))
    monkeypatch.setattr(chat, 'can_user_invoke_skill', lambda *_a, **_k: True)
    source = tmp_path / 'source'
    source.mkdir()
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    (source / 'example.py').write_text('value = 9\n')
    subprocess.run(['git', '-C', str(source), 'add', 'example.py'], check=True)
    repo = apex_tools.ReadOnlyRepository(source)
    monkeypatch.setattr(apex_tools, 'ReadOnlyRepository', lambda: repo)
    agent_identity.save_memory('apex', 'existing lesson', 'my private task context')
    outputs = iter([
        json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}], 'answer': ''}),
        json.dumps({'tool_calls': [], 'answer': 'The file contains value = 9.'}),
    ])
    seen = []
    def gateway(_model, messages, **_kwargs):
        seen.append(str(messages))
        return next(outputs), 1
    monkeypatch.setattr(llm, 'chat_via_gateway', gateway)
    response = client.post('/api/chat', json={'message': 'Read example.py', 'local_only': True, 'new_thread': True})
    assert response.status_code == 200, response.get_json()
    receipt = response.get_json()['tool_receipts'][0]
    assert receipt['executor'] == 'apex' and receipt['requested_by'] == 'ghost'
    assert receipt['model'] == 'apex-direct:7b'
    assert 'my private task context' in seen[0]
    notes = agent_identity.read_memory('apex')
    assert any(row['content'] == 'The file contains value = 9.' for row in notes)
    actions = agent_identity.audit_rows(agent='apex')
    assert any(row['tool'] == 'read_file' and row['requested_by'] == 'ghost' and row['model']=='apex-direct:7b' for row in actions)


def test_untagged_main_chat_ignores_stale_online_selection_and_uses_local_policy(healthy_route, monkeypatch):
    from core import apex_routing, llm
    from core.seven_llm.registry import ModelEntry
    client, _, calls = healthy_route
    entries=[ModelEntry('gemma-direct:3','llamacpp',path='/gemma',ctx=16384,ram_gb=3),
             ModelEntry('apex-direct:7b','llamacpp',role='coder',path='/coder',ctx=16384,ram_gb=6)]
    monkeypatch.setattr(apex_routing,'choose_local_model',lambda message:
        apex_routing.select_local_model(message,entries,exists=lambda _:True))
    original=llm.chat_via_gateway
    options=[]
    def gateway(model,messages,**kwargs):
        options.append(kwargs['options'])
        return original(model,messages,**kwargs)
    monkeypatch.setattr(llm,'chat_via_gateway',gateway)
    for text,expected in [('hello','gemma-direct:3'),('debug a syntax error','apex-direct:7b')]:
        response=client.post('/api/chat',json={'message':text,'agent':'ten','local_only':False,'new_thread':True})
        data=response.get_json()
        assert response.status_code==200,data
        assert data['agent']=='apex' and data['model']==expected
        assert data['model_routing']['model']==expected
        assert calls[-1][0]==expected and options[-1]['num_ctx']==16384
