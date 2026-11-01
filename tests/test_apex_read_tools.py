import json
from pathlib import Path
import subprocess

import pytest

from core.apex_tools import ReadOnlyRepository, TURN_FORMAT, run_apex_tools
from core.chat_continuity import APEX_AGENT, apex_system_prompt


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    (tmp_path / "sample.py").write_text("hello\nworld\n")
    (tmp_path / ".env").write_text("must not read")
    (tmp_path / "data.db").write_bytes(b"database")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "artifact.txt").write_text("private runtime data")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore", "sample.py", ".env", "data.db"], check=True)
    return ReadOnlyRepository(tmp_path)


def envelope(*calls):
    return json.dumps({"tool_calls": [{"name": name, "arguments": args} for name, args in calls]})


def test_actual_status_listing_read_and_literal_grep(repository):
    before = (repository.root / ".gitignore").read_bytes()
    assert "?? runtime/" in repository.call("git_status", {})
    assert ".gitignore" in repository.call("list_files", {})
    assert "runtime/artifact.txt" in repository.call("list_files", {"path": "runtime"})
    assert repository.call("read_file", {"path": ".gitignore"}) == "1: *.pyc"
    assert "sample.py:2: world" in repository.call("grep_repo", {"query": "world"})
    assert "files searched" in repository.call("grep_repo", {"query": ".*", "path": "sample.py"})
    assert (repository.root / ".gitignore").read_bytes() == before


@pytest.mark.parametrize("path", [
    "../outside.txt", "/etc/passwd", ".env", "data.db", "runtime/artifact.txt",
    ".git/config", "untracked.txt", "sandpits/apex/memory.json",
])
def test_protected_and_outside_paths_are_denied(repository, path):
    with pytest.raises((PermissionError, ValueError)):
        repository.call("read_file", {"path": path})


def test_symlinks_including_sibling_prefix_escape_are_denied(repository, tmp_path):
    sibling = tmp_path.parent / (tmp_path.name + "-other")
    sibling.mkdir()
    (sibling / "private.py").write_text("private")
    (tmp_path / "link.py").symlink_to(sibling / "private.py")
    (tmp_path / "inside.py").symlink_to(tmp_path / "sample.py")
    subprocess.run(["git", "-C", str(tmp_path), "add", "link.py", "inside.py"], check=True)
    for path in ("link.py", "inside.py", "../" + sibling.name + "/private.py"):
        with pytest.raises(PermissionError):
            repository.call("read_file", {"path": path})


@pytest.mark.parametrize("args", [
    {"path": "sample.py", "start": True}, {"path": "sample.py", "start": 0},
    {"path": "sample.py", "end": 201}, {"path": "sample.py", "extra": "ignored"},
])
def test_argument_ranges_are_strict(repository, args):
    with pytest.raises(ValueError):
        repository.call("read_file", args)


def test_multiround_receipts_come_from_backend_and_return_to_model(repository):
    outputs = iter([
        envelope(("git_status", {})),
        envelope(("read_file", {"path": ".gitignore"})),
        "I found runtime artifacts and read the ignore rules.",
    ])
    seen, emitted = [], []

    def model(name, messages):
        assert name == APEX_AGENT["model"]
        seen.append(list(messages))
        return next(outputs), 3

    answer, tokens, receipts = run_apex_tools(
        model, [{"role": "user", "content": "Inspect untracked files and ignore rules"}],
        lambda: True, emitted.append, repository)
    assert tokens == 9 and "runtime artifacts" in answer
    assert emitted == receipts
    assert [receipt["status"] for receipt in receipts] == ["succeeded", "succeeded"]
    assert "?? runtime/" in receipts[0]["output"]
    assert "1: *.pyc" in receipts[1]["output"]
    assert receipts[0]["id"] != receipts[1]["id"]
    assert receipts[0]["id"] in seen[1][-1]["content"]


@pytest.mark.parametrize("name", ["write_file", "shell", "web_search", "fs_write"])
def test_unattached_tools_never_reach_executor(repository, name, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Denied tool executed"))
    outputs = iter([envelope((name, {})), "The tool was denied."])
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1),
                                   [{"role": "user", "content": "Inspect"}],
                                   lambda: True, lambda _: None, repository)
    assert receipts[0]["status"] == "denied"


@pytest.mark.parametrize("content", [
    'An example: {"tool_calls":[{"name":"git_status","arguments":{}}]}',
    '```json\n{"tool_calls":[{"name":"git_status","arguments":{}}]}\n```',
    'SKILL shell touch /tmp/nope',
])
def test_quoted_prose_fences_and_skill_lines_are_not_executable(repository, content, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Prose executed"))
    answer, _, receipts = run_apex_tools(lambda *_: (content, 1),
                                        [{"role": "user", "content": "Explain the format"}],
                                        lambda: True, lambda _: None, repository)
    assert answer == content and receipts == []


@pytest.mark.parametrize("content", [
    '{"tool_calls":', '{"tool_calls":[]}', '{"tool_calls":[{}]}',
    '{"tool_calls":[{"name":"git_status","arguments":{}}],"other":1}',
])
def test_malformed_calls_fail_explicitly(repository, content):
    with pytest.raises(RuntimeError):
        run_apex_tools(lambda *_: (content, 1), [], lambda: True, lambda _: None, repository)


def test_operator_denial_and_no_tools_request_fail_closed(repository, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Denied inspection ran"))
    for authorize, request in ((lambda: False, "Inspect"), (lambda: True, "Do not use tools")):
        outputs = iter([envelope(("git_status", {})), "Denied."])
        _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1),
                                       [{"role": "user", "content": request}],
                                       authorize, lambda _: None, repository)
        assert receipts[0]["status"] == "denied"


def test_authorization_failure_does_not_read(repository, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Authorization failed open"))

    def unavailable():
        raise RuntimeError("authorization unavailable")

    with pytest.raises(RuntimeError, match="authorization unavailable"):
        run_apex_tools(lambda *_: (envelope(("git_status", {})), 1), [],
                       unavailable, lambda _: None, repository)


def test_failures_are_explicit(repository):
    outputs = iter([envelope(("read_file", {"path": "sample.py", "start": 0})), "Read failed."])
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1), [],
                                   lambda: True, lambda _: None, repository)
    assert receipts[0]["status"] == "failed"
    assert "Invalid line range" in receipts[0]["output"]


def test_output_truncation_is_explicit(repository, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: "x" * 9000)
    outputs = iter([envelope(("git_status", {})), "Result was truncated."])
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1), [],
                                   lambda: True, lambda _: None, repository)
    assert len(receipts[0]["output"]) == 8000
    assert receipts[0]["truncated"] is True


def test_constrained_final_answer_is_unwrapped(repository):
    content = json.dumps({"tool_calls": [], "answer": "Hello from APEX."})
    answer, _, receipts = run_apex_tools(lambda *_: (content, 1), [],
                                       lambda: True, lambda _: None, repository)
    assert answer == "Hello from APEX." and not receipts


@pytest.mark.parametrize("payload", [
    {"tool_calls": [], "answer": ""},
    {"tool_calls": [], "answer": 7},
    {"tool_calls": [{"name": "git_status", "arguments": {}}], "answer": "Also execute"},
])
def test_constrained_turn_shape_is_validated(repository, payload):
    with pytest.raises(RuntimeError):
        run_apex_tools(lambda *_: (json.dumps(payload), 1), [],
                       lambda: True, lambda _: None, repository)


def test_repeated_calls_are_bounded(repository):
    receipts = []
    with pytest.raises(RuntimeError, match="round limit"):
        run_apex_tools(lambda *_: (envelope(("git_status", {})), 1), [],
                       lambda: True, receipts.append, repository)
    assert len(receipts) == 6


def test_prompt_attaches_only_read_tools_and_recovery_has_none():
    prompt = apex_system_prompt(APEX_AGENT, recovery=False)
    assert "No tools are attached." not in prompt
    assert "READ-ONLY REPOSITORY BRIDGE" in prompt
    recovery = apex_system_prompt(APEX_AGENT, recovery=True)
    assert "No tools are attached in recovery" in recovery
    assert "READ-ONLY REPOSITORY BRIDGE" not in recovery


@pytest.mark.parametrize("path", [".env", "data.db", "runtime/artifact.txt"])
def test_grep_cannot_turn_protected_file_refusals_into_empty_success(repository, path):
    with pytest.raises(PermissionError):
        repository.call("grep_repo", {"query": "private", "path": path})


def test_both_chat_surfaces_render_backend_receipts():
    root = Path(__file__).resolve().parents[1]
    for name in ("chat.js", "home-chat.js"):
        source = (root / "frontend/static/js/views" / name).read_text()
        assert "Array.isArray(data.tool_receipts)" in source
        assert "receipt.status" in source and "receipt.id" in source


def test_call_limit_rejects_batch_before_any_read(repository, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Excessive batch executed"))
    content = envelope(*[("git_status", {})] * 13)
    with pytest.raises(RuntimeError, match="excessive"):
        run_apex_tools(lambda *_: (content, 1), [], lambda: True, lambda _: None, repository)


def test_transport_schema_requires_integer_line_arguments():
    args = TURN_FORMAT["json_schema"]["schema"]["properties"]["tool_calls"]["items"]["properties"]["arguments"]
    assert args["properties"]["start"] == {"type": "integer", "minimum": 1}
    assert args["properties"]["end"] == {"type": "integer", "minimum": 1}
    assert args["additionalProperties"] is False
