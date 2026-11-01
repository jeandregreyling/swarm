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


def test_read_file_returns_at_most_one_hundred_lines(repository):
    repository.root.joinpath("sample.py").write_text("".join(f"line {i}\n" for i in range(250)))
    result = repository.call("read_file", {"path": "sample.py"})
    assert len(result.splitlines()) == 100
    assert result.endswith("100: line 99")
    with pytest.raises(ValueError, match="maximum 100 lines"):
        repository.call("read_file", {"path": "sample.py", "start": 1, "end": 101})
    page = repository.call("read_file", {"path": "sample.py", "start": 101, "end": 200, "raw": True})
    assert len(page.splitlines()) == 100 and page.startswith("line 100\n")


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


def test_leading_sentence_does_not_bypass_proposal_gate(repository):
    calls = []
    content = ('I have prepared the change for review.\n'
               '{"tool_calls":[{"name":"propose_write_file","arguments":'
               '{"path":"sample.py","content":"hello\\n"}}],"answer":""}')
    outputs = iter([content, '{"tool_calls":[],"answer":"User denied execution."}'])

    def propose(repo, name, args):
        calls.append((name, args))
        assert repo.root.joinpath("sample.py").read_text() == "hello\nworld\n"
        return {"status": "denied", "output": "User Denied Execution"}

    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1), [],
                                   lambda: True, lambda _: None, repository, propose)
    assert calls == [("propose_write_file", {"path": "sample.py", "content": "hello\n"})]
    assert receipts[0]["status"] == "denied"
    assert repository.root.joinpath("sample.py").read_text() == "hello\nworld\n"


@pytest.mark.parametrize("prefix,suffix", [
    ("Here is an example.\n", ""), ("I found the file. ", ""),
    ("I will call the tool:\n", ""), ("I found the file.\n```json\n", "\n```"),
    ("I found the file.\n", "\nTrailing prose"),
    ("I found the file.\n", '\n{"tool_calls":[],"answer":"Other"}'),
])
def test_ambiguous_embedded_payloads_are_not_executed(repository, monkeypatch, prefix, suffix):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Ambiguous payload executed"))
    content = prefix + envelope(("git_status", {})) + suffix
    answer, _, receipts = run_apex_tools(lambda *_: (content, 1), [],
                                       lambda: True, lambda _: None, repository)
    assert answer == content and receipts == []


def test_no_final_channel_gets_one_bounded_retry_without_executing_reasoning(repository):
    messages = []

    def model(_, working):
        messages.append(list(working))
        if len(messages) == 1:
            raise RuntimeError("Direct model produced no final answer; reasoning is not an executable reply")
        return '{"tool_calls":[],"answer":"Blocked on a complete file read."}', 2

    answer, _, receipts = run_apex_tools(model, [], lambda: True, lambda _: None, repository)
    assert len(messages) == 2 and not receipts
    assert "BACKEND FORMAT ERROR" in messages[1][-1]["content"]
    assert answer == "Blocked on a complete file read."


def test_no_final_channel_repeated_failure_stops(repository):
    attempts = []

    def model(*_):
        attempts.append(1)
        raise RuntimeError("Direct model produced no final answer; reasoning is not an executable reply")

    with pytest.raises(RuntimeError, match="no final answer"):
        run_apex_tools(model, [], lambda: True, lambda _: None, repository)
    assert len(attempts) == 2


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


def test_owner_prompt_contains_complete_patch_envelope_only_when_attached():
    from core.apex_tools import PROPOSAL_GUIDANCE
    marker = '{"tool_calls":[{"name":"propose_patch"'
    example = PROPOSAL_GUIDANCE[PROPOSAL_GUIDANCE.index(marker):].split(". This complete", 1)[0]
    payload = json.loads(example)
    assert payload["answer"] == ""
    assert set(payload["tool_calls"][0]["arguments"]) == {"file_path", "exact_old_text", "new_text"}
    assert marker in apex_system_prompt(APEX_AGENT, recovery=False, proposals=True)
    assert marker not in apex_system_prompt(APEX_AGENT, recovery=False, proposals=False)


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
    variants = TURN_FORMAT["json_schema"]["schema"]["oneOf"][0]["properties"]["tool_calls"]["items"]["oneOf"]
    read = next(item for item in variants if item["properties"]["name"]["const"] == "read_file")
    args = read["properties"]["arguments"]
    assert args["properties"]["start"] == {"type": "integer", "minimum": 1}
    assert args["properties"]["end"] == {"type": "integer", "minimum": 1}
    assert args["additionalProperties"] is False


def test_transport_schema_restricts_arguments_to_each_tool():
    read, proposal, _ = TURN_FORMAT["json_schema"]["schema"]["oneOf"]
    variants = (read["properties"]["tool_calls"]["items"]["oneOf"]
                + proposal["properties"]["tool_calls"]["items"]["oneOf"])
    expected = {
        "git_status": ([], []), "list_files": (["path"], []),
        "grep_repo": (["query", "path"], ["query"]),
        "read_file": (["path", "start", "end", "raw"], ["path"]),
        "get_diff": (["path", "offset"], ["path"]),
        "propose_write_file": (["path", "content"], ["path", "content"]),
        "propose_commit": (["paths", "message"], ["paths", "message"]),
        "propose_patch": (["file_path", "exact_old_text", "new_text"],
                          ["file_path", "exact_old_text", "new_text"]),
    }
    assert {item["properties"]["name"]["const"] for item in variants} == set(expected)
    for item in variants:
        name = item["properties"]["name"]["const"]
        arguments = item["properties"]["arguments"]
        keys, required = expected[name]
        assert set(arguments["properties"]) == set(keys)
        assert arguments["required"] == required
        assert arguments["additionalProperties"] is False
        assert item["required"] == ["name", "arguments"]
        assert item["additionalProperties"] is False
        if "path" in keys:
            assert arguments["properties"]["path"] == {"type": "string", "minLength": 1}


def test_invalid_read_arguments_return_actionable_receipt(repository):
    outputs = iter([
        envelope(("grep_repo", {"query": "world", "paths": ["sample.py"]})),
        envelope(("grep_repo", {"query": "world", "path": "sample.py"})),
        "Corrected the arguments and found the text.",
    ])
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1), [],
                                   lambda: True, lambda _: None, repository)
    assert receipts[0]["status"] == "failed"
    assert "unexpected keys ['paths']" in receipts[0]["output"]
    assert "singular path as a string" in receipts[0]["output"]
    assert receipts[1]["status"] == "succeeded"
    assert "sample.py:2: world" in receipts[1]["output"]


def test_raw_read_preserves_blank_lines_and_final_newline(repository):
    text = "value = 1\n\n\n# comment\n"
    repository.root.joinpath("sample.py").write_text(text)
    assert repository.call("read_file", {"path": "sample.py", "raw": True}) == text
    with pytest.raises(ValueError, match="boolean"):
        repository.call("read_file", {"path": "sample.py", "raw": "true"})


def test_inspection_reads_one_mebibyte_files_and_refuses_larger(repository):
    from core.apex_tools import MAX_FILE_BYTES
    assert MAX_FILE_BYTES >= 1024 * 1024
    path = repository.root / "sample.py"
    path.write_text("a" * (MAX_FILE_BYTES - 1) + "\n")
    assert repository.call("read_file", {"path": "sample.py"}).startswith("1: a")
    path.write_text("a" * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="limit"):
        repository.call("read_file", {"path": "sample.py"})


def test_get_diff_is_paginated_and_real_index_stays_unchanged(repository):
    repository._git("config", "user.name", "Test")
    repository._git("config", "user.email", "test@example.invalid")
    repository._git("commit", "-m", "baseline")
    repository.root.joinpath("new.py").write_text("".join(f"line {i}\n" for i in range(600)))
    before = repository._git("ls-files", "--stage", "-z")
    offset, pages = 0, []
    while offset is not None:
        result = json.loads(repository.call("get_diff", {"path": "new.py", "offset": offset}))
        pages.append(result["diff"])
        offset = result["next_offset"]
    assert len(pages) > 1
    assert "new file mode" in "".join(pages)
    assert "+line 599" in "".join(pages)
    assert repository._git("ls-files", "--stage", "-z") == before
    assert "new.py" not in repository._tracked()


@pytest.mark.parametrize("path", [".env", "data.db", "runtime/artifact.txt", "../outside.py"])
def test_get_diff_cannot_read_protected_files(repository, path):
    with pytest.raises(PermissionError):
        repository.call("get_diff", {"path": path})
