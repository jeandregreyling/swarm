import json
import re

from core import apex_tools


GUIDANCE = {name: value for name, value in vars(apex_tools).items()
            if name.endswith("_GUIDANCE") and isinstance(value, str)}


def _allowed_arguments(tool):
    allowed = set(apex_tools._REQUIRED_ARGUMENTS.get(tool, []))
    for schemas in (apex_tools.TOOL_SCHEMAS, apex_tools.WEB_TOOL_SCHEMAS,
                    apex_tools.TEST_TOOL_SCHEMAS):
        allowed.update(schemas.get(tool) or {})
    if tool == "studio_handoff":
        allowed.update(apex_tools.STUDIO_HANDOFF_SCHEMA)
    return allowed


def _examples():
    decoder = json.JSONDecoder()
    tools = "|".join(sorted(apex_tools._REQUIRED_ARGUMENTS, key=len, reverse=True))
    pattern = re.compile(rf"\b({tools})(?: arguments:)? (?=\{{)")
    for name, text in GUIDANCE.items():
        for match in pattern.finditer(text):
            try:
                arguments, _ = decoder.raw_decode(text, match.end())
            except json.JSONDecodeError:
                continue
            yield name, match.group(1), arguments


def test_guidance_contains_json_tool_examples():
    assert any(tool == "grep_repo" for _, tool, _ in _examples())


def test_every_guidance_tool_example_uses_real_argument_names():
    for name, tool, arguments in _examples():
        missing = set(apex_tools._REQUIRED_ARGUMENTS[tool]) - set(arguments)
        unknown = set(arguments) - _allowed_arguments(tool)
        assert not missing, f"{name}: {tool} example lacks {sorted(missing)}"
        assert not unknown, f"{name}: {tool} example uses unknown {sorted(unknown)}"


def _inventory(prompt):
    marker = "ATTACHED TOOLS THIS TURN (complete list): "
    return prompt.rsplit(marker, 1)[1].split(". ", 1)[0].split(", ")


def test_attached_tool_inventory_matches_the_turn_mode():
    from core.chat_continuity import APEX_AGENT, apex_system_prompt
    full = _inventory(apex_system_prompt(APEX_AGENT, recovery=False, proposals=True, web=True))
    assert set(full) <= set(apex_tools._REQUIRED_ARGUMENTS)
    assert {"run_tests", "alm_step_get", "propose_patch", "web_search", "grep_repo"} <= set(full)
    read_only = _inventory(apex_system_prompt(APEX_AGENT, recovery=False))
    assert read_only == ["git_status", "list_files", "read_file", "grep_repo", "get_diff"]
    assert "ATTACHED TOOLS" not in apex_system_prompt(APEX_AGENT, recovery=True)
