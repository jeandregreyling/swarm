"""Practice 152 (owner 18 Nov 2026: "the models should be swappable, the global name is apex, it doesn't matter which model drives
apex"): /apex model <name> changes only APEX's model file and template, restarts, checks it answers, and rolls back when it does not."""
from core import hb_apex_swap as s, hb_commands

DROPIN = """[Unit]
Description=APEX gpt-oss:20B Vulkan llama-server (0.0.0.0:8080)
[Service]
ExecStart=
ExecStart=/x/llama-server \\
    -m /blobs/gptoss \\
    --device Vulkan0 --fit on -fitt 1536 -fitc 16384 \\
    --host 0.0.0.0 --port 8080 --parallel 1 \\
    --jinja --chat-template-file /t/gpt-oss.jinja \\
    --flash-attn on --no-webui
"""
ROWS = [{'name': 'gpt-oss:20b', 'path': '/blobs/gptoss', 'template': '/t/gpt-oss.jinja', 'size_gb': 13.8, 'fits': True},
        {'name': 'swift-qwen3.8-27b', 'path': '/m/swift.gguf', 'template': None, 'size_gb': 12.0, 'fits': True},
        {'name': 'qwen2.5-32b-instruct', 'path': '/m/q32.gguf', 'template': None, 'size_gb': 19.9, 'fits': False}]


def test_practice_152_render_changes_only_model_and_template():
    new = s.render(DROPIN, ROWS[1])
    assert '-m /m/swift.gguf' in new and '--chat-template-file' not in new and '-fitt 3584' in new and '--jinja' in new   # Practice 192: Ghost reserve floor
    assert 'Description=APEX swift-qwen3.8-27b Vulkan llama-server' in new
    back = s.render(new, ROWS[0])
    assert '-m /blobs/gptoss' in back and '--jinja --chat-template-file /t/gpt-oss.jinja' in back


def test_practice_152_swap_backs_up_and_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(s, '_record', lambda name: None)
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN)
    said = []
    ok, msg = s.swap('swift-qwen3.8-27b', said.append, p, reload=lambda: True, restart=lambda: True, answers=lambda: True, rows=ROWS)
    assert ok and '-m /m/swift.gguf' in p.read_text() and (tmp_path / 'gpu-offload.conf.before-swap').read_text() == DROPIN and said
    p.write_text(DROPIN)
    answers = iter([False, True])
    ok, msg = s.swap('swift-qwen3.8-27b', said.append, p, reload=lambda: True, restart=lambda: True, answers=lambda: next(answers), rows=ROWS)
    assert not ok and p.read_text() == DROPIN and 'put the previous model back' in msg


def test_practice_152_too_big_and_unknown_are_refused(tmp_path):
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN)
    assert not s.swap('qwen2.5-32b-instruct', print, p, rows=ROWS)[0]
    assert not s.swap('nope', print, p, rows=ROWS)[0]
    assert p.read_text() == DROPIN


def test_practice_152_back_returns_to_the_saved_model(tmp_path, monkeypatch):
    monkeypatch.setattr(s, '_record', lambda name: None)
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(DROPIN)
    s.swap('swift-qwen3.8-27b', print, p, reload=lambda: True, restart=lambda: True, answers=lambda: True, rows=ROWS)
    ok, _m = s.back(print, p, reload=lambda: True, restart=lambda: True, answers=lambda: True, rows=ROWS)
    assert ok and '-m /blobs/gptoss' in p.read_text()


def test_practice_152_command_is_wired():
    assert hb_commands.parse('apex models') == ('apex', ['models'])
    assert any(c[0] == 'apex' for c in hb_commands.COMMANDS)
