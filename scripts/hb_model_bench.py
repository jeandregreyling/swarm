#!/usr/bin/env python3
"""HB model benchmark (plan step 19, build item 1): the numbers that set the harness routing thresholds.

For each local model and placement (GPU / CPU) it starts its own llama-server on a free port (no --alias, so HB's
pool and housekeeping ignore it), measures load time, RAM, VRAM, prompt and generation speed, optionally sits the
8-item learning exam through the real APEX tool loop, then stops the server it started. The APEX service on :8080
is only ever measured, never stopped.

  python scripts/hb_model_bench.py --list
  python scripts/hb_model_bench.py seven-direct:daily@cpu llama3.2:latest@gpu qwen2.5:7b-instruct@cpu --exam
  python scripts/hb_model_bench.py apex                      # the running :8080 service, speed only
  placements: gpu | cpu | gpu-kv8 (8-bit KV cache) | gpu-moe-cpu (MoE experts in RAM)

Results: runtime/learning/bench-<timestamp>.json (one record per run) and a markdown table on stdout.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'utils'), str(ROOT / 'frontend')]

from core import hb_hardware as hw                       # noqa: E402
from core.seven_llm import registry, llama_server        # noqa: E402

PROMPT = ('You are a payroll consultant. A client runs SAP SuccessFactors Employee Central Payroll for 1,200 Australian employees. '
          'They ask whether superannuation guarantee contributions should be calculated on ordinary time earnings or total earnings, '
          'and how a retrospective pay rise paid in the current period affects the calculation. Explain in plain language, '
          'then list the configuration areas you would check.')
GEN_TOKENS = 160
CTX = 8192


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _get(url, timeout=5):
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url, body, timeout=600):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _rss_gb(pid):
    try:
        m = re.search(r'VmRSS:\s*(\d+)', open(f'/proc/{pid}/status').read())
        return round(int(m.group(1)) / 2**20, 2) if m else None
    except OSError:
        return None


VRAM_MARGIN_GB = 1.5       # never fill the card: 13 Nov a 12.8 GB load on top of other models froze the machine


def vram_need_gb(file_gb, placement):
    """Conservative VRAM estimate at CTX 8192: weights on the GPU + working memory + compute buffers."""
    if placement == 'cpu':
        return 0.0
    kv = 1.5 if file_gb >= 8 else 1.0 if file_gb >= 3.5 else 0.6
    if placement == 'gpu-kv8':
        kv /= 2
    weights = file_gb * 0.25 if placement == 'gpu-moe-cpu' else file_gb      # MoE: experts stay in RAM
    return round(weights + kv + 0.8, 2)


def preflight(entry, placement, gpu=None):
    """Hardware gatekeeper for the bench: refuse a GPU load that does not fit with a safety margin."""
    if placement == 'cpu':
        return None
    gpu = gpu or hw.gpu_stats()
    if gpu.get('vram_total_gb') is None:
        raise RuntimeError('GPU memory is unreadable; refusing a GPU load')
    file_gb = os.path.getsize(entry.path) / 2**30
    need = vram_need_gb(file_gb, placement)
    free = gpu['vram_total_gb'] - gpu['vram_used_gb'] - VRAM_MARGIN_GB
    if need > free:
        raise RuntimeError(f'Gatekeeper: {entry.name}@{placement} needs about {need} GB VRAM, only {round(free, 2)} GB free '
                           f'after the {VRAM_MARGIN_GB} GB margin; not loaded')
    return {'need_gb': need, 'free_gb': round(free, 2)}


def start(entry, placement):
    """Start a bench server for a registry entry; returns (proc, port, load_seconds)."""
    preflight(entry, placement)
    port = _free_port()
    opts = entry.options or {}
    threads = str(opts.get('threads') or max(4, os.cpu_count() // 2))
    cmd = [llama_server.default_binary(), '-m', entry.path, '--host', '127.0.0.1', '--port', str(port), '--ctx-size', str(CTX),
           '--parallel', '1', '--no-webui', '--threads', threads, '--flash-attn', 'on']
    if placement == 'cpu':
        cmd += ['--n-gpu-layers', '0', '--device', 'none']
    else:
        cmd += ['--n-gpu-layers', '99']
    if placement == 'gpu-moe-cpu':                    # mixture-of-experts: attention on the GPU, experts in RAM
        cmd += ['--n-cpu-moe', '99']
    if placement == 'gpu-kv8':                        # 8-bit working memory (KV cache)
        cmd += ['--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0']
    if 'gpt-oss' in entry.name:                       # harmony chat format needs the model's own template
        cmd += ['--jinja']
        template = Path.home() / 'llama.cpp/models/templates/openai-gpt-oss-120b.jinja'
        if template.is_file():
            cmd += ['--chat-template-file', str(template)]
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = t0 + 600
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('llama-server exited: ' + (proc.stderr.read() or '')[-600:])
        try:
            if _get(f'http://127.0.0.1:{port}/health', 2).get('status') == 'ok':
                return proc, port, round(time.monotonic() - t0, 1)
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError('llama-server did not become healthy in 10 minutes')


def speed(port):
    """One warm-up, then one timed completion. Returns prompt and generation tokens/s from the server's own timings."""
    _post(f'http://127.0.0.1:{port}/v1/chat/completions', {'messages': [{'role': 'user', 'content': 'Say OK.'}], 'max_tokens': 4}, 600)
    t0 = time.monotonic()
    r = _post(f'http://127.0.0.1:{port}/v1/chat/completions',
              {'messages': [{'role': 'user', 'content': PROMPT}], 'max_tokens': GEN_TOKENS, 'temperature': 0.2}, 1800)
    wall = round(time.monotonic() - t0, 1)
    t = r.get('timings') or {}
    usage = r.get('usage') or {}
    text = ((r.get('choices') or [{}])[0].get('message') or {}).get('content', '')
    return {'wall_s': wall, 'prompt_tokens': usage.get('prompt_tokens'), 'completion_tokens': usage.get('completion_tokens'),
            'prompt_tps': round(t.get('prompt_per_second') or 0, 1), 'gen_tps': round(t.get('predicted_per_second') or 0, 1),
            'answer': str(text)[:400]}


def exam(port):
    """The 8-item learning exam through the real APEX tool loop, answered by the bench server."""
    import copy
    from core import hb_learning_exam as ex
    from core.apex_tools import TURN_FORMAT, response_format_for_turn
    from core.apex_context import generation_budget
    fmt = copy.deepcopy(TURN_FORMAT)
    variants = []
    for variant in fmt['json_schema']['schema']['oneOf']:
        items = variant['properties']['tool_calls'].get('items', {})
        if 'oneOf' in items:
            items['oneOf'] = [v for v in items['oneOf'] if v['properties']['name']['const'] in ex.EXAM_TOOLS]
            if not items['oneOf']:
                continue
        variants.append(variant)
    fmt['json_schema']['schema']['oneOf'] = variants

    def model_call(_model, messages):
        body = {'messages': messages, 'max_tokens': generation_budget(messages), 'temperature': 0.2,
                'response_format': llama_server._openai_response_format(response_format_for_turn(fmt))}
        r = _post(f'http://127.0.0.1:{port}/v1/chat/completions', body, 600)
        text = ((r.get('choices') or [{}])[0].get('message') or {}).get('content', '')
        return text, int((r.get('usage') or {}).get('total_tokens') or 0)
    # The exam normally asks HB to pick and load a route model; here the bench server answers, so nothing
    # else may be loaded (13 Nov: HB loaded apex-direct:7b next to the benched model and crowded the GPU).
    from contextlib import contextmanager
    from core import apex_routing

    @contextmanager
    def no_load(_route):
        yield
    from core import apex_context

    def bench_tokens(messages):                      # count tokens on the benched model itself, not the APEX service
        prompt = _post(f'http://127.0.0.1:{port}/apply-template', {'messages': messages}, 30).get('prompt')
        tokens = _post(f'http://127.0.0.1:{port}/tokenize', {'content': prompt, 'add_special': True}, 30).get('tokens')
        return len(tokens) + 128
    saved = (apex_routing.choose_local_model, apex_routing.use_model, apex_context._server_prompt_tokens)
    apex_routing.choose_local_model = lambda _prompt: apex_routing.LocalRoute('bench', 'bench', 8192, 'bench server')
    apex_routing.use_model = no_load
    apex_context._server_prompt_tokens = bench_tokens
    try:
        result = ex.run(label='bench', model_call=model_call)
    finally:
        apex_routing.choose_local_model, apex_routing.use_model, apex_context._server_prompt_tokens = saved
    return {'score': result.get('score'), 'total': result.get('total'), 'by_skill': result.get('by_skill'),
            'file': result.get('file'), 'seconds': result.get('seconds')}


def bench_apex():
    procs = [p for p in hw.model_processes() if p['model'] == 'apex-server']
    rec = {'model': 'apex-server (:8080)', 'placement': 'gpu', 'load_s': None,
           'vram_gb': procs[0]['vram_gb'] if procs else None, 'rss_gb': procs[0]['ram_gb'] if procs else None}
    rec.update(speed(8080))
    return rec


def bench(name, placement, with_exam):
    entry = registry.get(name)
    if not entry or entry.driver != 'llamacpp' or not entry.path or not os.path.isfile(entry.path):
        raise RuntimeError(f'{name}: not a local GGUF HB knows')
    gpu0 = hw.gpu_stats()['vram_used_gb'] or 0
    proc, port, load_s = start(entry, placement)
    try:
        rec = {'model': name, 'placement': placement, 'quant': entry.quant, 'file_gb': round(os.path.getsize(entry.path) / 2**30, 2),
               'load_s': load_s, 'port': port}
        rec.update(speed(port))
        rec['vram_gb'] = hw._process_vram_gb(proc.pid) or round(max(0, (hw.gpu_stats()['vram_used_gb'] or 0) - gpu0), 2)
        rec['rss_gb'] = _rss_gb(proc.pid)
        if with_exam:
            rec['exam'] = exam(port)
        return rec
    finally:
        proc.terminate()
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('targets', nargs='*', help='name@gpu | name@cpu | apex')
    ap.add_argument('--exam', action='store_true')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if a.list:
        for e in registry.list_models():
            if e.driver == 'llamacpp' and e.path and os.path.isfile(e.path):
                print(f"{e.name:28} {e.role:8} {round(os.path.getsize(e.path)/2**30,1):>5} GB  ngl={(e.options or {}).get('ngl')}")
        return
    out = []
    path = ROOT / 'runtime' / 'learning' / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    for target in a.targets:
        try:
            if target == 'apex':
                rec = bench_apex()
            else:
                name, _, placement = target.partition('@')
                rec = bench(name, placement or 'gpu', a.exam)
        except Exception as exc:
            rec = {'model': target, 'error': f'{type(exc).__name__}: {str(exc)[:300]}'}
        rec['at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        out.append(rec)
        print(json.dumps(rec, ensure_ascii=False)[:600], flush=True)
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False))     # saved after every model: a crash keeps what finished
    print('\n| model | where | load s | VRAM GB | RAM GB | prompt tok/s | gen tok/s | exam |')
    print('|---|---|---|---|---|---|---|---|')
    for r in out:
        ex_ = r.get('exam') or {}
        print(f"| {r.get('model')} | {r.get('placement','')} | {r.get('load_s','')} | {r.get('vram_gb','')} | {r.get('rss_gb','')} | "
              f"{r.get('prompt_tps','')} | {r.get('gen_tps','')} | {str(ex_.get('score',''))+'/'+str(ex_.get('total','')) if ex_ else r.get('error','')} |")
    print('saved', path)


if __name__ == '__main__':
    main()
