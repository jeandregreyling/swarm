"""Prepare Practice 173: /apex bench rocm|vulkan and /apex backend rocm|vulkan - HB tests ROCm against Vulkan on the live APEX server."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
S = 'core/hb_apex_swap.py'
C = 'core/hb_commands.py'

code = '''# Practice 173 (owner 19 Nov 2026: "putting it through HB would be the cherry on top"): ROCm 10.2 is installed (admin steps A-CC1A70 and
# A-08E6C6) and llama.cpp is built for it in build-rocm next to build-vulkan. The Vulkan baseline for the 27B from the server log the
# same evening: 35 tok/s reading, 13 tok/s writing (244 APEX turns). /apex bench <backend> waits until APEX is idle, measures the live
# server on one fixed long prompt, switches it to the other backend (backup, check, roll back - like a model swap), measures again and
# keeps the new backend only when it read AND wrote faster and answered every run; otherwise the old backend goes back. Either way HB
# posts the comparison in main chat. /apex backend <backend> switches without a test.
LLAMA = '/home/jd/llama.cpp'
BACKENDS = {'vulkan': {'server': LLAMA + '/build-vulkan/bin/llama-server', 'device': 'Vulkan0', 'label': 'Vulkan'},
            'rocm': {'server': LLAMA + '/build-rocm/bin/llama-server', 'device': 'ROCm0', 'label': 'ROCm'}}
BENCH_RUNS = 2
BENCH_WAIT_S = 1800
BENCH_PROMPT = (' '.join(f'Note {i}: payroll schema step {i} reads wage type {1000 + i} and posts it to period {i % 12 + 1} of year '
                         f'{2020 + i % 6}.' for i in range(120))
                + '\\n\\nSummarise the notes above in three sentences.')


def _servers(text):
    return re.findall(r'^ExecStart=(\\S+)', text, re.M)


def backend(text=None):
    """'vulkan', 'rocm' or None - which llama-server build APEX runs on."""
    text = guard.dropin().read_text() if text is None else text
    servers = _servers(text)
    return next((k for k, b in BACKENDS.items() if servers and servers[-1] == b['server']), None)


def render_backend(text, name):
    """The drop-in with this backend's llama-server and device; model, batches and everything else as they were."""
    b = BACKENDS[name]
    servers = _servers(text)
    if not servers:
        return text
    new = re.sub(r'^ExecStart=' + re.escape(servers[-1]), lambda m: 'ExecStart=' + b['server'], text, count=1, flags=re.M)
    new = re.sub(r'(--device\\s+)\\S+', lambda m: m.group(1) + b['device'], new, count=1)
    return re.sub(r'(Description=APEX \\S+ )\\S+( llama-server)', lambda m: m.group(1) + b['label'] + m.group(2), new, count=1)


def switch_backend(name, say=print, path=None, reload=None, restart=None, answers=None):
    """Run APEX on another llama-server build. Returns (ok, message)."""
    reload, restart, answers = reload or guard._reload, restart or guard._restart, answers or guard._answers
    path = Path(path) if path else guard.dropin()
    b = BACKENDS.get(str(name).lower())
    if not b:
        return False, f"{name} is not a backend HB knows - use {' or '.join(BACKENDS)}."
    if not Path(b['server']).exists():
        return False, f"There is no {b['label']} build of llama-server ({b['server']})."
    if not _busy.acquire(blocking=False):
        return False, 'An APEX swap is already running.'
    try:
        before = path.read_text()
        new = render_backend(before, str(name).lower())
        if new == before:
            return True, f"APEX already runs on {b['label']}."
        path.with_name(path.name + '.before-backend').write_text(before)
        path.write_text(new)
        say(f"Switching APEX to {b['label']} - APEX is offline for a minute or two; the previous settings are saved as "
            f"{path.name}.before-backend.")
        if reload() and restart() and answers():
            return True, f"APEX now runs on {b['label']} and answers."
        path.write_text(before)
        reload()
        restart()
        ok = answers()
        return False, (f"APEX did not start or answer on {b['label']}, so HB put the previous backend back"
                       + (' - APEX answers again.' if ok else ' - and APEX does not answer yet: check /status.'))
    finally:
        _busy.release()


def _completion(url, body):
    import json as _j
    import urllib.request as _u
    req = _u.Request(url, _j.dumps(body).encode(), {'Content-Type': 'application/json'})
    with _u.urlopen(req, timeout=900) as r:
        return _j.loads(r.read())


def measure(url=None, runs=BENCH_RUNS, post=None):
    """Reading and writing speed (tokens/s) of the live server on BENCH_PROMPT, prompt cache off."""
    url, post = url or guard.URL, post or _completion
    got = []
    for _ in range(runs):
        try:
            t = post(url + '/completion', {'prompt': BENCH_PROMPT, 'n_predict': 128, 'temperature': 0, 'cache_prompt': False}).get('timings') or {}
            got.append((float(t.get('prompt_per_second') or 0), float(t.get('predicted_per_second') or 0)))
        except Exception:
            got.append((0.0, 0.0))
    return {'read': round(sum(p for p, _ in got) / len(got), 1), 'write': round(sum(g for _, g in got) / len(got), 1),
            'ok': all(p and g for p, g in got)}


def bench(target, say=print, idle=None, sleep=None, switcher=None, measurer=None, start=None):
    """Compare the backend APEX runs on with target; keep target only when it is faster at both. Returns (ok, report)."""
    import time as _t
    idle, sleep = idle or guard._idle, sleep or _t.sleep
    switcher, measurer = switcher or switch_backend, measurer or measure
    target = str(target).lower()
    if target not in BACKENDS:
        return False, f"{target} is not a backend HB knows - use {' or '.join(BACKENDS)}."
    start = backend() if start is None else start
    if start not in BACKENDS:
        return False, 'HB cannot tell which llama-server build APEX runs on, so it does not test.'
    if start == target:
        return False, f"APEX already runs on {BACKENDS[target]['label']}; /apex bench " + next(k for k in BACKENDS if k != target) + ' tests the other one.'
    waited = 0
    while not idle():
        if waited >= BENCH_WAIT_S:
            return False, 'APEX stayed busy for 30 minutes, so HB did not test - try /apex bench again later.'
        if not waited:
            say('HB: the backend test waits until APEX finishes what it is doing.')
        sleep(30)
        waited += 30
    old, new = BACKENDS[start]['label'], BACKENDS[target]['label']
    say(f'HB: backend test {old} vs {new} - same model, same long prompt, {BENCH_RUNS} runs each. APEX is offline for a few minutes.')
    a = measurer()
    ok, msg = switcher(target, say)
    if not ok:
        return False, f'{msg} No comparison was made.'
    b = measurer()
    table = (f'| backend | reading tok/s | writing tok/s | answered |\\n|---|---|---|---|\\n'
             f"| {old} | {a['read']} | {a['write']} | {'yes' if a['ok'] else 'no'} |\\n"
             f"| {new} | {b['read']} | {b['write']} | {'yes' if b['ok'] else 'no'} |")
    if b['ok'] and b['read'] > a['read'] and b['write'] > a['write']:
        return True, f'{table}\\n{new} is faster at both, so APEX stays on {new}. /apex backend {start} goes back.'
    back_ok, back_msg = switcher(start, say)
    return True, (f'{table}\\n{new} was not faster at both (or did not answer every run), so APEX goes back to {old}: '
                  + ('done.' if back_ok else back_msg))


def command(conn, args, actor='owner'):
'''

edits = [
    {'path': S, 'old': "def command(conn, args, actor='owner'):\n", 'new': code},
    {'path': S, 'old': '''    if args[0].lower() == 'models':
        return 'Models that can play APEX''', 'new': '''    if args[0].lower() == 'backend' and len(args) == 1:      # Practice 173
        b = BACKENDS.get(backend() or '')
        return (f"APEX runs on {b['label'] if b else 'an unknown llama-server build'}. /apex bench rocm|vulkan compares them on the "
                "live server; /apex backend rocm|vulkan switches.")
    if args[0].lower() in ('backend', 'bench') and len(args) == 2:
        kind, target = args[0].lower(), args[1].lower()
        if target not in BACKENDS:
            return f"Use /apex {kind} " + ' or '.join(BACKENDS) + '.'
        from core.hb_model_bench import _post as _post_b

        def work_b():
            from contextlib import closing as _cl
            from utils.db._connection import get_connection as _gc

            def say(text):
                with _cl(_gc()) as c:
                    _post_b(c, text)
                    c.commit()
            ok, msg = bench(target, say) if kind == 'bench' else switch_backend(target, say)
            say(('Backend test: ' if kind == 'bench' else ('Done: ' if ok else 'Not done: ')) + msg)
        threading.Thread(target=work_b, name='hb-apex-backend', daemon=True).start()
        return (f"Testing APEX on {BACKENDS[target]['label']} - HB waits until APEX is idle and posts the comparison in main chat."
                if kind == 'bench' else f"Switching APEX to {BACKENDS[target]['label']} - HB reports in main chat when it answers.")
    if args[0].lower() == 'models':
        return 'Models that can play APEX'''},
    {'path': S, 'old': "    new = re.sub(r'(Description=APEX )[^\\n]*?( Vulkan llama-server)'",
     'new': "    new = re.sub(r'(Description=APEX )[^\\n]*?( (?:Vulkan|ROCm) llama-server)'"},     # Practice 173: model swaps on ROCm too
    {'path': S, 'old': "        return 'Use /apex, /apex models, /apex model <name> or /apex back.'",
     'new': "        return 'Use /apex, /apex models, /apex model <name>, /apex back, /apex backend or /apex bench rocm|vulkan.'"},
    {'path': C, 'old': "    ('apex', '/apex [models | model <name> | back]', 'Which model plays APEX; swap it (HB backs up, restarts, checks, rolls back)', False),",
     'new': "    ('apex', '/apex [models | model <name> | back | backend | bench rocm|vulkan]', 'Which model plays APEX and on which GPU backend; swap or test them (HB backs up, restarts, checks, rolls back)', False),"},
]

test = '''"""Practice 173: HB tests ROCm against Vulkan on the live APEX server and keeps the faster backend."""
from core import hb_apex_swap as s

DROPIN = """[Unit]
Description=APEX swift-qwen3.8-27b Vulkan llama-server (0.0.0.0:8080)

[Service]
ExecStart=
ExecStart=/home/jd/llama.cpp/build-vulkan/bin/llama-server \\\\
    -m /models/a.gguf \\\\
    --device Vulkan0 --fit on -fitt 2048 -fitc 16384 \\\\
    --jinja \\\\
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
    assert 'ExecStart=\\n' in rocm                  # the reset line stays
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
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov (\"putting it through HB would be the cherry on top\"): ROCm 10.2 is installed and llama.cpp is built "
                            "for it (build-rocm). core/hb_apex_swap: /apex bench rocm|vulkan waits until APEX is idle, measures the live server "
                            "(fixed ~2.4k-token prompt, 2 runs), switches backend (backup, check, roll back), measures again and keeps the new "
                            "backend only when it reads AND writes faster and answered every run; otherwise switches back. Comparison table "
                            "in main chat. /apex backend rocm|vulkan switches by hand. Model swaps keep the backend label."),
                 edits=edits, new_files={'tests/test_practice_173_apex_backend.py': test},
                 test={'tests': ['tests/test_practice_173_apex_backend.py', 'tests/test_practice_152_apex_swap.py',
                                 'tests/test_practice_159_model_batches.py', 'tests/test_practice_161_settings_reload.py',
                                 'tests/test_practice_153_apex_routing.py'], 'keyword': ''}, run=run)
print(out['verified'])
