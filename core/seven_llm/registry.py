"""core/llm/registry.py — Seven's own model catalogue.

Every model known to the Swarm lives here: GGUF path, ctx window, quantisation,
role, RAM ceiling and idle TTL. Drivers consult the registry to decide whether
they can serve a given model id and how to parameterise loading.

Entries come from three layers, later ones winning: the builtin DEFAULTS
below, every model already pulled into the Ollama store (served straight from
its GGUF blob by llama-server, so Ollama itself is not needed), and
ops/llm_registry.yaml. Set SWARM_OLLAMA_STORE to choose the store directory
("" disables discovery). Hot-reload is supported through :func:`reload`.
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


_OLLAMA_STORE_CANDIDATES = ("/mnt/archive/models", "~/.ollama/models")
_DISCOVERED_TTL_S = 1800


def _ollama_store_root() -> Optional[str]:
    configured = os.environ.get("SWARM_OLLAMA_STORE")
    if configured is not None:
        configured = configured.strip()
        return os.path.expanduser(configured) if configured else None
    for candidate in (os.environ.get("OLLAMA_MODELS", ""), *_OLLAMA_STORE_CANDIDATES):
        path = os.path.expanduser(candidate) if candidate else ""
        if path and os.path.isdir(os.path.join(path, "blobs")):
            return path
    return None


def _manifest_names(root: str) -> dict[str, str]:
    """Map 'name:tag' -> manifest file across Ollama's v1 and v2 layouts."""
    found: dict[str, str] = {}
    for layout, host in (("manifests-v2", "ollama.com"), ("manifests", "registry.ollama.ai")):
        base = os.path.join(root, layout, host)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for tag in files:
                rel = os.path.relpath(os.path.join(dirpath, tag), base).split(os.sep)
                if len(rel) < 3:
                    continue
                namespace, name = rel[-3], rel[-2]
                model = f"{name}:{tag}" if namespace == "library" else f"{namespace}/{name}:{tag}"
                found.setdefault(model.lower(), os.path.join(dirpath, tag))
    return found


def _read_blob_json(root: str, digest: str) -> dict:
    try:
        import json
        with open(os.path.join(root, "blobs", digest.replace(":", "-")), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_blob_text(root: str, digest: str) -> str:
    try:
        with open(os.path.join(root, "blobs", digest.replace(":", "-")), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _entry_from_manifest(root: str, name: str, manifest_path: str) -> Optional[ModelEntry]:
    try:
        import json
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None
    model_path, size, params, system, projector, proj_size = None, 0, {}, "", "", 0
    for layer in manifest.get("layers") or []:
        kind = str(layer.get("mediaType") or "").rsplit(".", 1)[-1]
        digest = str(layer.get("digest") or "")
        if kind == "model" and model_path is None:
            model_path = os.path.join(root, "blobs", digest.replace(":", "-"))
            size = int(layer.get("size") or 0)
        elif kind == "projector" and not projector:
            projector = os.path.join(root, "blobs", digest.replace(":", "-"))
            proj_size = int(layer.get("size") or 0)
        elif kind == "params":
            params = _read_blob_json(root, digest)
        elif kind == "system":
            system = _read_blob_text(root, digest).strip()
    if not model_path or not os.path.isfile(model_path):
        return None

    role = "embed" if "embed" in name else ("coder" if "coder" in name else "general")
    size_gb = size / 1024 ** 3
    ctx = int(params.get("num_ctx") or (2048 if role == "embed" else 8192))
    # weights + KV cache/compute buffers at the configured context
    ram_gb = round(size_gb + (0.3 if role == "embed" else 0.5 + size_gb * 0.1 * ctx / 8192), 1)
    options: dict = {"mode": "server", "slots": 1, "source": "ollama-store"}
    if projector and os.path.isfile(projector):
        options["mmproj"] = projector
        ram_gb = round(ram_gb + proj_size / 1024 ** 3, 1)
    if role == "embed":
        options.update({"embedding": True, "ngl": 0})
    if "num_gpu" in params:
        options["ngl"] = int(params["num_gpu"])
    if params.get("num_thread"):
        options["threads"] = int(params["num_thread"])
    if params.get("temperature") is not None:
        options["temperature"] = float(params["temperature"])
    if params.get("stop"):
        options["stop"] = list(params["stop"]) if isinstance(params["stop"], list) else [params["stop"]]
    if system:
        options["default_system"] = system
    return ModelEntry(
        name=name, driver="llamacpp", role=role, path=model_path, ctx=ctx,
        quant="auto", ram_gb=ram_gb, ttl_seconds=_DISCOVERED_TTL_S, options=options,
    )


def _ollama_store_entries() -> list[ModelEntry]:
    """Serve models already pulled into the Ollama store straight from their GGUF blobs."""
    root = _ollama_store_root()
    if not root:
        return []
    entries = []
    for name, manifest_path in sorted(_manifest_names(root).items()):
        entry = _entry_from_manifest(root, name, manifest_path)
        if entry:
            entries.append(entry)
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
_ALIASES: dict[str, str] = {}


def _load_from_disk() -> dict[str, ModelEntry]:
    result: dict[str, ModelEntry] = {m.name: m for m in DEFAULTS}
    for entry in _ollama_store_entries():
        result[entry.name] = entry
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


def _build_aliases(models: dict[str, ModelEntry]) -> dict[str, str]:
    """Ollama lets callers drop ':latest'; mirror that for direct entries."""
    aliases: dict[str, str] = {}
    for name, entry in models.items():
        if entry.driver == "llamacpp" and name.endswith(":latest"):
            bare = name[: -len(":latest")]
            if bare not in models or models[bare].driver == "ollama":
                aliases[bare] = name
    return aliases


def _ensure_loaded() -> None:
    if not _MODELS:
        _MODELS.update(_load_from_disk())
        _ALIASES.clear()
        _ALIASES.update(_build_aliases(_MODELS))
        for bare in _ALIASES:
            _MODELS.pop(bare, None)


def reload() -> int:
    """Reload the registry from disk. Returns count of entries."""
    with _LOCK:
        _MODELS.clear()
        _ensure_loaded()
        return len(_MODELS)


def list_models() -> list[ModelEntry]:
    with _LOCK:
        _ensure_loaded()
        return list(_MODELS.values())


def get(name: str) -> Optional[ModelEntry]:
    with _LOCK:
        _ensure_loaded()
        key = str(name or "").strip()
        entry = _MODELS.get(key)
        if entry is None:
            lowered = key.lower()
            entry = _MODELS.get(lowered) or _MODELS.get(_ALIASES.get(lowered, ""))
        return entry


def register(entry: ModelEntry) -> None:
    with _LOCK:
        _ensure_loaded()
        _MODELS[entry.name] = entry
        _ALIASES.pop(entry.name, None)


def to_dicts() -> list[dict]:
    return [asdict(m) for m in list_models()]
