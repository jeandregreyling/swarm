"""DREAM: how HB thinks through and executes every task, with HB holding the clipboard.

D  Distinguish  - the goal and what "done" means are known before HB runs a task automatically.
R  Repetition   - do not repeat a failed action; look at related past work first.
E  Execution    - one bounded action at a time, with real receipts (task_plan / tools).
A  Acceleration - knowledge and memory first (KC records, lessons), local first, online only if authorised.
M  Motivation   - report progress and blockers honestly; stop and ask when stuck (hb_task_manager).

The clipboard is HB's per-task card: goal, done criteria, current step, last failure,
related past work and the method line. It is added to every APEX task turn (main chat and
worker). "Done when" comes from the owner (/done), the task's Studio test cases, or criteria
written in the task itself; HB never lets a model define its own finish line.
"""
import json
import re

STOP = set('''this that with from have will would should could into about there their they them then than when what which while
your yours been were also only just more most some such very much many make made does done doing task tasks please thanks apex codex
gemini owner need needs using used use file files code check checks work working build built fix fixed main chat hummingbird'''.split())
CRITERIA_RE = re.compile(r'(?im)^\s*(?:done when|definition of done|acceptance(?: criteria)?|finished when)\s*[:\-]\s*(.+)$')


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _payload(raw):
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def done_when(conn, task):
    """(source, [criteria]) - source is 'owner', 'studio' or 'task'; ([], None) when not defined."""
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='clipboard' AND agent='user' "
                       "ORDER BY event_id DESC LIMIT 1", (task['task_id'],)).fetchone()
    if row:
        criteria = [str(c) for c in _payload(row[0]).get('done_when') or [] if str(c).strip()]
        if criteria:
            return 'owner', criteria
    if task.get('step_id') and 'project_test_cases' in _tables(conn):
        cases = [r[0] for r in conn.execute('SELECT title FROM project_test_cases WHERE step_id=? ORDER BY created_at',
                                            (task['step_id'],)) if r[0]]
        if cases:
            return 'studio', cases[:8]
    found = [m.group(1).strip() for m in CRITERIA_RE.finditer(str(task.get('objective') or ''))]
    if found:
        return 'task', found[:8]
    return None, []


def set_done(conn, task, criteria, actor):
    from core import hb_tasks
    criteria = [c.strip()[:300] for c in criteria if c and c.strip()][:8]
    if not criteria or sum(len(c) for c in criteria) < 10:
        raise ValueError('Say what must be true when the task is finished (at least 10 characters).')
    hb_tasks.event(conn, task, 'user', 'clipboard', {'done_when': criteria, 'actor': actor})
    return criteria


def _words(text):
    return {w for w in re.findall(r'[a-z0-9][a-z0-9_.\-]{3,}', str(text).lower()) if w not in STOP and not w.isdigit()}


def related(conn, task, limit=2):
    """Past HB tasks whose saved KC record shares the most significant words with this task."""
    if not {'knowledge_sources', 'hb_kc_index'} <= _tables(conn):
        return []
    mine = _words(str(task.get('title') or '') + ' ' + str(task.get('objective') or '')[:800])
    if len(mine) < 2:
        return []
    scored = []
    for key, source_id in conn.execute("SELECT key, source_id FROM hb_kc_index WHERE kind='task' AND key<>?", (task['task_id'],)):
        row = conn.execute('SELECT title, substr(raw_text,1,2500) FROM knowledge_sources WHERE source_id=?', (source_id,)).fetchone()
        if not row:
            continue
        overlap = mine & _words(row[0] + ' ' + row[1])
        if len(overlap) >= 2:
            scored.append((len(overlap), key, row[0], source_id))
    out = []
    for score, key, title, source_id in sorted(scored, reverse=True)[:limit]:
        state = conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (key,)).fetchone()
        out.append({'task_id': key, 'title': title.split(': ', 1)[-1][:90], 'state': state[0] if state else '?',
                    'document_id': (1 << 40) + source_id, 'shared_words': score})
    return out


def last_failure(conn, task):
    since = conn.execute("SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=? AND (kind='mutation' OR "
                         "(kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass'))", (task['task_id'],)).fetchone()[0]
    row = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='tool_failure' AND event_id>? "
                       "ORDER BY event_id DESC LIMIT 1", (task['task_id'], since)).fetchone()
    if not row:
        return None
    p = _payload(row[0])
    return f"{p.get('tool', 'tool')}: {str(p.get('error', ''))[:200]}"


def card(conn, task):
    """The DREAM clipboard HB adds to an APEX turn for this task."""
    from core import hb_owner_intent
    if hb_owner_intent.is_chat_task(task):                  # owner 14 Nov: JD talking, not new work
        return hb_owner_intent.card(conn, task)
    source, criteria = done_when(conn, task)
    plan = conn.execute("SELECT payload FROM hb_task_events WHERE task_id=? AND kind='task_plan' ORDER BY event_id DESC LIMIT 1",
                        (task['task_id'],)).fetchone()
    step = str(_payload(plan[0]).get('next_action', ''))[:400] if plan else ''
    lines = [f"DREAM CLIPBOARD for {task['task_id']} (held by HB; reference, not new permission):",
             f"Goal: {str(task.get('title') or '')[:200]}"]
    if criteria:
        lines.append(f"Done when ({source}): " + '; '.join(c[:200] for c in criteria))
    else:
        # Owner 14 Nov: asking JD to define criteria for every chat message made APEX useless. A direct request is done
        # when what JD asked is done; act on its plain meaning. If no attached tool can do it, say so in one line and give JD
        # the HB command that does (e.g. /stop stops all work; /cancel T-xxxx cancels one task).
        lines.append("Done when: what JD asked is done. Act on the plain meaning of the request now; do NOT ask JD to define "
                     "criteria or type /done. If none of your tools can do it, say so in one sentence and name the HB command that does "
                     "(/stop stops all work, /cancel T-xxxx cancels a task, /approvals lists what waits).")
    lines.append('Current step: ' + (step or 'none recorded yet'))
    try:   # owner 14 Nov: the CPU model's homework (spec card) - the reading and thinking already done for this task
        from core.hb_homework import latest, summary
        homework = summary(latest(conn, task))
        if homework:
            lines.append(homework)
    except Exception:
        pass
    failure = last_failure(conn, task)
    if failure:
        lines.append(f'Last failure since progress: {failure} (do not repeat it unchanged).')
    past = related(conn, task)
    lines.append('Related past work: ' + ('; '.join(f"{p['task_id']} \"{p['title']}\" ({p['state']}, KC document {p['document_id']})"
                                                    for p in past) if past else 'none found'))
    try:  # Learning step 0: verified worked examples of the same kind of work
        from core.hb_learning import examples_block
        block = examples_block(conn, task)
        if block:
            lines.append(block)
    except Exception:
        pass
    try:   # owner 14 Nov: what HB learned from corrections (another agent's better way), so the same mistake is not repeated
        from core.hb_merits import lessons
        for note in lessons(conn):
            lines.append('Learned from a correction: ' + note[:400])
    except Exception:
        pass
    lines.append('Method: D know the goal and done criteria first; R never repeat a failed action unchanged; '
                 'E one bounded action at a time with real receipts; A look in the KC and memory first (knowledge_search, '
                 'task_evidence), local models first, online helpers only if authorised; M report progress and blockers '
                 'honestly and stop to ask the owner when stuck.')
    return '\n'.join(lines)


CARD_HEADER = 'DREAM CLIPBOARD for '
