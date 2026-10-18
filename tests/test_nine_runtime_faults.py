from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_nine_classifies_groq_403_as_runtime_fault():
    from agents.nine.nine_agent import _classify_groq_error

    msg, runtime_fault = _classify_groq_error(
        Exception("Error code: 403 - {'error': {'message': 'Access denied. Please check your network settings.'}}")
    )

    assert runtime_fault is True
    assert 'Groq access denied' in msg


def test_chat_disable_logic_treats_groq_403_as_runtime_fault():
    import importlib
    from frontend.terminal import create_app

    app = create_app()
    assert app is not None
    chat_mod = importlib.import_module('blueprints.chat')

    text = '[Nine] Groq access denied. Check network egress, proxy, firewall, or account policy.'
    assert chat_mod._chat_error_should_disable_agent(text) is True


def test_chat_disable_logic_ignores_auth_words_in_successful_skill_output():
    import importlib
    from frontend.terminal import create_app

    app = create_app()
    assert app is not None
    chat_mod = importlib.import_module('blueprints.chat')

    text = (
        '[skill:fs_readonly] OK\n'
        '[utils/governance.py lines 80–100]\n'
        'Ask Ghost One for approval before changing authentication settings.'
    )
    assert chat_mod._chat_error_should_disable_agent(text) is False


def test_chat_disable_logic_recognizes_structured_local_runtime_errors():
    import importlib
    from frontend.terminal import create_app

    app = create_app()
    assert app is not None
    chat_mod = importlib.import_module('blueprints.chat')

    assert chat_mod._chat_error_should_disable_agent(
        '[local runtime error: 401 Unauthorized]'
    ) is True
