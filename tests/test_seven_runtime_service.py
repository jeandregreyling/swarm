import json
import sqlite3
import threading
import time
import urllib.request


def _read_json(url, *, data=None, timeout=5):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_health_snapshot_is_standalone_direct_runtime():
    from core.seven_runtime import service

    snap = service.health_snapshot()

    assert snap["service"] == "seven-runtime"
    assert snap["flask_required"] is False
    assert snap["ollama_required"] is False
    assert snap["model"] == "seven-direct:daily"
    assert "direct" in snap


def test_standalone_http_health_and_models():
    from core.seven_runtime import service

    httpd = service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        health = _read_json(base + "/health")
        models = _read_json(base + "/v1/models")
    finally:
        httpd.shutdown()
        thread.join(timeout=3)

    assert health["service"] == "seven-runtime"
    assert models["object"] == "list"
    assert any(row["id"] == "seven-direct:daily" for row in models["data"])


def test_standalone_http_chat_uses_guarded_seven(monkeypatch):
    from core.seven_runtime import service

    monkeypatch.setattr(
        service,
        "guarded_chat",
        lambda payload: {
            "ok": True,
            "content": f"echo:{payload['message']}",
            "tokens": 1,
            "stages": ["test"],
            "model": "seven-direct:daily",
        },
    )
    httpd = service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        out = _read_json(base + "/chat", data={"message": "hello"})
    finally:
        httpd.shutdown()
        thread.join(timeout=3)

    assert out["ok"] is True
    assert out["content"] == "echo:hello"
    assert out["model"] == "seven-direct:daily"


def test_standalone_http_exposes_bounded_model_operator(monkeypatch):
    from core.seven_runtime import model_operator, service

    monkeypatch.setattr(model_operator, "inventory", lambda: {
        "ok": True,
        "models": [{"name": "gemma3:latest", "driver": "ollama", "installed": True}],
        "resident": [],
        "warnings": [],
    })
    monkeypatch.setattr(model_operator, "run", lambda model, prompt, **kwargs: {
        "ok": True, "model": model, "content": f"echo:{prompt}", "tokens": 1,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {
        "ok": True, "model": model, "action": "unload",
    })
    monkeypatch.setattr(model_operator, "roll_call", lambda model, **kwargs: {
        "ok": False, "model": model, "grade": "weak", "content": "A-OK!",
    })
    monkeypatch.setattr(model_operator, "peer_turn", lambda peer, question, **kwargs: {
        "ok": True, "peer": peer, "model": "gemma-direct:3", "answer": f"peer:{question}",
    })
    monkeypatch.setattr(model_operator, "constrained_peer_turn", lambda peer, question, **kwargs: {
        "ok": True, "peer": peer, "parsed": {"status": "doing"},
    })
    monkeypatch.setattr(model_operator, "consult", lambda question, **kwargs: {
        "ok": True, "answer": f"consult:{question}", "selection": {"peer": "gemma"},
    })
    monkeypatch.setattr(model_operator, "routed_acceptance_review", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "review": {"decision": "remain_supervised"},
    })
    monkeypatch.setattr(model_operator, "instruction_drill", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "passed": 2, "attempt_count": 2,
    })
    monkeypatch.setattr(model_operator, "grounded_transfer_lesson", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "grade": "passed",
    })
    monkeypatch.setattr(model_operator, "bounded_repair_lesson", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "final_grade": "passed",
    })
    monkeypatch.setattr(model_operator, "schema_constrained_lesson", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "grade": "passed",
    })
    monkeypatch.setattr(model_operator, "schema_robustness_lesson", lambda peer, **kwargs: {
        "ok": True, "peer": peer, "final_grade": "passed",
    })
    httpd = service.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        tags = _read_json(base + "/api/tags")
        run = _read_json(base + "/api/generate", data={"model": "gemma3:latest", "prompt": "health"})
        stop = _read_json(base + "/api/stop", data={"model": "gemma3:latest"})
        roll_call = _read_json(base + "/api/roll-call", data={"model": "gemma3:latest"})
        peer_turn = _read_json(base + "/api/peer-turn", data={"peer": "gemma", "question": "review this"})
        constrained = _read_json(base + "/api/constrained-peer-turn", data={"peer": "gemma", "question": "review this", "contract_name": "studio_current_step"})
        consult = _read_json(base + "/api/consult", data={"question": "plan this"})
        acceptance = _read_json(base + "/api/routed-acceptance-review", data={"peer": "gemma"})
        drill = _read_json(base + "/api/instruction-drill", data={"peer": "gemma"})
        transfer = _read_json(base + "/api/grounded-transfer-lesson", data={"peer": "gemma"})
        repair = _read_json(base + "/api/bounded-repair-lesson", data={"peer": "gemma"})
        schema = _read_json(base + "/api/schema-constrained-lesson", data={"peer": "gemma"})
        robust = _read_json(base + "/api/schema-robustness-lesson", data={"peer": "gemma"})
    finally:
        httpd.shutdown()
        thread.join(timeout=3)

    assert tags["models"][0]["name"] == "gemma3:latest"
    assert run["content"] == "echo:health"
    assert stop["ok"] is True
    assert roll_call["grade"] == "weak"
    assert peer_turn["answer"] == "peer:review this"
    assert constrained["parsed"]["status"] == "doing"
    assert consult["selection"]["peer"] == "gemma"
    assert acceptance["review"]["decision"] == "remain_supervised"
    assert drill["passed"] == 2
    assert transfer["grade"] == "passed"
    assert repair["final_grade"] == "passed"
    assert schema["grade"] == "passed"
    assert robust["final_grade"] == "passed"


def test_model_roll_call_grades_weak_and_unloads(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "run", lambda *args, **kwargs: {
        "ok": True, "model": "qwen:latest", "content": "A-OK!", "tokens": 2,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {
        "ok": True, "model": model, "action": "unloaded",
    })

    out = model_operator.roll_call("qwen:latest")

    assert out["grade"] == "weak"
    assert out["ok"] is False
    assert out["unload"]["ok"] is True


def test_direct_peer_turn_is_serialized_contextual_logged_and_unloaded(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["routing"],
        "items": [{"source": "blackboard:P-1", "content": "Routing must be truthful."}],
        "chars": 25,
    })
    calls = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: calls.append((model, prompt)) or {
        "ok": True, "model": model, "content": "Use the blackboard's direct routing rule.", "tokens": 6,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_log_peer_turn", lambda **kwargs: {"sandpit": "receipt.md"})

    out = model_operator.peer_turn("llama", "How should routing work?", project_id="P-1")

    assert out["ok"] is True
    assert out["grade"] == "passed"
    assert out["grounding_hits"] == ["blackboard"]
    assert out["model"] == "llama-direct:3.2"
    assert "Routing must be truthful." in calls[0][1]
    assert out["unload"]["ok"] is True
    assert out["receipt"]["sandpit"] == "receipt.md"


def test_relevant_context_labels_memory_authority_and_retrieves_project_sources(monkeypatch, tmp_path):
    from core.seven_runtime import model_operator

    db = tmp_path / "context.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE project_blackboard_notes (project_id TEXT, author TEXT, kind TEXT, content TEXT, status TEXT, updated_at TEXT);
        CREATE TABLE project_step_evidence (id INTEGER PRIMARY KEY, project_id TEXT, step_id TEXT, source_type TEXT, source_ref TEXT, summary TEXT, status TEXT);
        CREATE TABLE project_docs (doc_name TEXT, tags TEXT, content TEXT, updated_at TEXT);
        CREATE TABLE time_events (id INTEGER PRIMARY KEY, agent TEXT, action TEXT, event_type TEXT, target TEXT, details TEXT);
        INSERT INTO project_blackboard_notes VALUES ('P-1','seven','handoff','routing context','active','1');
        INSERT INTO project_step_evidence VALUES (1,'P-1','S-1','test','pytest','routing proof','ok');
        INSERT INTO project_docs VALUES ('P-1 guide','P-1','routing reference','1');
        INSERT INTO time_events VALUES (1,'seven','route','model','P-1','routing checkpoint');
        """
    )
    conn.commit()
    conn.close()

    def get_connection():
        out = sqlite3.connect(db)
        out.row_factory = sqlite3.Row
        return out

    monkeypatch.setattr("utils.db._connection.get_connection", get_connection)
    monkeypatch.setattr("utils.sandpits.get_all_sandpit_files", lambda: [
        {"agent": "seven", "filename": "routing.md", "content": "routing historical note"},
    ])

    out = model_operator._relevant_context("routing", project_id="P-1")
    sources = [row["source"] for row in out["items"]]

    assert any(source.startswith("authoritative:evidence:") for source in sources)
    assert any(source.startswith("coordination:blackboard:") for source in sources)
    assert any(source.startswith("durable:kc:") for source in sources)
    assert any(source.startswith("checkpoint:vortex:") for source in sources)
    assert any(source.startswith("historical:sandpit:") for source in sources)
    assert out["precedence"][0] == "authoritative:evidence"
    assert out["precedence"][-1] == "historical:sandpit"


def test_direct_peer_turn_requires_all_explicit_grounding_sources(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["thread", "blackboard", "sandpit"],
        "items": [{"source": "thread:1", "content": "Use all durable sources."}],
        "chars": 24,
    })
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "model": "llama-direct:3.2", "content": "I checked the thread.", "tokens": 4,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_log_peer_turn", lambda **kwargs: {})

    out = model_operator.peer_turn("llama", "Name the thread, blackboard, and sandpit.")

    assert out["ok"] is True
    assert out["grade"] == "weak"
    assert out["required_grounding"] == ["blackboard", "sandpit", "thread"]


def test_direct_peer_turn_requires_explicit_task_contract_terms(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["passed", "weak"],
        "items": [{"source": "thread:1", "content": "Gemma passed and Llama remains weak."}],
        "chars": 36,
    })
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "model": "llama-direct:3.2", "content": "I checked the thread.", "tokens": 4,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_log_peer_turn", lambda **kwargs: {})

    out = model_operator.peer_turn("llama", "State which lesson passed and which remains weak.")

    assert out["grade"] == "weak"
    assert out["required_terms"] == ["passed", "weak"]
    assert out["missing_terms"] == ["passed", "weak"]


def test_direct_peer_turn_requires_explicit_task_contract_phrases(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["next", "step"],
        "items": [{"source": "blackboard:P-1", "content": "Continue training."}],
        "chars": 18,
    })
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "model": "gemma-direct:3", "content": "Review the thread and blackboard.", "tokens": 6,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_log_peer_turn", lambda **kwargs: {})

    out = model_operator.peer_turn("gemma", "Plan the next step using the thread and blackboard.")

    assert out["grade"] == "weak"
    assert out["missing_phrases"] == ["next step"]


def test_constrained_peer_turn_uses_named_contract_normal_context_and_scores(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_build_named_contract", lambda *args: {
        "capability": "orchestration",
        "evidence": ("[Studio] current step is S-1 doing.",),
        "schema": {"type": "object"},
        "expected": {"step_id": "S-1", "status": "doing"},
    })
    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["studio"], "items": [{"source": "blackboard:P-1", "content": "Current training lesson."}], "chars": 24,
    })
    calls = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: calls.append((prompt, kwargs)) or {
        "ok": True, "content": '{"step_id":"S-1","status":"doing"}', "tokens": 5,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda *args, **kwargs: {"grade": args[-1]})
    monkeypatch.setattr(model_operator, "_log_constrained_peer_turn", lambda **kwargs: {"sandpit": "turn.md"})

    out = model_operator.constrained_peer_turn("gemma", "Inspect Studio.", contract_name="studio_current_step", project_id="P-1")

    assert out["ok"] is True
    assert out["grade"] == "passed"
    assert out["fallback_used"] is False
    assert "UNTRUSTED DURABLE CONTEXT" in calls[0][0]
    assert "AUTHORITATIVE EVIDENCE always wins" in calls[0][0]
    assert calls[0][1]["response_format"]["type"] == "json_schema"
    assert out["ready_for_autonomy"] is False


def test_constrained_peer_turn_repairs_context_conflict_with_authoritative_evidence(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_build_named_contract", lambda *args: {
        "capability": "orchestration",
        "evidence": ("[Studio] current step is S-NEW doing.",),
        "schema": {"type": "object"},
        "expected": {"step_id": "S-NEW", "status": "doing"},
    })
    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {
        "keywords": ["studio"],
        "items": [{"source": "blackboard:P-1", "content": "Historical step S-OLD is done."}],
        "chars": 30,
    })
    answers = iter([
        '{"step_id":"S-OLD","status":"done"}',
        '{"step_id":"S-NEW","status":"doing"}',
    ])
    prompts = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: prompts.append(prompt) or {
        "ok": True, "content": next(answers), "tokens": 5,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_constrained_peer_turn", lambda **kwargs: {})

    out = model_operator.constrained_peer_turn(
        "gemma", "Inspect current Studio.", contract_name="studio_current_step", project_id="P-1"
    )

    assert out["ok"] is True
    assert out["grade"] == "passed"
    assert out["authoritative_repair_used"] is True
    assert [row["grade"] for row in out["attempts"]] == ["weak", "passed"]
    assert "Historical step S-OLD" in prompts[0]
    assert "Historical step S-OLD" not in prompts[1]
    assert "one bounded repair attempt" in prompts[1]
    assert out["ready_for_autonomy"] is False


def test_constrained_peer_turn_visibly_falls_back_only_on_constraint_failure(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "_build_named_contract", lambda *args: {
        "capability": "research", "evidence": ("scores",), "schema": {"type": "object"}, "expected": {"mode": "supervised_only"},
    })
    monkeypatch.setattr(model_operator, "_relevant_context", lambda *args, **kwargs: {"keywords": [], "items": [], "chars": 0})
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {"ok": False, "error": "schema unavailable", "content": ""})
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "peer_turn", lambda *args, **kwargs: {"ok": True, "grade": "passed", "answer": "visible fallback"})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_constrained_peer_turn", lambda **kwargs: {})

    out = model_operator.constrained_peer_turn("llama", "Check readiness.", contract_name="peer_readiness")

    assert out["ok"] is False
    assert out["grade"] == "failed"
    assert out["fallback_used"] is True
    assert out["fallback"]["answer"] == "visible fallback"
    assert out["runtime"]["error"] == "schema unavailable"
    assert out["authoritative_repair_used"] is True
    assert [row["grade"] for row in out["attempts"]] == ["failed", "failed"]


def test_instruction_drill_is_isolated_exact_graded_logged_and_unloaded(monkeypatch):
    from core.seven_runtime import model_operator

    answers = iter(["SEVEN_DRILL_OK", "NEXT_STEP: inspect one Studio task"])
    prompts = []
    unloads = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: prompts.append(prompt) or {
        "ok": True, "model": model, "content": next(answers), "tokens": 4,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: unloads.append(model) or {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_instruction_grade", lambda peer, grade, contract: {
        "agent": peer, "capability": "instruction_following", "grade": grade, "contract": contract,
    })
    monkeypatch.setattr(model_operator, "_log_instruction_drill", lambda **kwargs: {"sandpit": "drill.md"})

    out = model_operator.instruction_drill("gemma", project_id="P-1")

    assert out["ok"] is True
    assert out["isolated"] is True
    assert out["passed"] == 2
    assert out["ready_for_autonomy"] is False
    assert all("DURABLE CONTEXT" not in prompt for prompt in prompts)
    assert len(unloads) >= 2
    assert out["receipt"]["sandpit"] == "drill.md"


def test_instruction_drill_requires_exact_output(monkeypatch):
    from core.seven_runtime import model_operator

    answers = iter(["SEVEN_DRILL_OK!", "NEXT_STEP: inspect one Studio task"])
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": next(answers), "tokens": 4,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_instruction_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_instruction_drill", lambda **kwargs: {})

    out = model_operator.instruction_drill("llama")

    assert out["ok"] is False
    assert out["passed"] == 1
    assert out["attempts"][0]["grade"] == "weak"
    assert out["attempts"][1]["grade"] == "passed"


def test_grounded_transfer_uses_curated_evidence_exact_grading_and_unloads(monkeypatch):
    from core.seven_runtime import model_operator

    prompts = []
    unloads = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: prompts.append(prompt) or {
        "ok": True, "model": model, "content": "STATUS: doing\nNEXT_STEP: grounded transfer", "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: unloads.append(model) or {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_transfer_grade", lambda peer, capability, grade: {
        "agent": peer, "capability": capability, "grade": grade,
    })
    monkeypatch.setattr(model_operator, "_log_grounded_transfer", lambda **kwargs: {"sandpit": "transfer.md"})

    out = model_operator.grounded_transfer_lesson("gemma", project_id="P-1")

    assert out["ok"] is True
    assert out["grade"] == "passed"
    assert out["capability"] == "orchestration"
    assert out["curated"] is True
    assert out["ready_for_autonomy"] is False
    assert "CURATED EVIDENCE" in prompts[0]
    assert "DURABLE CONTEXT" not in prompts[0]
    assert unloads
    assert out["receipt"]["sandpit"] == "transfer.md"


def test_grounded_transfer_requires_exact_derived_answer(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": "Both peers passed.", "tokens": 4,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_transfer_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_grounded_transfer", lambda **kwargs: {})

    out = model_operator.grounded_transfer_lesson("llama")

    assert out["ok"] is False
    assert out["grade"] == "weak"
    assert out["expected"] == "EVIDENCE: Gemma 2/2; Llama 2/2\nOUTCOME: supervised-only"


def test_transfer_validator_reports_deterministic_defects():
    from core.seven_runtime import model_operator

    out = model_operator.validate_transfer_answer("gemma", "STATUS: Doing.\nNEXT_STEP: Grounded transfer.")

    assert out["valid"] is False
    assert out["defects"] == [
        "line_1:terminal_punctuation",
        "line_1:case_mismatch",
        "line_2:terminal_punctuation",
        "line_2:case_mismatch",
    ]


def test_bounded_repair_allows_one_retry_preserves_attempts_and_scores_once(monkeypatch):
    from core.seven_runtime import model_operator

    answers = iter(["STATUS: Doing.\nNEXT_STEP: Grounded transfer.", "STATUS: doing\nNEXT_STEP: grounded transfer"])
    prompts = []
    unloads = []
    score_updates = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: prompts.append(prompt) or {
        "ok": True, "model": model, "content": next(answers), "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: unloads.append(model) or {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_transfer_grade", lambda peer, capability, grade: score_updates.append(grade) or {
        "agent": peer, "capability": capability, "grade": grade,
    })
    monkeypatch.setattr(model_operator, "_log_bounded_repair", lambda **kwargs: {"sandpit": "repair.md"})

    out = model_operator.bounded_repair_lesson("gemma", project_id="P-1")

    assert out["ok"] is True
    assert out["repaired"] is True
    assert out["attempt_count"] == 2
    assert out["attempts"][0]["grade"] == "weak"
    assert out["attempts"][1]["grade"] == "passed"
    assert "DETERMINISTIC VALIDATOR DEFECTS" in prompts[1]
    assert "STATUS: doing\nNEXT_STEP: grounded transfer" not in prompts[1]
    assert score_updates == ["passed"]
    assert len(unloads) >= 2
    assert out["ready_for_autonomy"] is False


def test_bounded_repair_stops_after_one_failed_retry(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": "wrong", "tokens": 2,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_transfer_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_bounded_repair", lambda **kwargs: {})

    out = model_operator.bounded_repair_lesson("llama")

    assert out["ok"] is False
    assert out["attempt_count"] == 2
    assert out["final_grade"] == "weak"
    assert out["repaired"] is False


def test_schema_constrained_lesson_passes_schema_and_preserves_raw_output(monkeypatch):
    from core.seven_runtime import model_operator

    calls = []
    monkeypatch.setattr(model_operator, "run_direct", lambda model, prompt, **kwargs: calls.append(kwargs) or {
        "ok": True, "content": '{"status":"doing","next_step":"grounded transfer"}', "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda peer, capability, grade: {"grade": grade})
    monkeypatch.setattr(model_operator, "_log_schema_lesson", lambda **kwargs: {"sandpit": "schema.md"})

    out = model_operator.schema_constrained_lesson("gemma", project_id="P-1")

    assert out["ok"] is True
    assert out["grade"] == "passed"
    assert out["raw_answer"] == '{"status":"doing","next_step":"grounded transfer"}'
    assert out["parsed"] == {"status": "doing", "next_step": "grounded transfer"}
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert len(calls[0]["response_format"]["json_schema"]["schema"]["properties"]["status"]["enum"]) > 1
    assert out["ready_for_autonomy"] is False


def test_schema_constrained_lesson_grades_valid_decoy_json_weak(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": '{"gemma_passes":"2/2","llama_passes":"2/2","outcome":"autonomous"}', "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_schema_lesson", lambda **kwargs: {})

    out = model_operator.schema_constrained_lesson("llama")

    assert out["ok"] is False
    assert out["grade"] == "weak"
    assert out["parsed"]["outcome"] == "autonomous"


def test_schema_robustness_runs_varied_matrix_and_scores_once(monkeypatch):
    from core.seven_runtime import model_operator

    answers = iter([
        '{"status":"todo","next_step":"isolated drill"}',
        '{"status":"doing","next_step":"grounded transfer"}',
        '{"status":"blocked","next_step":"autonomy"}',
    ])
    score_updates = []
    unloads = []
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": next(answers), "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: unloads.append(model) or {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda peer, capability, grade: score_updates.append(grade) or {"grade": grade})
    monkeypatch.setattr(model_operator, "_log_schema_robustness", lambda **kwargs: {"sandpit": "robust.md"})

    out = model_operator.schema_robustness_lesson("gemma")

    assert out["ok"] is True
    assert out["passed"] == 3
    assert out["variant_count"] == 3
    assert score_updates == ["passed"]
    assert len(unloads) >= 3
    assert out["ready_for_autonomy"] is False


def test_schema_robustness_rejects_semantic_decoy_selection(monkeypatch):
    from core.seven_runtime import model_operator

    answers = iter([
        '{"gemma_passes":"0/2","llama_passes":"0/2","outcome":"blocked"}',
        '{"gemma_passes":"1/2","llama_passes":"1/2","outcome":"autonomous"}',
        '{"gemma_passes":"2/2","llama_passes":"2/2","outcome":"autonomous"}',
    ])
    monkeypatch.setattr(model_operator, "run_direct", lambda *args, **kwargs: {
        "ok": True, "content": next(answers), "tokens": 8,
    })
    monkeypatch.setattr(model_operator, "stop", lambda model: {"ok": True, "model": model})
    monkeypatch.setattr(model_operator, "_record_schema_grade", lambda *args, **kwargs: {})
    monkeypatch.setattr(model_operator, "_log_schema_robustness", lambda **kwargs: {})

    out = model_operator.schema_robustness_lesson("llama")

    assert out["ok"] is False
    assert out["passed"] == 2
    assert out["final_grade"] == "weak"
    assert out["variants"][1]["grade"] == "weak"


def test_task_fit_selector_is_explainable_and_conservative(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr("core.agent_scorecards.list_scorecards", lambda **kwargs: [{
        "agent": kwargs["agents"][0], "capability": kwargs["capability"], "score": 0.8, "confidence": 0.7,
        "evidence_count": 2, "source": "lesson",
    }])

    research = model_operator.select_peer("Research and compare the evidence.")
    planning = model_operator.select_peer("Plan the next step.")
    ambiguous = model_operator.select_peer("Help with this.")

    assert research["peer"] == "llama"
    assert research["capability"] == "research"
    assert "research" in research["reason"]
    assert research["trusted"] is True
    assert planning["peer"] == "gemma"
    assert planning["capability"] == "orchestration"
    assert ambiguous["peer"] == "gemma"
    assert "conservative synthesis fallback" in ambiguous["reason"]


def test_consult_selects_one_peer_and_teaches_scorecard(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "select_peer", lambda question: {
        "peer": "llama", "model": "llama-direct:3.2", "capability": "research", "reason": "test", "matched": [], "scorecard": {},
    })
    monkeypatch.setattr(model_operator, "peer_turn", lambda peer, question, **kwargs: {
        "ok": True, "peer": peer, "grade": "passed", "answer": "evidence",
    })
    monkeypatch.setattr(model_operator, "_record_peer_grade", lambda selection, result: {
        "agent": selection["peer"], "capability": selection["capability"], "score": 0.81,
    })

    out = model_operator.consult("research this")

    assert out["selection"]["peer"] == "llama"
    assert out["scorecard_update"]["capability"] == "research"
    assert out["consult_route"]["route"] == "free_form"
    assert out["autonomous_allowed"] is False


def test_consult_routes_eligible_supervised_questions_through_named_contract(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr(model_operator, "select_peer", lambda question: {
        "peer": "gemma", "model": "gemma-direct:3", "capability": "orchestration",
        "reason": "test", "matched": ["current", "studio"], "scorecard": {}, "trusted": False,
    })
    monkeypatch.setattr(model_operator, "constrained_peer_turn", lambda peer, question, **kwargs: {
        "ok": True, "peer": peer, "grade": "passed", "parsed": {"step_id": "S-1"},
        "scorecard_update": {"capability": "orchestration"},
    })
    monkeypatch.setattr(model_operator, "peer_turn", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("free form not expected")))

    out = model_operator.consult("Inspect the current Studio lesson status.", project_id="P-1")

    assert out["consult_route"]["route"] == "constrained"
    assert out["consult_route"]["contract_name"] == "studio_current_step"
    assert out["parsed"]["step_id"] == "S-1"
    assert out["autonomous_allowed"] is False


def test_consult_does_not_route_ambiguous_questions_to_named_contract():
    from core.seven_runtime import model_operator

    route = model_operator.select_consult_contract(
        {"peer": "gemma", "capability": "orchestration"},
        "Plan something useful.",
        "P-1",
    )

    assert route["contract_name"] == ""


def test_trust_promotion_review_uses_fresh_scorecard_and_keeps_review_non_autonomous(monkeypatch):
    from core.seven_runtime import model_operator

    monkeypatch.setattr("core.agent_scorecards.list_scorecards", lambda **kwargs: [{
        "agent": kwargs["agents"][0], "capability": kwargs["capability"], "score": 0.71,
        "confidence": 1.0, "evidence_count": 12, "source": "seven:schema_constrained_lesson",
    }])
    attempts = [{"grade": "passed", "fallback_used": False}, {"grade": "passed", "fallback_used": False}]

    out = model_operator.trust_promotion_review("gemma", "orchestration", attempts)

    assert out["repeated_acceptance"] is True
    assert out["threshold_passed"] is True
    assert out["promotion_approved"] is True
    assert out["decision"] == "promotion_candidate"
    assert out["autonomous_allowed"] is False


def test_routed_acceptance_review_repeats_consults_and_rejects_fallback(monkeypatch):
    from core.seven_runtime import model_operator

    attempts = iter([
        {"grade": "passed", "fallback_used": False},
        {"grade": "failed", "fallback_used": True},
    ])
    monkeypatch.setattr(model_operator, "consult", lambda *args, **kwargs: next(attempts))
    monkeypatch.setattr(model_operator, "trust_promotion_review", lambda peer, capability, rows: {
        "repeated_acceptance": False, "decision": "remain_supervised", "autonomous_allowed": False,
    })

    out = model_operator.routed_acceptance_review("llama", project_id="P-1", rounds=2)

    assert out["ok"] is False
    assert len(out["attempts"]) == 2
    assert out["review"]["decision"] == "remain_supervised"
    assert out["autonomous_allowed"] is False


def test_guarded_chat_timeout_returns_promptly(monkeypatch):
    from core.seven_runtime import service

    def slow_chat(_payload):
        time.sleep(3)
        return {"ok": True, "content": "late", "tokens": 1}

    monkeypatch.setattr(service, "_chat", slow_chat)
    started = time.monotonic()
    out = service.guarded_chat({"message": "hello", "timeout_seconds": 1})
    elapsed = time.monotonic() - started

    assert out["ok"] is False
    assert "timeout after 1s" in out["error"]
    assert elapsed < 2
