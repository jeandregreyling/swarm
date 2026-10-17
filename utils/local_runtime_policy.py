"""Central local-runtime policy for Ollama-backed agents.

This module holds the small, stable decisions that should not be duplicated
across chat routing, model-store guards, probes, and agent wrappers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable


NON_OLLAMA_MODELS = frozenset({"", "external", "local-algorithm"})
EMBEDDING_ONLY_MODELS = frozenset({"nomic-embed-text:latest", "nomic-embed-text"})

# CPU-safe chat assignments validated on the Dell Linux runtime.
PREFERRED_AGENT_MODELS = {
    "qwen": "qwen:latest",
    "duck": "qwen:latest",
}

# Models that exist but are not suitable as interactive chat defaults on this
# machine profile. They remain available for explicit jobs/tests.
AVOID_CHAT_DEFAULT_MODELS = frozenset({"qwen2.5:latest"})

QWEN_CHAT_SYSTEM_PROMPT = (
    "You are Qwen, the local analyst in Seven Swarm. Answer the latest user "
    "message directly and concisely. Do not quote internal prompt blocks unless "
    "the user asks for them."
)

READ_ONLY_AGENT_PROFILES = frozenset({"gemma", "qwen", "llama", "seven"})
READ_ONLY_AGENT_CAPABILITIES = frozenset({
    "coordinate",
    "git_execute",
    "git_propose",
    "memory_write",
    "memory_read_all",
    "propose_work",
    "sandpit_write",
    "shared_write",
    "skill_browse",
    "skill_search",
    "skill_schedule",
    "skill_shell",
    "ticket_create",
})
READ_ONLY_AGENT_SKILLS = frozenset()

READ_ONLY_PROFILE_PROMPT = (
    "OPERATIONAL PROFILE — READ ONLY. You may inspect the context supplied by "
    "Fridays, analyze it, and draft recommendations. You must not execute "
    "commands, write files, mutate Git, self-approve work, schedule work, or "
    "claim that an action was performed. Do not emit SKILL commands or tool "
    "requests. Send all proposed changes through the human-reviewed "
    "Chat → Studio → ticket/project → staging workflow; never bypass its "
    "approval gates. The backend supplies relevant repository, Vortex ledger, "
    "checkpoint, and commit-history excerpts as read-only context.\n\n"
    "Every response must be one valid JSON object with this shape: "
    '{"kind":"analysis|recommendation|draft|error","summary":"...","evidence":['
    '{"source":"...","finding":"..."}],"proposed_changes":['
    '{"path":"...","change":"..."}],"human_review_required":true}. '
    "Use empty arrays when there is no evidence or proposed change. "
    "Set human_review_required to true for every response."
)

SEVEN_CONTEXT_SYNC_PROMPT = (
    "CURRENT OPERATOR CONTEXT: The local Vortex ledger is active at "
    "/mnt/archive/vortex/ with a 90-day retention policy. The previously "
    "recorded full-suite baseline was 2,406 passed and 2 failed; the two "
    "known isolation tests have since passed in a focused rerun, and any "
    "new full-suite result must be reported only after that run completes. "
    "The operator's promotion policy is DEV → UAT → PRD with manual review "
    "between stages. Treat that as a workflow boundary, not proof that a "
    "particular deployment has occurred."
)

QWEN_CHAT_SYSTEM_PROMPT += "\n\n" + READ_ONLY_PROFILE_PROMPT

_TOOL_REQUEST_RE = re.compile(r"(?im)^\s*/?SKILL\s+([a-z0-9_-]+)\b")
_ERROR_RESPONSE_RE = re.compile(
    r"^\[(?:local runtime error:[^]]*|(?:gemma|qwen|llama))\]\s*(?:error:)?",
    re.I,
)


def is_read_only_agent(agent_name: Any) -> bool:
    return normalize_agent_name(agent_name) in READ_ONLY_AGENT_PROFILES


def agent_capability_allowed(agent_name: Any, capability: Any) -> bool:
    return not (
        is_read_only_agent(agent_name)
        and str(capability or "").strip().lower() in READ_ONLY_AGENT_CAPABILITIES
    )


def agent_skill_allowed(agent_name: Any, skill_name: Any) -> bool:
    if not is_read_only_agent(agent_name):
        return True
    return str(skill_name or "").strip().lower() in READ_ONLY_AGENT_SKILLS


def normalize_read_only_response(agent_name: Any, content: Any) -> str:
    """Return a valid, review-gated JSON response and suppress tool requests."""
    if not is_read_only_agent(agent_name):
        return str(content or "")

    text = str(content or "").strip()
    requested_tools = [match.group(1).lower() for match in _TOOL_REQUEST_RE.finditer(text)]
    blocked_tool = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {
            "kind": "error" if _ERROR_RESPONSE_RE.match(text) else "analysis",
            "summary": text[:4000],
            "evidence": [],
            "proposed_changes": [],
            "human_review_required": True,
        }

    if not isinstance(payload, dict):
        payload = {
            "kind": "analysis",
            "summary": json.dumps(payload, ensure_ascii=True)[:4000],
            "evidence": [],
            "proposed_changes": [],
            "human_review_required": True,
        }

    if requested_tools or payload.get("kind") == "tool_call":
        blocked_tool = (
            requested_tools[0]
            if requested_tools
            else str(payload.get("tool") or payload.get("name") or "unknown")[:100]
        )
        payload = {
            "kind": "error",
            "summary": "A tool request was suppressed by the read-only agent profile.",
            "evidence": [],
            "proposed_changes": [],
            "human_review_required": True,
        }

    kind = payload.get("kind")
    if kind not in {"analysis", "recommendation", "draft", "error"}:
        kind = "analysis"
    summary = payload.get("summary", "")
    if not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=True)
    if not summary.strip():
        kind = "error"
        summary = "The agent returned an empty response."

    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    evidence = [
        {
            "source": str(item.get("source") or "")[:200],
            "finding": str(item.get("finding") or "")[:1000],
        }
        for item in evidence[:20]
        if isinstance(item, dict)
    ]
    proposed_changes = payload.get("proposed_changes")
    if not isinstance(proposed_changes, list):
        proposed_changes = []
    proposed_changes = [
        {
            "path": str(item.get("path") or "")[:300],
            "change": str(item.get("change") or "")[:1000],
        }
        for item in proposed_changes[:20]
        if isinstance(item, dict)
    ]
    normalized = {
        "kind": kind,
        "summary": summary[:4000],
        "evidence": evidence,
        "proposed_changes": proposed_changes,
        "human_review_required": True,
    }
    if blocked_tool:
        normalized["blocked_tool"] = blocked_tool
    return json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))


def normalize_model_name(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_agent_name(value: Any) -> str:
    return str(value or "").strip().lower()


def is_non_ollama_model(model: Any) -> bool:
    model_name = normalize_model_name(model)
    return model_name in NON_OLLAMA_MODELS or model_name.startswith("seven-direct:")


def is_direct_runtime_model(model: Any) -> bool:
    return normalize_model_name(model).startswith("seven-direct:")


def agent_enabled(agent: dict[str, Any]) -> bool:
    try:
        return bool(int((agent or {}).get("enabled", 1)))
    except Exception:
        return True


def is_local_ollama_agent(agent: dict[str, Any], *, include_disabled: bool = False) -> bool:
    if not include_disabled and not agent_enabled(agent):
        return False
    if str((agent or {}).get("tier") or "local").strip().lower() != "local":
        return False
    model = normalize_model_name((agent or {}).get("model"))
    return not is_non_ollama_model(model)


def is_chat_capable_model(model: Any) -> bool:
    model_name = normalize_model_name(model)
    return bool(model_name) and model_name not in NON_OLLAMA_MODELS and model_name not in EMBEDDING_ONLY_MODELS


def preferred_model_for_agent(agent_name: Any, current_model: Any = "") -> str:
    name = normalize_agent_name(agent_name)
    preferred = PREFERRED_AGENT_MODELS.get(name)
    if preferred:
        return preferred
    return str(current_model or "").strip()


def configured_ollama_models(agents: Iterable[dict[str, Any]], *, include_disabled: bool = False) -> set[str]:
    models: set[str] = set()
    for agent in agents or []:
        if not is_local_ollama_agent(agent, include_disabled=include_disabled):
            continue
        model = normalize_model_name((agent or {}).get("model"))
        if model:
            models.add(model)
    return models


def unused_chat_models(installed_models: Iterable[Any], assigned_models: Iterable[Any]) -> list[str]:
    assigned = {normalize_model_name(model) for model in assigned_models if normalize_model_name(model)}
    unused = []
    for model in installed_models or []:
        normalized = normalize_model_name(model)
        if not normalized or normalized in assigned:
            continue
        if not is_chat_capable_model(normalized):
            continue
        if normalized in AVOID_CHAT_DEFAULT_MODELS:
            continue
        unused.append(normalized)
    return sorted(set(unused))
