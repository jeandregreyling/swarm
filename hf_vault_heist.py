"""Revision-pinned archive downloader. Defaults to preflight, not downloading."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

VAULT_DIR = Path("/mnt/archive/hf_archive")
VAULT_MOUNT = Path("/mnt/archive")
GIB = 1024**3
TARGETS = {
    "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF": (
        "model", "d0a692ef765eefbf2fabb130b3cb2e8917e3d225", "apache-2.0"),
    "bartowski/Mistral-Nemo-Instruct-2407-GGUF": (
        "model", "a2dd64a0a76ea1bdb2bb6ab6fa5496b003c7c908", "apache-2.0"),
    "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF": (
        "model", "bf5b95e96dac0462e2a09145ec66cae9a3f12067", "llama3.1"),
    "bigcode/the-stack-smol": (
        "dataset", "4a6938ce94446f324c6629e7de00ac591710044b", None),
    "HuggingFaceH4/ultrachat_200k": (
        "dataset", "8049631c405ae6576f93f445c6b8166f76f5505a", "mit"),
    "Open-Orca/OpenOrca": (
        "dataset", "e9c87b4abb2609913751f9b26553fdb9c061796c", "mit"),
}
DEFAULT_REPOS = [repo for repo, (_, _, license_id) in TARGETS.items()
                 if license_id in {"apache-2.0", "mit"}]


def emit(status: str, **details) -> None:
    print(json.dumps({"status": status, **details}), flush=True)


def contained(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative:
        raise ValueError(f"Unsafe archive path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes archive: {relative}")
    return path


def validate_destination(vault: Path, mount: Path = VAULT_MOUNT) -> Path:
    if not mount.is_mount() or mount.resolve() == Path("/"):
        raise ValueError(f"Expected archive volume is not mounted: {mount}")
    resolved = vault.resolve()
    if resolved == mount.resolve() or not resolved.is_relative_to(mount.resolve()):
        raise ValueError(f"Archive must be a subdirectory of {mount}")
    return resolved


def selected_files(info, kind: str) -> list:
    if kind == "dataset":
        return list(info.siblings)
    selected = [f for f in info.siblings if
                f.rfilename.lower().endswith(("q4_k_m.gguf", "q8_0.gguf"))
                or PurePosixPath(f.rfilename).name.lower().startswith(
                    ("readme", "license", "notice", "use_policy"))]
    for quant in ("q4_k_m.gguf", "q8_0.gguf"):
        if sum(f.rfilename.lower().endswith(quant) for f in selected) != 1:
            raise ValueError(f"Expected exactly one complete {quant} file; refusing partial/duplicate weights")
    return selected


def preflight(api, repos: list[str], vault: Path, *, accept_llama: bool,
              max_bytes: int, reserve_bytes: int) -> list[dict]:
    plan = []
    for repo in repos:
        kind, revision, license_id = TARGETS[repo]
        if license_id is None:
            raise ValueError(f"{repo}: gated dataset with unverified per-source licenses; separate review required")
        if license_id == "llama3.1" and not accept_llama:
            raise ValueError(f"{repo}: requires explicit --accept-llama-license; it is not Apache/MIT")
        info = api.repo_info(repo, repo_type=kind, revision=revision, files_metadata=True)
        if info.sha != revision:
            raise ValueError(f"Revision mismatch: {repo}")
        if info.gated:
            raise ValueError(f"{repo}: gated access requires separate operator approval/authentication")
        actual_license = info.card_data.get("license") if info.card_data else None
        if actual_license != license_id:
            raise ValueError(f"License metadata mismatch for {repo}: {actual_license}")
        directory = contained(vault, f"{kind}/{repo}/{revision}")
        files = []
        for item in selected_files(info, kind):
            contained(directory, item.rfilename)
            if not isinstance(item.size, int) or item.size < 0:
                raise ValueError(f"Missing file size: {repo}/{item.rfilename}")
            source_hash = item.lfs.sha256 if item.lfs else item.blob_id
            algorithm = "sha256" if item.lfs else "git-sha1"
            expected_length = 64 if item.lfs else 40
            if (not isinstance(source_hash, str) or len(source_hash) != expected_length
                    or any(c not in "0123456789abcdef" for c in source_hash)):
                raise ValueError(f"Missing trusted source hash: {repo}/{item.rfilename}")
            files.append({"path": item.rfilename, "size": item.size,
                          "source_hash": source_hash, "source_hash_type": algorithm})
        if not files:
            raise ValueError(f"No files selected: {repo}")
        plan.append({"repo_id": repo, "repo_type": kind, "revision": revision,
                     "license": license_id, "directory": str(directory), "files": files})
    total = sum(f["size"] for entry in plan for f in entry["files"])
    if total > max_bytes:
        raise ValueError(f"Selection needs {total} bytes, above budget {max_bytes}")
    check_space(vault, total, reserve_bytes)
    return plan


def check_space(vault: Path, required: int, reserve: int) -> None:
    parent = vault
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    if free < required + reserve:
        raise ValueError(f"Insufficient archive space: free={free}, required={required}, reserve={reserve}")


def verify_file(directory: Path, item: dict) -> dict:
    path = contained(directory, item["path"])
    if path.stat().st_size != item["size"]:
        raise ValueError(f"Size mismatch: {path}")
    local = hashlib.sha256()
    source = hashlib.sha1() if item["source_hash_type"] == "git-sha1" else hashlib.sha256()
    if item["source_hash_type"] == "git-sha1":
        source.update(f"blob {item['size']}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            local.update(chunk)
            source.update(chunk)
    if source.hexdigest() != item["source_hash"]:
        raise ValueError(f"Source hash mismatch: {path}")
    return {**item, "local_sha256": local.hexdigest(), "source_integrity_verified": True}


def download_plan(plan: list[dict], vault: Path, snapshot_download, *,
                  workers: int, reserve_bytes: int) -> None:
    for entry in plan:
        validate_destination(vault)
        directory = contained(vault, str(Path(entry["directory"]).relative_to(vault)))
        for item in entry["files"]:
            contained(directory, item["path"])
        contained(directory, ".cache/huggingface")
        check_space(vault, sum(f["size"] for f in entry["files"]), reserve_bytes)
        emit("downloading", repo_id=entry["repo_id"], revision=entry["revision"])
        snapshot_download(
            repo_id=entry["repo_id"], repo_type=entry["repo_type"],
            revision=entry["revision"], token=False, local_dir=str(directory),
            allow_patterns=[f["path"] for f in entry["files"]], max_workers=workers,
        )
        verified = [verify_file(directory, item) for item in entry["files"]]
        receipt = {**entry, "files": verified, "download_verified": True, "indexed": False}
        receipt_path = contained(directory, "archive-receipt.json")
        temporary = contained(directory, "archive-receipt.json.tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        temporary.replace(receipt_path)
        if json.loads(receipt_path.read_text()) != receipt:
            raise ValueError(f"Receipt readback mismatch: {receipt_path}")
        emit("verified", repo_id=entry["repo_id"], receipt=str(receipt_path), indexed=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-dir", type=Path, default=VAULT_DIR)
    parser.add_argument("--repo", action="append", choices=TARGETS)
    parser.add_argument("--download", action="store_true", help="Execute after operator confirmation")
    parser.add_argument("--accept-llama-license", action="store_true")
    parser.add_argument("--max-gib", type=int, default=100)
    parser.add_argument("--reserve-gib", type=int, default=10)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args(argv)
    try:
        if args.max_gib <= 0 or args.reserve_gib < 1:
            raise ValueError("A positive budget and at least 1 GiB reserve are required")
        vault = validate_destination(args.vault_dir)
        for key, relative in (("HF_HOME", ".cache/huggingface"),
                              ("HF_HUB_CACHE", ".cache/huggingface/hub"),
                              ("HF_XET_CACHE", ".cache/huggingface/xet")):
            os.environ[key] = str(contained(vault, relative))
        os.environ["HF_HUB_DISABLE_XET"] = "1"
        from huggingface_hub import HfApi, snapshot_download
        from huggingface_hub.errors import HfHubHTTPError

        repos = list(dict.fromkeys(args.repo or DEFAULT_REPOS))
        try:
            plan = preflight(HfApi(token=False), repos, vault,
                             accept_llama=args.accept_llama_license,
                             max_bytes=args.max_gib * GIB, reserve_bytes=args.reserve_gib * GIB)
            emit("preflight", vault=str(vault), plan=plan,
                 total_bytes=sum(f["size"] for entry in plan for f in entry["files"]),
                 excluded=[repo for repo in TARGETS if repo not in repos])
            if args.download:
                download_plan(plan, vault, snapshot_download, workers=args.workers,
                              reserve_bytes=args.reserve_gib * GIB)
                emit("download_complete", indexed=False, repositories=len(plan))
        except HfHubHTTPError as exc:
            emit("failed", error=str(exc))
            return 1
    except (OSError, ValueError, ImportError) as exc:
        emit("failed", error=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
