"""Practice 159 (owner 18 Nov 2026): the dense 27B reset the card twice in 30 minutes with -b 2048 -ub 1024; at a swap each model now
gets its own batch sizes, and the defaults come back for gpt-oss."""
from core import hb_apex_swap as s

DROPIN = """[Unit]
Description=APEX gpt-oss:20B Vulkan llama-server (0.0.0.0:8080)
[Service]
ExecStart=
ExecStart=/x/llama-server \\
    -m /blobs/gptoss \\
    --device Vulkan0 --fit on -fitt 1536 -fitc 16384 \\
    --host 0.0.0.0 --port 8080 --parallel 1 \\
    --jinja --chat-template-file /t/gpt-oss.jinja \\
    --flash-attn on -b 2048 -ub 1024 --no-webui
"""
SWIFT = {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None}
GPT = {'name': 'gpt-oss:20b', 'path': '/blobs/gptoss', 'template': '/t/gpt-oss.jinja'}


def test_practice_159_27b_gets_small_batches_and_gpt_oss_gets_them_back():
    new = s.render(DROPIN, SWIFT)
    assert '-b 512 -ub 256 -ctk q8_0 -ctv q8_0 --no-webui' in new and '-fitt 3584' in new and '-m /m/swift.gguf' in new   # Practice 192
    back = s.render(new, GPT)
    assert '-b 2048 -ub 1024 --no-webui' in back and '-m /blobs/gptoss' in back and '-ctk' not in back


def test_practice_159_missing_flags_are_added():
    plain = DROPIN.replace(' -b 2048 -ub 1024', '')
    new = s.render(plain, SWIFT)
    assert '-b 512 -ub 256 -ctk q8_0 -ctv q8_0 --no-webui' in new   # Practice 192: 8-bit KV for the 27B
