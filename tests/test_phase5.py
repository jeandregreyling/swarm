"""Phase-5 refinements — regression tests.

Covers:
- Seven's default model switched to phi3:mini.
- Coding Bible prepended to every coder-capable *_SYSTEM_PROMPT in utils.config.
"""
import sys
import os
sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')


def test_seven_default_model_is_phi3_mini(monkeypatch):
    """Seven's paperclip brain is phi3:mini by default (Phase-5 swap)."""
    monkeypatch.delenv('SEVEN_MODEL', raising=False)
    for mod in list(sys.modules):
        if mod.startswith('agents.seven'):
            del sys.modules[mod]
    from agents.seven import seven_agent  # type: ignore
    assert seven_agent.SEVEN_MODEL == 'phi3:mini'


def test_seven_model_env_override(monkeypatch):
    """SEVEN_MODEL env still wins."""
    monkeypatch.setenv('SEVEN_MODEL', 'llama3.2:latest')
    for mod in list(sys.modules):
        if mod.startswith('agents.seven'):
            del sys.modules[mod]
    from agents.seven import seven_agent  # type: ignore
    assert seven_agent.SEVEN_MODEL == 'llama3.2:latest'


def test_coding_bible_is_injected_into_all_coder_prompts():
    """All coder-capable system prompts must start with the Coding Bible quick card."""
    from utils import config as cfg
    names = (
        'GEMMA_SYSTEM_PROMPT', 'LLAMA_SYSTEM_PROMPT', 'QWEN_SYSTEM_PROMPT',
        'MISTRAL_SYSTEM_PROMPT', 'TWENTY_SYSTEM_PROMPT', 'EIGHT_SYSTEM_PROMPT',
        'ELEVEN_SYSTEM_PROMPT', 'NINE_SYSTEM_PROMPT', 'TEN_SYSTEM_PROMPT',
        'TWELVE_SYSTEM_PROMPT', 'THIRTEEN_SYSTEM_PROMPT', 'NINETEEN_SYSTEM_PROMPT',
        'SCHOLAR_SYSTEM_PROMPT', 'SEEKER_SYSTEM_PROMPT', 'GHOST_CODER_SYSTEM_PROMPT',
    )
    missing = []
    for name in names:
        val = getattr(cfg, name, None)
        if not isinstance(val, str) or 'CODING BIBLE' not in val:
            missing.append(name)
    assert not missing, f'Coding Bible missing from: {missing}'


def test_coding_bible_only_injected_once():
    """Re-importing config must not stack multiple bible prefixes."""
    from utils import config as cfg
    prompt = cfg.TWENTY_SYSTEM_PROMPT
    # Bible header appears exactly once.
    assert prompt.count('CODING BIBLE') == 1


def test_twenty_prompt_still_big_coder_after_bible():
    """Bible prefix must not clobber the BIG CODER identity (Phase-4 regression)."""
    from utils import config as cfg
    assert 'BIG CODER' in cfg.TWENTY_SYSTEM_PROMPT


def test_nervous_system_prompt_still_exists():
    """Legacy Nervous System card kept under distinct name."""
    from utils import config as cfg
    assert hasattr(cfg, 'NERVOUS_SYSTEM_PROMPT')
    assert 'Nervous System' in cfg.NERVOUS_SYSTEM_PROMPT
