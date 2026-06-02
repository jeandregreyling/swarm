"""Ollama model-store guardrails for shared NTFS model storage."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


DEFAULT_EXPECTED_MODEL_STORE = "/mnt/llm/.ollama/models"
_NON_OLLAMA_MODELS = {"", "external", "local-algorithm"}


def normalize_model_name(value: Any) -> str:
    return str(value or "").strip().lower()


def expected_model_store() -> str:
    return os.environ.get("SWARM_OLLAMA_MODEL_STORE", DEFAULT_EXPECTED_MODEL_STORE).strip() or DEFAULT_EXPECTED_MODEL_STORE


def manifest_models(model_store: str | os.PathLike[str] | None = None) -> set[str]:
    """Return model:tag names from an Ollama manifests directory."""
    root = Path(model_store or expected_model_store())
    manifests = root / "manifests"
    if not manifests.is_dir():
        return set()

    models: set[str] = set()
    for path in manifests.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(manifests).parts
        if len(rel) < 2:
            continue
        models.add(normalize_model_name(f"{rel[-2]}:{rel[-1]}"))
    return models


def configured_ollama_models(agents: Iterable[dict[str, Any]]) -> set[str]:
    models: set[str] = set()
    for agent in agents or []:
        tier = str((agent or {}).get("tier") or "local").strip().lower()
        if tier != "local":
            continue
        model = normalize_model_name((agent or {}).get("model"))
        if model not in _NON_OLLAMA_MODELS:
            models.add(model)
    return models


def build_model_store_guard(
    agents: Iterable[dict[str, Any]],
    installed_models: Iterable[str],
    *,
    model_store: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Compare configured agent models, live Ollama models, and the shared store.

    This catches the specific failure mode where Ollama starts against a small
    local model directory while the real shared NTFS model store is mounted.
    """
    store = str(model_store or expected_model_store())
    store_path = Path(store)
    active = {normalize_model_name(model) for model in installed_models if normalize_model_name(model)}
    expected = manifest_models(store)
    configured = configured_ollama_models(agents)

    missing_active = sorted(model for model in configured if model not in active)
    present_in_expected = sorted(model for model in missing_active if model in expected)
    absent_from_expected = sorted(model for model in missing_active if model not in expected)
    expected_invisible = sorted(model for model in (expected & configured) if model not in active)

    issues: list[dict[str, Any]] = []
    if not store_path.exists():
        issues.append({
            "kind": "model_store_missing",
            "severity": "blocker",
            "message": f"Expected Ollama model store is not mounted: {store}",
        })
    elif not expected:
        issues.append({
            "kind": "model_store_empty",
            "severity": "blocker",
            "message": f"Expected Ollama model store has no manifests: {store}",
        })

    if present_in_expected:
        issues.append({
            "kind": "ollama_model_path_mismatch",
            "severity": "blocker",
            "models": present_in_expected,
            "message": "Configured agent models exist in the shared store but are not visible to live Ollama.",
        })

    if absent_from_expected:
        issues.append({
            "kind": "configured_model_absent",
            "severity": "warn",
            "models": absent_from_expected,
            "message": "Configured local agent models are absent from both live Ollama and the shared store.",
        })

    return {
        "ok": not any(issue.get("severity") == "blocker" for issue in issues),
        "expected_store": store,
        "expected_store_exists": store_path.exists(),
        "configured_models": sorted(configured),
        "active_models": sorted(active),
        "expected_models": sorted(expected),
        "missing_active": missing_active,
        "present_in_expected": present_in_expected,
        "absent_from_expected": absent_from_expected,
        "expected_invisible": expected_invisible,
        "issues": issues,
    }
