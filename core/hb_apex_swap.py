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
         'qwen2.5-32b-instruct': '/srv/archive/models/gguf/qwen2.5-32b-instruct/Qwen2.5-32B-Instruct-Q4_K_M.gguf'}
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
            out.setdefault(path, {'name': name, 'path': path, 'template': None})
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
    new = re.sub(r'(Description=APEX )[^\n]*?( Vulkan llama-server)', lambda m: m.group(1) + cand['name'] + m.group(2), new, count=1)
    for flag, value in server_args(cand['name']).items():     # Practice 159
        if re.search(r'(?<=\s)' + re.escape(flag) + r'\s+\S+', new):
            new = re.sub(r'((?<=\s)' + re.escape(flag) + r'\s+)\S+', lambda m: m.group(1) + value, new, count=1)
        else:
            new = new.replace('--no-webui', f'{flag} {value} --no-webui', 1)
    return new


# Practice 159 (owner 18 Nov 2026, "go"): the card reset twice in 30 minutes, both times while swift-qwen3.8-27b processed a long prompt
# ("comp_1.x ring reset ... device wedged"). It is a dense 27B model; with -b 2048 -ub 1024 one GPU job runs long enough for the kernel's
# compute-ring timeout. gpt-oss:20b is a mixture-of-experts model (~3.6B active per token) and never came close. Each model now gets its
# own batch sizes at a swap; the defaults come back when another model plays APEX.
DEFAULT_ARGS = {'-b': '2048', '-ub': '1024'}
ARGS_BY_MODEL = {'swift-qwen3.8-27b': {'-b': '512', '-ub': '256'}, 'qwen2.5:14b-instruct': {'-b': '1024', '-ub': '512'},
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
        if current(before) == cand['path']:
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
    if args[0].lower() == 'models':
        return 'Models that can play APEX (16 GB card):\n' + '\n'.join(
            f"- {r['name']}: {r['size_gb']} GB - " + ('fits' if r['fits'] else 'too big for the card') + (' (playing now)' if r['path'] == now else '')
            for r in rows)
    if args[0].lower() in ('model', 'use') and len(args) == 2:
        target = args[1]
    elif args[0].lower() == 'back':
        target = None
    else:
        return 'Use /apex, /apex models, /apex model <name> or /apex back.'
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
ROUNDS_BY_MODEL = {'swift-qwen3.8-27b': 9}   # Practice 154
_playing_cache = {'key': None, 'name': None}


def playing():
    """Name of the model that plays APEX now (cached on the drop-in's mtime)."""
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


def route_for(conn, text, say=print, idle=None, swapper=None):
    """Before an APEX turn: if this kind of question has a preferred model that is not playing, swap it in (APEX idle only).
    Returns what HB did, or ''."""
    kind = kind_of(text)
    want = prefs(conn).get(kind) or ''
    have = playing()
    if not want or not have or want.lower() == str(have).lower():
        return ''
    if not (idle or guard._idle)():
        return ''
    say(f'HB: this is a {kind} question - {want} handles those better than {have}, so HB swaps APEX first (a minute or two).')
    ok, msg = (swapper or swap)(want, say)
    return msg if ok else f'{msg} HB answers with {have}.'

