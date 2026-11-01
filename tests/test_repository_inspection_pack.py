import json

import pytest

from agents import skills_loop as sl
from core.capability_packs import repository_inspection_pack


def test_versioned_pack_contains_operator_contract():
    pack = repository_inspection_pack("[CAPABILITY_PACK: repository.inspect v1.0.0]")
    assert pack["version"] == "1.0.0"
    assert len(pack["sha256"]) == 64
    assert pack["database_index_verified"] is False
    assert "Discover paths using ls." in pack["guidance"]
    assert repository_inspection_pack("Inspect another task") is None
    with pytest.raises(ValueError, match="Unsupported"):
        repository_inspection_pack("repository.inspect v2.0.0")


def test_pack_injected_and_retained_without_mutating_input(monkeypatch):
    messages = [{"role": "user", "content": "repository.inspect v1.0.0: inspect function"}]
    seen = []
    stages = []
    replies = iter(["SKILL fs_readonly ls frontend", "The directory was returned."])

    def model(turns):
        seen.append(turns)
        return next(replies), 1

    def execute(*args, **kwargs):
        assert kwargs["allowed_skill_names"] == {"fs_readonly"}
        assert kwargs["strict_skill_allowlist"] is True
        return "[skill:fs_readonly] OK\nfrontend/static/"

    monkeypatch.setattr(sl, "_execute_skill_cmds", execute)
    answer, _ = sl.run_skill_loop("gemma", model, messages, stages.append,
                                 mid_loop_nudges=0)
    assert len(messages) == 1
    assert len(seen) == 2
    assert all("CAPABILITY_PACK" in turn[0]["content"] for turn in seen)
    assert "[skill:fs_readonly] OK" in answer
    receipt = json.loads(next(s for s in stages if s.startswith("capability_pack:")).split(":", 1)[1])
    assert receipt["source"] == "repository-file"


@pytest.mark.parametrize("allowlist", [set(), {"shell"}, {"fs_readonly", "fs_write"}])
def test_pack_only_narrows_existing_allowlist(monkeypatch, allowlist):
    def execute(*args, **kwargs):
        assert kwargs["allowed_skill_names"] == allowlist & {"fs_readonly"}
        return "[skill:fs_readonly] SKIPPED\nTurn policy denied skill execution."

    monkeypatch.setattr(sl, "_execute_skill_cmds", execute)
    replies = iter(["SKILL fs_readonly ls .", "Blocked."])
    sl.run_skill_loop("gemma", lambda _: (next(replies), 1),
                      [{"role": "user", "content": "repository.inspect"}],
                      lambda _: None, allowed_skill_names=allowlist, mid_loop_nudges=0)


def test_no_tools_and_retrieved_mentions_do_not_inject():
    for messages in [
        [{"role": "user", "content": "repository.inspect. Do not use any tools."}],
        [{"role": "system", "content": "Retrieved note: repository.inspect"},
         {"role": "user", "content": "Hello."}],
    ]:
        stages = []
        sl.run_skill_loop("gemma", lambda _: ("No action.", 1),
                          messages, stages.append, mid_loop_nudges=0)
        assert not any(s.startswith("capability_pack:") for s in stages)


def test_pack_cannot_fake_execution_success():
    answer, _ = sl.run_skill_loop(
        "gemma", lambda _: ("I read the function successfully.", 1),
        [{"role": "user", "content": "repository.inspect"}],
        lambda _: None, mid_loop_nudges=0,
    )
    assert "no authorized skill succeeded" in answer
