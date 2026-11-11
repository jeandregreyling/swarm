"""Read-only, bounded runtime and archive status for the owner chat surface."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from urllib.request import urlopen

ARCHIVE_ROOT = Path("/mnt/archive/hf_archive")
ARCHIVE_MOUNT = Path("/mnt/archive")
ARCHIVE_PLAN = ARCHIVE_ROOT / ".hummingbird-archive-plan.json"
APEX_API = "http://127.0.0.1:8080/v1/models"
APEX_MODEL = "qwen2.5:14b-instruct"


def _download_process() -> int | None:
    proc_root = Path("/proc")
    try:
        entries = proc_root.iterdir()
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                args = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
                args = [arg for arg in args if arg]
            except (OSError, PermissionError):
                continue
            script = next((arg for arg in args
                           if arg.endswith("/hf_vault_heist.py") or arg == "hf_vault_heist.py"), None)
            if (len(args) >= 2 and Path(args[0]).name.startswith("python") and script
                    and "--download" in args
                    and "--vault-dir" in args
                    and args[args.index("--vault-dir") + 1] == str(ARCHIVE_ROOT)):
                return int(entry.name)
    except OSError:
        return None
    return None


def _archive_progress() -> dict:
    root = ARCHIVE_ROOT
    try:
        if (not ARCHIVE_MOUNT.is_mount() or root.is_symlink()
                or not root.resolve().is_relative_to(ARCHIVE_MOUNT.resolve())
                or ARCHIVE_PLAN.is_symlink()):
            raise ValueError("archive volume or plan is not trusted")
        from core.hf_library import managed_plan
        plan = managed_plan(ARCHIVE_PLAN)
        if plan.get("vault") != str(root) or not isinstance(plan.get("plan"), list):
            raise ValueError("archive plan does not match the mounted volume")
        running_pid = _download_process()
        repositories = []
        total_bytes = 0
        present_bytes = 0
        active_repository = None
        for repo in plan["plan"]:
            directory = Path(repo["directory"])
            if directory.is_symlink() or not directory.resolve().is_relative_to(root.resolve()):
                raise ValueError("archive repository path escaped the volume")
            expected = 0
            present = 0
            verified = set()
            receipt_path = directory / "archive-receipt.json"
            if receipt_path.is_file() and not receipt_path.is_symlink():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt.get("revision") == repo.get("revision") and receipt.get("download_verified") is True:
                    verified = {f.get("path") for f in receipt.get("files", [])
                                if f.get("source_integrity_verified") is True}
            download_cache = directory / ".cache/huggingface/download"
            for item in repo["files"]:
                size = int(item["size"])
                expected += size
                relative = Path(item["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("archive file path escaped its repository")
                final = directory / relative
                if final.is_symlink() or not final.resolve().is_relative_to(directory.resolve()):
                    raise ValueError("archive file path escaped its repository")
                file_present = min(final.stat().st_size, size) if final.is_file() and not final.is_symlink() else 0
                if item["path"] not in verified and download_cache.is_dir():
                    pattern = f"*{item['source_hash']}*.incomplete"
                    partials = [p for p in download_cache.glob(pattern) if p.is_file() and not p.is_symlink()]
                    if partials:
                        file_present = max(file_present, min(max(p.stat().st_size for p in partials), size))
                present += file_present
            if len(verified) != len(repo["files"]):
                present = min(present, expected)
            total_bytes += expected
            present_bytes += present
            state = "verified" if len(verified) == len(repo["files"]) else "pending"
            if state != "verified" and running_pid is not None and active_repository is None:
                state = "downloading"
                active_repository = repo["repo_id"]
            repositories.append({
                "repo_id": repo["repo_id"], "state": state,
                "bytes_present": present, "bytes_expected": expected,
                "verified_files": len(verified), "file_count": len(repo["files"]),
            })
        disk = os.statvfs(root)
        return {
            "state": "downloading" if running_pid is not None else (
                "verified" if repositories and all(r["state"] == "verified" for r in repositories)
                else "pending"),
            "mount": str(root), "free_bytes": disk.f_bavail * disk.f_frsize,
            "bytes_present": present_bytes, "bytes_expected": total_bytes,
            "downloader_pid": running_pid, "active_repository": active_repository,
            "repositories": repositories, "download_verified_is_not_indexed": True,
            "observed_at": time.time(),
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {"state": "unavailable", "mount": str(root), "observed_at": time.time()}


def _apex_status() -> dict:
    try:
        with urlopen(APEX_API, timeout=1) as response:
            data = json.load(response)
        models = data.get("data") if isinstance(data, dict) else None
        match = next((model for model in models or []
                      if isinstance(model, dict) and model.get("id") == APEX_MODEL), None)
        if match:
            metadata = match.get("meta") or {}
            return {
                "state": "online", "model": match["id"],
                "context_tokens": metadata.get("n_ctx"),
                "backend": "llama.cpp / Vulkan",
            }
        return {"state": "identity_mismatch", "expected_model": APEX_MODEL}
    except (OSError, ValueError, TypeError):
        return {"state": "offline", "expected_model": APEX_MODEL}


def runtime_stack_status() -> dict:
    available_ram = None
    try:
        memory = Path("/proc/meminfo").read_text(encoding="ascii")
        available_kib = next(int(line.split()[1]) for line in memory.splitlines()
                             if line.startswith("MemAvailable:"))
        available_ram = round(available_kib / 1024**2, 1)
    except (OSError, StopIteration, ValueError):
        pass
    apex = {**_apex_status(), "selection": "per_question", "online_agents": "explicit_tags_only"}
    return {
        "apex": apex,
        "host_available_ram_gib": available_ram,
        "archive": _archive_progress(),
    }
