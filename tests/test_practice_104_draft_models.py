"""Practice 104 (owner 16 Nov 2026, the ArtyomITA test): MiniCPM5-2B with the author's DSpark draft ran at 18-25 tok/s on the CPU against 10
without it, with the same output. HB can now start a local model with a draft, and MiniCPM5 is a registered CPU model."""
from pathlib import Path

from core.seven_llm import registry

ROOT = Path(__file__).resolve().parents[1]


def test_practice_104_minicpm5_is_registered_with_its_draft():
    entry = registry.get('minicpm5-cpu:2b')
    assert entry is not None and entry.driver == 'llamacpp'
    assert entry.options['ngl'] == 0 and entry.options['spec_type'] == 'draft-dspark'
    assert entry.options['draft_model'].endswith('MiniCPM5-DSpark-fr32k-Q8_0.gguf')


def test_practice_104_the_launcher_passes_the_draft_and_keeps_it_off_the_card():
    src = (ROOT / 'core/seven_llm/llama_server.py').read_text()
    i = src.index('if opts.get("draft_model"):')
    block = src[i:i + 900]
    assert '"-md", str(opts["draft_model"])' in block and '"--spec-type"' in block
    assert 'cmd.extend(["-ngld", "0", "--device-draft", "none"])' in block
