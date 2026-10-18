import sys
import types

sys.path[:0] = ['.', 'utils', 'lib/system']


def test_fs_write_strips_pasted_markers_and_line_numbers():
    from fridays.skills import _clean_fs_write_content as clean

    assert clean("    1  # Title\n    2\n    3  Body\n```") == "# Title\n\nBody"
    assert clean("<<<NEW>>>\nHello\n<<<END>>>") == "Hello"
    assert clean("1984 was a year\nplain") == "1984 was a year\nplain"
    assert clean("a\n2  b\nc") == "a\n2  b\nc"


def test_ask_agent_routes_parked_agent_to_fred(monkeypatch):
    from core.pipeline import orchestrator as o

    seen = {}

    def fake_chat(model, messages, temperature=0.5, keep_alive=None, **_):
        seen['model'] = model
        seen['system'] = messages[0]['content']
        return 'ok', 1

    monkeypatch.setattr(o, '_get_agents', lambda: {'seven': 'x', 'fred': 'mistral-small:24b'})
    monkeypatch.setattr(o, '_get_system_prompts', lambda: {'fred': 'FRED', 'llama': 'LLAMA ROLE'})
    monkeypatch.setattr(o, 'log_action', lambda *a, **k: None)
    monkeypatch.setattr(o, 'log_agent_thinking', lambda *a, **k: None)
    monkeypatch.setattr(o, 'batch_commit', lambda *a, **k: None)
    import core.llm as llm
    monkeypatch.setattr(llm, 'chat_via_gateway', fake_chat)

    assert o.ask_agent('LLaMA', 'q') == 'ok'
    assert seen['model'] == 'mistral-small:24b'
    assert 'FRED' in seen['system'] and 'LLAMA ROLE' in seen['system'] and 'retired llama' in seen['system']
