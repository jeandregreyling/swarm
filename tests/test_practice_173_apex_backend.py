"""Practice 173: HB tests ROCm against Vulkan on the live APEX server and keeps the faster backend."""
from core import hb_apex_swap as s

DROPIN = """[Unit]
Description=APEX swift-qwen3.8-27b Vulkan llama-server (0.0.0.0:8080)

[Service]
ExecStart=
ExecStart=/home/jd/llama.cpp/build-vulkan/bin/llama-server \\
    -m /models/a.gguf \\
    --device Vulkan0 --fit on -fitt 2048 -fitc 16384 \\
    --jinja \\
    --flash-attn on -b 512 -ub 256 --no-webui
"""


def _builds(tmp_path, monkeypatch):
    for k in ('vulkan', 'rocm'):
        f = tmp_path / k
        f.write_text('')
        monkeypatch.setitem(s.BACKENDS, k, {**s.BACKENDS[k], 'server': str(f)})
    return DROPIN.replace('/home/jd/llama.cpp/build-vulkan/bin/llama-server', str(tmp_path / 'vulkan'))


def test_render_backend_changes_only_server_device_and_label():
    rocm = s.render_backend(DROPIN, 'rocm')
    assert 'ExecStart=/home/jd/llama.cpp/build-rocm/bin/llama-server' in rocm and '--device ROCm0' in rocm
    assert 'swift-qwen3.8-27b ROCm llama-server' in rocm and '-m /models/a.gguf' in rocm and '-b 512 -ub 256' in rocm
    assert 'ExecStart=\n' in rocm                  # the reset line stays
    assert s.backend(DROPIN) == 'vulkan' and s.backend(rocm) == 'rocm'
    assert s.render_backend(rocm, 'vulkan') == DROPIN


def test_model_swap_keeps_backend_label():
    rocm = s.render_backend(DROPIN, 'rocm')
    swapped = s.render(rocm, {'name': 'other', 'path': '/models/b.gguf', 'template': None})
    assert 'APEX other ROCm llama-server' in swapped and 'build-rocm' in swapped and '-m /models/b.gguf' in swapped


def test_switch_backend_rolls_back_when_apex_does_not_answer(tmp_path, monkeypatch):
    text = _builds(tmp_path, monkeypatch)
    p = tmp_path / 'gpu-offload.conf'
    p.write_text(text)
    ok, msg = s.switch_backend('rocm', say=lambda m: None, path=p, reload=lambda: True, restart=lambda: True, answers=lambda: False)
    assert not ok and 'put the previous backend back' in msg and p.read_text() == text
    assert (tmp_path / 'gpu-offload.conf.before-backend').read_text() == text
    ok, msg = s.switch_backend('rocm', say=lambda m: None, path=p, reload=lambda: True, restart=lambda: True, answers=lambda: True)
    assert ok and s.backend(p.read_text()) == 'rocm'


def test_switch_backend_refuses_missing_build(tmp_path, monkeypatch):
    monkeypatch.setitem(s.BACKENDS, 'rocm', {**s.BACKENDS['rocm'], 'server': str(tmp_path / 'nope')})
    ok, msg = s.switch_backend('rocm', say=lambda m: None, path=tmp_path / 'x.conf')
    assert not ok and 'no ROCm build' in msg


def _run(results, idle_after=0):
    calls, said, waits = [], [], []
    seq = iter(results)
    idles = iter([False] * idle_after + [True] * 5)
    ok, rep = s.bench('rocm', say=said.append, idle=lambda: next(idles), sleep=waits.append,
                      switcher=lambda name, say: (calls.append(name), (True, 'ok'))[1], measurer=lambda: next(seq), start='vulkan')
    return ok, rep, calls, said, waits


def test_bench_keeps_rocm_when_faster_at_both():
    ok, rep, calls, said, waits = _run([{'read': 35.0, 'write': 13.0, 'ok': True}, {'read': 120.0, 'write': 15.0, 'ok': True}], idle_after=2)
    assert ok and calls == ['rocm'] and 'stays on ROCm' in rep and '| ROCm | 120.0 | 15.0 | yes |' in rep
    assert waits == [30, 30] and 'waits until APEX finishes' in said[0]


def test_bench_goes_back_when_not_faster_at_both():
    ok, rep, calls, *_ = _run([{'read': 35.0, 'write': 13.0, 'ok': True}, {'read': 120.0, 'write': 12.0, 'ok': True}])
    assert ok and calls == ['rocm', 'vulkan'] and 'goes back to Vulkan' in rep
    ok, rep, calls, *_ = _run([{'read': 35.0, 'write': 13.0, 'ok': True}, {'read': 120.0, 'write': 20.0, 'ok': False}])
    assert calls == ['rocm', 'vulkan']


def test_bench_refuses_same_backend_and_gives_up_when_busy():
    ok, rep = s.bench('rocm', say=lambda m: None, start='rocm')
    assert not ok and 'already runs on ROCm' in rep
    ok, rep = s.bench('rocm', say=lambda m: None, idle=lambda: False, sleep=lambda _s: None, start='vulkan')
    assert not ok and 'stayed busy' in rep


def test_measure_averages_and_flags_failures():
    got = iter([{'timings': {'prompt_per_second': 100, 'predicted_per_second': 10}}, {'timings': {'prompt_per_second': 120, 'predicted_per_second': 14}}])
    assert s.measure(url='http://x', post=lambda u, b: next(got)) == {'read': 110.0, 'write': 12.0, 'ok': True}

    def boom(u, b):
        raise OSError('down')
    assert s.measure(url='http://x', post=boom)['ok'] is False


def test_apex_backend_command(monkeypatch):
    monkeypatch.setattr(s, 'backend', lambda text=None: 'vulkan')
    monkeypatch.setattr(s, 'candidates', lambda: [])
    monkeypatch.setattr(s, 'current', lambda text=None: None)
    assert 'APEX runs on Vulkan' in s.command(None, ['backend'])
    assert 'Use /apex bench vulkan or rocm' in s.command(None, ['bench', 'cuda'])
