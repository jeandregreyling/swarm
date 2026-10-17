import json
import sqlite3
import threading
import time


def _connection_factory(path):
    def _get():
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    return _get


def test_json_only_handoff_regenerates_at_zero_temperature(monkeypatch):
    from core import diamond_sch
    from core import llm

    calls = []
    response_formats = []
    responses = iter([
        "I think this should escalate.",
        '{"decision":"ESCALATE","technical_query":"inspect locking","reason":"specialist review"}',
    ])

    def fake_chat(model, messages, **kwargs):
        calls.append(kwargs.get("temperature"))
        response_formats.append(kwargs.get("response_format"))
        return next(responses), 0

    monkeypatch.setattr(llm, "chat_via_gateway", fake_chat)
    out = diamond_sch._call_json_model(
        "seven-direct:daily",
        [{"role": "user", "content": "triage"}],
        diamond_sch.validate_triage,
        temperature=diamond_sch.STANDARD_TEMPERATURE,
        timeout_s=10,
    )

    assert out["decision"] == "ESCALATE"
    assert calls == [0.6, 0.0]
    assert response_formats == [diamond_sch.TRIAGE_RESPONSE_FORMAT, diamond_sch.TRIAGE_RESPONSE_FORMAT]


def test_explicit_council_request_overrides_weak_respond_triage(monkeypatch, tmp_path):
    from core import diamond_sch

    db_path = str(tmp_path / "sch-explicit.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))

    def fake_json(model, messages, validator, **kwargs):
        if model == "seven-direct:daily":
            return {"decision": "RESPOND", "technical_query": "", "reason": "weak tiny-model triage"}
        agent = "llama" if model == "llama3.2:latest" else "qwen"
        return {"agent": agent, "answer": "Use bounded locks.", "confidence": 1.0, "risks": []}

    monkeypatch.setattr(diamond_sch, "_call_json_model", fake_json)

    result = diamond_sch.route("/council analyze the SQLite lock")

    assert result.decision == "ESCALATE"


def test_sch_escalation_writes_counsel_and_releases_state(monkeypatch, tmp_path):
    from core import diamond_sch
    from core import llm

    db_path = str(tmp_path / "sch.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))
    temperatures = []
    response_formats = []

    def fake_chat(model, messages, **kwargs):
        temperatures.append((model, kwargs.get("temperature")))
        response_formats.append((model, kwargs.get("response_format")))
        if model == "seven-direct:daily":
            return json.dumps({
                "decision": "ESCALATE",
                "technical_query": "Design a synchronous SQLite council gate.",
                "reason": "Requires specialist concurrency review",
            }), 0
        agent = "llama" if model == "llama3.2:latest" else "qwen"
        return json.dumps({
            "agent": agent,
            "answer": "Use one coordinator lock and short atomic SQL transactions.",
            "confidence": 0.9,
            "risks": ["Do not hold a write transaction during inference."],
        }), 0

    monkeypatch.setattr(llm, "chat_via_gateway", fake_chat)
    result = diamond_sch.route(
        "Design the council lock.",
        history=[{"role": "user", "content": "prior"}],
        seven_model="seven-direct:daily",
        timeout_s=10,
    )

    assert result.decision == "ESCALATE"
    handoff = json.loads(result.council_context)
    assert handoff["parity"] == "high"
    assert "coordinator lock" in handoff["finalized_answer"]
    snapshot = diamond_sch.state_snapshot()
    assert snapshot["is_council_active"] == 0
    assert snapshot["phase"] == "complete"
    assert snapshot["latest_counsel"]["session_id"] == result.session_id
    assert ("seven-direct:daily", 0.6) in temperatures
    assert ("llama3.2:latest", 0.1) in temperatures
    assert ("qwen2.5:latest", 0.1) in temperatures
    assert ("llama3.2:latest", diamond_sch.COUNSEL_RESPONSE_FORMAT) in response_formats
    assert ("qwen2.5:latest", diamond_sch.COUNSEL_RESPONSE_FORMAT) in response_formats


def test_sch_lock_serializes_council_sessions(monkeypatch, tmp_path):
    from core import diamond_sch

    db_path = str(tmp_path / "sch-lock.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))
    active = 0
    max_active = 0
    council_sessions = set()
    gate = threading.Lock()

    def fake_json(model, messages, validator, **kwargs):
        nonlocal active, max_active
        if model == "seven-direct:daily":
            return {"decision": "ESCALATE", "technical_query": "x", "reason": "x"}
        payload = json.loads(messages[-1]["content"])
        with gate:
            council_sessions.add(payload["session_id"])
            active += 1
            max_active = max(max_active, len(council_sessions))
        time.sleep(0.03)
        with gate:
            active -= 1
            if active == 0:
                council_sessions.clear()
        agent = "llama" if model == "llama3.2:latest" else "qwen"
        return {"agent": agent, "answer": "same answer", "confidence": 1.0, "risks": []}

    monkeypatch.setattr(diamond_sch, "_call_json_model", fake_json)
    results = []
    threads = [threading.Thread(target=lambda: results.append(diamond_sch.route("x"))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 2
    assert all(item.decision == "ESCALATE" for item in results)
    assert max_active == 1
    assert diamond_sch.state_snapshot()["is_council_active"] == 0


def test_stale_active_state_is_recovered_only_when_lock_is_free(monkeypatch, tmp_path):
    from core import diamond_sch

    db_path = str(tmp_path / "sch-stale.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))
    monkeypatch.setattr(diamond_sch, "_SCH_LOCK_PATH", str(tmp_path / "sch.lock"))
    diamond_sch._set_state(True, "sch-abandoned", "council_inference")
    conn = _connection_factory(db_path)()
    conn.execute("UPDATE diamond_sch_state SET updated_at=datetime('now', '-10 minutes') WHERE state_id=1")
    conn.commit()
    conn.close()

    recovered = diamond_sch.recover_stale_state(stale_after_s=60)

    assert recovered["recovered"] is True
    assert recovered["state"]["is_council_active"] == 0
    assert recovered["state"]["phase"] == "recovered_stale"


def test_counsel_refusal_is_rejected():
    from core import diamond_sch

    try:
        diamond_sch.validate_counsel(
            {
                "agent": "qwen",
                "answer": "I cannot provide an answer. Please provide more information.",
                "confidence": 0.0,
                "risks": ["..."],
            },
            "qwen",
        )
    except diamond_sch.SCHValidationError:
        pass
    else:
        raise AssertionError("refusal counsel should be rejected")


def test_council_context_has_clean_deterministic_user_fallback():
    from core import diamond_sch

    context = json.dumps({
        "session_id": "sch-test",
        "parity": "high",
        "finalized_answer": "Llama: use short transactions.\\nQwen: use a coordinator lock.",
        "risks": ["stale active flag"],
    })

    answer = diamond_sch.format_council_for_user(context)

    assert "coordinator lock" in answer
    assert "Agreement: high" in answer
    assert "stale active flag" in answer


def test_last_five_nodes_are_loaded_from_sql(monkeypatch, tmp_path):
    from core import diamond_sch

    db_path = str(tmp_path / "sch-history.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))
    conn = _connection_factory(db_path)()
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            from_agent TEXT,
            content TEXT
        )"""
    )
    for index in range(7):
        conn.execute(
            "INSERT INTO messages(conversation_id, from_agent, content) VALUES (42, ?, ?)",
            ("user" if index % 2 == 0 else "seven", f"node-{index}"),
        )
    conn.commit()
    conn.close()

    nodes = diamond_sch._last_nodes(42, [{"role": "user", "content": "fallback"}])

    assert [node["content"] for node in nodes] == [f"node-{index}" for index in range(2, 7)]


def test_diamond_sch_state_endpoint(monkeypatch, tmp_path):
    from flask import Flask
    from core import diamond_sch
    from frontend.blueprints.diamond import diamond_bp

    db_path = str(tmp_path / "sch-endpoint.db")
    monkeypatch.setattr(diamond_sch, "get_connection", _connection_factory(db_path))
    app = Flask(__name__)
    app.register_blueprint(diamond_bp)

    response = app.test_client().get("/api/diamond/sch/state")

    assert response.status_code == 200
    assert response.get_json()["sch"]["is_council_active"] == 0


def test_seven_waits_for_sch_and_injects_counsel_before_final_generation(monkeypatch):
    from agents.seven import seven_agent
    from core import diamond_sch

    seen = {}
    monkeypatch.setattr(seven_agent, "_compose", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"local_agents": []})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda *args, **kwargs: [])
    context = json.dumps({
        "session_id": "sch-test",
        "parity": "high",
        "finalized_answer": "Llama: use short transactions.\\nQwen: use a coordinator lock.",
        "risks": ["stale active flag"],
    })
    monkeypatch.setattr(
        diamond_sch,
        "route",
        lambda *args, **kwargs: diamond_sch.SCHResult(
            decision="ESCALATE",
            session_id="sch-test",
            council_context=context,
        ),
    )

    def fake_llm(message, state, memories, history, stage_cb=None):
        seen["message"] = message
        return "Final Seven answer.", 3

    monkeypatch.setattr(seven_agent, "_llm_chat", fake_llm)
    answer, tokens = seven_agent.chat("Please solve the deep locking problem.")

    assert answer.startswith("Final Seven answer.")
    assert tokens == 3
    assert "DIAMOND SCH COUNCIL DATA" in seen["message"]
    assert "coordinator lock" in seen["message"]


def test_seven_uses_council_fallback_when_tiny_model_drifts_to_status(monkeypatch):
    from agents.seven import seven_agent
    from core import diamond_sch

    context = json.dumps({
        "session_id": "sch-test",
        "parity": "high",
        "finalized_answer": "Llama: use short transactions.\\nQwen: use a coordinator lock.",
        "risks": ["stale active flag"],
    })
    monkeypatch.setattr(seven_agent, "_compose", lambda *args, **kwargs: (None, 0))
    monkeypatch.setattr(seven_agent, "_read_state", lambda: {"local_agents": []})
    monkeypatch.setattr(seven_agent, "_load_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        diamond_sch,
        "route",
        lambda *args, **kwargs: diamond_sch.SCHResult(
            decision="ESCALATE",
            session_id="sch-test",
            council_context=context,
        ),
    )
    monkeypatch.setattr(
        seven_agent,
        "_llm_chat",
        lambda *args, **kwargs: ("Open tickets: 3\\nPending proposals: 31\\nLocal agents: Qwen", 10),
    )

    answer, tokens = seven_agent.chat("/council analyze locking")

    assert "coordinator lock" in answer
    assert "Open tickets" not in answer
    assert tokens == 0
