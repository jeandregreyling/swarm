"""Owner 14 Nov: "it's saying 'it's going to....' but not really doing anything". APEX wrote its tool calls into its text
(after a sentence with a colon, two envelopes in a row, or {"name", "arguments"} inside the answer); HB treated that as prose.
These are APEX's real replies from DOES rename 3 (main chat messages 13273 and 13285)."""
from core.apex_tools import _turn_payload

REPLY_13273 = ('scripts/ is clean: run the step test now.\n{"tool_calls": [{"name": "does_rename", "arguments": {"action": "apply", '
               '"path": "utils/handoff_contract.py"}}], "answer": ""}\n{"tool_calls": [{"name": "run_tests", "arguments": {"tests": '
               '["tests/test_does_rename.py"]}}], "answer": ""}\n[Backend step check: ALM step S-E1FB1DFE3C was never read]')
REPLY_13285 = ('All does_rename calls have succeeded. Next, running tests with the specified files.\n\nTool call for tests:\n'
               '{"name": "run_tests", "arguments": {"tests": ["tests/test_does_rename.py"]}}\n[Backend step check: ...]')


def test_calls_written_into_the_text_are_run():
    assert [c['name'] for c in _turn_payload(REPLY_13273)['tool_calls']] == ['does_rename', 'run_tests']
    assert _turn_payload(REPLY_13285) == {'tool_calls': [{'name': 'run_tests', 'arguments': {'tests': ['tests/test_does_rename.py']}}],
                                          'answer': ''}


def test_a_call_inside_the_answer_is_run_but_examples_and_unknown_names_are_not():
    inside = '{"tool_calls":[],"answer":"Running it now: {\\"name\\": \\"git_status\\", \\"arguments\\": {}}"}'
    assert _turn_payload(inside)['tool_calls'] == [{'name': 'git_status', 'arguments': {}}]
    example = '{"tool_calls":[],"answer":"For example {\\"name\\": \\"git_status\\", \\"arguments\\": {}}"}'
    assert _turn_payload(example)['tool_calls'] == []
    unknown = '{"tool_calls":[],"answer":"I will {\\"name\\": \\"rm_rf\\", \\"arguments\\": {}}"}'
    assert _turn_payload(unknown)['tool_calls'] == []
    assert _turn_payload('All done, the test passed.') is None
