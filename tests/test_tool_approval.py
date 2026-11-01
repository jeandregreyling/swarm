import json
from pathlib import Path
import queue
import subprocess
import threading
import time

import pytest
from flask import Flask

from core.apex_tools import ReadOnlyRepository, run_apex_tools
from core.tool_approval import ApprovalConflict, ApprovalStore


@pytest.fixture
def repository(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True)

    git("init", "-q")
    git("config", "user.name", "Isolated Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "probe.py").write_text("value = 1\n")
    (tmp_path / "other.py").write_text("other = 1\n")
    git("add", "--", "probe.py", "other.py")
    git("commit", "-qm", "baseline")
    return ReadOnlyRepository(tmp_path)


def write_proposal(store, repository, **overrides):
    args = {"path": "probe.py", "content": "# approved comment\nvalue = 1\n"}
    args.update(overrides)
    return store.propose(repository, "propose_write_file", args, "ghost", "session-1", 1)


def decide(store, transaction, decision=True):
    return store.decide(transaction.id, decision, "ghost", "session-1", transaction.csrf, lambda _: True)


def test_proposal_blocks_until_human_decision_then_executes_once(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    results = []
    thread = threading.Thread(target=lambda: results.append(store.wait(transaction)))
    thread.start()
    assert transaction.diff and transaction.hashes["probe.py"]
    assert not transaction.ready.wait(0.05)
    assert (repository.root / "probe.py").read_text() == "value = 1\n"
    result = decide(store, transaction)
    thread.join(timeout=2)
    assert result["status"] == "succeeded" and results == [result]
    assert (repository.root / "probe.py").read_text() == "# approved comment\nvalue = 1\n"
    assert store.list_for("ghost", "session-1") == []
    with pytest.raises(ApprovalConflict, match="consumed"):
        decide(store, transaction)


def test_rejection_resumes_with_denial_without_writing(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    assert decide(store, transaction, False)["output"] == "User Denied Execution"
    assert store.wait(transaction)["status"] == "denied"
    assert (repository.root / "probe.py").read_text() == "value = 1\n"


def patch_proposal(store, repository, **overrides):
    args = {"file_path": "probe.py", "exact_old_text": "value = 1", "new_text": "value = 2"}
    args.update(overrides)
    return store.propose(repository, "propose_patch", args, "ghost", "session-1", 1)


def test_patch_large_file_preserves_every_other_byte_and_uses_same_gate(repository):
    path = repository.root / "probe.py"
    original = b"# padding\r\n" * 30000 + b"value = 1\r\n# end"
    path.write_bytes(original)
    path.chmod(0o640)
    store = ApprovalStore()
    transaction = patch_proposal(store, repository)
    assert path.read_bytes() == original and not transaction.ready.is_set()
    assert len(transaction.diff) < 2000
    assert transaction.args.keys() == {"file_path", "exact_old_text", "new_text"}
    assert decide(store, transaction)["status"] == "succeeded"
    assert path.read_bytes() == original.replace(b"value = 1", b"value = 2", 1)
    assert path.stat().st_mode & 0o777 == 0o640
    with pytest.raises(ApprovalConflict, match="consumed"):
        decide(store, transaction)


@pytest.mark.parametrize("text", ["missing", "value"])
def test_patch_nonunique_match_fails_without_transaction(repository, text):
    repository.root.joinpath("probe.py").write_text("value = 1\nvalue = 2\n")
    store = ApprovalStore()
    with pytest.raises(ValueError, match="larger unique context"):
        patch_proposal(store, repository, exact_old_text=text)
    assert store.list_for("ghost", "session-1") == []


def test_patch_denial_and_drift_never_write(repository):
    store = ApprovalStore()
    transaction = patch_proposal(store, repository)
    assert decide(store, transaction, False)["status"] == "denied"
    assert repository.root.joinpath("probe.py").read_text() == "value = 1\n"
    transaction = patch_proposal(store, repository)
    repository.root.joinpath("probe.py").write_text("operator changed it\n")
    assert decide(store, transaction)["status"] == "failed"
    assert repository.root.joinpath("probe.py").read_text() == "operator changed it\n"


@pytest.mark.parametrize("overrides", [
    {"exact_old_text": ""}, {"new_text": "\0"}, {"new_text": "é" * 4001},
    {"file_path": "../probe.py"}, {"file_path": ".git/config"},
])
def test_patch_strict_arguments_and_paths(repository, overrides):
    with pytest.raises((ValueError, PermissionError)):
        patch_proposal(ApprovalStore(), repository, **overrides)


def test_patch_cannot_read_untracked_file_or_bypass_permission(repository):
    repository.root.joinpath("new.py").write_text("value = 1\n")
    with pytest.raises(PermissionError):
        patch_proposal(ApprovalStore(), repository, file_path="new.py")
    store = ApprovalStore()
    transaction = patch_proposal(store, repository)
    assert store.decide(transaction.id, True, "ghost", "session-1", transaction.csrf,
                        lambda _: False)["status"] == "denied"
    assert repository.root.joinpath("probe.py").read_text() == "value = 1\n"


def test_stale_file_and_mode_are_rejected(repository):
    for change_mode in (False, True):
        store = ApprovalStore()
        transaction = write_proposal(store, repository, content="replacement\n")
        path = repository.root / "probe.py"
        if change_mode:
            path.chmod(0o700)
        else:
            path.write_text("operator changed this\n")
        before = path.read_bytes()
        result = decide(store, transaction)
        assert result["status"] == "failed" and "Stale payload" in result["output"]
        assert path.read_bytes() == before
        path.chmod(0o644)


def test_session_csrf_and_owner_are_bound(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    assert store.list_for("ghost", "other-session") == []
    for owner, session, csrf in (
        ("apex", "session-1", transaction.csrf),
        ("ghost", "other-session", transaction.csrf),
        ("ghost", "session-1", "bad-token"),
    ):
        with pytest.raises(PermissionError):
            store.decide(transaction.id, True, owner, session, csrf, lambda _: True)
    assert not transaction.ready.is_set()
    decide(store, transaction, False)


def test_concurrent_duplicate_decisions_execute_once(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    results = []

    def run():
        try:
            results.append(decide(store, transaction)["status"])
        except ApprovalConflict:
            results.append("consumed")

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert sorted(results) == ["consumed", "succeeded"]


def test_expiration_reserves_target_and_restart_cannot_execute(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    with pytest.raises(ApprovalConflict, match="pending"):
        write_proposal(store, repository)
    transaction.expires_at = time.time() - 1
    assert store.list_for("ghost", "session-1") == []
    assert store.wait(transaction)["status"] == "denied"
    with pytest.raises(ApprovalConflict):
        decide(ApprovalStore(), transaction)


@pytest.mark.parametrize("args", [
    {"path": "../outside.py", "content": "bad"},
    {"path": "/tmp/outside.py", "content": "bad"},
    {"path": "probe.py", "content": "x", "execute": True},
    {"path": "new.py", "content": "new"},
    {"path": "other.py", "content": "\0"},
])
def test_invalid_write_proposals_do_not_create_transactions(repository, args):
    store = ApprovalStore()
    with pytest.raises((ValueError, PermissionError)):
        store.propose(repository, "propose_write_file", args, "ghost", "session-1", 1)
    assert store.list_for("ghost", "session-1") == []


@pytest.mark.parametrize("paths", ["probe.py", [], ["."], ["*.py"], ["probe.py", "probe.py"]])
def test_commit_requires_explicit_file_array(repository, paths):
    with pytest.raises((ValueError, PermissionError)):
        ApprovalStore().propose(repository, "propose_commit",
                                {"paths": paths, "message": "commit"},
                                "ghost", "session-1", 1)


def test_commit_excludes_unrelated_staged_and_worktree_changes(repository):
    repository.root.joinpath("probe.py").write_text("value = 2\n")
    repository.root.joinpath("other.py").write_text("other = 2\n")
    repository._git("add", "--", "other.py")
    other_index_before = repository._git("ls-files", "--stage", "--", "other.py")
    store = ApprovalStore()
    transaction = store.propose(repository, "propose_commit",
                                {"paths": ["probe.py"], "message": "Approved probe"},
                                "ghost", "session-1", 1)
    old_head = repository._git("rev-parse", "HEAD")
    assert "other.py" not in transaction.diff
    assert repository._git("rev-parse", "HEAD") == old_head
    result = decide(store, transaction)
    assert result["status"] == "succeeded", result
    assert repository._git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").strip() == "probe.py"
    assert repository._git("ls-files", "--stage", "--", "other.py") == other_index_before
    assert repository._git("diff", "--cached", "--name-only").strip() == "other.py"
    assert repository.root.joinpath("other.py").read_text() == "other = 2\n"
    assert "Co-authored-by: Copilot" in repository._git("log", "-1", "--format=%B")


@pytest.mark.parametrize("approved", [False, True])
def test_commit_previews_untracked_and_large_files_without_touching_real_index(repository, approved):
    root = repository.root
    large = "line of template text\n" * 15000
    (root / "template.html").write_text(large)
    repository._git("add", "--", "template.html")
    repository._git("commit", "-m", "large template baseline")
    (root / "template.html").write_text(large + "<!-- bridge -->\n")
    (root / "new_bridge.py").write_text("# new bridge\nvalue = 1\n")
    (root / "other.py").write_text("other = 2\n")
    repository._git("add", "--", "other.py")
    index_before = repository._git("ls-files", "--stage", "-z")
    other_index = repository._git("ls-files", "--stage", "--", "other.py")
    head_before = repository._git("rev-parse", "HEAD")
    store = ApprovalStore()
    transaction = store.propose(repository, "propose_commit",
                                {"paths": ["template.html", "new_bridge.py"], "message": "Real feature shapes"},
                                "ghost", "session-1", 1)
    assert "new file mode" in transaction.diff
    assert "+# new bridge" in transaction.diff and "+<!-- bridge -->" in transaction.diff
    assert repository._git("ls-files", "--stage", "-z") == index_before
    assert "new_bridge.py" not in repository._tracked()
    result = decide(store, transaction, approved)
    assert result["status"] == ("succeeded" if approved else "denied"), result
    assert repository._git("ls-files", "--stage", "--", "other.py") == other_index
    if approved:
        assert set(repository._git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()) == {
            "template.html", "new_bridge.py"}
        assert repository._git("diff", "--cached", "--name-only").strip() == "other.py"
    else:
        assert repository._git("ls-files", "--stage", "-z") == index_before
        assert repository._git("rev-parse", "HEAD") == head_before
        assert "new_bridge.py" not in repository._tracked()


def test_untracked_commit_drift_and_ignored_files_are_denied(repository):
    (repository.root / "new.py").write_text("before\n")
    store = ApprovalStore()
    transaction = store.propose(repository, "propose_commit",
                                {"paths": ["new.py"], "message": "New source"},
                                "ghost", "session-1", 1)
    (repository.root / "new.py").write_text("operator changed\n")
    assert decide(store, transaction)["status"] == "failed"
    assert "new.py" not in repository._tracked()
    (repository.root / ".gitignore").write_text("ignored.py\n")
    (repository.root / "ignored.py").write_text("private\n")
    with pytest.raises(PermissionError):
        store.propose(repository, "propose_commit", {"paths": ["ignored.py"], "message": "No"},
                      "ghost", "session-1", 1)


def test_write_limit_is_not_expanded_with_inspection_limit(repository):
    (repository.root / "probe.py").write_text("x" * 300_000)
    assert len(repository.call("read_file", {"path": "probe.py"}) ) > 0
    with pytest.raises(ValueError, match="limit"):
        write_proposal(ApprovalStore(), repository)


@pytest.mark.parametrize("drift", ["head", "index"])
def test_commit_head_or_index_drift_fails(repository, drift):
    repository.root.joinpath("probe.py").write_text("value = 2\n")
    store = ApprovalStore()
    transaction = store.propose(repository, "propose_commit",
                                {"paths": ["probe.py"], "message": "Approved probe"},
                                "ghost", "session-1", 1)
    if drift == "head":
        repository._git("commit", "--allow-empty", "-m", "operator advance")
    else:
        repository.root.joinpath("other.py").write_text("other = 2\n")
        repository._git("add", "--", "other.py")
    assert decide(store, transaction)["status"] == "failed"


def test_operator_permission_failure_does_not_execute(repository):
    store = ApprovalStore()
    transaction = write_proposal(store, repository)
    result = store.decide(transaction.id, True, "ghost", "session-1", transaction.csrf, lambda _: False)
    assert result["status"] == "denied"
    assert repository.root.joinpath("probe.py").read_text() == "value = 1\n"


def test_skill_loop_resumes_from_denied_proposal_receipt(repository):
    seen = []
    outputs = iter([
        json.dumps({"tool_calls": [{"name": "propose_write_file",
                                   "arguments": {"path": "probe.py", "content": "value = 2\n"}}], "answer": ""}),
        json.dumps({"tool_calls": [], "answer": "The user denied execution; nothing was changed."}),
    ])
    store = ApprovalStore()

    def handler(repo, name, args):
        transaction = store.propose(repo, name, args, "ghost", "session-1", 1)
        decide(store, transaction, False)
        return store.wait(transaction)

    def model(_, messages):
        seen.append(list(messages))
        return next(outputs), 1

    answer, _, receipts = run_apex_tools(model, [{"role": "user", "content": "Propose a comment"}],
                                         lambda: True, lambda _: None, repository, handler)
    assert "denied" in answer and receipts[0]["status"] == "denied"
    assert "User Denied Execution" in seen[1][-1]["content"]


@pytest.fixture
def approval_route(monkeypatch):
    from frontend.blueprints import chat
    from core import tool_approval
    store = ApprovalStore()
    monkeypatch.setattr(tool_approval, "APPROVALS", store)
    monkeypatch.setattr(chat, "get_current_user", lambda: {"username": "ghost", "role": "owner"})
    monkeypatch.setattr(chat, "can_user_invoke_skill", lambda *_args, **_kw: True)
    app = Flask(__name__)
    app.register_blueprint(chat.chat_bp)
    client = app.test_client()
    client.set_cookie("friday_session", "session-cookie")
    return client, store, chat


def test_route_requires_actual_cookie_owner_and_rejects_agent_headers(approval_route, monkeypatch):
    client, _, chat = approval_route
    assert client.get("/api/tool-approval", headers={"X-Agent-Id": "apex"}).status_code == 401
    monkeypatch.setattr(chat, "get_current_user", lambda: {"username": "user", "role": "user"})
    assert client.get("/api/tool-approval").status_code == 401
    monkeypatch.setattr(chat, "get_current_user", lambda: None)
    assert client.post("/api/tool-approval", json={"user": "ghost", "decision": True}).status_code == 401


def test_route_exact_payload_csrf_and_consumed_uuid(approval_route, repository):
    from core.tool_approval import session_identity
    client, store, _ = approval_route
    transaction = store.propose(repository, "propose_write_file",
                                {"path": "probe.py", "content": "value = 2\n"},
                                "ghost", session_identity("session-cookie"), 1)
    pending = client.get("/api/tool-approval").get_json()["pending"]
    assert pending[0]["transaction_id"] == transaction.id
    headers = {"X-Tool-Approval-CSRF": pending[0]["csrf_token"]}
    data = {"transaction_id": transaction.id, "decision": True}
    assert client.post("/api/tool-approval", json={**data, "decision": "true"}, headers=headers).status_code == 400
    assert client.post("/api/tool-approval", json=data).status_code == 403
    assert client.post("/api/tool-approval", json=data,
                       headers={**headers, "Origin": "https://untrusted.invalid"}).status_code == 403
    response = client.post("/api/tool-approval", json=data, headers=headers)
    assert response.status_code == 200 and response.get_json()["receipt"]["status"] == "succeeded"
    assert client.post("/api/tool-approval", json=data, headers=headers).status_code == 409


def test_private_sse_proposal_not_sent_to_other_sessions():
    from frontend.blueprints import sse
    owner, other = queue.Queue(), queue.Queue()
    with sse._sub_lock:
        sse._subscribers.extend([owner, other])
        sse._approval_audiences[owner] = "owner-session"
        sse._approval_audiences[other] = "other-session"
    try:
        sse.publish("tool_approval_pending", {"diff": "private patch"}, audience="owner-session")
        assert "private patch" in owner.get_nowait()
        assert other.empty()
    finally:
        with sse._sub_lock:
            for item in (owner, other):
                sse._subscribers.remove(item)
                sse._approval_audiences.pop(item, None)


def test_ui_approval_controls_are_explicit_and_diff_is_plain_text():
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend/static/js/core/tool-approval.js").read_text()
    assert "textContent" in source and "innerHTML" not in source
    assert "X-Tool-Approval-CSRF" in source
    assert "approve.addEventListener('click', () => decide(true))" in source
    assert "reject.addEventListener('click', () => decide(false))" in source
    assert "setInterval" not in source


def test_sse_storage_failure_does_not_grant_approval_audience(monkeypatch):
    import sqlite3
    from frontend.blueprints import sse
    from services import auth

    def unavailable():
        raise sqlite3.DatabaseError("malformed")

    monkeypatch.setattr(auth, "get_current_user", unavailable)
    app = Flask(__name__)
    app.register_blueprint(sse.sse_bp)
    with app.test_client() as client:
        response = client.get("/api/events", buffered=False)
        try:
            assert response.status_code == 200
            assert next(response.response) == b": connected\n\n"
            assert not sse._approval_audiences
        finally:
            response.close()


def test_transport_schema_prevents_mixed_proposal_and_read_batches():
    from core.apex_tools import TURN_FORMAT
    read, proposal, final = TURN_FORMAT["json_schema"]["schema"]["oneOf"]
    assert proposal["properties"]["tool_calls"]["maxItems"] == 1
    assert proposal["properties"]["answer"]["const"] == ""
    names = [item["properties"]["name"]["const"]
             for item in read["properties"]["tool_calls"]["items"]["oneOf"]]
    assert "propose_write_file" not in names
    assert final["properties"]["tool_calls"]["maxItems"] == 0
