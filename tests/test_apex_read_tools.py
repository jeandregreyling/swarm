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
    assert "complete: 1 readable source text files searched" in repository.call("grep_repo", {"query": ".*", "path": "sample.py"})
    assert (repository.root / ".gitignore").read_bytes() == before


def test_grep_reports_incomplete_coverage_and_where_it_stopped(repository, monkeypatch):
    import core.apex_tools as apex_tools
    monkeypatch.setattr(apex_tools, "MAX_GREP_FILES", 1)
    output = repository.call("grep_repo", {"query": "zzz-not-present"})
    assert "INCOMPLETE: searched 1 of 5 source candidates" in output
    assert "stopped before data.db" in output and "NOT searched" in output
    assert "narrower path" in output


@pytest.mark.parametrize("path", [
    "../outside.txt", "/etc/passwd", ".env", "data.db", "runtime/artifact.txt",
    ".git/config", "sandpits/apex/memory.json",
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


@pytest.mark.parametrize("name", ["studio_resume", "alm_step_get", "studio_evidence_get"])
def test_missing_studio_handler_has_an_actionable_denial(repository, name, monkeypatch):
    monkeypatch.setattr(repository, "call", lambda *_: pytest.fail("Denied tool executed"))
    outputs = iter([envelope((name, {})), "Studio is unavailable in this session."])
    _, _, receipts = run_apex_tools(
        lambda *_: (next(outputs), 1), [{"role": "user", "content": "Check Studio"}],
        lambda: True, lambda _: None, repository)
    assert receipts[0]["status"] == "denied"
    assert "authenticated owner" in receipts[0]["output"]
    assert "Studio handler" in receipts[0]["output"]
    assert "Read-only repository inspection" not in receipts[0]["output"]


def test_attached_web_tool_uses_separate_handler_and_returns_receipt(repository):
    calls, seen = [], []
    outputs = iter([
        envelope(("web_search", {"query": "Python documentation", "provider": "serper"})),
        '{"tool_calls":[],"answer":"Verified https://docs.python.org/"}',
    ])

    def model(_name, messages):
        seen.append(list(messages))
        return next(outputs), 1

    def web(args):
        calls.append(args)
        return {"sources": ["https://docs.python.org/"], "provider": "serper"}

    answer, _, receipts = run_apex_tools(model, [], lambda: False, lambda _: None,
                                        repository, web_handler=web)
    assert calls == [{"query": "Python documentation", "provider": "serper"}]
    assert receipts[0]["status"] == "succeeded"
    assert receipts[0]["id"] in seen[1][-1]["content"]
    assert "docs.python.org" in answer


@pytest.mark.parametrize("mode", ["no_tools", "denied", "failed", "invalid"])
def test_web_tool_respects_boundaries_and_reports_failures(repository, mode):
    args = {"query": "Python documentation", "provider": "serper"}
    if mode == "invalid":
        args["url"] = "https://example.com"
    outputs = iter([envelope(("web_search", args)), '{"tool_calls":[],"answer":"Stopped."}'])
    calls = []

    def web(arguments):
        calls.append(arguments)
        if mode == "denied":
            raise PermissionError("web_search denied")
        if mode == "failed":
            raise ValueError("provider unavailable")
        pytest.fail("Forbidden web call dispatched")

    messages = [{"role": "user", "content": "Do not use tools. Explain only."}] if mode == "no_tools" else []
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1), messages,
                                   lambda: True, lambda _: None, repository, web_handler=web)
    assert receipts[0]["status"] == ("denied" if mode in {"no_tools", "denied"} else "failed")
    assert len(calls) == (1 if mode in {"denied", "failed"} else 0)


def test_web_guidance_is_only_attached_when_requested():
    healthy = apex_system_prompt(APEX_AGENT, recovery=False, web=True)
    assert "WEB SEARCH BRIDGE (authenticated" in healthy
    assert "serper" in healthy and "tavily" in healthy
    assert "WEB SEARCH BRIDGE (authenticated" not in apex_system_prompt(APEX_AGENT, recovery=False)
    assert "WEB SEARCH BRIDGE" not in apex_system_prompt(APEX_AGENT, recovery=True, web=True)


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


@pytest.mark.parametrize("reason", ["User Denied Execution", "Approval expired; no execution occurred"])
def test_proposal_denial_ends_turn_without_retry_or_capacity_handoff(repository, reason):
    model_calls = []
    emitted = []

    def model(*args):
        model_calls.append(args)
        assert len(model_calls) == 1, "A denied proposal must not trigger another inference"
        return envelope(("propose_write_file", {"path": "sample.py", "content": "replacement"})), 7

    def propose(*_):
        return {"status": "denied", "output": reason, "transaction_id": "denied-transaction"}

    answer, tokens, receipts = run_apex_tools(
        model, [], lambda: True, emitted.append, repository, propose,
        prepare_receipts=lambda *_: pytest.fail("Denied proposal needs no further prompt"),
        studio_handler=lambda *_: pytest.fail("Denial is not capacity exhaustion"),
    )
    assert len(model_calls) == 1
    assert tokens == 7 and receipts == emitted
    assert receipts[0]["status"] == "denied"
    assert reason in answer and "new operator instruction" in answer
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
    assert "BOUNDED REPOSITORY BRIDGE" in prompt
    recovery = apex_system_prompt(APEX_AGENT, recovery=True)
    assert "No tools are attached in recovery" in recovery
    assert "BOUNDED REPOSITORY BRIDGE" not in recovery


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
    read, proposal, studio, _ = TURN_FORMAT["json_schema"]["schema"]["oneOf"]
    variants = (read["properties"]["tool_calls"]["items"]["oneOf"]
                + proposal["properties"]["tool_calls"]["items"]["oneOf"]
                + studio["properties"]["tool_calls"]["items"]["oneOf"])
    expected = {
        "local_review":(["question","evidence"],["question"]),
        "local_job_status":(["job_id"],["job_id"]),
        "archive_acquire":([],[]),
        "studio_accept":(["evidence_message_ids"],["evidence_message_ids"]),
        "gemini_status":([],[]),"gemini_reload":(["provider_model"],[]),
        "task_context":([],[]),"task_memory":([],[]),
        "task_evidence":(["evidence_id","offset"],["evidence_id"]),
        "studio_note":(["content"],["content"]),
        "studio_status":(["status"],["status"]),
        "studio_task":(["title","content"],["title","content"]),
        "reference_lookup":(["query","allow_online"],["query"]),
        "reference_import":(["kind","repo","revision","path"],["kind","repo","revision","path"]),
        "terminal_run": (["command"], ["command"]),
        "memory_search": (["query"], []), "memory_save": (["subject","content"], ["subject","content"]),
        "backlog_list": (["offset","query"], []), "runtime_status": ([], []),
        "archive_status": (["view", "offset"], []), "archive_ingest": ([], []),
        "archive_mirror_pause": ([], []), "archive_mirror_resume": ([], []),
        "archive_mirror_curate": (["repo"], []),
        "workflow_status": ([], []), "workflow_control": (["action", "target"], ["action", "target"]),
        "apex_dispatch": (["objective", "constraints", "acceptance_checks"], ["objective", "acceptance_checks"]),
        "knowledge_search": (["query"], ["query"]),
        "knowledge_read": (["document_id", "offset"], ["document_id"]),
        "ask_instructor": (["peer", "question", "context"], ["peer", "question", "context"]),
        "git_status": ([], []), "list_files": (["path"], []),
        "grep_repo": (["query", "path"], ["query"]),
        "read_file": (["path", "start", "end", "raw"], ["path"]),
        "get_diff": (["path", "offset"], ["path"]),
        "studio_resume": (["offset"], []),
        "studio_evidence_get": (["evidence_id"], ["evidence_id"]),
        "alm_step_get": (["step_id"], ["step_id"]),
        "web_search": (["query", "provider"], ["query", "provider"]),
        "run_tests": (["tests", "keyword", "case_id"], ["tests"]),
        "studio_handoff": (["title", "summary", "tasks"], ["title", "summary", "tasks"]),
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


def test_peer_dispatch_guidance_only_in_operator_prompt():
    assert "PEER DISPATCH" in apex_system_prompt(APEX_AGENT, recovery=False, proposals=True)
    assert "PEER DISPATCH" not in apex_system_prompt(APEX_AGENT, recovery=False, proposals=False)


def test_duplicate_successful_read_runs_backend_once_and_requests_final(repository, monkeypatch):
    calls = []
    original = repository.call
    def read(name, args):
        calls.append((name, args))
        return original(name, args)
    monkeypatch.setattr(repository, 'call', read)
    outputs = iter([envelope(('read_file', {'path': '.gitignore'})),
                    envelope(('read_file', {'path': '.gitignore'})),
                    json.dumps({'tool_calls': [], 'answer': 'The ignore rules were read once.'})])
    answer, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1),
        [{'role': 'user', 'content': 'Read the ignore rules.'}], lambda: True, lambda _: None,
        repository=repository)
    assert len(calls) == len(receipts) == 1
    assert 'once' in answer


def test_instructor_question_uses_owner_handler_and_real_queue_receipt(repository):
    calls = []
    args = {'peer': 'codex', 'question': 'Which guard should be tested?', 'context': 'One repeated read receipt.'}
    outputs = iter([envelope(('ask_instructor', args)),
                    json.dumps({'tool_calls': [], 'answer': 'The question is queued; no instructor answer yet.'})])
    def handler(name, arguments):
        calls.append((name, arguments))
        return {'status': 'queued', 'recipient': 'codex-instructor', 'request_ids': [1]}
    _, _, receipts = run_apex_tools(lambda *_: (next(outputs), 1),
        [{'role': 'user', 'content': 'Ask Codex to review the local loop.'}], lambda: True,
        lambda _: None, repository=repository, studio_handler=handler)
    assert calls == [('ask_instructor', args)]
    assert receipts[0]['status'] == 'succeeded'
    assert json.loads(receipts[0]['output'])['status'] == 'queued'


@pytest.mark.parametrize('tool,args', [('knowledge_search', {'query':'DEOS'}), ('knowledge_read', {'document_id':158})])
def test_knowledge_tools_use_kc_handler_and_never_repository_grep(repository, monkeypatch, tool, args):
    monkeypatch.setattr(repository, 'call', lambda *_: pytest.fail('Knowledge Centre call reached repository backend'))
    called=[]
    def handler(name, arguments):
        called.append((name,arguments))
        return {'status':'found','source':'project_docs','document_id':158}
    outputs=iter([envelope((tool,args)),json.dumps({'tool_calls':[],'answer':'The stored source was found.'})])
    _,_,receipts=run_apex_tools(lambda *_:(next(outputs),1),[{'role':'user','content':'Read Knowledge Centre evidence'}],lambda:True,lambda _:None,repository=repository,studio_handler=handler)
    assert called==[(tool,args)]
    assert json.loads(receipts[0]['output'])['source']=='project_docs'
    with pytest.raises(PermissionError):
        ReadOnlyRepository(repository.root).call(tool,args)


def test_duplicate_read_correction_allows_a_different_necessary_action(repository):
    outputs=iter([envelope(('read_file',{'path':'.gitignore'})),envelope(('read_file',{'path':'.gitignore'})),envelope(('grep_repo',{'query':'hello','path':'sample.py'})),json.dumps({'tool_calls':[],'answer':'I read the ignore rules and searched the relevant source.'})])
    _,_,receipts=run_apex_tools(lambda *_:(next(outputs),1),[{'role':'user','content':'Inspect the source'}],lambda:True,lambda _:None,repository=repository)
    assert [r['tool'] for r in receipts]==['read_file','grep_repo']


def test_file_inventory_request_cannot_end_with_aggregate_counts_only(repository):
    seen=[];calls=[]
    replies=iter([json.dumps({'tool_calls':[],'answer':'There are 10 indexed files and 35 blocked files.'}),
                  envelope(('archive_status',{'view':'files','offset':0})),
                  json.dumps({'tool_calls':[],'answer':'data.parquet is indexed at revision abc. Inspect the blocked mirror entries next; keep downloads paused.'})])
    def model(_name,messages):
        seen.append(messages[-1]['content']);return next(replies),1
    def handler(name,args):
        calls.append((name,args));return {'items':[{'filename':'data.parquet','revision':'abc','text_index':{'state':'indexed'}}], 'next_offset':None}
    text,_,receipts=run_apex_tools(model,[{'role':'user','content':'Identify the files downloaded and indexed, and report what remains.'}],
                                  lambda:True,lambda _:None,repository,studio_handler=handler)
    assert seen[1].startswith('BACKEND INVENTORY CHECK')
    assert calls==[('archive_status',{'view':'files','offset':0})]
    assert 'data.parquet' in text and len(receipts)==1


def test_missing_workspace_file_has_no_permission_implication(repository):
    with pytest.raises(FileNotFoundError,match='resolve the actual import'):
        repository.call('read_file',{'path':'untracked.txt'})


@pytest.mark.parametrize('state',['queued','completed'])
def test_scoped_acquisition_receipt_does_not_require_an_unattached_inventory_tool(repository,state):
    calls=[]
    outputs=iter([envelope(('archive_acquire',{})),json.dumps({'tool_calls':[],'answer':'The scoped HF job receipt was returned; report its actual state.'})])
    def handler(name,args):
        calls.append(name)
        assert name=='archive_acquire'
        return {'job_id':'J-123','status':state,'result':{'status':'verified_and_indexed'} if state=='completed' else None}
    answer,_,receipts=run_apex_tools(lambda *_:(next(outputs),1),[{'role':'user','content':'Start the approved files downloading and indexing; report the actual job receipt.'}],lambda:True,lambda _:None,repository,studio_handler=handler)
    assert calls==['archive_acquire'] and len(receipts)==1
    assert 'Backend inventory check' not in answer


def test_old_permission_claim_after_successful_read_is_corrected_with_current_evidence(repository):
    outputs=iter([envelope(('read_file',{'path':'sample.py'})),json.dumps({'tool_calls':[],'answer':'The task is blocked by inability to read scripts/config.py; ask someone else.'}),json.dumps({'tool_calls':[],'answer':'The current source read succeeded; I think the import path is wrong and the next local check is grep_repo.'})])
    answer,_,receipts=run_apex_tools(lambda *_:(next(outputs),1),[{'role':'user','content':'Complete the repair locally'}],lambda:True,lambda _:None,repository)
    assert 'current source read succeeded' in answer and 'blocked' not in answer
    assert receipts[0]['status']=='succeeded'


def test_focused_guidance_fits_local_window_and_does_not_list_unattached_tools():
    from core.apex_tools import scoped_tool_guidance
    text=scoped_tool_guidance(['read_file','propose_patch'])
    assert len(text)<4000 and 'testable hypothesis' in text
    assert '"read_file"' in text and '"propose_patch"' in text and '"ask_instructor"' not in text


@pytest.mark.parametrize('answer',[
    'I think the earlier inability to read scripts/config.py came from a guessed path. Current source search succeeds.',
    'The task is not blocked by the missing guessed file. I will inspect the actual import.',
    'That does not mean I cannot read the repository. Current grep succeeds.',
])
def test_local_diagnosis_can_explain_old_blockers_without_being_rejected(answer):
    from core.apex_tools import permission_excuse
    assert permission_excuse(answer) is False
