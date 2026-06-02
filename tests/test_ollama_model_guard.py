from __future__ import annotations

from pathlib import Path

from utils.ollama_model_guard import build_model_store_guard, manifest_models


def _manifest(root: Path, model: str, tag: str = "latest") -> None:
    path = root / "manifests" / "registry.ollama.ai" / "library" / model / tag
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def test_manifest_models_reads_ollama_manifest_names(tmp_path):
    _manifest(tmp_path, "Qwen2.5")
    _manifest(tmp_path, "gemma4", "26b")

    assert manifest_models(tmp_path) == {"qwen2.5:latest", "gemma4:26b"}


def test_guard_flags_active_path_mismatch_when_shared_store_has_model(tmp_path):
    _manifest(tmp_path, "Qwen2.5")
    _manifest(tmp_path, "nomic-embed-text")
    agents = [{"name": "qwen", "tier": "local", "model": "qwen2.5:latest"}]

    guard = build_model_store_guard(agents, {"qwen:latest"}, model_store=tmp_path)

    assert guard["ok"] is False
    assert guard["present_in_expected"] == ["qwen2.5:latest"]
    assert guard["expected_invisible"] == ["qwen2.5:latest"]
    assert guard["issues"][0]["kind"] == "ollama_model_path_mismatch"


def test_guard_warns_when_configured_model_is_not_in_shared_store(tmp_path):
    _manifest(tmp_path, "Qwen2.5")
    agents = [{"name": "sniffles", "tier": "local", "model": "deepseek-r1:7b"}]

    guard = build_model_store_guard(agents, {"qwen2.5:latest"}, model_store=tmp_path)

    assert guard["ok"] is True
    assert guard["absent_from_expected"] == ["deepseek-r1:7b"]
    assert guard["issues"][0]["kind"] == "configured_model_absent"


def test_guard_ignores_disabled_local_agents(tmp_path):
    _manifest(tmp_path, "Qwen2.5")
    agents = [
        {"name": "sniffles", "tier": "local", "model": "deepseek-r1:7b", "enabled": 0},
        {"name": "qwen", "tier": "local", "model": "qwen2.5:latest", "enabled": 1},
    ]

    guard = build_model_store_guard(agents, {"qwen2.5:latest"}, model_store=tmp_path)

    assert guard["ok"] is True
    assert guard["configured_models"] == ["qwen2.5:latest"]
    assert guard["absent_from_expected"] == []
    assert guard["issues"] == []
