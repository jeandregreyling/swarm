import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import core.hummingbird_status as status


def plan_for(root, *, verified=False):
    repo_dir = root / "model/Qwen/example/revision"
    repo_dir.mkdir(parents=True, exist_ok=True)
    content = b"weights"
    source_hash = hashlib.sha256(content).hexdigest()
    repo = {
        "repo_id": "Qwen/example",
        "revision": "revision",
        "directory": str(repo_dir),
        "files": [{"path": "model.gguf", "size": len(content),
                   "source_hash": source_hash}],
    }
    if verified:
        (repo_dir / "model.gguf").write_bytes(content)
        (repo_dir / "archive-receipt.json").write_text(json.dumps({
            "revision": "revision", "download_verified": True,
            "files": [{"path": "model.gguf", "source_integrity_verified": True}],
        }))
    else:
        partial_dir = repo_dir / ".cache/huggingface/download"
        partial_dir.mkdir(parents=True)
        (partial_dir / f"blob.{source_hash}.part.incomplete").write_bytes(content[:3])
    return {"vault": str(root), "plan": [repo]}


def test_archive_progress_is_mount_bounded_and_reports_downloaded_bytes(monkeypatch, tmp_path):
    plan = plan_for(tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_ROOT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_MOUNT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_PLAN", tmp_path / "plan.json")
    status.ARCHIVE_PLAN.write_text(json.dumps(plan))
    monkeypatch.setattr(Path, "is_mount", lambda path: path == tmp_path)
    monkeypatch.setattr(status, "_download_process", lambda: 710035)
    result = status._archive_progress()
    assert result["state"] == "downloading"
    assert result["downloader_pid"] == 710035
    assert result["bytes_present"] == 3
    assert result["bytes_expected"] == 7
    assert result["repositories"][0]["state"] == "downloading"


def test_archive_receipt_changes_status_to_verified_not_indexed(monkeypatch, tmp_path):
    plan = plan_for(tmp_path, verified=True)
    monkeypatch.setattr(status, "ARCHIVE_ROOT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_MOUNT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_PLAN", tmp_path / "plan.json")
    status.ARCHIVE_PLAN.write_text(json.dumps(plan))
    monkeypatch.setattr(Path, "is_mount", lambda path: path == tmp_path)
    monkeypatch.setattr(status, "_download_process", lambda: None)
    result = status._archive_progress()
    assert result["state"] == "verified"
    assert result["download_verified_is_not_indexed"] is True
    assert result["repositories"][0]["verified_files"] == 1


def test_archive_status_fails_closed_for_wrong_volume_or_escaping_path(monkeypatch, tmp_path):
    plan = plan_for(tmp_path)
    plan["plan"][0]["directory"] = str(tmp_path.parent / "outside")
    monkeypatch.setattr(status, "ARCHIVE_ROOT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_MOUNT", tmp_path)
    monkeypatch.setattr(status, "ARCHIVE_PLAN", tmp_path / "plan.json")
    status.ARCHIVE_PLAN.write_text(json.dumps(plan))
    monkeypatch.setattr(Path, "is_mount", lambda path: path == tmp_path)
    assert status._archive_progress()["state"] == "unavailable"
    monkeypatch.setattr(Path, "is_mount", lambda _: False)
    assert status._archive_progress()["state"] == "unavailable"


def test_apex_status_checks_the_served_model_identity(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps({"data": [{"id": status.APEX_MODEL,
                                         "meta": {"n_ctx": 16384}}]}).encode()

    monkeypatch.setattr(status, "urlopen", lambda *_, **__: Response())
    assert status._apex_status() == {
        "state": "online", "model": status.APEX_MODEL,
        "context_tokens": 16384, "backend": "llama.cpp / Vulkan",
    }
