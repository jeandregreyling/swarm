"""Bounded local-model controls owned by the standalone Seven runtime."""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

import requests

from core import model_runtime_gateway as gateway

SPEAKER_LOCK = threading.Lock()
_DIRECT_PEERS = {"gemma": "gemma-direct:3", "llama": "llama-direct:3.2"}
_TASK_FIT_RULES = (
    ("research", "llama", ("research", "find", "source", "evidence", "investigate", "compare", "history", "inspect")),
    ("synthesis", "gemma", ("summarise", "summarize", "synthesise", "synthesize", "combine", "conclude", "final answer")),
    ("orchestration", "gemma", ("plan", "route", "coordinate", "prioritise", "prioritize", "decide", "next step")),
)
_CONTRACT_TERMS = ("passed", "weak", "failed", "blocked", "done", "todo")
_CONTRACT_PHRASES = ("next step",)
_INSTRUCTION_DRILL_CONTRACTS = (
    {
        "name": "exact_marker",
        "expected": "SEVEN_DRILL_OK",
        "instruction": "Reply with exactly this text and nothing else: SEVEN_DRILL_OK",
    },
    {
        "name": "exact_next_step",
        "expected": "NEXT_STEP: inspect one Studio task",
        "instruction": "Reply with exactly this text and nothing else: NEXT_STEP: inspect one Studio task",
    },
)
_GROUNDED_TRANSFER_PACKETS = {
    "gemma": {
        "capability": "orchestration",
        "evidence": (
            "[Studio] The supervised multi-model training curriculum status is doing.",
            "[Training policy] The next action is grounded transfer.",
        ),
        "contract": (
            "Return exactly two lines. Line 1: STATUS: <Studio curriculum status>. "
            "Line 2: NEXT_STEP: <next action from training policy>. "
            "Copy evidence values verbatim, keep labels exactly uppercase, and add no terminal punctuation."
        ),
        "expected": "STATUS: doing\nNEXT_STEP: grounded transfer",
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "doing", "done", "blocked"]},
                "next_step": {"type": "string", "enum": ["isolated drill", "grounded transfer", "autonomy"]},
            },
            "required": ["status", "next_step"],
            "additionalProperties": False,
        },
        "expected_json": {"status": "doing", "next_step": "grounded transfer"},
    },
    "llama": {
        "capability": "research",
        "evidence": (
            "[Gemma drill receipt] passed 2/2 exact contracts.",
            "[Llama drill receipt] passed 2/2 exact contracts.",
            "[Autonomy policy] both peers remain supervised-only.",
        ),
        "contract": (
            "Return exactly two lines. Line 1: EVIDENCE: Gemma <pass count>; Llama <pass count>. "
            "Line 2: OUTCOME: <autonomy state>. "
            "Copy full evidence values verbatim including slash characters, keep labels exactly uppercase, "
            "and add no terminal punctuation."
        ),
        "expected": "EVIDENCE: Gemma 2/2; Llama 2/2\nOUTCOME: supervised-only",
        "schema": {
            "type": "object",
            "properties": {
                "gemma_passes": {"type": "string", "enum": ["0/2", "1/2", "2/2"]},
                "llama_passes": {"type": "string", "enum": ["0/2", "1/2", "2/2"]},
                "outcome": {"type": "string", "enum": ["supervised-only", "autonomous", "blocked"]},
            },
            "required": ["gemma_passes", "llama_passes", "outcome"],
            "additionalProperties": False,
        },
        "expected_json": {"gemma_passes": "2/2", "llama_passes": "2/2", "outcome": "supervised-only"},
    },
}
_SCHEMA_ROBUSTNESS_VARIANTS = {
    "gemma": (
        {
            "name": "correct_first",
            "evidence": ("[Studio] Curriculum status is todo.", "[Training policy] Next action is isolated drill."),
            "expected": {"status": "todo", "next_step": "isolated drill"},
            "enums": {"status": ["todo", "doing", "done", "blocked"], "next_step": ["isolated drill", "grounded transfer", "autonomy"]},
        },
        {
            "name": "correct_middle",
            "evidence": ("[Studio] Curriculum status is doing.", "[Training policy] Next action is grounded transfer."),
            "expected": {"status": "doing", "next_step": "grounded transfer"},
            "enums": {"status": ["todo", "doing", "done", "blocked"], "next_step": ["isolated drill", "grounded transfer", "autonomy"]},
        },
        {
            "name": "correct_last",
            "evidence": ("[Studio] Curriculum status is blocked.", "[Training policy] Next action is autonomy."),
            "expected": {"status": "blocked", "next_step": "autonomy"},
            "enums": {"status": ["done", "doing", "todo", "blocked"], "next_step": ["isolated drill", "grounded transfer", "autonomy"]},
        },
    ),
    "llama": (
        {
            "name": "correct_first",
            "evidence": ("[Gemma receipt] passed 0/2.", "[Llama receipt] passed 0/2.", "[Policy] outcome is blocked."),
            "expected": {"gemma_passes": "0/2", "llama_passes": "0/2", "outcome": "blocked"},
            "enums": {"gemma_passes": ["0/2", "1/2", "2/2"], "llama_passes": ["0/2", "1/2", "2/2"], "outcome": ["blocked", "supervised-only", "autonomous"]},
        },
        {
            "name": "correct_middle",
            "evidence": ("[Gemma receipt] passed 1/2.", "[Llama receipt] passed 1/2.", "[Policy] outcome is supervised-only."),
            "expected": {"gemma_passes": "1/2", "llama_passes": "1/2", "outcome": "supervised-only"},
            "enums": {"gemma_passes": ["0/2", "1/2", "2/2"], "llama_passes": ["0/2", "1/2", "2/2"], "outcome": ["blocked", "supervised-only", "autonomous"]},
        },
        {
            "name": "correct_last",
            "evidence": ("[Gemma receipt] passed 2/2.", "[Llama receipt] passed 2/2.", "[Policy] outcome is autonomous."),
            "expected": {"gemma_passes": "2/2", "llama_passes": "2/2", "outcome": "autonomous"},
            "enums": {"gemma_passes": ["0/2", "1/2", "2/2"], "llama_passes": ["0/2", "1/2", "2/2"], "outcome": ["blocked", "supervised-only", "autonomous"]},
        },
    ),
}


def inventory() -> dict[str, Any]:
    installed: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        response = requests.get(f"{gateway.OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        for row in (response.json() or {}).get("models") or []:
            name = str(row.get("name") or row.get("model") or "").strip()
            if name:
                installed.append({
                    "name": name,
                    "driver": "ollama",
                    "role": "local",
                    "installed": True,
                })
    except Exception as exc:
        warnings.append(f"ollama inventory unavailable: {exc}")

    try:
        from core.seven_llm import registry
        for entry in registry.list_models():
            if entry.driver != "llamacpp":
                continue
            installed.append({
                "name": entry.name,
                "driver": "llamacpp",
                "role": entry.role,
                "installed": bool(entry.path and os.path.isfile(entry.path)),
            })
    except Exception as exc:
        warnings.append(f"direct inventory unavailable: {exc}")

    resident = gateway.ollama_health()
    resident_names = {str(row.get("name") or "") for row in resident.get("models") or []}
    for row in installed:
        row["resident"] = row["name"] in resident_names
    return {
        "ok": bool(installed),
        "models": installed,
        "resident": list(resident.get("models") or []),
        "warnings": warnings + list(resident.get("warnings") or []),
    }


def run(model: str, prompt: str, *, timeout_seconds: int = 120, keep_alive: Any = "60s") -> dict[str, Any]:
    model = str(model or "").strip()
    prompt = str(prompt or "").strip()
    if not model or not prompt:
        return {"ok": False, "model": model, "error": "model and prompt are required"}
    known = {row["name"] for row in inventory().get("models") or [] if row.get("installed")}
    if model not in known:
        return {"ok": False, "model": model, "error": "model is not installed or registered"}
    timeout = max(15, min(int(timeout_seconds or 120), 600))
    result = gateway.chat(
        model,
        [{"role": "user", "content": prompt}],
        absolute_timeout_s=timeout,
        idle_timeout_s=timeout,
        keep_alive=keep_alive,
        options={"num_predict": 128},
    )
    return result.as_dict()


def run_direct(
    model: str,
    prompt: str,
    *,
    timeout_seconds: int = 120,
    response_format: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a registered GGUF without querying or falling back to Ollama."""
    model = str(model or "").strip()
    prompt = str(prompt or "").strip()
    if not model or not prompt:
        return {"ok": False, "model": model, "error": "model and prompt are required"}
    try:
        from core.seven_llm import registry
        entry = registry.get(model)
    except Exception as exc:
        return {"ok": False, "model": model, "error": f"direct registry unavailable: {exc}"}
    if not entry or entry.driver != "llamacpp" or not entry.path or not os.path.isfile(entry.path):
        return {"ok": False, "model": model, "error": "model is not a registered direct GGUF"}
    timeout = max(15, min(int(timeout_seconds or 120), 600))
    result = gateway.chat(
        model,
        [{"role": "user", "content": prompt}],
        absolute_timeout_s=timeout,
        idle_timeout_s=timeout,
        keep_alive=0,
        options={"num_predict": 96},
        response_format=response_format,
    )
    return result.as_dict()


def stop(model: str) -> dict[str, Any]:
    model = str(model or "").strip()
    if not model:
        return {"ok": False, "model": "", "error": "model is required"}
    try:
        from core.seven_llm import llama_server, registry
        entry = registry.get(model)
        if entry and entry.driver == "llamacpp":
            stopped = bool(llama_server.stop(model))
            return {"ok": stopped, "model": model, "action": "direct_stop"}
    except Exception:
        pass
    return gateway.force_unload(model)


def roll_call(model: str, *, timeout_seconds: int = 120) -> dict[str, Any]:
    """Run and grade one model health check, then always unload it."""
    model = str(model or "").strip()
    marker = "SEVEN_MODEL_ROLL_CALL_OK"
    result = run(
        model,
        f"Reply exactly: {marker}",
        timeout_seconds=timeout_seconds,
        keep_alive="5m",
    )
    content = str(result.get("content") or "").strip()
    if not result.get("ok"):
        grade = "failed"
    elif content == marker:
        grade = "passed"
    else:
        grade = "weak"
    unload = stop(model)
    return {
        "ok": grade == "passed",
        "model": model,
        "grade": grade,
        "expected": marker,
        "content": content,
        "runtime": result,
        "unload": unload,
    }


def _keywords(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9_-]{3,}", str(text or "").lower())
        if word not in {
            "about", "after", "and", "answering", "asking", "before", "current", "define",
            "for", "from", "have", "may", "review", "rule", "safest", "that", "the", "their",
            "there", "they", "this", "using", "what", "when", "where", "while", "with", "would",
        }
    }


def _relevant_context(question: str, *, conversation_id: Any = None, project_id: str = "", max_chars: int = 4000) -> dict[str, Any]:
    """Retrieve durable context and keep only rows pertinent to this peer turn."""
    terms = _keywords(question)
    candidates: list[tuple[int, str, str]] = []

    def add(source: str, text: Any) -> None:
        clean = str(text or "").strip()
        if not clean or len(clean) > 200000:
            return
        score = sum(1 for term in terms if term in clean.lower())
        candidates.append((score, source, clean))

    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            if conversation_id:
                rows = conn.execute(
                    """SELECT from_agent, to_agent, content FROM messages
                       WHERE conversation_id=? ORDER BY id DESC LIMIT 200""",
                    (int(conversation_id),),
                ).fetchall()
                for row in reversed(rows):
                    add(f"thread:{conversation_id}", f"{row['from_agent']} -> {row['to_agent']}: {row['content']}")
            if project_id:
                rows = conn.execute(
                    """SELECT author, kind, content FROM project_blackboard_notes
                       WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT 100""",
                    (str(project_id),),
                ).fetchall()
                for row in rows:
                    add(f"coordination:blackboard:{project_id}", f"{row['author']} [{row['kind']}]: {row['content']}")
                rows = conn.execute(
                    """SELECT step_id, source_type, source_ref, summary, status FROM project_step_evidence
                       WHERE project_id=? ORDER BY id DESC LIMIT 100""",
                    (str(project_id),),
                ).fetchall()
                for row in rows:
                    add(
                        f"authoritative:evidence:{row['step_id']}",
                        f"{row['status']} {row['source_type']} {row['source_ref']}: {row['summary']}",
                    )
                rows = conn.execute(
                    """SELECT doc_name, tags, content FROM project_docs
                       WHERE doc_name LIKE ? OR content LIKE ? OR tags LIKE ?
                       ORDER BY updated_at DESC LIMIT 50""",
                    (f"%{project_id}%", f"%{project_id}%", f"%{project_id}%"),
                ).fetchall()
                for row in rows:
                    add(f"durable:kc:{row['doc_name']}", f"tags={row['tags']}: {row['content']}")
                rows = conn.execute(
                    """SELECT agent, action, event_type, target, details FROM time_events
                       WHERE target LIKE ? OR details LIKE ?
                       ORDER BY id DESC LIMIT 50""",
                    (f"%{project_id}%", f"%{project_id}%"),
                ).fetchall()
                for row in rows:
                    add(
                        f"checkpoint:vortex:{row['event_type']}",
                        f"{row['agent']} {row['action']} target={row['target']} details={row['details']}",
                    )
        finally:
            conn.close()
    except Exception:
        pass

    try:
        from utils import sandpits
        for row in sandpits.get_all_sandpit_files():
            filename = str(row.get("filename") or "").lower()
            if filename.endswith((".html", ".json", ".log")):
                continue
            add(f"historical:sandpit:{row.get('agent')}/{row.get('filename')}", row.get("content"))
    except Exception:
        pass

    selected: list[dict[str, str]] = []
    used = 0
    for score, source, text in sorted(candidates, key=lambda row: row[0], reverse=True):
        if terms and score <= 0:
            continue
        excerpt = text[:2000]
        if used + len(excerpt) > max_chars:
            excerpt = excerpt[: max(0, max_chars - used)]
        if not excerpt:
            break
        selected.append({"source": source, "content": excerpt})
        used += len(excerpt)
        if used >= max_chars:
            break
    return {
        "keywords": sorted(terms),
        "items": selected,
        "chars": used,
        "precedence": [
            "authoritative:evidence",
            "coordination:blackboard",
            "durable:kc",
            "checkpoint:vortex",
            "thread",
            "historical:sandpit",
        ],
    }


def _log_peer_turn(
    *,
    peer: str,
    model: str,
    question: str,
    answer: str,
    conversation_id: Any = None,
    project_id: str = "",
    status: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"conversation": False, "blackboard": "", "sandpit": "", "vortex_event": False}
    summary = f"Seven direct peer turn | peer={peer} model={model} status={status}\nQuestion: {question[:1000]}\nAnswer: {answer[:2000]}"
    if conversation_id:
        try:
            from utils.db.chat import log_message
            log_message(int(conversation_id), "seven", question, to_agent=peer, message_type="peer_question")
            log_message(int(conversation_id), peer, answer, to_agent="seven", message_type="peer_answer")
            receipt["conversation"] = True
        except Exception:
            pass
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="handoff") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-peer-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="direct_peer_turn",
            event_type="model",
            target=peer,
            details={"model": model, "status": status, "conversation_id": conversation_id, "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def _log_instruction_drill(
    *,
    peer: str,
    model: str,
    attempts: list[dict[str, Any]],
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    passed = sum(1 for row in attempts if row.get("grade") == "passed")
    lines = [
        f"Seven isolated instruction drill | peer={peer} model={model} passed={passed}/{len(attempts)}",
        "No thread, blackboard, Knowledge Center, or sandpit context was injected.",
    ]
    for row in attempts:
        lines.append(
            f"- {row['contract']}: grade={row['grade']} expected={row['expected']!r} answer={row['answer'][:500]!r}"
        )
    summary = "\n".join(lines)
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-drill-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="isolated_instruction_drill",
            event_type="model",
            target=peer,
            details={"model": model, "passed": passed, "attempts": len(attempts), "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def _record_instruction_grade(peer: str, grade: str, contract: str) -> dict[str, Any]:
    try:
        from core.agent_scorecards import record_capability_result
        return record_capability_result(
            peer,
            "instruction_following",
            success=grade == "passed",
            quality_delta=0.10 if grade == "passed" else (-0.08 if grade == "weak" else -0.15),
            source="seven:isolated_instruction_drill",
            notes=f"Isolated exact-match drill contract={contract}; grade={grade}",
        )
    except Exception as exc:
        return {"error": str(exc)}


def instruction_drill(
    peer: str,
    *,
    project_id: str = "",
    rounds: int = 1,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Train one peer on exact contracts without injecting any durable context."""
    peer = str(peer or "").strip().lower()
    model = _DIRECT_PEERS.get(peer, "")
    if not model:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama"}
    rounds = max(1, min(int(rounds or 1), 3))
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 120), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    attempts: list[dict[str, Any]] = []
    try:
        for round_index in range(rounds):
            for contract in _INSTRUCTION_DRILL_CONTRACTS:
                prompt = (
                    "This is an isolated instruction-following drill from Seven. "
                    "There is no prior context to retrieve or discuss. "
                    "Follow the instruction literally; do not explain, preface, quote, or add punctuation.\n\n"
                    f"INSTRUCTION:\n{contract['instruction']}"
                )
                runtime = run_direct(model, prompt, timeout_seconds=timeout_seconds)
                answer = str(runtime.get("content") or runtime.get("error") or "").strip()
                if not runtime.get("ok") or not runtime.get("content"):
                    grade = "failed"
                elif answer == contract["expected"]:
                    grade = "passed"
                else:
                    grade = "weak"
                unload = stop(model)
                attempts.append({
                    "round": round_index + 1,
                    "contract": contract["name"],
                    "expected": contract["expected"],
                    "answer": answer,
                    "grade": grade,
                    "runtime": runtime,
                    "unload": unload,
                    "scorecard_update": _record_instruction_grade(peer, grade, contract["name"]),
                })
        passed = sum(1 for row in attempts if row["grade"] == "passed")
        receipt = _log_instruction_drill(peer=peer, model=model, attempts=attempts, project_id=project_id)
        return {
            "ok": passed == len(attempts),
            "peer": peer,
            "model": model,
            "isolated": True,
            "rounds": rounds,
            "passed": passed,
            "attempt_count": len(attempts),
            "ready_for_autonomy": False,
            "attempts": attempts,
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        stop(model)
        SPEAKER_LOCK.release()


def _log_grounded_transfer(
    *,
    peer: str,
    model: str,
    capability: str,
    evidence: tuple[str, ...],
    expected: str,
    answer: str,
    grade: str,
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    summary = (
        f"Seven curated grounded transfer | peer={peer} model={model} capability={capability} grade={grade}\n"
        f"Evidence: {' | '.join(evidence)}\nExpected: {expected!r}\nAnswer: {answer[:1000]!r}"
    )
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-transfer-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="curated_grounded_transfer",
            event_type="model",
            target=peer,
            details={"model": model, "capability": capability, "grade": grade, "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def _record_transfer_grade(peer: str, capability: str, grade: str) -> dict[str, Any]:
    try:
        from core.agent_scorecards import record_capability_result
        return record_capability_result(
            peer,
            capability,
            success=grade == "passed",
            quality_delta=0.10 if grade == "passed" else (-0.08 if grade == "weak" else -0.15),
            source="seven:curated_grounded_transfer",
            notes=f"Curated grounded transfer; grade={grade}; autonomy remained disabled",
        )
    except Exception as exc:
        return {"error": str(exc)}


def _record_schema_grade(peer: str, capability: str, grade: str) -> dict[str, Any]:
    try:
        from core.agent_scorecards import record_capability_result
        return record_capability_result(
            peer,
            capability,
            success=grade == "passed",
            quality_delta=0.10 if grade == "passed" else (-0.08 if grade == "weak" else -0.15),
            source="seven:schema_constrained_lesson",
            notes=f"Schema-constrained grounded lesson; grade={grade}; autonomy remained disabled",
        )
    except Exception as exc:
        return {"error": str(exc)}


def validate_transfer_answer(peer: str, answer: str) -> dict[str, Any]:
    """Return deterministic contract defects without rewriting the peer answer."""
    packet = _GROUNDED_TRANSFER_PACKETS.get(str(peer or "").strip().lower())
    if not packet:
        return {"valid": False, "defects": ["unknown_peer"]}
    answer = str(answer or "").strip()
    lines = answer.splitlines()
    expected_lines = str(packet["expected"]).splitlines()
    defects: list[str] = []
    if len(lines) != len(expected_lines):
        defects.append(f"line_count:{len(lines)}_expected:{len(expected_lines)}")
    for index, expected_line in enumerate(expected_lines):
        line_number = index + 1
        actual = lines[index] if index < len(lines) else ""
        expected_label = expected_line.split(":", 1)[0] + ":"
        if not actual.startswith(expected_label):
            defects.append(f"line_{line_number}:label_mismatch")
        if actual.endswith((".", "!", "?")):
            defects.append(f"line_{line_number}:terminal_punctuation")
        if actual != expected_line:
            without_terminal = actual.rstrip(".!?")
            if without_terminal == expected_line:
                pass
            elif without_terminal.lower() == expected_line.lower():
                defects.append(f"line_{line_number}:case_mismatch")
            else:
                defects.append(f"line_{line_number}:value_not_verbatim")
    return {"valid": not defects, "defects": defects}


def grounded_transfer_lesson(
    peer: str,
    *,
    project_id: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Test exact instruction transfer using a small curated evidence packet."""
    peer = str(peer or "").strip().lower()
    model = _DIRECT_PEERS.get(peer, "")
    packet = _GROUNDED_TRANSFER_PACKETS.get(peer)
    if not model or not packet:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 120), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    evidence = tuple(packet["evidence"])
    prompt = (
        "This is a supervised grounded-transfer lesson from Seven. Use only the curated evidence below. "
        "Derive the answer from the evidence and obey the output contract exactly. "
        "Do not explain, preface, quote the evidence, or add any other text.\n\n"
        f"CURATED EVIDENCE:\n{chr(10).join(evidence)}\n\n"
        f"OUTPUT CONTRACT:\n{packet['contract']}"
    )
    try:
        runtime = run_direct(model, prompt, timeout_seconds=timeout_seconds)
        answer = str(runtime.get("content") or runtime.get("error") or "").strip()
        if not runtime.get("ok") or not runtime.get("content"):
            grade = "failed"
        elif answer == packet["expected"]:
            grade = "passed"
        else:
            grade = "weak"
        unload = stop(model)
        receipt = _log_grounded_transfer(
            peer=peer,
            model=model,
            capability=packet["capability"],
            evidence=evidence,
            expected=packet["expected"],
            answer=answer,
            grade=grade,
            project_id=project_id,
        )
        return {
            "ok": grade == "passed",
            "peer": peer,
            "model": model,
            "capability": packet["capability"],
            "curated": True,
            "evidence": list(evidence),
            "expected": packet["expected"],
            "answer": answer,
            "grade": grade,
            "ready_for_autonomy": False,
            "runtime": runtime,
            "unload": unload,
            "scorecard_update": _record_transfer_grade(peer, packet["capability"], grade),
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        stop(model)
        SPEAKER_LOCK.release()


def _log_bounded_repair(
    *,
    peer: str,
    model: str,
    capability: str,
    attempts: list[dict[str, Any]],
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    lines = [f"Seven bounded peer repair | peer={peer} model={model} capability={capability}"]
    for row in attempts:
        lines.append(
            f"- attempt={row['attempt']} grade={row['grade']} defects={row['validation']['defects']} "
            f"answer={row['answer'][:500]!r}"
        )
    summary = "\n".join(lines)
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-repair-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="bounded_peer_repair",
            event_type="model",
            target=peer,
            details={
                "model": model,
                "capability": capability,
                "attempts": len(attempts),
                "final_grade": attempts[-1]["grade"],
                "project_id": project_id,
            },
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def bounded_repair_lesson(
    peer: str,
    *,
    project_id: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Give one grounded attempt and at most one defect-guided repair attempt."""
    peer = str(peer or "").strip().lower()
    model = _DIRECT_PEERS.get(peer, "")
    packet = _GROUNDED_TRANSFER_PACKETS.get(peer)
    if not model or not packet:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 120), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    evidence = tuple(packet["evidence"])
    base_prompt = (
        "This is a supervised grounded contract lesson from Seven. Use only the curated evidence below. "
        "Derive the answer and obey the output contract exactly. Do not explain, preface, quote evidence, "
        "or add other text.\n\n"
        f"CURATED EVIDENCE:\n{chr(10).join(evidence)}\n\nOUTPUT CONTRACT:\n{packet['contract']}"
    )
    attempts: list[dict[str, Any]] = []
    try:
        prompt = base_prompt
        for attempt_number in (1, 2):
            runtime = run_direct(model, prompt, timeout_seconds=timeout_seconds)
            answer = str(runtime.get("content") or runtime.get("error") or "").strip()
            validation = validate_transfer_answer(peer, answer)
            if not runtime.get("ok") or not runtime.get("content"):
                grade = "failed"
            elif validation["valid"]:
                grade = "passed"
            else:
                grade = "weak"
            unload = stop(model)
            attempts.append({
                "attempt": attempt_number,
                "answer": answer,
                "grade": grade,
                "validation": validation,
                "runtime": runtime,
                "unload": unload,
            })
            if grade == "passed" or attempt_number == 2:
                break
            prompt = (
                f"{base_prompt}\n\n"
                "YOUR FIRST ANSWER:\n"
                f"{answer}\n\n"
                "DETERMINISTIC VALIDATOR DEFECTS:\n"
                f"{chr(10).join('- ' + defect for defect in validation['defects'])}\n\n"
                "REPAIR INSTRUCTION:\nReturn one corrected answer only. Do not discuss the defects."
            )
        final_grade = attempts[-1]["grade"]
        receipt = _log_bounded_repair(
            peer=peer,
            model=model,
            capability=packet["capability"],
            attempts=attempts,
            project_id=project_id,
        )
        return {
            "ok": final_grade == "passed",
            "peer": peer,
            "model": model,
            "capability": packet["capability"],
            "bounded": True,
            "attempt_count": len(attempts),
            "repaired": len(attempts) == 2 and final_grade == "passed",
            "final_grade": final_grade,
            "ready_for_autonomy": False,
            "attempts": attempts,
            "scorecard_update": _record_transfer_grade(peer, packet["capability"], final_grade),
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        stop(model)
        SPEAKER_LOCK.release()


def _log_schema_lesson(
    *,
    peer: str,
    model: str,
    capability: str,
    raw_answer: str,
    parsed: dict[str, Any],
    grade: str,
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    summary = (
        f"Seven schema-constrained lesson | peer={peer} model={model} capability={capability} grade={grade}\n"
        f"Raw answer: {raw_answer[:1000]!r}\nParsed: {parsed}"
    )
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-schema-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="schema_constrained_peer_lesson",
            event_type="model",
            target=peer,
            details={"model": model, "capability": capability, "grade": grade, "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def schema_constrained_lesson(
    peer: str,
    *,
    project_id: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Use llama.cpp JSON-schema sampling while preserving and grading raw output."""
    peer = str(peer or "").strip().lower()
    model = _DIRECT_PEERS.get(peer, "")
    packet = _GROUNDED_TRANSFER_PACKETS.get(peer)
    if not model or not packet:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 120), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    schema = dict(packet["schema"])
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": f"seven_{peer}_grounded_contract", "strict": True, "schema": schema},
    }
    prompt = (
        "This is a supervised schema-constrained grounded lesson from Seven. "
        "Use only the curated evidence. Select the correct allowed JSON values from that evidence. "
        "Return the schema-constrained JSON object only.\n\n"
        f"CURATED EVIDENCE:\n{chr(10).join(packet['evidence'])}"
    )
    try:
        runtime = run_direct(model, prompt, timeout_seconds=timeout_seconds, response_format=response_format)
        raw_answer = str(runtime.get("content") or runtime.get("error") or "").strip()
        try:
            import json
            parsed = json.loads(raw_answer)
        except Exception:
            parsed = {}
        if not runtime.get("ok") or not runtime.get("content"):
            grade = "failed"
        elif parsed == packet["expected_json"]:
            grade = "passed"
        else:
            grade = "weak"
        unload = stop(model)
        receipt = _log_schema_lesson(
            peer=peer,
            model=model,
            capability=packet["capability"],
            raw_answer=raw_answer,
            parsed=parsed,
            grade=grade,
            project_id=project_id,
        )
        return {
            "ok": grade == "passed",
            "peer": peer,
            "model": model,
            "capability": packet["capability"],
            "constrained": True,
            "schema": schema,
            "expected": packet["expected_json"],
            "raw_answer": raw_answer,
            "parsed": parsed,
            "grade": grade,
            "ready_for_autonomy": False,
            "runtime": runtime,
            "unload": unload,
            "scorecard_update": _record_schema_grade(peer, packet["capability"], grade),
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        stop(model)
        SPEAKER_LOCK.release()


def _variant_schema(peer: str, enums: dict[str, list[str]]) -> dict[str, Any]:
    properties = {key: {"type": "string", "enum": list(values)} for key, values in enums.items()}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _log_schema_robustness(
    *,
    peer: str,
    model: str,
    capability: str,
    variants: list[dict[str, Any]],
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    passed = sum(1 for row in variants if row["grade"] == "passed")
    lines = [f"Seven schema robustness matrix | peer={peer} model={model} capability={capability} passed={passed}/{len(variants)}"]
    for row in variants:
        lines.append(f"- {row['name']}: grade={row['grade']} expected={row['expected']} parsed={row['parsed']} raw={row['raw_answer'][:500]!r}")
    summary = "\n".join(lines)
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-schema-robustness-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="schema_robustness_matrix",
            event_type="model",
            target=peer,
            details={"model": model, "capability": capability, "passed": passed, "variants": len(variants), "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def schema_robustness_lesson(
    peer: str,
    *,
    project_id: str = "",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Prove constrained peers follow varied evidence instead of enum position."""
    peer = str(peer or "").strip().lower()
    model = _DIRECT_PEERS.get(peer, "")
    packet = _GROUNDED_TRANSFER_PACKETS.get(peer)
    matrix = _SCHEMA_ROBUSTNESS_VARIANTS.get(peer)
    if not model or not packet or not matrix:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 120), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    results: list[dict[str, Any]] = []
    try:
        for variant in matrix:
            schema = _variant_schema(peer, variant["enums"])
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": f"seven_{peer}_{variant['name']}", "strict": True, "schema": schema},
            }
            prompt = (
                "This is a supervised schema robustness lesson from Seven. Use only the current evidence. "
                "Select the correct allowed JSON values from the evidence; do not rely on prior variants or enum order. "
                "Return the schema-constrained JSON object only.\n\n"
                f"CURRENT EVIDENCE:\n{chr(10).join(variant['evidence'])}"
            )
            runtime = run_direct(model, prompt, timeout_seconds=timeout_seconds, response_format=response_format)
            raw_answer = str(runtime.get("content") or runtime.get("error") or "").strip()
            try:
                import json
                parsed = json.loads(raw_answer)
            except Exception:
                parsed = {}
            if not runtime.get("ok") or not runtime.get("content"):
                grade = "failed"
            elif parsed == variant["expected"]:
                grade = "passed"
            else:
                grade = "weak"
            unload = stop(model)
            results.append({
                "name": variant["name"],
                "evidence": list(variant["evidence"]),
                "schema": schema,
                "expected": variant["expected"],
                "raw_answer": raw_answer,
                "parsed": parsed,
                "grade": grade,
                "runtime": runtime,
                "unload": unload,
            })
        passed = sum(1 for row in results if row["grade"] == "passed")
        final_grade = "passed" if passed == len(results) else ("failed" if any(row["grade"] == "failed" for row in results) else "weak")
        receipt = _log_schema_robustness(
            peer=peer, model=model, capability=packet["capability"], variants=results, project_id=project_id,
        )
        return {
            "ok": final_grade == "passed",
            "peer": peer,
            "model": model,
            "capability": packet["capability"],
            "variant_count": len(results),
            "passed": passed,
            "final_grade": final_grade,
            "ready_for_autonomy": False,
            "variants": results,
            "scorecard_update": _record_schema_grade(peer, packet["capability"], final_grade),
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        stop(model)
        SPEAKER_LOCK.release()


def _build_named_contract(peer: str, contract_name: str, project_id: str) -> dict[str, Any]:
    """Build an approved schema contract from authoritative live state."""
    peer = str(peer or "").strip().lower()
    contract_name = str(contract_name or "").strip().lower()
    if peer == "gemma" and contract_name == "studio_current_step" and project_id:
        try:
            from utils.db._connection import get_connection
            conn = get_connection()
            try:
                rows = conn.execute(
                    """SELECT step_id, title, status, owner FROM project_steps
                       WHERE project_id=? AND status IN ('doing','todo','blocked')
                       ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END,
                                COALESCE(updated_at, created_at) DESC, order_idx ASC LIMIT 12""",
                    (project_id,),
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            rows = []
        if not rows:
            return {}
        current = dict(rows[0])
        step_ids = [str(row["step_id"]) for row in rows]
        return {
            "capability": "orchestration",
            "evidence": (
                f"[Studio current supervised lesson] step_id={current['step_id']}; status={current['status']}; owner={current['owner']}.",
            ),
            "schema": _variant_schema(peer, {
                "step_id": step_ids,
                "status": ["todo", "doing", "blocked", "done"],
                "owner": sorted({str(row["owner"]) for row in rows} | {"seven", "watchdog"}),
            }),
            "expected": {"step_id": current["step_id"], "status": current["status"], "owner": current["owner"]},
        }
    if peer == "llama" and contract_name == "peer_readiness":
        try:
            from core.agent_scorecards import list_scorecards
            gemma = (list_scorecards(capability="orchestration", agents=["gemma"], limit=1) or [{}])[0]
            llama = (list_scorecards(capability="research", agents=["llama"], limit=1) or [{}])[0]
        except Exception:
            return {}

        def mode(row: dict[str, Any]) -> str:
            return "autonomous_candidate" if (
                float(row.get("score") or 0) >= 0.70
                and float(row.get("confidence") or 0) >= 0.60
                and int(row.get("evidence_count") or 0) >= 2
                and str(row.get("source") or "") != "seed"
            ) else "supervised_only"

        expected = {"gemma_mode": mode(gemma), "llama_mode": mode(llama)}
        return {
            "capability": "research",
            "evidence": (
                f"[Gemma orchestration scorecard] score={gemma.get('score')}; confidence={gemma.get('confidence')}; evidence_count={gemma.get('evidence_count')}; source={gemma.get('source')}.",
                f"[Llama research scorecard] score={llama.get('score')}; confidence={llama.get('confidence')}; evidence_count={llama.get('evidence_count')}; source={llama.get('source')}.",
                "[Trust rule] autonomous_candidate requires score>=0.70, confidence>=0.60, evidence_count>=2, and non-seed source.",
            ),
            "schema": _variant_schema(peer, {
                "gemma_mode": ["autonomous_candidate", "supervised_only"],
                "llama_mode": ["autonomous_candidate", "supervised_only"],
            }),
            "expected": expected,
        }
    return {}


def _log_constrained_peer_turn(
    *,
    peer: str,
    model: str,
    contract_name: str,
    grade: str,
    raw_answer: str,
    parsed: dict[str, Any],
    fallback: dict[str, Any] | None,
    attempts: list[dict[str, Any]] | None = None,
    project_id: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {"blackboard": "", "sandpit": "", "vortex_event": False}
    attempt_summary = [
        {"mode": row.get("mode"), "grade": row.get("grade"), "raw_answer": str(row.get("raw_answer") or "")[:500]}
        for row in (attempts or [])
    ]
    summary = (
        f"Seven constrained normal peer turn | peer={peer} model={model} contract={contract_name} grade={grade}\n"
        f"Attempts: {attempt_summary}\nRaw answer: {raw_answer[:1000]!r}\nParsed: {parsed}\nFallback used: {bool(fallback)}"
    )
    if project_id:
        try:
            from core.knowledge.projects import add_blackboard_note
            receipt["blackboard"] = add_blackboard_note(project_id, summary, author=peer, kind="test") or ""
        except Exception:
            pass
    try:
        from fridays.file_agent import write_shared
        ok, path = write_shared("seven", f"seven-constrained-turn-{peer}-latest.md", summary)
        receipt["sandpit"] = path if ok else ""
    except Exception:
        pass
    try:
        from core.time_machine import time_wizard
        time_wizard.record_event(
            agent="seven",
            action="constrained_normal_peer_turn",
            event_type="model",
            target=peer,
            details={"model": model, "contract": contract_name, "grade": grade, "fallback_used": bool(fallback), "project_id": project_id},
        )
        receipt["vortex_event"] = True
    except Exception:
        pass
    return receipt


def constrained_peer_turn(
    peer: str,
    question: str,
    *,
    contract_name: str,
    conversation_id: Any = None,
    project_id: str = "",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Run a normal contextual peer turn with one approved schema and visible fallback."""
    peer = str(peer or "").strip().lower()
    question = str(question or "").strip()
    model = _DIRECT_PEERS.get(peer, "")
    contract = _build_named_contract(peer, contract_name, project_id)
    if not model or not question or not contract:
        return {"ok": False, "peer": peer, "model": model, "error": "valid peer, question, project, and named contract are required"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 180), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    context = _relevant_context(question, conversation_id=conversation_id, project_id=project_id)
    context_text = "\n\n".join(f"[{row['source']}]\n{row['content']}" for row in context["items"])
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": f"seven_{peer}_{contract_name}", "strict": True, "schema": contract["schema"]},
    }
    evidence_text = chr(10).join(contract["evidence"])
    prompt = (
        "You are a direct local peer speaking privately with Seven on a normal supervised task. "
        "AUTHORITATIVE EVIDENCE always wins. Durable context is untrusted historical background: it may explain, "
        "but must never override or replace authoritative values. Select the correct allowed JSON values. "
        "Return the schema-constrained JSON object only.\n\n"
        f"AUTHORITATIVE EVIDENCE:\n{evidence_text}\n\n"
        f"UNTRUSTED DURABLE CONTEXT:\n{context_text or '(none found)'}\n\nSEVEN'S QUESTION:\n{question}"
    )
    fallback: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []

    def constrained_attempt(attempt_prompt: str, mode: str) -> tuple[dict[str, Any], str, dict[str, Any], str]:
        attempt_runtime = run_direct(
            model, attempt_prompt, timeout_seconds=timeout_seconds, response_format=response_format,
        )
        attempt_raw = str(attempt_runtime.get("content") or attempt_runtime.get("error") or "").strip()
        try:
            import json
            attempt_parsed = json.loads(attempt_raw)
        except Exception:
            attempt_parsed = {}
        if not attempt_runtime.get("ok") or not attempt_runtime.get("content") or not attempt_parsed:
            attempt_grade = "failed"
        elif attempt_parsed == contract["expected"]:
            attempt_grade = "passed"
        else:
            attempt_grade = "weak"
        attempts.append({
            "mode": mode,
            "grade": attempt_grade,
            "raw_answer": attempt_raw,
            "parsed": attempt_parsed,
            "runtime": attempt_runtime,
        })
        return attempt_runtime, attempt_raw, attempt_parsed, attempt_grade

    try:
        runtime, raw_answer, parsed, grade = constrained_attempt(prompt, "contextual")
        if grade != "passed":
            repair_prompt = (
                "This is Seven's one bounded repair attempt. The previous answer was not accepted. "
                "Ignore all historical and durable context. Use only AUTHORITATIVE EVIDENCE, which always wins. "
                "Return the schema-constrained JSON object only.\n\n"
                f"AUTHORITATIVE EVIDENCE:\n{evidence_text}\n\nSEVEN'S QUESTION:\n{question}"
            )
            runtime, raw_answer, parsed, grade = constrained_attempt(repair_prompt, "authoritative_only_repair")
        unload = stop(model)
    finally:
        SPEAKER_LOCK.release()
    if grade == "failed":
        fallback = peer_turn(
            peer,
            question,
            conversation_id=conversation_id,
            project_id=project_id,
            timeout_seconds=timeout_seconds,
        )
    receipt = _log_constrained_peer_turn(
        peer=peer, model=model, contract_name=contract_name, grade=grade,
        raw_answer=raw_answer, parsed=parsed, fallback=fallback, attempts=attempts, project_id=project_id,
    )
    return {
        "ok": grade == "passed",
        "peer": peer,
        "model": model,
        "contract_name": contract_name,
        "capability": contract["capability"],
        "constrained": True,
        "raw_answer": raw_answer,
        "parsed": parsed,
        "expected": contract["expected"],
        "grade": grade,
        "attempts": attempts,
        "authoritative_repair_used": len(attempts) > 1,
        "context": context,
        "fallback_used": bool(fallback),
        "fallback": fallback,
        "runtime": runtime,
        "unload": unload,
        "ready_for_autonomy": False,
        "scorecard_update": _record_schema_grade(peer, contract["capability"], grade),
        "receipt": receipt,
        "elapsed_s": round(time.time() - started, 3),
    }


def peer_turn(
    peer: str,
    question: str,
    *,
    conversation_id: Any = None,
    project_id: str = "",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Let Seven consult one direct GGUF peer, with serialized and durable turns."""
    peer = str(peer or "").strip().lower()
    question = str(question or "").strip()
    model = _DIRECT_PEERS.get(peer, "")
    if not model or not question:
        return {"ok": False, "peer": peer, "model": model, "error": "peer must be gemma or llama and question is required"}
    acquired = SPEAKER_LOCK.acquire(timeout=max(1, min(int(timeout_seconds or 180), 600)))
    if not acquired:
        return {"ok": False, "peer": peer, "model": model, "error": "another local peer is speaking"}
    started = time.time()
    context = _relevant_context(question, conversation_id=conversation_id, project_id=project_id)
    context_text = "\n\n".join(f"[{row['source']}]\n{row['content']}" for row in context["items"])
    prompt = (
        "You are a direct local peer speaking privately with Seven. Use the supplied durable context. "
        "Do not claim you lack context until you have checked it. Do not bluff; identify any specific missing fact. "
        "Do not copy or repeat prior peer answers, checklists, or retrieval descriptions from the context. "
        "Use the context to answer Seven's current question directly. Follow any requested output label or outcome terms. "
        "Answer only your own turn, then stop.\n\n"
        f"DURABLE CONTEXT:\n{context_text or '(no pertinent durable context found)'}\n\n"
        f"SEVEN'S QUESTION:\n{question}"
    )
    try:
        result = run_direct(model, prompt, timeout_seconds=timeout_seconds)
        answer = str(result.get("content") or result.get("error") or "direct peer returned no answer").strip()
        answer_lower = answer.lower()
        grounding_hits = sorted({
            label for label, markers in {
                "thread": ("thread", "conversation history"),
                "studio": ("studio",),
                "knowledge_center": ("knowledge center", "kc"),
                "blackboard": ("blackboard",),
                "sandpit": ("sandpit",),
            }.items()
            if any(marker in answer_lower for marker in markers)
        })
        question_lower = question.lower()
        required_grounding = sorted({
            label for label, markers in {
                "thread": ("thread",),
                "studio": ("studio",),
                "knowledge_center": ("knowledge center", "kc"),
                "blackboard": ("blackboard",),
                "sandpit": ("sandpit",),
            }.items()
            if any(marker in question_lower for marker in markers)
        })
        required_terms = sorted(term for term in _CONTRACT_TERMS if term in question_lower)
        missing_terms = sorted(term for term in required_terms if term not in answer_lower)
        required_phrases = sorted(phrase for phrase in _CONTRACT_PHRASES if phrase in question_lower)
        missing_phrases = sorted(phrase for phrase in required_phrases if phrase not in answer_lower)
        if not result.get("ok") or not result.get("content"):
            grade = "failed"
        elif missing_terms or missing_phrases:
            grade = "weak"
        elif required_grounding and not set(required_grounding).issubset(grounding_hits):
            grade = "weak"
        elif context["items"] and not grounding_hits:
            grade = "weak"
        else:
            grade = "passed"
        status = grade
        receipt = _log_peer_turn(
            peer=peer, model=model, question=question, answer=answer,
            conversation_id=conversation_id, project_id=project_id, status=status,
        )
        unload = stop(model)
        return {
            "ok": bool(result.get("ok") and result.get("content")),
            "peer": peer,
            "model": model,
            "answer": answer,
            "grade": grade,
            "grounding_hits": grounding_hits,
            "required_grounding": required_grounding,
            "required_terms": required_terms,
            "missing_terms": missing_terms,
            "required_phrases": required_phrases,
            "missing_phrases": missing_phrases,
            "context": context,
            "runtime": result,
            "unload": unload,
            "receipt": receipt,
            "elapsed_s": round(time.time() - started, 3),
        }
    finally:
        SPEAKER_LOCK.release()


def select_peer(question: str) -> dict[str, Any]:
    """Choose one direct peer for a bounded task and explain the choice."""
    text = str(question or "").strip().lower()
    capability = "synthesis"
    peer = "gemma"
    matched: list[str] = []
    for candidate_capability, candidate_peer, markers in _TASK_FIT_RULES:
        hits = [marker for marker in markers if marker in text]
        if hits:
            capability = candidate_capability
            peer = candidate_peer
            matched = hits
            break

    scorecard: dict[str, Any] = {}
    try:
        from core.agent_scorecards import list_scorecards
        rows = list_scorecards(capability=capability, agents=[peer], limit=1)
        if rows:
            scorecard = rows[0]
    except Exception:
        pass
    reason = (
        f"{peer} selected for {capability}; matched task signals: {', '.join(matched)}"
        if matched else
        "gemma selected as the conservative synthesis fallback because no proven specialist signal matched"
    )
    score = float(scorecard.get("score") or 0.0)
    confidence = float(scorecard.get("confidence") or 0.0)
    evidence_count = int(scorecard.get("evidence_count") or 0)
    source = str(scorecard.get("source") or "")
    trusted = bool(score >= 0.70 and confidence >= 0.60 and evidence_count >= 2 and source != "seed")
    return {
        "peer": peer,
        "model": _DIRECT_PEERS[peer],
        "capability": capability,
        "matched": matched,
        "reason": reason,
        "scorecard": scorecard,
        "trusted": trusted,
        "mode": "autonomous_candidate" if trusted else "supervised_only",
    }


def _record_peer_grade(selection: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    try:
        from core.agent_scorecards import record_capability_result
        grade = str(result.get("grade") or "failed")
        return record_capability_result(
            selection["peer"],
            selection["capability"],
            success=grade == "passed",
            quality_delta=0.08 if grade == "passed" else (-0.04 if grade == "weak" else -0.10),
            source="seven:direct_peer_lesson",
            notes=(
                f"Seven selected {selection['peer']} for {selection['capability']}; "
                f"grade={grade}; reason={selection['reason']}"
            ),
        )
    except Exception as exc:
        return {"error": str(exc)}


def select_consult_contract(selection: dict[str, Any], question: str, project_id: str = "") -> dict[str, str]:
    """Choose an approved constrained contract only for explicitly eligible consults."""
    text = str(question or "").strip().lower()
    peer = str(selection.get("peer") or "")
    capability = str(selection.get("capability") or "")
    if peer == "gemma" and capability == "orchestration" and project_id:
        if "studio" in text and any(marker in text for marker in ("current", "active", "lesson", "step", "owner", "status")):
            return {
                "contract_name": "studio_current_step",
                "reason": "explicit current Studio orchestration question",
            }
    if peer == "llama" and capability == "research":
        if any(marker in text for marker in ("readiness", "ready", "trust", "autonomy", "scorecard")):
            return {
                "contract_name": "peer_readiness",
                "reason": "explicit peer readiness research question",
            }
    return {"contract_name": "", "reason": "no approved constrained consult contract matched"}


def consult(
    question: str,
    *,
    conversation_id: Any = None,
    project_id: str = "",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Select exactly one direct peer, run its turn, grade it, and teach routing."""
    selection = select_peer(question)
    contract_route = select_consult_contract(selection, question, project_id)
    if contract_route["contract_name"]:
        result = constrained_peer_turn(
            selection["peer"],
            question,
            contract_name=contract_route["contract_name"],
            conversation_id=conversation_id,
            project_id=project_id,
            timeout_seconds=timeout_seconds,
        )
        route = "constrained"
    else:
        result = peer_turn(
            selection["peer"],
            question,
            conversation_id=conversation_id,
            project_id=project_id,
            timeout_seconds=timeout_seconds,
        )
        result["scorecard_update"] = _record_peer_grade(selection, result)
        route = "free_form"
    result["selection"] = selection
    result["consult_route"] = {
        "route": route,
        "contract_name": contract_route["contract_name"],
        "reason": contract_route["reason"],
    }
    result["autonomous_allowed"] = bool(selection.get("trusted") and result.get("grade") == "passed")
    return result


def trust_promotion_review(peer: str, capability: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Review fresh scorecard state after repeated acceptance; never execute autonomy."""
    peer = str(peer or "").strip().lower()
    capability = str(capability or "").strip().lower()
    try:
        from core.agent_scorecards import list_scorecards
        rows = list_scorecards(capability=capability, agents=[peer], limit=1)
        scorecard = rows[0] if rows else {}
    except Exception:
        scorecard = {}
    passed = sum(1 for row in attempts if row.get("grade") == "passed")
    fallback_free = all(not row.get("fallback_used") for row in attempts)
    repeated_acceptance = bool(len(attempts) >= 2 and passed == len(attempts) and fallback_free)
    score = float(scorecard.get("score") or 0.0)
    confidence = float(scorecard.get("confidence") or 0.0)
    evidence_count = int(scorecard.get("evidence_count") or 0)
    source = str(scorecard.get("source") or "")
    threshold_passed = bool(score >= 0.70 and confidence >= 0.60 and evidence_count >= 2 and source != "seed")
    promotion_approved = bool(repeated_acceptance and threshold_passed)
    return {
        "peer": peer,
        "capability": capability,
        "attempt_count": len(attempts),
        "passed": passed,
        "fallback_free": fallback_free,
        "repeated_acceptance": repeated_acceptance,
        "scorecard": scorecard,
        "thresholds": {"score": 0.70, "confidence": 0.60, "evidence_count": 2, "non_seed_source": True},
        "threshold_passed": threshold_passed,
        "promotion_approved": promotion_approved,
        "decision": "promotion_candidate" if promotion_approved else "remain_supervised",
        "autonomous_allowed": False,
    }


def routed_acceptance_review(
    peer: str,
    *,
    project_id: str = "",
    rounds: int = 2,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Repeat eligible normal consults and perform a fresh explicit trust review."""
    peer = str(peer or "").strip().lower()
    rounds = max(2, min(int(rounds or 2), 3))
    if peer == "gemma":
        question = "Plan from the current Studio lesson status and owner."
        capability = "orchestration"
    elif peer == "llama":
        question = "Research current peer readiness and autonomy from the scorecards."
        capability = "research"
    else:
        return {"ok": False, "peer": peer, "error": "peer must be gemma or llama"}
    attempts = [
        consult(question, project_id=project_id, timeout_seconds=timeout_seconds)
        for _ in range(rounds)
    ]
    review = trust_promotion_review(peer, capability, attempts)
    return {
        "ok": review["repeated_acceptance"],
        "peer": peer,
        "capability": capability,
        "rounds": rounds,
        "attempts": attempts,
        "review": review,
        "autonomous_allowed": False,
    }
