from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _write(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _seed_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "master", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "remote", "add", "origin", str(remote))

    _write(repo, "README.md", "base\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "push", "-u", "origin", "master")

    _git(repo, "checkout", "-b", "feature/branch-mirror")
    _write(repo, "README.md", "base\nfeature\n")
    _write(repo, "feature.txt", "branch\n")
    _git(repo, "add", "README.md", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "push", "-u", "origin", "feature/branch-mirror")
    _git(repo, "checkout", "master")
    return repo, remote


def _client(monkeypatch, repo: Path):
    import frontend.blueprints.git as git_bp_mod

    monkeypatch.setattr(
        git_bp_mod,
        "_GIT_ENVS",
        {"prod": repo, "dev": repo, "uat": repo},
    )
    monkeypatch.setattr(git_bp_mod, "_git_repo_root", lambda: repo)
    monkeypatch.setattr(git_bp_mod, "log_activity", lambda *a, **k: None)
    app = Flask(__name__)
    app.register_blueprint(git_bp_mod.git_bp)
    app.config["TESTING"] = True
    return app.test_client()


def test_branch_endpoint_lists_origin_branches(tmp_path, monkeypatch):
    repo, _remote = _seed_repo(tmp_path)
    client = _client(monkeypatch, repo)

    data = client.get("/api/git/branches?environment=dev").get_json()

    assert data["ok"] is True
    assert data["environment"] == "dev"
    assert data["current"]["branch"] == "master"
    assert any(b["name"] == "origin/feature/branch-mirror" for b in data["remote"])


def test_compare_endpoint_does_not_checkout_branch(tmp_path, monkeypatch):
    repo, _remote = _seed_repo(tmp_path)
    client = _client(monkeypatch, repo)

    data = client.get(
        "/api/git/compare?environment=dev&base=HEAD&head=origin/feature/branch-mirror"
    ).get_json()

    assert data["ok"] is True
    assert data["file_count"] == 2
    assert {f["path"] for f in data["files"]} == {"README.md", "feature.txt"}
    assert _git(repo, "branch", "--show-current") == "master"


def test_checkout_requires_dirty_confirmation(tmp_path, monkeypatch):
    repo, _remote = _seed_repo(tmp_path)
    client = _client(monkeypatch, repo)
    _write(repo, "dirty.txt", "not committed\n")

    response = client.post(
        "/api/git/checkout",
        json={"environment": "dev", "branch": "origin/feature/branch-mirror"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert data["needs_confirm_dirty"] is True
    assert _git(repo, "branch", "--show-current") == "master"


def test_invalid_environment_rejected(tmp_path, monkeypatch):
    repo, _remote = _seed_repo(tmp_path)
    client = _client(monkeypatch, repo)

    response = client.get("/api/git/branches?environment=qa")

    assert response.status_code == 500
    assert response.get_json()["ok"] is False
