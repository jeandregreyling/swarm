"""Practice 246: bare /continue resumes held work tasks; task envelopes never forbid tools."""
from core import hb_commands
from utils.local_runtime_policy import is_explicitly_no_tools_request


def test_bare_and_all_continue_parse_to_all():
    assert hb_commands.parse('continue') == ('continue', ['ALL'])
    assert hb_commands.parse('continue all') == ('continue', ['ALL'])
    assert hb_commands.parse('continue T-0123456789AB') == ('continue', ['T-0123456789AB'])


def test_run_routes_all_to_continue_all(monkeypatch):
    monkeypatch.setattr(hb_commands, '_continue_all', lambda conn, cid, actor: f'all {cid}')
    assert hb_commands.run(None, 2845, 'continue', ['ALL'], 'JD') == 'all 2845'


def test_a_task_envelope_never_forbids_tools():
    body = '{"task_type": "hb_owner_resumed", "next_task": "a plain question (no task and no tool work) is answered"}'
    assert is_explicitly_no_tools_request(body) is False
    assert is_explicitly_no_tools_request("answer this without using tools, no tools please") is True
