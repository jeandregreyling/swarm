"""core/llm/registry.py — Seven's own model catalogue.

Every model known to the Swarm lives here: GGUF path, ctx window, quantisation,
role, RAM ceiling and idle TTL. Drivers consult the registry to decide whether
they can serve a given model id and how to parameterise loading.

Entries are loaded from ops/llm_registry.yaml if present, otherwise the builtin
DEFAULTS below are used. Hot-reload is supported through :func:`reload`.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional

try:  # PyYAML is an optional runtime dep
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml always present in this repo
    yaml = None  # type: ignore


REGISTRY_PATH = os.environ.get(
    "SEVEN_LLM_REGISTRY", os.path.join(os.path.dirname(__file__), "..", "..", "ops", "llm_registry.yaml")
)


@dataclass(frozen=True)
class ModelEntry:
    """One model declaration."""

    name: str
    driver: str  # 'ollama' | 'llamacpp' | 'lmstudio' | 'openai'
    role: str = "general"  # 'general' | 'coder' | 'reasoner' | 'embed' | 'vision'
    path: Optional[str] = None  # GGUF path for llamacpp; None for remote drivers
    ctx: int = 4096
    quant: str = "Q4_K_M"
    ram_gb: float = 6.0  # expected resident set
    ttl_seconds: int = 300  # warm-pool idle TTL before eviction
    endpoint: Optional[str] = None  # for lmstudio/openai/ollama
    options: dict = field(default_factory=dict)


_SWARM_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SEVEN_DAILY_GGUF = os.path.join(
    _SWARM_ROOT, "agents", "seven", "models", "small", "qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
_SEVEN_Q8_GGUF = os.path.join(_SWARM_ROOT, "agents", "seven", "models", "seven-7b-q8_0.gguf")
_SEVEN_FP16_GGUF = os.path.join(_SWARM_ROOT, "agents", "seven", "models", "seven-7b-fp16.gguf")
_NOMIC_LMSTUDIO_GGUF = os.path.expanduser(
    "~/.lmstudio/.internal/bundled-models/nomic-ai/"
    "nomic-embed-text-v1.5-GGUF/nomic-embed-text-v1.5.Q4_K_M.gguf"
)


def _optional_defaults() -> list[ModelEntry]:
    entries: list[ModelEntry] = []
    if os.path.isfile(_SEVEN_DAILY_GGUF):
        entries.append(ModelEntry(
            name="seven-direct:daily",
            driver="llamacpp",
            role="general",
            path=_SEVEN_DAILY_GGUF,
            ctx=2048,
            quant="Q4_K_M",
            ram_gb=1.2,
            ttl_seconds=0,
            options={"binary": "llama-cli", "mode": "server", "profile": "chatml", "threads": 4},
        ))
    if os.path.isfile(_SEVEN_Q8_GGUF):
        entries.append(ModelEntry(
            name="seven-direct:q8",
            driver="llamacpp",
            role="general",
            path=_SEVEN_Q8_GGUF,
            ctx=2048,
            quant="Q8_0",
            ram_gb=8.2,
            ttl_seconds=0,
            options={"binary": "llama-cli", "mode": "server", "profile": "chatml"},
        ))
    if os.path.isfile(_SEVEN_FP16_GGUF):
        entries.append(ModelEntry(
            name="seven-direct:fp16",
            driver="llamacpp",
            role="general",
            path=_SEVEN_FP16_GGUF,
            ctx=2048,
            quant="F16",
            ram_gb=16.2,
            ttl_seconds=0,
            options={"binary": "llama-cli", "mode": "server", "profile": "chatml"},
        ))
    if os.path.isfile(_NOMIC_LMSTUDIO_GGUF):
        entries.append(ModelEntry(
            name="nomic-embed-text-direct",
            driver="llamacpp",
            role="embed",
            path=_NOMIC_LMSTUDIO_GGUF,
            ctx=2048,
            quant="Q4_K_M",
            ram_gb=1.0,
            ttl_seconds=0,
            options={"binary": "llama-cli", "embedding": True},
        ))
    return entries


DEFAULTS: tuple[ModelEntry, ...] = (
    ModelEntry(name="llama3.2:3b", driver="ollama", role="general", ram_gb=3.5),
    ModelEntry(name="qwen2.5:7b", driver="ollama", role="reasoner", ram_gb=6.5),
    ModelEntry(name="deepseek-coder:6.7b", driver="ollama", role="coder", ram_gb=5.5),
    ModelEntry(name="nomic-embed-text", driver="ollama", role="embed", ram_gb=1.0),
    *_optional_defaults(),
)


_LOCK = threading.RLock()
_MODELS: dict[str, ModelEntry] = {}


def _load_from_disk() -> dict[str, ModelEntry]:
    result: dict[str, ModelEntry] = {m.name: m for m in DEFAULTS}
    if not yaml:
        return result
    path = os.path.abspath(REGISTRY_PATH)
    if not os.path.isfile(path):
        return result
    try:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        return result
    for raw in (data.get("models") or []):
        try:
            entry = ModelEntry(**raw)
        except TypeError:
            continue
        result[entry.name] = entry
    return result


def reload() -> int:
    """Reload the registry from disk. Returns count of entries."""
    with _LOCK:
        _MODELS.clear()
        _MODELS.update(_load_from_disk())
        return len(_MODELS)


def list_models() -> list[ModelEntry]:
    with _LOCK:
        if not _MODELS:
            _MODELS.update(_load_from_disk())
        return list(_MODELS.values())


def get(name: str) -> Optional[ModelEntry]:
    with _LOCK:
        if not _MODELS:
            _MODELS.update(_load_from_disk())
        return _MODELS.get(name)


def register(entry: ModelEntry) -> None:
    with _LOCK:
        _MODELS[entry.name] = entry


def to_dicts() -> list[dict]:
    return [asdict(m) for m in list_models()]
