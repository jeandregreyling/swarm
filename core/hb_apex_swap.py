"""APEX is a role; the model that plays it is swappable (Practice 152, owner 18 Nov 2026: "the models should be swappable, the global name is
apex, it doesn't matter which model drives apex").

The APEX model server (systemd user service apex-server, port 8080) is configured by HB's drop-in gpu-offload.conf - the same file the GPU
guard (core/hb_gpu_guard) tunes. /apex model <name> changes only the model file (-m) and its chat template in that drop-in; the guard's
--fit margin and every other setting stay. Before the change the drop-in is copied to gpu-offload.conf.before-swap; after the restart HB proves
the server answers, and if it does not, the previous drop-in goes back and APEX restarts on it. The role register (core/hb_roles) records
which model plays APEX. Everything is announced in main chat. JD runs it; nothing here runs by itself.

  candidates()          models that can play APEX: registered llama.cpp models plus EXTRA files, with size and whether they fit the card
  render(text, c)       the drop-in with candidate c's model file and template
  swap(name, ...)       back up, write, reload, restart, check, roll back on failure
  command(conn, args)   /apex, /apex models, /apex model <name>, /apex back
"""
import os
import re
import threading
from pathlib import Path

from core import hb_gpu_guard as guard

CARD_GB = 16.0
HEADROOM_GB = 1.5          # as core/hb_model_bench; --fit puts what does not fit in RAM
EXTRA = {'swift-qwen3.8-27b': '/srv/archive/models/gguf/swift-qwen3.8-27b/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf',
         'qwen2.5-32b-instruct': '/srv/archive/models/gguf/qwen2.5-32b-instruct/Qwen2.5-32B-Instruct-Q4_K_M.gguf',
         # Practice 205 (JD 21 Nov: "there's at least 2 without filters"): Mistral's own models, from HB's HF archive
         'mistral-nemo-12b': '/srv/archive/hf_archive/model/bartowski/Mistral-Nemo-Instruct-2407-GGUF/a2dd64a0a76ea1bdb2bb6ab6fa5496b003c7c908/Mistral-Nemo-Instruct-2407-Q4_K_M.gguf',
         'mistral-nemo-12b-q8': '/srv/archive/hf_archive/model/bartowski/Mistral-Nemo-Instruct-2407-GGUF/a2dd64a0a76ea1bdb2bb6ab6fa5496b003c7c908/Mistral-Nemo-Instruct-2407-Q8_0.gguf',
         'mixtral-8x7b': '/srv/archive/models/gguf/mixtral-8x7b-instruct-v2/Mixtral-8x7B-Instruct-v0.1-Q4_K_M.gguf'}
_busy = threading.Lock()


def candidates():
    out = {}
    try:
        from core.seven_llm import registry
        entries = registry.list_models()
    except Exception:
        entries = []
    for e in entries:
        if getattr(e, 'driver', '') == 'llamacpp' and getattr(e, 'role', '') != 'embed' and e.path and os.path.isfile(e.path):
            out.setdefault(e.path, {'name': e.name, 'path': e.path, 'template': (e.options or {}).get('chat_template_file')})
    for name, path in EXTRA.items():
        if os.path.isfile(path):
            out[path] = {'name': name, 'path': path, 'template': None}
    rows = []
    for c in out.values():
        size = os.path.getsize(c['path']) / 1e9
        rows.append({**c, 'size_gb': round(size, 1), 'fits': size + HEADROOM_GB <= CARD_GB})
    return sorted(rows, key=lambda r: r['name'])


def find(name, rows=None):
    rows = candidates() if rows is None else rows
    name = str(name or '').strip().lower()
    return next((r for r in rows if r['name'].lower() == name), None)


def current(text=None):
    text = guard.dropin().read_text() if text is None else text
    m = re.search(r'-m\s+(\S+)', text)
    return m.group(1) if m else None


def render(text, cand):
    """The drop-in with this candidate's model file and template; everything else as it was."""
    new = re.sub(r'(-m\s+)\S+', lambda m: m.group(1) + cand['path'], text, count=1)
    if cand.get('template'):
        if '--chat-template-file' in new:
            new = re.sub(r'(--chat-template-file\s+)\S+', lambda m: m.group(1) + cand['template'], new, count=1)
        else:
            new = new.replace('--jinja', '--jinja --chat-template-file ' + cand['template'], 1)
    else:
        new = re.sub(r'\s*--chat-template-file\s+\S+', '', new, count=1)
    new = re.sub(r'(Description=APEX )[^\n]*?( (?:Vulkan|ROCm) llama-server)', lambda m: m.group(1) + cand['name'] + m.group(2), new, count=1)
    # The service alias follows the model actually selected, never a prior model.
    new = re.sub(r'^Environment=LLAMA_ARG_ALIAS=.*$',
                 lambda _m: 'Environment=LLAMA_ARG_ALIAS=APEX,' + cand['name'], new, flags=re.M)
    for flag, value in server_args(cand['name']).items():     # Practice 159
        if re.search(r'(?<=\s)' + re.escape(flag) + r'\s+\S+', new):
            new = re.sub(r'((?<=\s)' + re.escape(flag) + r'\s+)\S+', lambda m: m.group(1) + value, new, count=1)
        else:
            new = new.replace('--no-webui', f'{flag} {value} --no-webui', 1)
    for flag in ('-ctk', '-ctv'):   # Practice 192: KV cache types belong to the model that asked for them; a swap removes them
        if flag not in server_args(cand['name']):
            new = re.sub(r'\s' + re.escape(flag) + r'\s+\S+', '', new, count=1)
    try:   # Practice 192: never less than the Ghost reserve margin (JD's desktop keeps 2 GB+ of the GPU); higher spill margins stay
        floor = guard.GHOST_MARGIN_MIB
        current = guard.margin(new)
        if current is not None and current < floor:
            new = guard.with_margin(new, floor)
    except Exception:
        pass
    return new


# Practice 159 (owner 18 Nov 2026, "go"): the card reset twice in 30 minutes, both times while swift-qwen3.8-27b processed a long prompt
# ("comp_1.x ring reset ... device wedged"). It is a dense 27B model; with -b 2048 -ub 1024 one GPU job runs long enough for the kernel's
# compute-ring timeout. gpt-oss:20b is a mixture-of-experts model (~3.6B active per token) and never came close. Each model now gets its
# own batch sizes at a swap; the defaults come back when another model plays APEX.
DEFAULT_ARGS = {'-b': '2048', '-ub': '1024', '-ctk': 'q8_0', '-ctv': 'q8_0'}   # Practice 286: 8-bit KV cache for every APEX model (about twice the window)
ARGS_BY_MODEL = {'swift-qwen3.8-27b': {'-b': '512', '-ub': '256', '-ctk': 'q8_0', '-ctv': 'q8_0'},   # Practice 192: 8-bit KV 'qwen2.5:14b-instruct': {'-b': '1024', '-ub': '512'},
                 'fred-cpu:24b': {'-b': '512', '-ub': '256'}}


def server_args(name):
    return {**DEFAULT_ARGS, **ARGS_BY_MODEL.get(str(name or ''), {})}


def swap(name, say=print, path=None, reload=None, restart=None, answers=None, rows=None):
    """Swap the model that plays APEX. Returns (ok, message)."""
    reload, restart, answers = reload or guard._reload, restart or guard._restart, answers or guard._answers
    path = Path(path) if path else guard.dropin()
    cand = find(name, rows)
    if not cand:
        return False, f'{name} is not a model HB can run as APEX. /apex models lists them.'
    if not cand['fits']:
        return False, f"{cand['name']} needs about {cand['size_gb'] + HEADROOM_GB:.1f} GB and the card has {CARD_GB:.0f} GB - it cannot play APEX."
    if not _busy.acquire(blocking=False):
        return False, 'An APEX swap is already running.'
    try:
        before = path.read_text()
        if render(before, cand) == before:         # Practice 160: same model AND same settings; new settings reload it
            return True, f"APEX is already {cand['name']}."
        path.with_name(path.name + '.before-swap').write_text(before)
        path.write_text(render(before, cand))
        say(f"Swapping APEX to {cand['name']} ({cand['size_gb']} GB). APEX is offline for a minute or two; the previous settings are saved "
            f"as {path.name}.before-swap.")
        if reload() and restart() and answers():
            _record(cand['name'])
            return True, f"APEX is now {cand['name']} and answers. /apex back returns to the previous model."
        path.write_text(before)
        reload()
        restart()
        ok = answers()
        return False, (f"{cand['name']} did not start or did not answer, so HB put the previous model back"
                       + (' - APEX answers again.' if ok else ' - and APEX does not answer yet: check /status.'))
    finally:
        _busy.release()


def back(say=print, path=None, reload=None, restart=None, answers=None, rows=None):
    path = Path(path) if path else guard.dropin()
    saved = path.with_name(path.name + '.before-swap')
    if not saved.exists():
        return False, 'There is no earlier APEX model to go back to.'
    prev = current(saved.read_text())
    rows = candidates() if rows is None else rows
    cand = next((r for r in rows if r['path'] == prev), None)
    return swap(cand['name'], say, path, reload, restart, answers, rows) if cand else (False, 'The earlier model file is no longer on disk.')


def _record(name):
    try:
        from contextlib import closing
        from utils.db._connection import get_connection
        from core import hb_roles
        with closing(get_connection()) as conn:
            hb_roles.assign(conn, 'apex', name, 'hb_apex_swap', known=lambda _m: True)
            conn.commit()
    except Exception:
        pass


# Practice 173 (owner 19 Nov 2026: "putting it through HB would be the cherry on top"): ROCm 10.2 is installed (admin steps A-CC1A70 and
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
                + '\n\nSummarise the notes above in three sentences.')


def _servers(text):
    return re.findall(r'^ExecStart=(\S+)', text, re.M)


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
    new = re.sub(r'(--device\s+)\S+', lambda m: m.group(1) + b['device'], new, count=1)
    return re.sub(r'(Description=APEX \S+ )\S+( llama-server)', lambda m: m.group(1) + b['label'] + m.group(2), new, count=1)


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
    table = (f'| backend | reading tok/s | writing tok/s | answered |\n|---|---|---|---|\n'
             f"| {old} | {a['read']} | {a['write']} | {'yes' if a['ok'] else 'no'} |\n"
             f"| {new} | {b['read']} | {b['write']} | {'yes' if b['ok'] else 'no'} |")
    if b['ok'] and b['read'] > a['read'] and b['write'] > a['write']:
        return True, f'{table}\n{new} is faster at both, so APEX stays on {new}. /apex backend {start} goes back.'
    back_ok, back_msg = switcher(start, say)
    return True, (f'{table}\n{new} was not faster at both (or did not answer every run), so APEX goes back to {old}: '
                  + ('done.' if back_ok else back_msg))


def command(conn, args, actor='owner'):
    """/apex | /apex models | /apex model <name> | /apex back"""
    rows = candidates()
    now = current()
    playing = next((r['name'] for r in rows if r['path'] == now), now)
    if not args:
        p = prefs(conn)
        return (f'APEX is played by {playing}. Preferred by kind: ' + (', '.join(f'{k} -> {m}' for k, m in p.items() if m) or 'none')
                + '. /apex models lists the others; /apex model <name> swaps; /apex back returns; /apex prefer <kind> <model|none>.')
    if args[0].lower() == 'prefer' and len(args) == 3:
        return prefer(conn, args[1].lower(), args[2], actor)
    if args[0].lower() == 'backend' and len(args) == 1:      # Practice 173
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
        return 'Models that can play APEX (16 GB card):\n' + '\n'.join(
            f"- {r['name']}: {r['size_gb']} GB - " + ('fits' if r['fits'] else 'too big for the card') + (' (playing now)' if r['path'] == now else '')
            for r in rows)
    if args[0].lower() in ('model', 'use') and len(args) == 2:
        target = args[1]
    elif args[0].lower() == 'back':
        target = None
    else:
        return 'Use /apex, /apex models, /apex model <name>, /apex back, /apex backend or /apex bench rocm|vulkan.'
    from core.hb_model_bench import _post

    def work():
        from contextlib import closing
        from utils.db._connection import get_connection

        def say(text):
            with closing(get_connection()) as c:
                _post(c, text)
                c.commit()
        ok, msg = back(say) if target is None else swap(target, say)
        say(('Done: ' if ok else 'Not done: ') + msg)
    threading.Thread(target=work, name='hb-apex-swap', daemon=True).start()
    return f"Swapping APEX {'back' if target is None else 'to ' + target} - HB reports in main chat when it answers."

# Practice 153 (owner 18 Nov 2026: "HB should be the one orchestrating this by knowing what the question is about and which model to use").
# Benchmark the same morning (MCB and STP2 questions, two runs each): swift-qwen3.8-27b answered all four perfectly - every MCB fact from the
# notes, all 14 PY-AU-STP notes in its own text, no false "not found" - where gpt-oss:20b was right about half the time; but it took
# 230-330 s and always hit the 360 s turn limit. So: research questions go to the preferred research model (swapped in while APEX is idle,
# announced in main chat); HB never swaps back by itself, so models do not ping-pong; and each model has its own turn time.
DEFAULT_PREFS = {'research': 'swift-qwen3.8-27b'}
TURN_BY_MODEL = {'swift-qwen3.8-27b': 600, 'qwen2.5-32b-instruct': 900}
ROUNDS_BY_MODEL = {'swift-qwen3.8-27b': 20}   # Practice 154; 266: Swift plays APEX now - same 20 rounds as 243
_playing_cache = {'key': None, 'name': None}


def playing():
    """Name of the model that plays APEX now (cached on the drop-in's mtime)."""
    import os
    if os.environ.get('PYTEST_CURRENT_TEST'):
        # Practice 167 (owner 18 Nov 2026, full test run): with the 27B on the card, turn_rounds/turn_seconds gave 9 rounds and 600 s and
        # the loop tests that expect 6 and 360 failed. Tests never depend on the machine's live model; they patch playing() when needed.
        return None
    try:
        p = guard.dropin()
        key = p.stat().st_mtime
    except Exception:
        return None
    if _playing_cache['key'] != key:
        path = current()
        _playing_cache.update(key=key, name=next((r['name'] for r in candidates() if r['path'] == path), path))
    return _playing_cache['name']


def turn_rounds(default=6):
    return ROUNDS_BY_MODEL.get(playing() or '', default)


def turn_seconds(default=360):
    return TURN_BY_MODEL.get(playing() or '', default)


def ensure_prefs(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_apex_prefs(kind TEXT PRIMARY KEY, model TEXT NOT NULL, set_by TEXT, updated_at REAL)')


def prefs(conn):
    ensure_prefs(conn)
    out = dict(DEFAULT_PREFS)
    out.update({k: m for k, m in conn.execute('SELECT kind, model FROM hb_apex_prefs')})
    return out


def prefer(conn, kind, model, actor='owner'):
    import time as _t
    if model.lower() in ('none', 'off', '-'):
        ensure_prefs(conn)
        conn.execute('INSERT OR REPLACE INTO hb_apex_prefs VALUES (?,?,?,?)', (kind, '', actor, _t.time()))
        return f'{kind} questions run on whatever model plays APEX.'
    if not find(model):
        return f'{model} is not a model HB can run as APEX. /apex models lists them.'
    ensure_prefs(conn)
    conn.execute('INSERT OR REPLACE INTO hb_apex_prefs VALUES (?,?,?,?)', (kind, find(model)['name'], actor, _t.time()))
    return f"{kind} questions go to {find(model)['name']}."


def kind_of(text):
    try:
        from core.apex_tools import research_question
        return 'research' if research_question(text) else 'default'
    except Exception:
        return 'default'


# Practice 160 (owner 18 Nov 2026: "shouldn't HB check and review questions before automatically assigning an agent unless I manually pick
# one"): route_for() swapped on a word list, silently, and ignored JD's own picks - an @model in his message and the On/Off/Auto switches in
# Live status. Now JD's pick wins, and otherwise HB reviews the question first (kind, the topic words, how well the Knowledge Centre covers
# it) and says in one line what it decided and why before APEX starts.
def manual_pick(text, modes=None, rows=None):
    """(model, how) when JD chose: an @model in the message, or a model switched On in Live status; else (None, '')."""
    rows = candidates() if rows is None else rows
    names = {r['name'].lower(): r['name'] for r in rows}
    for m in re.findall(r'@([\w.:-]+)', str(text or '')):
        if m.lower() in names:
            return names[m.lower()], f'you named {names[m.lower()]} with @'
    if modes is None:
        try:
            from core.hb_model_switches import current_modes
            modes = current_modes()
        except Exception:
            modes = {}
    on = [names[m.lower()] for m, mode in (modes or {}).items() if mode == 'on' and m.lower() in names]
    return (on[0], f'{on[0]} is switched On in Live status') if on else (None, '')


def review(text, search=None):
    """HB's look at a question before it assigns a model: {kind, terms, strong, total, plan}."""
    kind = kind_of(text)
    out = {'kind': kind, 'terms': [], 'strong': 0, 'total': 0, 'plan': ''}
    if kind != 'research':
        return out
    try:
        from core.apex_knowledge import focus_words
        out['terms'] = focus_words(text)[:6]
        result = (search or __import__('core.apex_knowledge', fromlist=['search']).search)(' '.join(out['terms']) or str(text)[:200])
        matches = [str(m) for m in result.get('matches') or []]
        out['total'] = len(matches)
        words = [w.lower() for w in out['terms']]
        out['strong'] = sum(1 for m in matches if sum(1 for w in words if w in m.split(' | ')[0].lower()) >= max(1, min(2, len(words))))
    except Exception:
        pass
    out['plan'] = ('our notes look relevant - APEX reads them first' if out['strong'] >= 2 else
                   'our notes have no strong match - APEX also searches public SAP pages and HB keeps what it finds')
    return out


def route_for(conn, text, say=print, idle=None, swapper=None, modes=None, search=None):
    """Before an APEX turn: honour JD's pick, else review the question, say what HB decided, and swap in the model for that kind of
    question when it is not playing (APEX idle only). Returns what HB did, or ''."""
    have = playing()
    picked, how = manual_pick(text, modes)
    if picked:
        if not have or picked.lower() == str(have).lower() or not (idle or guard._idle)():
            return ''
        say(f'HB: {how}, so APEX switches to {picked} (a minute or two).')
        ok, msg = (swapper or swap)(picked, say)
        return msg if ok else f'{msg} HB answers with {have}.'
    r = review(text, search)
    want = prefs(conn).get(r['kind']) or ''
    try:
        from core.hb_model_switches import current_modes
        if want and (modes if modes is not None else current_modes()).get(want) == 'off':
            want = ''                                       # switched Off by JD: never swapped in
    except Exception:
        pass
    if r['kind'] == 'research':
        about = ', '.join(r['terms']) or 'your question'
        model_part = (f'{want} handles research better than {have}, so HB swaps APEX first (a minute or two)'
                      if want and have and want.lower() != str(have).lower() else f'{have} answers')
        say(f"HB review: research question ({about}) - {r['plan']} - {model_part}. Name a model with @ to choose yourself.")
    if not want or not have or want.lower() == str(have).lower():
        return ''
    if not (idle or guard._idle)():
        return ''
    ok, msg = (swapper or swap)(want, say)
    return msg if ok else f'{msg} HB answers with {have}.'


# Practice 161 (owner 18 Nov 2026: "I don't want to manually swap models, this should be done via HB automatically"): Practice 159 gave
# the 27B smaller GPU batches, but they only took effect at a swap, so the card kept resetting until JD would type /apex. settings_tick():
# when the model playing APEX runs with settings other than HB prescribes for it, HB reloads it itself while APEX is idle (backup, check,
# roll back - the same swap), at most once per SETTINGS_GAP_S, and says so in main chat.
SETTINGS_GAP_S = 1800


def settings_tick(conn, now=None, idle=None, swapper=None, say=None, rows=None, text=None):
    import time as _t
    now = now or _t.time()
    conn.execute('CREATE TABLE IF NOT EXISTS hb_apex_settings_reload(at REAL, model TEXT, ok INTEGER)')
    last = conn.execute('SELECT MAX(at) FROM hb_apex_settings_reload').fetchone()[0]
    if last and now - last < SETTINGS_GAP_S:
        return None
    try:
        text = guard.dropin().read_text() if text is None else text
    except Exception:
        return None
    rows = candidates() if rows is None else rows
    path = current(text)
    cand = next((r for r in rows if r['path'] == path), None)
    if not cand or render(text, cand) == text or not (idle or guard._idle)():
        return None
    if say is None:
        from core.hb_model_bench import _post
        def say(msg):                                    # committed at once: no write lock held during the reload
            _post(conn, msg)
            conn.commit()
    say(f"HB: {cand['name']} plays APEX with older settings than HB now uses for it - reloading it with "
        + ', '.join(f'{k} {v}' for k, v in server_args(cand['name']).items()) + ' while APEX is idle (a minute or two).')
    ok, msg = (swapper or swap)(cand['name'], say)
    conn.execute('INSERT INTO hb_apex_settings_reload VALUES (?,?,?)', (now, cand['name'], int(ok)))
    say(('Done: ' if ok else 'Not done: ') + msg)
    return msg


