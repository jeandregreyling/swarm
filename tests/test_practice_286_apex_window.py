"""Practice 286 (JD 22 Nov: "is the context of 24,832 still relevant? why do I feel like that's quite small for APEX"): Practice 192 gave APEX
an 8-bit KV cache, but only in the old Qwen 27B's own settings, and a swap removes flags the new model did not ask for - so the swap to
Mistral Nemo halved APEX's window to 24,832 tokens. The 8-bit KV cache is now the default for every model that plays APEX."""
from core import hb_apex_swap as sw

DROPIN = ("ExecStart=/home/jd/llama.cpp/build-rocm/bin/llama-server \\\n    -m /old.gguf \\\n    --device ROCm0 --fit on -fitt 4096 -fitc 16384 \\\n"
          "    --jinja \\\n    --flash-attn on -b 2048 -ub 1024 --no-webui\n")


def test_every_apex_model_gets_the_8_bit_kv_cache():
    for name in ('mistral-nemo-12b-abliterated', 'gpt-oss:20b', 'swift-qwen3.8-27b'):
        args = sw.server_args(name)
        assert args['-ctk'] == 'q8_0' and args['-ctv'] == 'q8_0', name


def test_a_swap_writes_the_kv_flags_into_the_dropin():
    out = sw.render(DROPIN, {'name': 'mistral-nemo-12b-abliterated', 'path': '/new.gguf'})
    assert '-ctk q8_0' in out and '-ctv q8_0' in out and '-m /new.gguf' in out and '--flash-attn on' in out
