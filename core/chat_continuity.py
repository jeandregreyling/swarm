"""Explicit local chat continuity when primary conversation storage is corrupt."""
from __future__ import annotations

import fcntl
import json
import logging
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from core.recovery_supervisor import NO_BS_DIRECTIVE, ROOT, _write_json


def conversation_lesson() -> str:
    lesson = json.loads((ROOT / "core" / "capability_packs" / "conversation.coordinator.v1.json").read_text())
    if lesson['id'] != 'conversation.coordinator' or lesson['version'] != '1.1.0':
        raise ValueError("Invalid conversation.coordinator lesson identity/version")
    return "Repository-backed role guidance, not permission: " + json.dumps(lesson)


LOG = logging.getLogger(__name__)
NOTICE = (
    "[Local recovery chat: primary conversation storage is unavailable. "
    "This thread is saved separately; old history and database memory are unavailable. "
    "Operational tools are disabled. The original database has not been replaced.]"
)
ID_FLOOR = 1 << 48

# Chat lane states surfaced to the UI. `ok` = primary storage + APEX healthy,
# `recovery` = storage exception (continuity journal in use),
# `offline` = APEX endpoint unreachable / timed out.
STATE_OK = "ok"
STATE_RECOVERY = "recovery"
STATE_OFFLINE = "offline"

# APEX (gpt-oss:20B on the externally owned llama-server) is the only routing
# target for local chat. The registry name maps to the service's api_model
# alias; no Gemma/Qwen/LLaMA/Mistral fallback exists on this lane.
APEX_AGENT = {"name": "apex", "model": "gpt-oss:20b", "tier": "local", "label": "APEX"}

_OFFLINE_MARKERS = (
    "unavailable", "timeout", "timed out", "connection", "refused",
    "unreachable", "disconnected", "no route", "name or service not known",
    "max retries", "server_alive", "not alive",
)


class ApexOffline(RuntimeError):
    """APEX endpoint could not be reached or did not answer in time."""


def strip_notice_prefix(text: str) -> str:
    text = text.lstrip()
    while text.startswith(NOTICE):
        text = text[len(NOTICE):].lstrip()
    return text


def classify_runtime_error(error: str) -> str:
    """Map a runtime failure string to a lane state; transport faults are `offline`."""
    lowered = str(error or "").lower()
    if any(marker in lowered for marker in _OFFLINE_MARKERS):
        return STATE_OFFLINE
    return "error"


def call_apex(call_model, model: str, messages: list[dict]) -> tuple[str, int]:
    """Invoke APEX and convert transport/timeout failures into ApexOffline."""
    try:
        text, tokens = call_model(model, messages)
    except ApexOffline:
        raise
    except Exception as exc:  # network layer raised instead of returning an error marker
        error = str(exc) or exc.__class__.__name__
        if classify_runtime_error(error) == STATE_OFFLINE:
            raise ApexOffline(error) from exc
        raise RuntimeError(error) from exc
    text = strip_notice_prefix(str(text or ""))
    if not text.strip() or text.startswith("[local runtime error:"):
        error = text or "Local runner returned no content"
        if classify_runtime_error(error) == STATE_OFFLINE:
            raise ApexOffline(error)
        raise RuntimeError(error)
    return text, int(tokens or 0)


def apex_roster(*, storage_degraded: bool = False) -> list[dict]:
    """Single-entry roster; DB-independent so routing never depends on the agents table."""
    role = "Local recovery chat; no operational tools" if storage_degraded else "Sole local chat target; bounded repository inspection"
    return [{**APEX_AGENT, "enabled": True, "status": "on_demand",
             "available": True, "storage_degraded": storage_degraded,
             "role": role, "roles": ["recovery-chat"] if storage_degraded else ["apex-chat"],
             "availability_reason": "", "eta_seconds": 90, "temperature": 0.2,
             "api_key_var": "", "api_key_set": None, "system_prompt": NO_BS_DIRECTIVE}]


def recovery_roster() -> list[dict]:
    """Known local bootstrap identity; configuration is not inference readiness."""
    return apex_roster(storage_degraded=True)


def apex_system_prompt(agent: dict, *, recovery: bool, proposals: bool = False) -> str:
    directive = NO_BS_DIRECTIVE if recovery else (
        "Reasoning: low\nNever guess paths or results. Discover workspace facts with attached "
        "read-only tools; ask for context only when discovery is unavailable or insufficient."
    )
    base = (
        f"You are {agent.get('label') or agent['name']}, the local DEOS chat agent for JD.\n"
        + directive + "\n" + conversation_lesson()
        + "\nNever invent execution or missing context. Do not echo wrapper status text."
    )
    if recovery:
        base += ("\nNo tools are attached in recovery. Never claim file access or command execution. "
                 "The current recovery thread is available; original database memories are unavailable. "
                 "Use only this recovery thread; unavailable memories must not be invented.")
    else:
        from core.apex_tools import TOOL_GUIDANCE
        base += TOOL_GUIDANCE
        if proposals:
            from core.apex_tools import PROPOSAL_GUIDANCE
            base += PROPOSAL_GUIDANCE
    return base


def storage_fault(connect) -> str | None:
    """Probe the actual conversation read; do not treat a fast count as integrity."""
    try:
        with closing(connect()) as conn:
            conn.execute("SELECT id, title FROM conversations ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.DatabaseError as exc:
        if getattr(exc, "sqlite_errorcode", None) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB} or (
            "malformed" in str(exc).lower() or "not a database" in str(exc).lower()
        ):
            LOG.error("Primary chat storage fault; engaging local continuity: %s", exc)
            return str(exc)
        raise
    return None


class ContinuityChat:
    def __init__(self, root: Path = ROOT / "runtime" / "chat-continuity"):
        if root.is_symlink():
            raise ValueError("Continuity root cannot be a symlink")
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, conversation_id) -> Path:
        value = int(conversation_id)
        if not ID_FLOOR <= value < 2 * ID_FLOOR:
            raise ValueError("Not a recovery conversation ID")
        path = self.root / f"{value}.json"
        if path.is_symlink():
            raise ValueError("Continuity thread cannot be a symlink")
        return path

    def owns_id(self, conversation_id) -> bool:
        try:
            return ID_FLOOR <= int(conversation_id) < 2 * ID_FLOOR
        except (TypeError, ValueError):
            return False

    def read(self, conversation_id, owner: str) -> dict:
        thread = json.loads(self.path(conversation_id).read_text())
        if thread["owner"] != owner:
            raise PermissionError("Recovery conversation belongs to another operator identity")
        for message in thread['messages']:
            if message['sender'] != 'user':
                message['content'] = NOTICE + '\n\n' + strip_notice_prefix(message['content'])
        return thread

    def recent(self, owner: str) -> list[dict]:
        threads = []
        for path in self.root.glob("*.json"):
            thread = json.loads(self.path(path.stem).read_text())
            if thread["owner"] == owner:
                threads.append({key: thread[key] for key in ("id", "title", "source", "created_at")})
        return sorted(threads, key=lambda item: item["created_at"], reverse=True)[:40]

    def send(self, data: dict, agents: list[dict], owner: str, fault: str, call_model) -> dict:
        """Durably record input before inference; never import agent database context."""
        requested = data.get("conversation_id")
        if self.owns_id(requested) and not data.get("new_thread"):
            thread = self.read(requested, owner)
        else:
            conversation_id = ID_FLOOR + (uuid.uuid4().int % ID_FLOOR)
            thread = {
                "id": conversation_id, "owner": owner, "title": data["message"][:90],
                "source": "local-recovery-chat", "created_at": self._now(),
                "original_conversation_id": requested, "messages": [], "fault": fault,
            }
        path = self.path(thread["id"])
        lock_path = path.with_suffix(".lock")
        if lock_path.is_symlink():
            raise ValueError("Continuity lock cannot be a symlink")
        with lock_path.open("a") as lock:
            import os

            os.chmod(lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if path.exists():
                thread = self.read(thread["id"], owner)
            previous = thread["messages"][-24:]
            thread["messages"].append(self._message(thread, "user", data["message"].strip()))
            _write_json(path, thread)
            responses = []
            for agent in agents:
                started = time.monotonic()
                model = str(agent.get("model") or "")
                if not model or agent.get("tier") != "local":
                    raise ValueError("Recovery dispatch requires a registered local model")
                if model != APEX_AGENT["model"]:
                    raise ValueError("Recovery dispatch permits only the APEX model")
                messages = [{"role": "system", "content": apex_system_prompt(agent, recovery=True)}]
                for item in previous:
                    messages.append({"role": "user" if item["sender"] == "user" else "assistant",
                                     "content": item['content'] if item['sender'] == 'user' else strip_notice_prefix(item['content'])})
                messages.append({"role": "user", "content": data["message"].strip()})
                try:
                    text, tokens = call_apex(call_model, model, messages)
                except RuntimeError as exc:
                    state = STATE_OFFLINE if isinstance(exc, ApexOffline) else "error"
                    thread["last_error"] = {"agent": agent["name"], "model": model,
                                            "error": str(exc), "state": state}
                    _write_json(path, thread)
                    raise
                content = NOTICE + "\n\n" + text
                thread["messages"].append(self._message(thread, agent["name"], content))
                _write_json(path, thread)
                responses.append({"agent": agent["name"], "response": content,
                                  "tokens": tokens, "elapsed_ms": int((time.monotonic() - started) * 1000),
                                  "pending": False, "model": model, "runtime_class": "local"})
            return {
                "ok": True, "mode": "local_recovery", "state": STATE_RECOVERY, "storage_degraded": True,
                "storage_error": fault, "conversation_id": thread["id"],
                "recovered_from_conversation_id": thread["original_conversation_id"],
                "agent": responses[0]["agent"], "response": responses[0]["response"],
                "responses": responses, "pending_jobs": [], "agents": [r["agent"] for r in responses],
                "tokens": sum(r["tokens"] for r in responses),
            }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _message(self, thread: dict, sender: str, content: str) -> dict:
        return {"id": len(thread["messages"]) + 1, "sender": sender, "content": content,
                "conversation_id": thread["id"], "created_at": self._now(),
                "message_type": "chat" if sender == "user" else "response",
                "to_agent": None, "tokens_used": 0}
