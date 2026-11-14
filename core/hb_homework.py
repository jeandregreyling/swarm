"""Homework on the CPU (owner 14 Nov 2026): small models scope and spec a task before the GPU model runs it.

"The system takes a prompt from me and scopes and specs and updates it, and when the GPU model picks it up most of the homework
is already done. We don't need to use the GPU for everything; there's 64 GB of RAM."

For each task coming up in HB's queue (and each new piece of work JD types), HB writes a SPEC CARD in the background:

  1 facts  HB's own tools, no model: files named in the request that exist, and the exact matching lines for its distinctive words
           (git grep), the step's existing "Done when" lines and Studio test cases. Long files are never pushed through a model.
  2 card   a CPU model (homework-cpu:7b: Qwen 2.5 7B in system RAM, no GPU) turns request + facts into JSON: goal, check, plan,
           relevant files (only from the facts), open questions, suggested doer, importance.
  3 ready  HB decides, by rule: a goal, a CONCRETE check (a test, a command or a visible behaviour - not "verify it works"),
           and at least one real file (or HB itself as the doer). Only a ready card lets a task skip the GPU scoping turn.

The card is a task event ('spec_card'). The DREAM clipboard shows it to APEX, the workflow uses its check and plan instead of
spending a GPU turn on scoping, and the clipboard (core/hb_clipboard.py) shows Ready, the doer and the importance.
One homework job at a time, in its own thread; never while Fred (the other CPU model) is working or RAM is short.
"""
import json
import re
import subprocess
import threading
import time
from contextlib import closing
from pathlib import Path

from core import hb_tasks

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'homework-cpu:7b'
DOERS = ('hb', 'small', 'apex', 'fred')
LOOKAHEAD = 3
_RUNNING = threading.Lock()
_PATH = re.compile(r'(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|js|css|html|json|md|sh|yaml|yml|txt|toml|service))\b')
_IDENT = re.compile(r'\b([A-Za-z_][\w]*_[\w]+|[a-z]+[A-Z]\w+|[\w-]+\.(?:js|py))\b')
_CONCRETE = re.compile(r'(pytest|tests?/|test_\w+|\brun_tests\b|\bnode\b|--check|\.py\b|\.js\b|`[^`]+`|"[^"]{3,}"|\bshows?\b|\bappears?\b|'
                       r'\breturns?\b|\bexit code\b|\bpasses\b|\bcurl\b|/api/)', re.I)
_VAGUE = re.compile(r'^\s*(verify|ensure|make sure|check)( that)? (it|everything|the (change|feature|fix)s?) (works?|is correct|is done)\b', re.I)


# ------------------------------------------------------------------ 1 facts (HB tools, no model)
def _git_grep(word, limit=4):
    try:
        # --untracked: much of HB is not committed yet; only exclusions that exist (git refuses a missing path)
        out = subprocess.run(['git', '-C', str(ROOT), 'grep', '--untracked', '-n', '-I', '-i', '-F', '-m', str(limit), '--', word,
                              ':!*.db', ':!*.min.js', ':!*.orig', *[f':!{d}/' for d in ('runtime', 'archive', 'logs') if (ROOT / d).is_dir()]],
                             capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split(':', 2)
        if len(parts) == 3 and parts[1].isdigit():
            rows.append((parts[0], int(parts[1]), parts[2].strip()[:200]))
    return rows


def facts(conn, task, max_files=6):
    text = f"{task.get('title') or ''}\n{task.get('objective') or ''}"
    files = {}
    for path in _PATH.findall(text):
        if (ROOT / path).is_file() and path not in files:
            files[path] = []
    words = []
    for word in _IDENT.findall(text) + re.findall(r'"([^"\n]{4,60})"', text):
        if word not in words and not re.fullmatch(r'[ST]-[0-9A-F]+', word):
            words.append(word)
    for word in words[:8]:
        hits = _git_grep(word)
        files_hit = {p for p, _, _ in hits}
        if not hits or len(files_hit) > 15:
            continue                                     # not distinctive enough to point anywhere
        for path, number, line in hits:
            if len(files) >= max_files and path not in files:
                continue
            files.setdefault(path, [])
            if len(files[path]) < 4 and (number, line) not in files[path]:
                files[path].append((number, line))
    from core.hb_dream_method import done_when
    source, criteria = done_when(conn, task)
    return {'files': [{'path': p, 'lines': [{'n': n, 'text': t} for n, t in lines]} for p, lines in list(files.items())[:max_files]],
            'done_when': criteria, 'done_source': source}


# ------------------------------------------------------------------ 2 card (CPU model)
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['goal', 'check', 'plan', 'files', 'questions', 'doer', 'importance', 'why'],
          'properties': {'goal': {'type': 'string', 'maxLength': 300}, 'check': {'type': 'string', 'maxLength': 300},
                         'plan': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string', 'maxLength': 240}},
                         'files': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string', 'maxLength': 200}},
                         'questions': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'maxLength': 200}},
                         'doer': {'type': 'string', 'enum': list(DOERS)},
                         'importance': {'type': 'integer', 'minimum': 1, 'maximum': 5},
                         'why': {'type': 'string', 'maxLength': 300}}}


def prompt(task, gathered):
    from core.hb_master_prompt import for_role
    system = (for_role('default') + '\nYou are HB\'s homework model. You never change anything. You turn one task into a precise spec card '
              'so the GPU model can start with the reading and thinking done. Rules: goal = one sentence of what JD wants. check = ONE '
              'concrete check that proves it is done: a test file or command to run, or an exact visible behaviour ("the header shows ..."); '
              'never "verify it works". plan = 2-6 short steps, the first doable at once. files = only paths from the facts below that the '
              'work really touches. questions = only real blockers that need JD; usually none. doer: hb if an HB command or tool does it '
              'without a model, small for text-only work, apex for code changes, fred only for a hard review. importance 1-5 (5 = blocks '
              'other work or JD is waiting). why = one line on the doer and importance. Answer JSON only.')
    user = json.dumps({'task': str(task.get('title') or '')[:200], 'request': str(task.get('objective') or '')[:2500], 'facts': gathered})
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def call_model(messages):
    from core import llm
    from core.seven_llm import registry
    entry = registry.get(MODEL)
    text, _ = llm.chat_via_gateway(MODEL, messages, temperature=0.1, absolute_timeout_s=600, idle_timeout_s=300, queue_timeout_s=10,
                                   keep_alive=900, options={'num_ctx': entry.ctx if entry else 8192, 'num_predict': 600, 'timeout': 600,
                                                            'startup_timeout': 240, 'require_complete_output': True},
                                   response_format={'type': 'json_schema', 'json_schema': {'name': 'hb_spec_card', 'strict': True,
                                                                                            'schema': SCHEMA}})
    return json.loads(text)


# ------------------------------------------------------------------ 3 ready (HB's rule)
def judge(card, gathered):
    """HB, not the model, decides whether a card is ready. Returns (ready, reasons)."""
    known = {f['path'] for f in gathered['files']}
    card['files'] = [p for p in card.get('files') or [] if p in known] or ([f['path'] for f in gathered['files']][:3] if card.get('doer') == 'apex' else [])
    reasons = []
    if len(str(card.get('goal') or '').strip()) < 8:
        reasons.append('no clear goal')
    check = str(card.get('check') or '').strip()
    if not check or _VAGUE.match(check) or not _CONCRETE.search(check):
        reasons.append('the check is not concrete (name a test, a command or an exact visible behaviour)')
    if card.get('doer') != 'hb' and not card['files']:
        reasons.append('no real file found for the work')
    if card.get('questions'):
        reasons.append('open question for JD: ' + '; '.join(card['questions'])[:200])
    return not reasons, reasons


def latest(conn, task):
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='spec_card' ORDER BY event_id DESC LIMIT 1",
                       (task['task_id'],)).fetchone()
    try:
        card = json.loads(row[0]) if row else None
    except (TypeError, ValueError):
        return None
    return card if card and card.get('task_version') == task.get('version') else None


def write(conn, task, model=call_model):
    """Do the homework for one task now. Returns the card (saved as a 'spec_card' task event)."""
    from core import hb_background as bg
    bg.start('homework', task, MODEL, f"writing the spec card for {str(task.get('title') or '')[:70]}", conn)
    gathered = facts(conn, task)
    bg.step('homework', f"found {len(gathered['files'])} file(s) with HB's tools; asking {MODEL} for the card")
    started = time.time()
    try:
        card = model(prompt(task, gathered))
    except Exception as exc:                             # the GPU model can still scope it the old way
        card = {'goal': '', 'check': '', 'plan': [], 'files': [], 'questions': [], 'doer': 'apex', 'importance': 3,
                'why': f'homework model failed: {str(exc)[:160]}'}
    if gathered['done_when'] and not card.get('check'):
        card['check'] = gathered['done_when'][0]
    ready, reasons = judge(card, gathered)
    card.update(ready=ready, not_ready=reasons, facts=gathered, model=MODEL, seconds=round(time.time() - started, 1),
                task_version=task.get('version'))
    hb_tasks.event(conn, task, 'homework', 'spec_card', card)
    bg.finish('homework', conn, task, (f"📝 Homework card for {str(task.get('title') or '')[:70]}: READY - check: {card.get('check')}"
                                       if ready else f"📝 Homework card for {str(task.get('title') or '')[:70]}: not ready - {'; '.join(reasons)[:160]}"))
    return card


def summary(card):
    """The card as a few lines for APEX's DREAM clipboard."""
    if not card:
        return ''
    lines = [f"Homework (spec card by {card.get('model')} on the CPU; {'READY' if card.get('ready') else 'not ready: ' + '; '.join(card.get('not_ready') or [])}):",
             f"- goal: {card.get('goal')}", f"- check: {card.get('check')}"]
    if card.get('plan'):
        lines.append('- plan: ' + ' | '.join(f'{n}. {p}' for n, p in enumerate(card['plan'], 1)))
    for f in (card.get('facts') or {}).get('files', []):
        if f['path'] in (card.get('files') or []):
            lines.append(f"- {f['path']}: " + '; '.join(f"L{x['n']} {x['text'][:90]}" for x in f['lines'][:3]))
    return '\n'.join(lines)[:1600]


# ------------------------------------------------------------------ background runner
def candidates(conn):
    """Tasks that need homework next: the queue's coming steps without done criteria, then new work JD typed (last 24 h)."""
    from core import hb_plan_workflow as wf
    from core.hb_dream_method import done_when
    from core.hb_owner_intent import is_chat_task
    out = []
    w = wf.settings(conn) or {}
    upcoming = [s for s in wf.steps(conn) if s['task_id'] and s['step_id'] != w.get('step_id')
                and not str(s['skip'] or '').startswith(('not APEX', 'blocked'))][:LOOKAHEAD]
    for s in upcoming:
        task = hb_tasks.get(conn, s['task_id'])
        if task and not done_when(conn, task)[1] and not latest(conn, task):
            out.append(task)
    for (tid,) in conn.execute("SELECT task_id FROM hb_tasks WHERE step_id IS NOT NULL AND project_id<>? AND state IN ('active','todo') "
                               "AND created_at>? ORDER BY created_at DESC LIMIT 5", (wf.DEFAULT_PROJECT, time.time() - 86400)):
        task = hb_tasks.get(conn, tid)
        from core.hb_owner_intent import classify
        if classify(task['objective'] if task else ''):
            continue                                     # a remark or go-ahead that became a task before 14 Nov: no homework
        if task and not is_chat_task(task) and not latest(conn, task) and task not in out:
            out.append(task)
    return out


def can_run(conn):
    from core.hb_model_switches import current_modes
    if current_modes().get(MODEL) == 'off':
        return False, 'homework model switched Off'
    if conn.execute("SELECT name FROM sqlite_master WHERE name='hb_local_jobs'").fetchone() and conn.execute(
            "SELECT 1 FROM hb_local_jobs WHERE status='running'").fetchone():
        return False, 'Fred is using the CPU'
    try:
        available = next(int(l.split()[1]) / 1024 ** 2 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
    except (OSError, StopIteration):
        available = 0
    return (available >= 5.5 + 8, f'{available:.0f} GB RAM free')


def tick(conn):
    """Coordinator tick: start one homework job in its own thread when there is homework and room for it."""
    if not _RUNNING.acquire(blocking=False):
        return None
    try:
        todo = candidates(conn)
        ok, why = can_run(conn) if todo else (False, 'nothing to do')
    except Exception:
        _RUNNING.release()
        raise
    if not todo or not ok:
        _RUNNING.release()
        return None
    task_id = todo[0]['task_id']

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                task = hb_tasks.get(own, task_id)
                if task and not latest(own, task):
                    write(own, task)
        except Exception:
            import logging
            logging.getLogger('hb.homework').exception('homework failed for %s', task_id)
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-homework', daemon=True).start()
    return task_id
