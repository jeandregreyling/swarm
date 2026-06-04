"""Direct GGUF model inventory for Seven Runtime."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


DEFAULT_SCAN_ROOTS = (
    "/mnt/llm",
    "/home/seven/swarm/agents/seven/models",
    "/home/seven/.lmstudio/.internal/bundled-models",
)


def _mounted(path: str) -> bool:
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as fh:
            mounts = {line.split()[1] for line in fh if line.strip()}
        p = Path(path)
        return any(str(p) == m or str(p).startswith(m.rstrip("/") + "/") for m in mounts)
    except OSError:
        return os.path.ismount(path)


def scan_gguf(roots: Iterable[str] | None = None, *, limit: int = 200) -> dict:
    """Scan known local model stores for GGUF files.

    The scanner distinguishes a missing mount/root from an empty model store so
    UI and watchdog checks can report the real fault instead of saying "no
    models" for a disconnected drive.
    """
    out = {
        "ok": True,
        "roots": [],
        "models": [],
        "warnings": [],
    }
    seen: set[str] = set()
    for raw_root in roots or DEFAULT_SCAN_ROOTS:
        root = os.path.abspath(os.path.expanduser(str(raw_root)))
        root_info = {
            "path": root,
            "exists": os.path.exists(root),
            "mounted": _mounted(root) if root.startswith("/mnt/") else None,
            "gguf_count": 0,
        }
        out["roots"].append(root_info)
        if not root_info["exists"]:
            out["warnings"].append(f"missing model root: {root}")
            continue
        if root.startswith("/mnt/") and root_info["mounted"] is False:
            out["warnings"].append(f"model root not mounted: {root}")
            continue
        try:
            for path in Path(root).rglob("*.gguf"):
                full = str(path)
                if full in seen:
                    continue
                seen.add(full)
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                root_info["gguf_count"] += 1
                out["models"].append({
                    "name": path.stem,
                    "path": full,
                    "size": size,
                    "size_gb": round(size / 1_000_000_000, 2),
                    "source_root": root,
                    "role": "embed" if "embed" in path.name.lower() or "nomic" in full.lower() else "general",
                    "direct": True,
                })
                if len(out["models"]) >= limit:
                    out["warnings"].append(f"scan limit reached: {limit}")
                    return out
        except OSError as exc:
            out["warnings"].append(f"scan failed for {root}: {exc}")
    return out
