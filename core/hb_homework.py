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
from core.hb_roles import model_for
MODEL = model_for('homework')   # owner 14 Nov: roles, not names (core/hb_roles.py)
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


ANY_PATH = re.compile(r'\b[\w-]+(?:/[\w.-]+)+\.(?:py|js|html|css|json|md|sh)\b')   # Practice 294


def test_files(text, root=None):
    """Practice 294 (JD 22 Nov: the BA's spec 'just doesn't look right'): it invented ui/status_drawer.py because it was never shown the real
    files. The step's Done-when test names them (ROOT / 'frontend/static/js/hb-live.js'): the test and every real file it references."""
    root = root or ROOT
    out = {}
    for t in re.findall(r'tests/[\w/.-]+\.py', str(text or '')):
        p = root / t
        if not p.is_file() or t in out:
            continue
        out[t] = []
        body = p.read_text(errors='replace')
        mods = re.findall(r'^\s*from ((?:core|utils|frontend|scripts)(?:\.\w+)*) import ([\w ,()]+)', body, re.M)   # Practice 295: imports
        refs = list(ANY_PATH.findall(body))
        for pkg, names in mods:
            refs.append(pkg.replace('.', '/') + '.py')
            refs += [pkg.replace('.', '/') + '/' + n.strip() + '.py' for n in re.split(r'[,()\s]+', names) if n.strip() and ' as ' not in n]
        for ref in refs:
            if ref not in out and not ref.startswith('tests/') and (root / ref).is_file():
                out[ref] = []
    return out


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
    files = {**test_files(text + '\n' + '\n'.join(str(c) for c in criteria or [])), **files}   # Practice 294: the test's own files first
    file_entries = []
    for p, lines in list(files.items())[:max_files]:
        total = None
        try:
            full = ROOT / p
            if full.is_file():
                total = sum(1 for _ in full.open('rb'))
        except OSError:
            pass
        entry = {'path': p, 'lines': [{'n': n, 'text': t} for n, t in lines]}
        if total is not None:
            entry['total_lines'] = total
        file_entries.append(entry)
    kc_notes = []
    try:
        from core.apex_knowledge import search as kc_search
        q = str(task.get('title') or '').strip()[:120]
        if len(q) >= 3:
            for item in kc_search(q).get('items', [])[:3]:
                kc_notes.append({'id': item.get('document_id'), 'title': str(item.get('title') or '')[:120],
                                 'excerpt': str(item.get('excerpt') or '')[:220]})
    except Exception:
        pass
    return {'files': file_entries, 'kc_notes': kc_notes, 'done_when': criteria, 'done_source': source}


# ------------------------------------------------------------------ 2 card (CPU model)
SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['goal', 'scope_in', 'scope_out', 'design', 'risks', 'check', 'plan', 'files', 'questions', 'doer', 'importance', 'why'],
          'properties': {'goal': {'type': 'string', 'maxLength': 300}, 'check': {'type': 'string', 'maxLength': 300},
                         'scope_in': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string', 'maxLength': 200}},   # Practice 284: the BA's spec
                         'scope_out': {'type': 'array', 'maxItems': 5, 'items': {'type': 'string', 'maxLength': 200}},
                         'design': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string', 'maxLength': 240}},
                         'risks': {'type': 'array', 'maxItems': 4, 'items': {'type': 'string', 'maxLength': 200}},
                         'plan': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string', 'maxLength': 240}},
                         'files': {'type': 'array', 'maxItems': 6, 'items': {'type': 'string', 'maxLength': 200}},
                         'questions': {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'maxLength': 200}},
                         'doer': {'type': 'string', 'enum': list(DOERS)},
                         'importance': {'type': 'integer', 'minimum': 1, 'maximum': 5},
                         'why': {'type': 'string', 'maxLength': 300}}}


BA_METHOD = "You are HB's business analyst (BA). You never change anything. Like a good BA you interrogate one task before anyone builds it, in this order: 1. GOAL - what JD really wants, in one sentence (goal). 2. SCOPE - what is in (scope_in) and what is explicitly out (scope_out), so APEX does not wander. 3. DESIGN - which files and functions from the facts change and how, one line each (design). 4. RISKS - what could break or is unknown (risks); a real blocker that only JD can answer goes in questions, usually none. 5. CHECK - ONE concrete check that proves it is done (check). 6. CHUNKS - the plan APEX works one chunk at a time (plan). Then write the spec card so the GPU model can start with the reading and thinking done. Rules: "   # Practice 284


def prompt(task, gathered, rejected=None):
    from core.hb_master_prompt import for_role
    system = (for_role('default') + '\n' + BA_METHOD + 'goal = one sentence of what JD wants. check = ONE '
              'concrete check that proves it is done: a test file or command to run, or an exact visible behaviour ("the header shows ..."); '
              'never "verify it works". plan = 2-6 short steps, the first doable at once. files = only paths from the facts below that the '
              'work really touches. questions = only real blockers that need JD; usually none. doer: hb if an HB command or tool does it '
              'without a model, small for text-only work, apex for code changes, fred only for a hard review. importance 1-5 (5 = blocks '
              'other work or JD is waiting). why = one line on the doer and importance. Answer JSON only.'
              ' Plan rules (Practice 282 - HB turns each plan step into one chunk for APEX, a 12B model that reads 100 lines at a time): each step is ONE action on ONE named file or test from the facts or the request, starting with a verb (run, read, write, add, fix, change, remove); say where (file, line range within total_lines, and the function or section) so APEX reads the exact section ONCE instead of hunting. Leverage facts.kc_notes from the Knowledge Centre when relevant. never invent a path that is not in the facts or the request. No vague steps: never ensure, verify that, make sure, update the necessary, improve, enhance. If the request names test files in its Done when line, use one step per test file: make tests/x.py pass: run it, read the first failure, read those exact lines, patch only them, run it again; the last step runs them all. GOOD plan: ["run tests/test_hb_phone_flow.py and read the first failure", "in core/hb_channels.py fix _reply_target so a follow-up keeps its question", "run tests/test_hb_phone_flow.py again until it passes"]. BAD plan (HB rejects it): ["Update hb-live.js to include the necessary API endpoints", "Ensure that the tests pass", "Add tests in tests/test_new_thing.py" (a file that does not exist and is not asked for)]. If your_last_card_was_rejected_because is given, fix exactly those points.')
    ask = {'task': str(task.get('title') or '')[:200], 'request': str(task.get('objective') or '')[:2500], 'facts': gathered}
    if rejected:      # Practice 282: corrected, not left to repeat itself
        ask['your_last_card_was_rejected_because'] = list(rejected)[:6]
    user = json.dumps(ask)
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def call_model(messages):
    from core import llm
    from core.seven_llm import registry
    entry = registry.get(MODEL)
    text, _ = llm.chat_via_gateway(MODEL, messages, temperature=0.1, absolute_timeout_s=600, idle_timeout_s=300, queue_timeout_s=10,
                                   keep_alive=900, options={'num_ctx': entry.ctx if entry else 8192, 'num_predict': 1000, 'timeout': 600,
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
    reasons += plan_problems(card.get('plan') or [], known, gathered, card)   # Practice 282/294: HB judges the plan, scope and design
    if not [s for s in card.get('scope_in') or [] if str(s).strip()]:   # Practice 284: a BA spec says what is in scope
        reasons.append('no scope: say what is in (scope_in) and what is out (scope_out)')
    elif card.get('doer') != 'hb' and not any(p in str(d) or p.rsplit('/', 1)[-1] in str(d) for d in card.get('design') or [] for p in known):
        reasons.append('the design names no real file: say which file and function from the facts change and how')
    return not reasons, reasons


_VAGUE_STEP = re.compile(r'\b(ensure|verify that|make sure|the necessary|improve|enhance|as needed|appropriate(ly)?|the (whole )?test suite|all (the )?tests)\b', re.I)
_PATH = re.compile(r'\b(?:core|tests|frontend|scripts|utils|agents|fridays|runtime|docs)/[\w/-]+(?:\.[\w-]+)*\.(?:py|js|html|css|json|md|sh|txt)\b')   # Practice 283: files, not module.function


def plan_problems(plan, known, gathered, card_extra=None):
    """Practice 282: a plan step must be one concrete action; vague steps and paths that exist nowhere are named back to homework."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    asked = ' '.join(str(x) for x in gathered.get('done_when') or []) + ' ' + str(gathered.get('request') or '')
    out = []
    for key, items in (('scope', (card_extra or {}).get('scope_in') or []), ('design', (card_extra or {}).get('design') or [])):   # Practice 294
        for item in items:
            for p in ANY_PATH.findall(str(item)):
                if p not in known and p not in asked and not (root / p).exists():
                    out.append(f'the {key} names {p}, which does not exist - use the real files from the facts')
    for n, step in enumerate(plan, 1):
        s = str(step)
        if _VAGUE_STEP.search(s) and not (ANY_PATH.search(s) and re.search(r'\b\w+\(|\b_?\w+_\w+\b', s)):   # Practice 295: a step naming file and function is concrete
            out.append(f'plan step {n} is vague: "{s[:80]}" - say the one action and where')
        for p in set(_PATH.findall(s)) | set(ANY_PATH.findall(s)):
            if p not in known and p not in asked and not (root / p).exists():
                out.append(f'plan step {n} names {p}, which does not exist and is not asked for')
    return out[:6]


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
    last = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='spec_card' ORDER BY event_id DESC LIMIT 1",
                        (task['task_id'],)).fetchone()
    try:
        rejected = (json.loads(last[0]).get('not_ready') or []) if last else []
    except (TypeError, ValueError):
        rejected = []
    try:
        card = model(prompt(task, gathered, rejected=rejected))   # Practice 282: told why its last card was rejected
    except Exception as exc:                             # the GPU model can still scope it the old way
        card = {'goal': '', 'check': '', 'plan': [], 'files': [], 'questions': [], 'doer': 'apex', 'importance': 3,
                'why': f'homework model failed: {str(exc)[:160]}'}
    if gathered['done_when'] and not card.get('check'):
        card['check'] = gathered['done_when'][0]
    ready, reasons = judge(card, gathered)
    card.update(ready=ready, not_ready=reasons, facts=gathered, model=MODEL, seconds=round(time.time() - started, 1),
                task_version=task.get('version'))
    hb_tasks.event(conn, task, 'homework', 'spec_card', card)
    try:   # Practice 293 (JD 22 Nov: the BA was "not actually reporting on the scope or main question or chunks and details"): the spec in main chat
        from core.hb_chat import owner_chat
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (owner_chat(conn), spec_post(task, card)))
    except Exception:
        pass
    handoff(conn, task, card)                            # Practice 113: a READY backlog card goes to APEX
    bg.finish('homework', conn, task, (f"📝 BA spec for {str(task.get('title') or '')[:70]}: READY - check: {card.get('check')}"
                                       if ready else f"📝 BA spec for {str(task.get('title') or '')[:70]}: not ready - {'; '.join(reasons)[:160]}"))
    return card


# Practice 113 (owner 16 Nov 2026): "the little bots should be doing some more specs on them to add to APEX to work on properly". Homework
# only carded APEX's own coming steps; the 15 open living-plan steps owned by claude-code never got a spec (last card: 16 Nov 09:03).
# Now those get a task so homework can card them, two at a time; a READY card (concrete goal and check) hands the step to APEX with the
# spec written into it. JD's own steps and steps that were carded before are left alone.
BACKLOG_OWNERS = ('claude-code',)
_SKIP = {}            # Practice 115: step_id -> when binding its homework task failed; skipped for SKIP_S
SKIP_S = 3600


def backlog(conn, limit=2):
    """Open living-plan steps owned by claude-code with no spec card yet: their tasks (made when missing)."""
    from core import hb_plan_workflow as wf
    from core.hb_chat import owner_chat
    from core.hb_plain import message
    out = []
    marks = ','.join('?' * len(BACKLOG_OWNERS))
    rows = conn.execute(f"SELECT step_id, title, description FROM project_steps WHERE project_id=? AND status IN ('todo','partial') "
                        f"AND owner IN ({marks}) ORDER BY rowid", (wf.DEFAULT_PROJECT, *BACKLOG_OWNERS)).fetchall()
    for step_id, title, desc in rows:
        if len(out) >= limit:
            break
        if time.time() - _SKIP.get(step_id, 0) < SKIP_S:
            continue
        if conn.execute("SELECT 1 FROM hb_task_events e JOIN hb_tasks t ON t.task_id=e.task_id WHERE t.step_id=? AND e.kind='spec_card'",
                        (step_id,)).fetchone():
            continue                                     # carded before: never twice
        try:   # Practice 293: a step with a prepared change set is already specced and built - no BA spec for it
            from core import hb_change_sets
            if hb_change_sets.load(step_id):
                continue
        except Exception:
            pass
        row = conn.execute("SELECT task_id FROM hb_tasks WHERE step_id=? AND state NOT IN ('completed','cancelled') "
                           "ORDER BY created_at DESC LIMIT 1", (step_id,)).fetchone()
        if row:
            task = hb_tasks.get(conn, row[0])
        else:
            chat = owner_chat(conn)
            mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                               "VALUES (?,'hummingbird','user',?,'response',0)",
                               (chat, message(f'📐 BA: HB\'s business analyst specs "{str(title)[:120]}" (scope, design, check, chunks) so APEX can work on it.',
                                              details=[f'Studio step {step_id}']))).lastrowid
            # Practice 115 (owner 16 Nov 2026): bind() links only APEX's own steps to Studio ("Selected Studio step is not assigned to
            # APEX"), and the line above was already posted - so every 6 s HB posted it again and failed again (30 lines in 3 minutes).
            # Homework's task is bound without that check and carries its step itself; any failure removes the line and skips the step.
            try:
                task = hb_tasks.bind(conn, chat, mid, objective=f'Studio step {step_id} ({wf.DEFAULT_PROJECT}): {title}\n{desc or ""}',
                                     title=f'{step_id} {title}'[:140], studio=False)
                conn.execute('UPDATE hb_tasks SET project_id=?, step_id=? WHERE task_id=?', (wf.DEFAULT_PROJECT, step_id, task['task_id']))
                task = hb_tasks.get(conn, task['task_id'])
            except Exception:
                conn.execute('DELETE FROM messages WHERE id=?', (mid,))
                _SKIP[step_id] = time.time()
                continue
        if task and not latest(conn, task):
            out.append(task)
    return out


def handoff(conn, task, card):
    """A READY card on a backlog step: the step goes to APEX with the spec written into it. Returns True/False, or None when not a backlog step."""
    step_id = task.get('step_id') if task else None
    row = conn.execute('SELECT owner, title, description FROM project_steps WHERE step_id=?', (step_id,)).fetchone() if step_id else None
    if not row or row[0] not in BACKLOG_OWNERS or not card.get('ready'):
        return None if not row or row[0] not in BACKLOG_OWNERS else False
    # Practice 116 (monitoring 16 Nov 21:52): a READY card for "Daily grounding" had the check "HB's self-check passes, the sundial
    # shows the current day name" - APEX found nothing to run, said it was blocked, and Fred took the CPU. APEX only gets a step whose
    # check it can run (a test or a command, the workflow's own runnable_check); otherwise the spec stays on the step for Claude Code.
    from core.hb_plan_workflow import runnable_check
    if not runnable_check(card.get('check')):
        return False
    # Practice 122 (monitoring 17 Nov 03:35): an audit-fix card for aig_focus.js had the check "npm run lint ..." - a command, so
    # runnable_check passed, but there is no package.json. APEX applied the spec and broke _surfaceFromNode (an early return skipped
    # the window fallback); a syntax check would not have caught it either. APEX now only gets a step whose check names an existing
    # test file, so the behaviour is verified; everything else stays with Claude Code.
    named = re.findall(r'tests/[\w/.-]+\.py', str(card.get('check') or ''))
    if not named or not all((ROOT / p).is_file() for p in named):
        return False
    from core.hb_chat import owner_chat
    from core.hb_plain import message
    plan = '\n'.join(f'{n}. {p}' for n, p in enumerate(card.get('plan') or [], 1))
    spec = (f"\n\nSPEC (homework card by {card.get('model')}, {time.strftime('%d %b %H:%M')}):\nGoal: {card.get('goal')}\n"
            + (f'Plan:\n{plan}\n' if plan else '') + (f"Files: {', '.join(card.get('files') or [])}\n" if card.get('files') else '')
            + f"Done when: {card.get('check')}\nHB restart after: ui\n")
    conn.execute("UPDATE project_steps SET owner='apex', description=?, updated_at=? WHERE step_id=?", ((row[2] or '') + spec, time.time(), step_id))
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                 (owner_chat(conn), message(f'📐 Spec ready for "{str(row[1])[:120]}": APEX takes it.', f"Done when: {card.get('check')}",
                                            details=[f'Studio step {step_id}', f"goal: {str(card.get('goal'))[:200]}"])))
    return True


def spec_post(task, card):
    """Practice 293: the BA's whole spec as one main-chat message."""
    lines = [f"📝 BA spec: {str(task.get('title') or '')[:110]} - " + ('READY for APEX' if card.get('ready') else 'NOT ready')]
    lines.append(f"Main question: {card.get('goal') or '-'}")
    for key, word in (('scope_in', 'In scope'), ('scope_out', 'Out of scope'), ('design', 'Design'), ('risks', 'Risks')):
        if card.get(key):
            lines.append(f'{word}: ' + '; '.join(str(x) for x in card[key]))
    lines.append(f"Check: {card.get('check') or '-'}")
    if card.get('plan'):
        lines.append('Chunks: ' + ' '.join(f'{n}. {p}' for n, p in enumerate(card['plan'], 1)))
    if card.get('questions'):
        lines.append('Question for JD: ' + '; '.join(card['questions']))
    if not card.get('ready') and card.get('not_ready'):
        lines.append('Not ready because: ' + '; '.join(card['not_ready']) + ' (the BA is told this on its next spec)')
    return '\n'.join(lines)[:3000]


def summary(card):
    """The card as a few lines for APEX's DREAM clipboard."""
    if not card:
        return ''
    lines = [f"BA spec (by {card.get('model')} on the CPU; {'READY' if card.get('ready') else 'not ready: ' + '; '.join(card.get('not_ready') or [])}):",
             f"- goal: {card.get('goal')}"]
    for key, word in (('scope_in', 'in scope'), ('scope_out', 'out of scope'), ('design', 'design'), ('risks', 'risks')):   # Practice 284
        if card.get(key):
            lines.append(f'- {word}: ' + ' | '.join(str(x) for x in card[key]))
    lines.append(f"- check: {card.get('check')}")
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
    for task in backlog(conn):                           # Practice 113: the claude-code backlog gets specs too
        if task not in out:
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
