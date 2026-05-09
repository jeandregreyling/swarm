from __future__ import annotations

from pathlib import Path
import sys

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "frontend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class _Proc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _client(monkeypatch, fake_git):
    from frontend.blueprints import git as git_bp_mod

    monkeypatch.setattr(git_bp_mod, "_run_git_command", fake_git)
    monkeypatch.setattr(git_bp_mod, "_alm_gate_or_response", lambda data, action: None)
    monkeypatch.setattr(git_bp_mod, "log_activity", lambda *args, **kwargs: None)

    app = Flask(__name__)
    app.register_blueprint(git_bp_mod.git_bp)
    return app.test_client()


def test_git_branches_endpoint_returns_current_local_branch(monkeypatch):
    def fake_git(args, timeout=20, env=""):
        assert env == "dev"
        assert args == ["branch", "--format=%(refname:short)\t%(upstream:short)\t%(HEAD)"]
        return _Proc("main\torigin/main\t\nfeature/dev\torigin/feature/dev\t*\n")

    client = _client(monkeypatch, fake_git)
    resp = client.get("/api/git/branches?environment=dev")
    data = resp.get_json()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["current"] == "feature/dev"
    assert data["branches"][1]["current"] is True


def test_git_checkout_blocks_dirty_worktree(monkeypatch):
    calls = []

    def fake_git(args, timeout=20, env=""):
        calls.append(args)
        if args[:2] == ["rev-parse", "--verify"]:
            return _Proc("abc123\n")
        if args == ["status", "--porcelain=1"]:
            return _Proc(" M frontend/static/js/views/projects.js\n")
        raise AssertionError(f"unexpected git command: {args}")

    client = _client(monkeypatch, fake_git)
    resp = client.post(
        "/api/git/checkout",
        json={"environment": "dev", "branch": "feature/dev", "proposal_id": "PROP-1"},
    )
    data = resp.get_json()

    assert resp.status_code == 409
    assert data["ok"] is False
    assert "uncommitted changes" in data["error"]
    assert ["checkout", "feature/dev"] not in calls


def test_projects_panel_exposes_git_branch_controls():
    template = (ROOT / "frontend/templates/terminal_base.html").read_text()
    js = (ROOT / "frontend/static/js/views/projects.js").read_text()

    assert 'id="projects-git-status"' in template
    assert 'id="projects-branch-select"' in template
    assert "projectsCheckoutBranch()" in template
    assert "/api/git/status?environment=dev" in js
    assert "/api/git/branches?environment=dev" in js
    assert "/api/git/checkout" in js
