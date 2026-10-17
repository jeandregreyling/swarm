"""Diamond Layer Sequential Council Handoff (SCH).

This module is the strict middleware boundary between Seven and council models.
It owns JSON validation, council temperature policy, one-at-a-time execution,
and durable SQL state. SQLite transactions are kept short; the Python lock and
``is_council_active`` flag suspend Seven while inference is in progress.
"""
from __future__ import annotations

import json
import fcntl
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from utils.db._connection import get_connection


STANDARD_TEMPERATURE = 0.6
COUNCIL_TEMPERATURE = 0.1
REGEN_TEMPERATURE = 0.0
COUNCIL_MODELS = {"llama": "llama3.2:latest", "qwen": "qwen2.5:latest"}
TRIAGE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "diamond_sch_triage",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["RESPOND", "ESCALATE"]},
                "technical_query": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["decision", "technical_query", "reason"],
            "additionalProperties": False,
        },
    },
}
COUNSEL_RESPONSE_FORMAT = {
    "type": "object",
    "properties": {
        "agent": {"type": "string", "enum": ["llama", "qwen"]},
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["agent", "answer", "confidence", "risks"],
}
_SCH_LOCK = threading.RLock()
_SCH_LOCK_PATH = os.environ.get("DIAMOND_SCH_LOCK_PATH", "/tmp/seven-diamond-sch.lock")


class SCHValidationError(ValueError):
    pass


@dataclass
class SCHResult:
    decision: str
    session_id: str = ""
    council_context: str = ""
    error: str = ""


@contextmanager
def _council_guard():
    """Serialize council sessions across threads and Seven runtime processes."""
    with _SCH_LOCK:
        handle = open(_SCH_LOCK_PATH, "a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def ensure_schema(conn=None) -> None:
    own = conn is None
    conn = conn or get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS diamond_sch_state (
                state_id INTEGER PRIMARY KEY CHECK (state_id=1),
                is_council_active INTEGER NOT NULL DEFAULT 0,
                session_id TEXT NOT NULL DEFAULT '',
                phase TEXT NOT NULL DEFAULT 'idle',
                error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO diamond_sch_state(state_id) VALUES (1);
            CREATE TABLE IF NOT EXISTS diamond_sch_counsel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                conversation_id INTEGER DEFAULT 0,
                technical_query TEXT NOT NULL,
                llama_json TEXT NOT NULL DEFAULT '{}',
                qwen_json TEXT NOT NULL DEFAULT '{}',
                parity TEXT NOT NULL DEFAULT 'unknown',
                finalized_answer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_diamond_sch_counsel_session
            ON diamond_sch_counsel(session_id);
            """
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def _strict_json(raw: Any, required: set[str], allowed: set[str]) -> dict[str, Any]:
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw or "").strip()
        if not text.startswith("{") or not text.endswith("}"):
            raise SCHValidationError("handoff must be one JSON object with no conversational text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SCHValidationError(f"invalid JSON handoff: {exc}") from exc
    if not isinstance(data, dict):
        raise SCHValidationError("handoff root must be an object")
    missing = required - set(data)
    extra = set(data) - allowed
    if missing:
        raise SCHValidationError(f"missing JSON fields: {sorted(missing)}")
    if extra:
        raise SCHValidationError(f"unexpected JSON fields: {sorted(extra)}")
    return data


def validate_triage(raw: Any) -> dict[str, Any]:
    data = _strict_json(raw, {"decision", "technical_query", "reason"}, {"decision", "technical_query", "reason"})
    decision = str(data["decision"]).strip().upper()
    if decision not in {"RESPOND", "ESCALATE"}:
        raise SCHValidationError("decision must be RESPOND or ESCALATE")
    query = str(data["technical_query"] or "").strip()
    if decision == "ESCALATE" and not query:
        raise SCHValidationError("ESCALATE requires technical_query")
    return {"decision": decision, "technical_query": query, "reason": str(data["reason"] or "").strip()}


def validate_counsel(raw: Any, expected_agent: str) -> dict[str, Any]:
    data = _strict_json(
        raw,
        {"agent", "answer", "confidence", "risks"},
        {"agent", "answer", "confidence", "risks"},
    )
    agent = str(data["agent"]).strip().lower()
    if agent != expected_agent:
        raise SCHValidationError(f"counsel agent must be {expected_agent}")
    answer = str(data["answer"] or "").strip()
    if not answer:
        raise SCHValidationError("counsel answer required")
    lowered = answer.lower()
    if any(phrase in lowered for phrase in ("i cannot provide", "i can't provide", "need more information", "please provide")):
        raise SCHValidationError("counsel answer was a refusal instead of technical analysis")
    confidence = float(data["confidence"])
    if not 0 <= confidence <= 1:
        raise SCHValidationError("confidence must be between 0 and 1")
    risks = data["risks"]
    if not isinstance(risks, list) or any(not isinstance(item, str) for item in risks):
        raise SCHValidationError("risks must be an array of strings")
    if any(item.strip() in {"", "..."} for item in risks):
        raise SCHValidationError("risks must not contain placeholders")
    return {"agent": agent, "answer": answer, "confidence": confidence, "risks": risks}


def _call_json_model(
    model: str,
    messages: list[dict[str, str]],
    validator: Callable[[Any], dict[str, Any]],
    *,
    temperature: float,
    timeout_s: int,
) -> dict[str, Any]:
    from core import llm

    response_format = TRIAGE_RESPONSE_FORMAT if model == "seven-direct:daily" else COUNSEL_RESPONSE_FORMAT
    raw, _tokens = llm.chat_via_gateway(
        model,
        messages,
        temperature=temperature,
        idle_timeout_s=timeout_s,
        absolute_timeout_s=timeout_s,
        keep_alive=0,
        options={"temperature": temperature, "num_predict": 180, "num_ctx": 2048},
        response_format=response_format,
    )
    try:
        return validator(raw)
    except SCHValidationError as first:
        repair = messages + [
            {"role": "assistant", "content": str(raw or "")[:1200]},
            {
                "role": "system",
                "content": f"SYSTEM ERROR: {first}. Regenerate one valid JSON object only.",
            },
        ]
        raw, _tokens = llm.chat_via_gateway(
            model,
            repair,
            temperature=REGEN_TEMPERATURE,
            idle_timeout_s=timeout_s,
            absolute_timeout_s=timeout_s,
            keep_alive=0,
            options={"temperature": REGEN_TEMPERATURE, "num_predict": 160, "num_ctx": 2048},
            response_format=response_format,
        )
        return validator(raw)


def _last_nodes(conversation_id: int | None, history: list[dict] | None) -> list[dict[str, str]]:
    if conversation_id:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT from_agent, content FROM messages
                   WHERE conversation_id=? ORDER BY id DESC LIMIT 5""",
                (int(conversation_id),),
            ).fetchall()
            if rows:
                return [
                    {"role": "user" if row["from_agent"] == "user" else "assistant", "content": str(row["content"])}
                    for row in reversed(rows)
                ]
        finally:
            conn.close()
    nodes = []
    for item in (history or [])[-5:]:
        content = str(item.get("content") or item.get("message") or "").strip()
        if content:
            role = str(item.get("role") or "user")
            nodes.append({"role": role if role in {"user", "assistant"} else "user", "content": content})
    return nodes


def _set_state(active: bool, session_id: str, phase: str, error: str = "") -> None:
    conn = get_connection()
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """UPDATE diamond_sch_state
               SET is_council_active=?, session_id=?, phase=?, error=?, updated_at=datetime('now')
               WHERE state_id=1""",
            (1 if active else 0, session_id, phase, str(error or "")[:1000]),
        )
        conn.commit()
    finally:
        conn.close()


def _parity(llama: dict[str, Any], qwen: dict[str, Any]) -> str:
    left = set(re.findall(r"[a-z0-9_]{4,}", llama["answer"].lower()))
    right = set(re.findall(r"[a-z0-9_]{4,}", qwen["answer"].lower()))
    if not left or not right:
        return "low"
    score = len(left & right) / max(1, len(left | right))
    return "high" if score >= 0.35 else "medium" if score >= 0.15 else "low"


def _explicit_council_request(prompt: str) -> bool:
    text = str(prompt or "").strip().lower()
    return (
        text.startswith(("/council", "council:", "sch:"))
        or "requires deep specialist review" in text
        or "require deep specialist review" in text
    )


def _finalize_counsel(session_id: str, llama: dict[str, Any], qwen: dict[str, Any], parity: str) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "parity": parity,
            "finalized_answer": (
                f"Llama: {llama['answer']}\n"
                f"Qwen: {qwen['answer']}"
            ),
            "risks": list(dict.fromkeys(llama["risks"] + qwen["risks"])),
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def format_council_for_user(council_context: str) -> str:
    """Deterministically format validated counsel when Seven's tiny model drifts."""
    data = json.loads(str(council_context or ""))
    finalized = str(data.get("finalized_answer") or "").strip()
    if not finalized:
        raise SCHValidationError("finalized council answer required")
    risks = [str(item).strip() for item in (data.get("risks") or []) if str(item).strip()]
    response = f"Council review:\n\n{finalized}\n\nAgreement: {str(data.get('parity') or 'unknown')}."
    if risks:
        response += "\n\nRisks: " + "; ".join(risks)
    return response


def route(
    prompt: str,
    *,
    history: list[dict] | None = None,
    conversation_id: int | None = None,
    seven_model: str = "seven-direct:daily",
    timeout_s: int = 90,
) -> SCHResult:
    """Triage one Seven turn and synchronously execute SCH when escalated."""
    nodes = _last_nodes(conversation_id, history)
    context = json.dumps(nodes, ensure_ascii=True)
    triage_messages = [
        {
            "role": "system",
            "content": (
                "You are Seven's Diamond triage gate. Output JSON only with exactly: "
                '{"decision":"RESPOND|ESCALATE","technical_query":"...","reason":"..."}. '
                "ESCALATE only for deep technical specialization requiring Llama and Qwen."
            ),
        },
        {"role": "user", "content": f"LAST_5_NODES={context}\nCURRENT_PROMPT={prompt}"},
    ]
    try:
        triage = _call_json_model(
            seven_model,
            triage_messages,
            validate_triage,
            temperature=STANDARD_TEMPERATURE,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        return SCHResult(decision="ERROR", error=f"triage failed: {type(exc).__name__}: {exc}")
    if _explicit_council_request(prompt):
        triage = {
            "decision": "ESCALATE",
            "technical_query": str(prompt).strip(),
            "reason": "Diamond explicit council policy",
        }
    if triage["decision"] == "RESPOND":
        return SCHResult(decision="RESPOND")

    session_id = f"sch-{uuid.uuid4().hex[:12]}"
    with _council_guard():
        _set_state(True, session_id, "council_inference")
        try:
            payload = json.dumps(
                {
                    "session_id": session_id,
                    "technical_query": triage["technical_query"],
                    "context_nodes": nodes,
                },
                ensure_ascii=True,
            )

            def ask(agent: str) -> dict[str, Any]:
                schema = '{"agent":"' + agent + '","answer":"...","confidence":0.0,"risks":["..."]}'
                messages = [
                    {
                        "role": "system",
                        "content": (
                            f"You are {agent} in SCH. Give concrete technical counsel in at most 90 words. "
                            f"Output JSON only using exactly this schema: {schema}"
                        ),
                    },
                    {"role": "user", "content": payload},
                ]
                return _call_json_model(
                    COUNCIL_MODELS[agent],
                    messages,
                    lambda raw: validate_counsel(raw, agent),
                    temperature=COUNCIL_TEMPERATURE,
                    timeout_s=timeout_s,
                )

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="diamond-sch") as pool:
                llama_future = pool.submit(ask, "llama")
                qwen_future = pool.submit(ask, "qwen")
                llama = llama_future.result()
                qwen = qwen_future.result()
            parity = _parity(llama, qwen)
            finalized = _finalize_counsel(session_id, llama, qwen, parity)
            conn = get_connection()
            try:
                ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO diamond_sch_counsel
                       (session_id, conversation_id, technical_query, llama_json, qwen_json, parity, finalized_answer)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        int(conversation_id or 0),
                        triage["technical_query"],
                        json.dumps(llama, ensure_ascii=True),
                        json.dumps(qwen, ensure_ascii=True),
                        parity,
                        finalized,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            _set_state(False, session_id, "complete")
            return SCHResult(decision="ESCALATE", session_id=session_id, council_context=finalized)
        except Exception as exc:
            _set_state(False, session_id, "failed", f"{type(exc).__name__}: {exc}")
            return SCHResult(decision="ERROR", session_id=session_id, error=f"{type(exc).__name__}: {exc}")


def state_snapshot() -> dict[str, Any]:
    conn = get_connection()
    try:
        ensure_schema(conn)
        state = dict(conn.execute("SELECT * FROM diamond_sch_state WHERE state_id=1").fetchone())
        latest = conn.execute("SELECT * FROM diamond_sch_counsel ORDER BY id DESC LIMIT 1").fetchone()
        state["latest_counsel"] = dict(latest) if latest else None
        return state
    finally:
        conn.close()


def recover_stale_state(stale_after_s: int = 300) -> dict[str, Any]:
    """Clear an abandoned active flag only when no council process owns the lock."""
    snapshot = state_snapshot()
    if not snapshot.get("is_council_active"):
        return {"recovered": False, "reason": "inactive", "state": snapshot}

    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT CAST((julianday('now') - julianday(updated_at)) * 86400 AS INTEGER) AS age_s
               FROM diamond_sch_state WHERE state_id=1"""
        ).fetchone()
        age_s = int(row["age_s"] or 0) if row else 0
    finally:
        conn.close()
    if age_s < max(30, int(stale_after_s)):
        return {"recovered": False, "reason": "active_not_stale", "age_s": age_s, "state": snapshot}

    handle = open(_SCH_LOCK_PATH, "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"recovered": False, "reason": "council_lock_owned", "age_s": age_s, "state": snapshot}
        session_id = str(snapshot.get("session_id") or "")
        _set_state(False, session_id, "recovered_stale", f"Watchdog cleared stale council state after {age_s}s")
        return {"recovered": True, "reason": "stale_lock_free", "age_s": age_s, "state": state_snapshot()}
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
