"""Model benchmark (owner 14 Nov 2026): a clean record of every local model - does it fit the GPU, and is it a programmer, researcher,
social, generalist or useless?

"FRED is a placeholder, same as APEX. HB can use the new models as Fred counterparts or any model that doesn't fit the GPU but is required.
We need a clean record of each model: in GPU if they fit, and the model test to see if they are social, programmer, researcher, useless."

For each distinct model file (aliases share one test):
  fit     size on disk + working memory against the 16 GB card - recorded, never loaded onto the GPU (APEX owns it)
  tests   four short tests, scored by HB's own rules, never by a model:
            programmer  write merge_intervals(); HB runs hidden tests on it
            tools       answer with one exact JSON tool call
            researcher  answer from a passage, including a trap question whose answer is NOT in it ("not in the text")
            social      reply to a frustrated person: short, kind, a next step, no "as an AI"
  tag     programmer (code + tools), researcher, social; generalist when it passes two kinds; useless when it passes none
  speed   tokens per second, load time
Each model runs alone on the CPU in its own llama-server (-ngl 0, no GPU device), then is stopped. APEX's model is asked where it already
runs. Every test posts its result in main chat and shows in the live activity; the full record lands in Studio (and so the KC).
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path

SERVER = '/home/jd/llama.cpp/build-vulkan/bin/llama-server'
GPU_GB = 16.0
GPU_HEADROOM_GB = 1.5
RECORD_STEP_TITLE = 'Model benchmark record: every local model - GPU fit, programmer / researcher / social / useless'
PLAN = 'P-2AB8250A87'
EXTRA = [('mixtral-8x7b-instruct', '/mnt/archive/models/gguf/mixtral-8x7b-instruct/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf'),
         ('qwen2.5-32b-instruct', '/mnt/archive/models/gguf/qwen2.5-32b-instruct/Qwen2.5-32B-Instruct-Q4_K_M.gguf')]
_RUNNING = threading.Lock()

# ------------------------------------------------------------------ the four tests (scored by HB, not by a model)
CODE_PROMPT = ('Write a Python function merge_intervals(intervals) that takes a list of [start, end] pairs and returns the merged, '
               'overlapping-free list sorted by start. Touching intervals like [1,2] and [2,3] merge. Reply with ONLY the code in one ```python block.')
CODE_TESTS = [([[1, 3], [2, 6], [8, 10], [15, 18]], [[1, 6], [8, 10], [15, 18]]), ([[1, 4], [4, 5]], [[1, 5]]), ([], []),
              ([[5, 7], [1, 2]], [[1, 2], [5, 7]]), ([[1, 10], [2, 3], [4, 5]], [[1, 10]])]
TOOLS_PROMPT = ('You can call one tool. Reply with ONLY this JSON shape and nothing else: {"tool": "<name>", "arguments": {...}}. '
                'Task: read lines 1 to 40 of the file core/hb_rename.py with the tool read_file (arguments: path, start, end).')
PASSAGE = ('Hummingbird (HB) is JD\'s local agent system. DOES stands for Do, Operate, Execute, Sustain. The rename tool lives in '
           'core/hb_rename.py. Every restart is announced by scripts/hb_restart.py, which shows "Maintenance in progress".')
RESEARCH_PROMPT = (f'Text: "{PASSAGE}"\nAnswer from the text only, one line each:\n1. What does DOES stand for?\n2. Which file holds the '
                   'rename tool?\n3. Which script announces restarts?\n4. What is HB\'s monthly budget? (If the text does not say, answer: not in the text.)')
SOCIAL_PROMPT = 'A user writes: "this is the third time it broke today, I am so done with this". Reply to them directly.'


def score_code(text):
    m = re.search(r'```(?:python)?\s*\n(.*?)```', str(text), re.S)
    code = m.group(1) if m else str(text)
    if 'def merge_intervals' not in code:
        return False, 'no merge_intervals function'
    harness = code + '\n\nimport json\ncases=' + json.dumps(CODE_TESTS) + \
        '\nok=all(merge_intervals([list(x) for x in a])==b for a,b in cases)\nprint(json.dumps(ok))\n'
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'm.py'
        f.write_text(harness)
        try:
            out = subprocess.run([sys.executable, '-I', str(f)], capture_output=True, text=True, timeout=10, cwd=d)
        except subprocess.TimeoutExpired:
            return False, 'the code ran too long'
    ok = out.stdout.strip().endswith('true')
    return ok, 'all 5 hidden cases pass' if ok else ('fails a hidden case' if out.returncode == 0 else 'the code crashes: ' + out.stderr.strip()[-120:])


def score_tools(text):
    m = re.search(r'\{.*\}', str(text), re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return False, 'no valid JSON'
    a = data.get('arguments') or {}
    ok = data.get('tool') == 'read_file' and a.get('path') == 'core/hb_rename.py' and int(a.get('start', 0) or 0) == 1 and int(a.get('end', 0) or 0) == 40
    return ok, 'exact tool call' if ok else 'JSON, but not the exact call'


def score_research(text):
    t = str(text).lower()
    hits = [all(w in t for w in ('do', 'operate', 'execute', 'sustain')), 'core/hb_rename.py' in t, 'hb_restart.py' in t,
            'not in the text' in t or 'does not say' in t or 'not mentioned' in t or 'not stated' in t]
    ok = sum(hits) >= 4
    return ok, f"{sum(hits)}/4 right" + ('' if hits[3] else ' (made up the budget)')


def score_social(text):
    t = str(text).strip()
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', t) if s.strip()]
    kind = re.search(r"\b(sorry|understand|frustrat|annoying|that's rough|that is rough|hear you)", t, re.I)
    step = re.search(r"\b(i'll|i will|let's|let me|next|we can|try|check|look into|fix)\b", t, re.I)
    robotic = re.search(r'as an ai|language model', t, re.I)
    ok = bool(kind and step and not robotic and 1 <= len(sentences) <= 5)
    why = [] if ok else [w for w, bad in (('too long', len(sentences) > 5), ('no empathy', not kind), ('no next step', not step),
                                          ('robotic', robotic)) if bad]
    return ok, 'short, kind, with a next step' if ok else ', '.join(why)


# Owner 14 Nov: give models room to finish - reasoning models (gpt-oss) spent the old caps (120/160) thinking and never answered.
# The scorers still judge length ("too long"), so a bigger cap only stops cut-off answers.
TESTS = [('programmer', CODE_PROMPT, score_code, 1600), ('tools', TOOLS_PROMPT, score_tools, 800),
         ('researcher', RESEARCH_PROMPT, score_research, 800), ('social', SOCIAL_PROMPT, score_social, 800)]


def tags(results):
    passed = {k for k, v in results.items() if v.get('passed')}
    out = []
    if {'programmer', 'tools'} <= passed:
        out.append('programmer')
    if 'researcher' in passed:
        out.append('researcher')
    if 'social' in passed:
        out.append('social')
    if len(out) >= 2:
        out.append('generalist')
    return out or ['useless']


# ------------------------------------------------------------------ which models
def models():
    """Distinct local model files: (label, path, aliases, endpoint or None)."""
    from core.seven_llm import registry
    found = {}
    for e in registry.list_models():
        p = str(e.path or '')
        if not p or not os.path.isfile(p) or e.role == 'embed':
            continue
        real = os.path.realpath(p)
        item = found.setdefault(real, {'path': real, 'aliases': [], 'endpoint': None})
        item['aliases'].append(e.name)
        if e.endpoint and e.name == 'qwen2.5:14b-instruct':
            item['endpoint'] = e.endpoint                    # APEX's model: ask it where it already runs
    for label, p in EXTRA:
        if os.path.isfile(p):
            found.setdefault(os.path.realpath(p), {'path': os.path.realpath(p), 'aliases': [label], 'endpoint': None})
    out = []
    for item in found.values():
        label = sorted(item['aliases'], key=lambda n: (n.startswith(('apex-', 'seven-', 'llama-direct', 'gemma-direct', 'homework-', 'fred-')), len(n)))[0]
        out.append({**item, 'label': label, 'size_gb': round(os.path.getsize(item['path']) / 1e9, 1)})
    return sorted(out, key=lambda m: m['size_gb'])


def gpu_fit(size_gb):
    need = round(size_gb + GPU_HEADROOM_GB, 1)
    return need <= GPU_GB - 0.5, need


# ------------------------------------------------------------------ running one model
def _free_port():
    with closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _post_json(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _ram_free_gb():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) / 1024 ** 2
    return 0


def ask(base, prompt, max_tokens, model='local'):
    t = time.time()
    out = _post_json(base + '/v1/chat/completions', {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                                                     'temperature': 0, 'max_tokens': max_tokens}, timeout=900)
    text = out['choices'][0]['message'].get('content') or ''
    timings = out.get('timings') or {}
    speed = timings.get('predicted_per_second') or (out.get('usage', {}).get('completion_tokens', 0) / max(0.1, time.time() - t))
    return text, round(float(speed or 0), 1), round(time.time() - t, 1)


def run_model(m, say=print, asker=ask, server=None):
    """Benchmark one model. Returns its record."""
    fits, need = gpu_fit(m['size_gb'])
    record = {'model': m['label'], 'aliases': m['aliases'], 'size_gb': m['size_gb'], 'gpu_fit': fits, 'gpu_need_gb': need, 'tests': {}}
    proc, base, load_s = None, m.get('endpoint'), 0.0
    try:
        if not base:
            if _ram_free_gb() < m['size_gb'] + 6:
                record['error'] = f"not enough free RAM ({_ram_free_gb():.0f} GB free, needs {m['size_gb'] + 6:.0f})"
                return record
            port = _free_port()
            t = time.time()
            proc = (server or subprocess.Popen)([SERVER, '-m', m['path'], '-ngl', '0', '--device', 'none', '--port', str(port), '--host', '127.0.0.1',
                                                 '-c', '4096', '-t', '8', '--jinja', '--no-webui'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f'http://127.0.0.1:{port}'
            for _ in range(600):
                if getattr(proc, 'poll', lambda: None)() is not None:      # the server died while loading: stop waiting (14 Nov, Mixtral)
                    record['error'] = f'the model server exited while loading (code {proc.poll()})'
                    say('✘ ' + record['error'])
                    return record
                try:
                    with urllib.request.urlopen(base + '/health', timeout=2) as r:
                        if json.loads(r.read()).get('status') == 'ok':
                            break
                except Exception:
                    time.sleep(1)
            load_s = round(time.time() - t, 1)
        record['load_s'] = load_s
        say(f"loaded into RAM in {load_s} s; running 4 tests" if load_s else 'already running on the GPU; running 4 tests')
        speeds = []
        for name, prompt, score, max_tokens in TESTS:
            try:
                text, speed, took = asker(base, prompt, max_tokens)
                ok, why = score(text)
            except Exception as exc:
                text, speed, took, ok, why = '', 0, 0, False, f'error: {str(exc)[:100]}'
            speeds.append(speed)
            record['tests'][name] = {'passed': ok, 'why': why, 'seconds': took, 'tok_s': speed, 'answer': text[:600]}
            say(f"{'✔' if ok else '✘'} {name}: {why} ({took} s, {speed} tok/s)")
        record['tok_s'] = round(sum(speeds) / max(1, len([s for s in speeds if s])), 1)
        record['tags'] = tags(record['tests'])
        return record
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(30)
            except Exception:
                proc.kill()


# ------------------------------------------------------------------ records, main chat, background
def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_model_bench(model TEXT PRIMARY KEY, at REAL, record TEXT)')


def save(conn, record):
    ensure_schema(conn)
    conn.execute('INSERT OR REPLACE INTO hb_model_bench VALUES(?,?,?)', (record['model'], time.time(), json.dumps(record)))
    rows = [json.loads(r[0]) for r in conn.execute('SELECT record FROM hb_model_bench ORDER BY model')]
    lines = ['Owner 14 Nov: a clean record of every local model. GPU fit = size + 1.5 GB working memory on the 16 GB card (recorded, not '
             'loaded). Tests scored by HB: programmer (hidden tests), tools (exact JSON call), researcher (from a passage, with a trap), social.',
             '', 'model | size | GPU fit | programmer | tools | researcher | social | tok/s | tags']
    for r in rows:
        t = r.get('tests', {})
        mark = lambda k: ('pass' if t.get(k, {}).get('passed') else 'fail') if k in t else '-'
        lines.append(f"{r['model']} | {r['size_gb']} GB | {'yes' if r['gpu_fit'] else 'no'} ({r['gpu_need_gb']} GB) | {mark('programmer')} | "
                     f"{mark('tools')} | {mark('researcher')} | {mark('social')} | {r.get('tok_s', '-')} | {', '.join(r.get('tags', [])) or r.get('error', '')}")
    desc = '\n'.join(lines) + '\nDone when: every distinct local model file has a row.'
    row = conn.execute('SELECT step_id FROM project_steps WHERE project_id=? AND title=?', (PLAN, RECORD_STEP_TITLE)).fetchone()
    if row:
        conn.execute('UPDATE project_steps SET description=?, updated_at=? WHERE step_id=?', (desc, time.time(), row[0]))
    else:
        from core.knowledge import projects
        projects.add_step(PLAN, RECORD_STEP_TITLE, description=desc, owner='hummingbird')


def _post(conn, text):
    from core.hb_plain import message
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2834,'hummingbird','user',?,'response',0)",
                 (message(text),))


def run_all(only=None):
    """Background: every model (or the named ones), one at a time, everything visible in main chat."""
    from core import hb_background as bg
    from utils.db._connection import get_connection
    for m in models():
        if only and m['label'] not in only and not set(only) & set(m['aliases']):
            continue
        task = {'task_id': None, 'title': f"Benchmark {m['label']}", 'conversation_id': 2834}
        fits, need = gpu_fit(m['size_gb'])
        with closing(get_connection()) as c, c:
            _post(c, f"🧪 Benchmarking {m['label']} ({m['size_gb']} GB; GPU fit: {'yes' if fits else 'no'}, needs {need} GB) - "
                     f"{'on the GPU where it runs' if m.get('endpoint') else 'alone on the CPU'}.")
        bg.start('bench', task, m['label'], 'loading the model')

        def say(text, label=m['label']):
            # Owner 14 Nov: "why am I not seeing these benchmarks in main chat as they are running" - every step goes to main chat
            # as it happens (and to the live activity), not only the start and the final result.
            bg.step('bench', text)
            with closing(get_connection()) as c2, c2:
                _post(c2, f"🧪 {label}: {text}")
        record = run_model(m, say=say)
        bg.finish('bench')
        with closing(get_connection()) as c, c:
            save(c, record)
            t = record.get('tests', {})
            details = [f"{k}: {'✔' if v['passed'] else '✘'} {v['why']} ({v['seconds']} s)" for k, v in t.items()]
            where = 'on the GPU (already loaded)' if m.get('endpoint') else f"on the CPU, loaded in {record.get('load_s', 0)} s"
            _post(c, (f"🧪 {m['label']} done: {', '.join(record.get('tags') or [])} - {record.get('tok_s', 0)} tok/s {where}."
                      if not record.get('error') else f"🧪 {m['label']} skipped: {record['error']}") + ('\n' + '\n'.join(details) if details else ''))
    try:   # owner 14 Nov: new results update the onboarded agents (status, exam, tags) without anyone asking
        from core import hb_agents
        with closing(get_connection()) as c, c:
            done = hb_agents.onboard_local_models(c, actor='HB after the benchmark')
            _post(c, f"🌱 HB updated {len(done)} local agents from the new benchmark results; /agents shows who is active.")
    except Exception as exc:
        with closing(get_connection()) as c, c:
            _post(c, f"↺ HB could not update the agents after the benchmark ({type(exc).__name__}); /agents onboard-local does it by hand.")


def start(only=None):
    """/bench: run in a background thread. Returns HB's answer."""
    if not _RUNNING.acquire(blocking=False):
        return 'A benchmark is already running; its results appear in main chat.'

    def work():
        try:
            run_all(only)
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-bench', daemon=True).start()
    n = len([m for m in models() if not only or m['label'] in only or set(only) & set(m['aliases'])])
    return f'Benchmarking {n} model(s), one at a time on the CPU; each result appears in main chat and in Studio ("{RECORD_STEP_TITLE[:40]}...").'


def running():
    return _RUNNING.locked()


def request(conn, only=None, actor='owner'):
    """/bench from any process: leave a request; HB's coordinator runs it (so main chat and the live activity show it)."""
    conn.execute('CREATE TABLE IF NOT EXISTS hb_bench_requests(id INTEGER PRIMARY KEY, models TEXT, actor TEXT, at REAL, started REAL)')
    conn.execute('INSERT INTO hb_bench_requests(models, actor, at) VALUES(?,?,?)', (json.dumps(only or []), actor, time.time()))
    n = len([m for m in models() if not only or m['label'] in only or set(only) & set(m['aliases'])])
    return f'HB will benchmark {n} model(s), one at a time on the CPU; each test result appears in main chat and the record in Studio.'


def tick(conn):
    """Coordinator: start a requested benchmark in its own thread."""
    if running() or not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_bench_requests'").fetchone():
        return None
    row = conn.execute('SELECT id, models FROM hb_bench_requests WHERE started IS NULL ORDER BY id LIMIT 1').fetchone()
    if not row:
        return None
    conn.execute('UPDATE hb_bench_requests SET started=? WHERE id=?', (time.time(), row[0]))
    conn.commit()
    return start(json.loads(row[1]) or None)
