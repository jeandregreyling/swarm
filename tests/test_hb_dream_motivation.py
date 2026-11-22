"""DREAM M = Motivation spark: every HB model starts its thinking with genuine positive problem-solving energy."""
import pytest

from core import apex_tools, hb_master_prompt as mp


@pytest.mark.parametrize('agent', ['apex', 'fred', 'nanny', 'gemini-advisor', 'codex-instructor', 'default'])
def test_all_hb_models_receive_dream_motivation_spark(agent):
    text = mp.for_role(agent)
    assert 'Motivation - spark genuine positive curiosity and problem-solving energy' in text


def test_apex_tool_guidance_prompts_motivation_spark_in_thought():
    guidance = apex_tools.scoped_tool_guidance(['read_file', 'grep_repo'])
    assert 'DREAM Motivation spark' in guidance
