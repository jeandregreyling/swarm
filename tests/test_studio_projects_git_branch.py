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


def test_git_pull_blocks_dirty_worktree(monkeypatch):
    calls = []

    def fake_git(args, timeout=20, env=""):
        calls.append(args)
        if args == ["status", "--porcelain=1"]:
            return _Proc(" M frontend/static/js/views/git.js\n")
        raise AssertionError(f"unexpected git command: {args}")

    client = _client(monkeypatch, fake_git)
    resp = client.post(
        "/api/git/pull",
        json={"environment": "dev", "proposal_id": "PROP-1"},
    )
    data = resp.get_json()

    assert resp.status_code == 409
    assert data["ok"] is False
    assert "uncommitted changes" in data["error"]
    assert ["pull", "--ff-only"] not in calls


def test_git_fetch_and_push_routes(monkeypatch):
    calls = []

    def fake_git(args, timeout=20, env=""):
        calls.append((args, env))
        return _Proc("ok\n")

    client = _client(monkeypatch, fake_git)

    fetch = client.post("/api/git/fetch", json={"environment": "dev"}).get_json()
    push = client.post("/api/git/push", json={"environment": "dev", "proposal_id": "PROP-1"}).get_json()

    assert fetch["ok"] is True
    assert push["ok"] is True
    assert (["fetch", "--prune", "origin"], "dev") in calls
    assert (["push"], "dev") in calls


def test_projects_panel_exposes_git_branch_controls():
    template = (ROOT / "frontend/templates/terminal_base.html").read_text()
    js = (ROOT / "frontend/static/js/views/projects.js").read_text()

    assert 'id="projects-git-status"' in template
    assert 'id="projects-branch-select"' in template
    assert "projectsCheckoutBranch()" in template
    assert "/api/git/status?environment=dev" in js
    assert "/api/git/branches?environment=dev" in js
    assert "/api/git/checkout" in js


def test_projects_tile_exposes_blackboard_count():
    js = (ROOT / "frontend/static/js/views/projects.js").read_text()

    assert "p.blackboard_count" in js
    assert "Blackboard active:" in js


def test_git_panel_defaults_to_dev_environment():
    js = (ROOT / "frontend/static/js/views/git.js").read_text()

    assert "environment: 'dev'" in js
    assert "envSelect.value = state.environment" in js


def test_git_panel_exposes_branch_dropdown_and_direct_buttons():
    template = (ROOT / "frontend/templates/terminal_base.html").read_text()
    js = (ROOT / "frontend/static/js/views/git.js").read_text()

    assert 'id="git-branch-select"' in template
    assert 'id="git-checkout-btn"' in template
    assert 'id="git-pull-btn"' in template
    assert 'id="git-push-btn"' in template
    assert "gitRefreshBranches()" in js
    assert "/api/git/fetch" in js
    assert "/api/git/pull" in js
    assert "/api/git/push" in js


def test_git_panel_filters_to_git_linked_proposals():
    js = (ROOT / "frontend/static/js/views/git.js").read_text()

    assert "proposals.filter" in js
    assert "git (stage|unstage|commit|checkout)" in js
    assert "Studio Projects:" in js
