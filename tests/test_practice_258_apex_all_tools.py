"""Practice 258: APEX's task turns carry every tool he has, except self-acceptance and online model switching."""
from core import apex_tools, hb_task_manager


def test_task_turns_have_everything_but_the_two_kept_back():
    allt = set(apex_tools.TOOL_SCHEMAS) | set(apex_tools.TEST_TOOL_SCHEMAS) | set(apex_tools.WEB_TOOL_SCHEMAS)
    assert allt - set(hb_task_manager.EXECUTION_TOOLS) == {'studio_accept', 'gemini_reload', 'local_review'}   # 264: Fred is JD's
    assert len(hb_task_manager.EXECUTION_TOOLS) + 1 <= 64     # fits the scope cap (64) with change_set appended


def test_the_account_grant_lists_them():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / 'frontend/blueprints/agent_identity.py').read_text()
    assert "Practice 258: all of APEX's tools (not studio_accept)" in src
