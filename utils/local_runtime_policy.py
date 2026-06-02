"""Central local-runtime policy for Ollama-backed agents.

This module holds the small, stable decisions that should not be duplicated
across chat routing, model-store guards, probes, and agent wrappers.
"""
from __future__ import annotations

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


def normalize_model_name(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_agent_name(value: Any) -> str:
    return str(value or "").strip().lower()


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
    return model not in NON_OLLAMA_MODELS


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
