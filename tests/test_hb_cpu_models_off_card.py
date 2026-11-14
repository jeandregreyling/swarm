"""Practice 80 (owner 15 Nov): at 07:10:44 the CPU "homework" model started; at 07:10:50 the card reset and APEX answered
ErrorDeviceLost. A CPU-only model must not touch the card at all."""
from pathlib import Path


def test_practice_80_cpu_models_start_with_the_card_switched_off():
    src = (Path(__file__).resolve().parents[1] / 'core/seven_llm/llama_server.py').read_text()
    i = src.index('cmd.extend(["--n-gpu-layers", str(int(opts["ngl"]))])')
    block = src[i:i + 900]
    assert 'if int(opts["ngl"]) == 0:' in block and 'cmd.extend(["--device", "none"])' in block
    assert src.count('cmd.extend(["--device", "none"])') == 1
