"""Chunks: HB breaks each task into small pieces and gives APEX ONE at a time (Practice 216; JD 21 Nov 2026: "an entire task is being
handled as a whole instead of homework and HB breaking it down into more manageable chunks for apex").

Practice 232 (JD 21 Nov: "just get the chunking to work ... make it work the way you think it should with my intent"):
  plan(text)          the step's own "Do:" sequence, split only at real step boundaries (", then", "; ", "->" - never inside brackets),
                      else an action-only numbered/bulleted list; descriptions and constraints are never chunks.
                      No such list: homework's plan, else one piece.
  ensure(conn, task)  the task's chunks; rebuilt when the step's spec changed and no chunk is done yet
  advance(conn, task) what was recorded is matched to the chunks IN ORDER - a look (run, read, check, show) is finished by a test run or
                      tool result, a change by a change / note / passing check, a report by the reply - so one turn can finish several
                      chunks. Runs at the end of every turn (HB's task tick) and when the next card is built. Each finished chunk is a
                      'chunk_done' event (progress for APEX's attempts and Fred's turn) and one line in main chat.
  focus(conn, task)   the card line: "HB CHUNK - work ONLY on chunk 2 of 5: ... Done so far: ... Next after this: ..."
  /chunks T-xxx [add <text> | done | reset]   see or steer a task's chunks (JD, HB, Telegram)
"""
import hashlib
import re
import time

DO = re.compile(r'\bDo:\s*(.+)$', re.M | re.I)   # Practice 217: prepared steps say '... change set. Do: ...' mid-line
ITEM = re.compile(r'^\s*(?:\d+[.)]|[-*•])\s+(.+)$', re.M)
ACTION = re.compile(r'^(?:read|inspect|check|find|search|review|show|run|write|create|add|edit|update|change|fix|implement|build|remove|replace|apply|test|verify|report|answer|summari[sz]e|collect|extract|compare|identify|prepare|define|split|send)\b', re.I)
SKIP = re.compile(r'^\s*(?:Done when|HB extra tools|HB restart after|PREPARED|Owner\b|JD\b)', re.I)
SEQ = re.compile(r',\s*then\s+|;\s*then\s+|\s+then\s+|;\s+|\s+->\s+', re.I)
COMMA = re.compile(r',\s+')
PROGRESS = ("kind IN ('mutation','studio_note','studio_task') OR (kind='test_result' AND json_extract(payload,'$.alm_run_status')='pass')")
RAN = "kind IN ('mutation','studio_note','studio_task','test_result','tool_result')"
REPLIED = "kind IN ('reply','studio_note','studio_task')"
LOOKS = re.compile(r'^\s*(?:then\s+)?(?:change_set show|run(?:_tests)?|read|check|find|show|inspect|look|list|search|grep|open|review)\b', re.I)
CHANGES = re.compile(r'\b(replace|fix|change|apply|write|add|remove|edit|create|update|patch|rename|move|implement|build|recolou?r)\b', re.I)
REPORT = re.compile(r'^\s*(?:then\s+)?(?:report|answer|reply|say|tell|summari[sz]e)\b', re.I)


def table(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_chunks(task_id TEXT, n INTEGER, text TEXT, state TEXT, started_event INTEGER, '
                 'updated_at REAL, PRIMARY KEY(task_id, n))')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_chunk_source(task_id TEXT PRIMARY KEY, hash TEXT)')


def _depths(text):
    """Bracket/quote depth at each character - commas inside (...), [...], {...}, "..." or `...` are never chunk boundaries."""
    depth, quote, out = 0, None, []
    for c in text:
        if quote:
            out.append(1)
            if c == quote:
                quote = None
            continue
        if c in '"`':
            quote = c
            out.append(1)
            continue
        if c in '([{':
            depth += 1
        out.append(depth)
        if c in ')]}':
            depth = max(0, depth - 1)
    return out


def _split_top(text, pattern):
    d = _depths(text)
    parts, last = [], 0
    for m in pattern.finditer(text):
        if d[m.start()] == 0:
            parts.append(text[last:m.start()])
            last = m.end()
    parts.append(text[last:])
    return [p.strip(' .') for p in parts if p.strip(' .')]


def _short_list(piece):
    """'change_set show (read why), change_set apply' is two short actions; a long clause with a comma is one."""
    bits = _split_top(piece, COMMA)
    return bits if len(bits) > 1 and all(len(b) <= 60 for b in bits) else [piece]


LETTERED = re.compile(r'(?:^|[,;:]\s+|\s+)(?=[A-H]\.\s)')
TESTS = re.compile(r'tests/[\w/.-]+\.py')


def _lettered(body):
    """Practice 281: 'intro: A. ..., B. ..., C. ...' -> one chunk per letter; the intro's test file travels with each chunk."""
    d = _depths(body)
    cuts = [m.end() for m in LETTERED.finditer(body) if d[min(m.end(), len(d) - 1)] == 0]
    if len(cuts) < 2:
        return []
    intro = body[:cuts[0]]
    tests = sorted(set(TESTS.findall(intro)))
    parts = [body[a:b].strip(' ,;.') for a, b in zip(cuts, cuts[1:] + [len(body)])]
    return [p + (f' (test first in {tests[0]})' if tests and tests[0] not in p else '') for p in parts if p]


def _merge_fragments(parts):
    """Practice 281: 'plan', 'result (core/x.py)', 'any actor can take it' are not chunks - they join the chunk before them."""
    out = []
    for p in parts:
        if out and len(p.split()) <= 3 and re.fullmatch(r'[a-z][a-z -]*', p) and not ACTION.match(p) and not LOOKS.match(p):
            out[-1] = f'{out[-1]}; {p}'
        else:
            out.append(p)
    return out


def test_chunks(text):
    """Practice 281: a spec with no plan of its own but test files in its 'Done when' line - one chunk per test file."""
    done = re.search(r'(?im)^\s*done when\s*:\s*(.+)$', str(text or ''))
    files = list(dict.fromkeys(TESTS.findall(done.group(1)))) if done else []
    if len(files) == 1:
        return [f'run {files[0]} and read the first failure: what does it expect that the code does not do',
                'fix the code that failure points at: read the exact lines first, then patch only those lines',
                f'run {files[0]} again: repeat read-fix-run until it passes, then report what you changed']
    if 2 <= len(files) <= 7:
        return ([f'make {f} pass: run it, read the first failure, read the exact lines it points at, patch only those, run it again' for f in files]
                + ['run all of them together and report which pass and what you changed'])
    return []


def plan(text, most=8):
    """Split explicit instructions without mistaking a specification for a plan."""
    text = str(text or '')
    m = DO.search(text)
    if m:
        parts = _lettered(m.group(1)) or _merge_fragments([b for p in _split_top(m.group(1), SEQ) for b in _short_list(p)])   # Practice 281
    else:
        # Only a standalone list of actions is a plan. Requirements, safety
        # constraints, and nested lists inside a larger directive are context.
        lines = [line for line in text.splitlines() if line.strip()]
        matches = [ITEM.fullmatch(line) for line in lines]
        parts = [m.group(1).strip() for m in matches] if lines and all(matches) else []
        if not all(ACTION.match(p) for p in parts):
            parts = []
    parts = [p for p in parts if p and not SKIP.match(p)]
    # Falling back to the whole instruction is safer than losing later steps.
    return parts if 2 <= len(parts) <= most and all(len(p) <= 500 for p in parts) else []


def kinds_for(text):
    """What finishes a chunk: a change needs a change, a note or a passing check; a report needs the reply; a look needs a run."""
    t = str(text or '')
    if CHANGES.search(t):
        return PROGRESS
    if REPORT.search(t):
        return REPLIED
    if LOOKS.search(t):
        return RAN
    return PROGRESS


def inspection(text):
    return kinds_for(text) == RAN


def _progress(conn, task_id):
    return conn.execute(f'SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=? AND ({PROGRESS})', (task_id,)).fetchone()[0]


def _last_event(conn, task_id):
    return conn.execute('SELECT COALESCE(MAX(event_id),0) FROM hb_task_events WHERE task_id=?', (task_id,)).fetchone()[0]


def _source(conn, task):
    source = task.get('objective') or ''
    if task.get('step_id'):
        try:
            row = conn.execute('SELECT title, description FROM project_steps WHERE step_id=?', (task['step_id'],)).fetchone()
            if row:
                source = f'{row[0]}\n{row[1] or ""}'
        except Exception:
            pass
    return source


def _parts(conn, task, source):
    parts = plan(source)
    if parts:
        return parts
    # An explicit but unsplittable Do sequence must remain intact. An inferred
    # plan must not silently replace its later or oversized instructions.
    if DO.search(str(source)):
        return []
    # A named immediate step in an owner directive takes precedence over an
    # inferred homework plan, which may omit its required answer or stop point.
    if re.search(r'^\s*#{1,6}\s*(?:\d+[.)]?\s*)?immediate\b', str(source), re.I | re.M):
        return []
    try:   # no Do: list or numbered lines in the spec: homework's plan, if it made one
        from core.hb_homework import latest
        card = latest(conn, task) or {}
        if card.get('ready') is False:   # Practice 282: a plan HB rejected (vague, invented files) is not a chunk list
            raise ValueError('homework plan rejected')
        steps = [str(s).strip() for s in (card.get('plan') or []) if str(s).strip()]
        if 2 <= len(steps) <= 8 and all(len(s) <= 500 for s in steps):
            return steps
    except Exception:
        pass
    return test_chunks(source)          # Practice 281: no plan anywhere - one chunk per Done-when test file


def ensure(conn, task):
    table(conn)
    tid = task['task_id']
    source = _source(conn, task)
    digest = hashlib.sha1(source.encode('utf-8', 'replace')).hexdigest()[:16]
    rows = conn.execute('SELECT n, text, state, started_event FROM hb_chunks WHERE task_id=? ORDER BY n', (tid,)).fetchall()
    stored = conn.execute('SELECT hash FROM hb_chunk_source WHERE task_id=?', (tid,)).fetchone()
    start = None
    if rows:
        if any(r[2] == 'done' for r in rows) or (stored and stored[0] == digest):
            if not stored:
                conn.execute('INSERT OR REPLACE INTO hb_chunk_source VALUES (?,?)', (tid, digest))
            return [r[:3] for r in rows]
        start = next((r[3] for r in rows if r[2] == 'doing' and r[3] is not None), None)   # rebuilt: work since then still counts
        conn.execute('DELETE FROM hb_chunks WHERE task_id=?', (tid,))
    if start is None:
        start = _last_event(conn, tid)          # only work recorded from now on finishes a new chunk
    for n, text in enumerate(_parts(conn, task, source), 1):
        conn.execute('INSERT OR IGNORE INTO hb_chunks VALUES (?,?,?,?,?,?)',
                     (tid, n, text, 'doing' if n == 1 else 'todo', start if n == 1 else None, time.time()))
    conn.execute('INSERT OR REPLACE INTO hb_chunk_source VALUES (?,?)', (tid, digest))
    return conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (tid,)).fetchall()


def _finish(conn, tid, n, ev):
    conn.execute("UPDATE hb_chunks SET state='done', updated_at=? WHERE task_id=? AND n=?", (time.time(), tid, n))
    conn.execute("UPDATE hb_chunks SET state='doing', started_event=?, updated_at=? WHERE task_id=? AND n=(SELECT MIN(n) FROM hb_chunks "
                 "WHERE task_id=? AND state='todo')", (ev, time.time(), tid, tid))


def _record(conn, task, finished):
    """Each finished chunk: a chunk_done event (progress) and, for the batch, one line in main chat."""
    try:
        from core import hb_tasks
        for n, _, text in finished:
            hb_tasks.event(conn, task, 'hummingbird', 'chunk_done', {'chunk': n, 'text': str(text or '')[:200]})
    except Exception:
        pass
    try:
        tid = task['task_id']
        total = conn.execute('SELECT COUNT(*) FROM hb_chunks WHERE task_id=?', (tid,)).fetchone()[0]
        nxt = conn.execute("SELECT n, text FROM hb_chunks WHERE task_id=? AND state='doing'", (tid,)).fetchone()
        first, last = finished[0][0], finished[-1][0]
        which = f'chunk {first}' if first == last else f'chunks {first}-{last}'
        title = str(task.get('title') or tid)[:70]
        line = (f"▸ {title}: {which} of {total} done ({str(finished[-1][2] or '')[:80]})"
                + (f" - next: chunk {nxt[0]}, {str(nxt[1] or '')[:90]}" if nxt else " - all chunks done; the step's own check decides"))
        if task.get('conversation_id'):
            conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                         "VALUES (?,'hummingbird','user',?,'response',0)", (task['conversation_id'], line))
    except Exception:
        pass


ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
TEST_FIRST = re.compile(r'\bwrite\s+(tests/[\w/.-]+\.py)\b[^,;]*?\bfirst\b', re.I)
REAL_ASSERT = re.compile(r'^\s*assert\s+(?!(?:True|1|not\s+False)\s*(?:#.*)?$)\S|pytest\.raises\(', re.M)


def weak_test(text):
    """Practice 236: why a 'write tests/x.py first' chunk is not done yet, or None. A test-first test checks behaviour (a real assert
    or pytest.raises), so it can fail before the code exists; `assert True`, an import-only file or a skip cannot."""
    m = TEST_FIRST.search(str(text or ''))
    if not m:
        return None
    path = ROOT / m.group(1)
    if not path.is_file():
        return f'{m.group(1)} does not exist yet'
    body = path.read_text(errors='replace')
    if not REAL_ASSERT.search(body):
        return (f'{m.group(1)} has no real check (assert True or import only). A test asserts the behaviour the spec describes and '
                'FAILS before the code exists - write those asserts, run it, report the failure')
    if re.search(r'^\s*(?:@pytest\.mark\.skip\b|pytest\.skip\()', body, re.M):
        return f'{m.group(1)} skips itself - a skipped test proves nothing; remove the skip and make it check the behaviour'
    return None


def weak_done(task):
    """Practice 236: why the step's own 'Done when' test cannot prove it is done, or None. HB does not approve - or give a flower -
    on a test that cannot fail."""
    for line in re.findall(r'Done when:[^\n]*', str(task.get('objective') or ''), re.I):
        for path in re.findall(r'tests/[\w/.-]+\.py', line):
            why = weak_test(f'write {path} first')
            if why:
                return why
    return None


def _refuse(conn, task, n, why, label=None):
    """One line per chunk and reason (not every tick): the work stays open and APEX sees why in main chat and in his events."""
    tid = task['task_id']
    seen = conn.execute("SELECT 1 FROM hb_task_events WHERE task_id=? AND kind='chunk_refused' AND json_extract(payload,'$.chunk')=? "
                        "AND json_extract(payload,'$.why')=?", (tid, n, why)).fetchone()
    if seen:
        return
    from core import hb_tasks
    hb_tasks.event(conn, task, 'hummingbird', 'chunk_refused', {'chunk': n, 'why': why})
    what = label or f'chunk {n}'
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','apex',?,'response',0)",
                 (task.get('conversation_id') or 2845, f"▸ {str(task.get('title') or tid)[:70]}: {what} is NOT done - {why}."))


def advance(conn, task):
    """Match what was recorded to the chunks in order; finish every chunk whose work is there. Returns the last chunk finished, or None."""
    table(conn)
    tid = task['task_id']
    finished = []
    while True:
        cur = conn.execute("SELECT n, started_event, text FROM hb_chunks WHERE task_id=? AND state='doing' ORDER BY n LIMIT 1", (tid,)).fetchone()
        if not cur:
            break
        ev = conn.execute(f'SELECT MIN(event_id) FROM hb_task_events WHERE task_id=? AND event_id>? AND ({kinds_for(cur[2])})',
                          (tid, cur[1] or 0)).fetchone()[0]
        if not ev:
            break
        why = weak_test(cur[2])
        if why:                                  # Practice 236: a placeholder test is not a finished test-first chunk
            _refuse(conn, task, cur[0], why)
            break
        _finish(conn, tid, cur[0], ev)
        finished.append(cur)
    if finished:
        _record(conn, task, finished)
    return finished[-1][0] if finished else None


def view(conn, task_id):
    """Practice 234: a task's chunks for the interface - read-only (the Live pane polls this; it never writes). None: no chunks."""
    try:
        rows = conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (task_id,)).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    doing = next(({'n': r[0], 'text': r[1]} for r in rows if r[2] == 'doing'), None)
    nxt = next(({'n': r[0], 'text': r[1]} for r in rows if r[2] == 'todo'), None)
    return {'total': len(rows), 'done': sum(1 for r in rows if r[2] == 'done'), 'doing': doing, 'next': nxt,
            'list': [{'n': r[0], 'text': r[1], 'state': r[2]} for r in rows]}


def focus(conn, task, writer=None):
    """The line for APEX's card, or '' when the task has no chunks. Practice 217: with writer (a connect function) the chunks are
    saved on their own connection and committed - the card is built inside a transaction nobody commits, so they vanished."""
    # Practice 218: never open the writer while conn already holds a write transaction (peer inbox: authenticate wrote) -
    # the second connection waited 30 s on its own request's lock on every poll and locked HB's database. That caller commits itself.
    if writer is not None and not getattr(conn, 'in_transaction', False):
        import sqlite3
        from contextlib import closing
        with closing(writer()) as w:
            w.execute('PRAGMA busy_timeout=3000')   # Practice 218: a busy database costs this card its chunk line, never 30 s of lock
            try:
                line = focus(w, task)
                w.commit()
            except sqlite3.OperationalError:
                w.rollback()
                return ''
        return line
    rows = ensure(conn, task)
    if not rows:
        return ''
    advance(conn, task)
    rows = conn.execute('SELECT n, text, state FROM hb_chunks WHERE task_id=? ORDER BY n', (task['task_id'],)).fetchall()
    total = len(rows)
    doing = next((r for r in rows if r[2] == 'doing'), None)
    done = [r for r in rows if r[2] == 'done']
    if not doing:
        return f"All {total} chunks of this task are done - run the step's own check and report the receipts."
    nxt = next((r for r in rows if r[2] == 'todo'), None)
    return (f"HB CHUNK - work ONLY on chunk {doing[0]} of {total}: {doing[1]}\n"
            f"Finish it with your tools in this turn and stop; HB gives you the next chunk."
            + (f"\nDone so far: " + '; '.join(f'{r[0]}. {r[1][:80]}' for r in done) if done else '')
            + (f"\nNext after this: {nxt[1][:120]}" if nxt else "\nThis is the last chunk: then run the step's own check."))


def command(conn, args, actor):
    """/chunks T-xxx [add <text> | done | reset]"""
    if not args:
        return 'Use /chunks T-xxxx to see a task\'s chunks; /chunks T-xxxx add <text> | done | reset.'
    from core import hb_tasks
    task = hb_tasks.get(conn, args[0].upper())
    if not task:
        return f'No task {args[0]}.'
    table(conn)
    ensure(conn, task)                      # chunks and their source exist before anyone steers them
    sub = args[1].lower() if len(args) > 1 else ''
    if sub == 'reset':
        conn.execute('DELETE FROM hb_chunks WHERE task_id=?', (task['task_id'],))
        conn.execute('DELETE FROM hb_chunk_source WHERE task_id=?', (task['task_id'],))
    elif sub == 'add' and len(args) > 2:
        n = (conn.execute('SELECT COALESCE(MAX(n),0) FROM hb_chunks WHERE task_id=?', (task['task_id'],)).fetchone()[0]) + 1
        conn.execute('INSERT INTO hb_chunks VALUES (?,?,?,?,?,?)', (task['task_id'], n, ' '.join(args[2:])[:500], 'todo', None, time.time()))
        if not conn.execute("SELECT 1 FROM hb_chunks WHERE task_id=? AND state='doing'", (task['task_id'],)).fetchone():
            conn.execute("UPDATE hb_chunks SET state='doing', started_event=? WHERE task_id=? AND n=?", (_last_event(conn, task['task_id']), task['task_id'], n))
    elif sub == 'done':   # JD or HB says the current chunk is done
        cur = conn.execute("SELECT n, started_event, text FROM hb_chunks WHERE task_id=? AND state='doing' ORDER BY n LIMIT 1", (task['task_id'],)).fetchone()
        if cur:
            _finish(conn, task['task_id'], cur[0], _last_event(conn, task['task_id']))
            _record(conn, task, [cur])
    rows = ensure(conn, task)
    if not rows:
        return f"{task['task_id']} is one piece (no chunks). /chunks {task['task_id']} add <text> adds one."
    mark = {'done': '✓', 'doing': '▶', 'todo': '·'}
    return f"Chunks of {task['task_id']} ({task.get('title') or ''}):\n" + '\n'.join(f"{mark.get(s, '·')} {n}. {t}" for n, t, s in rows)
