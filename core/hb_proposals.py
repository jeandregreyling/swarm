"""Studio proposals from advisors (owner 14 Nov 2026): an online or outside agent proposes a change with actual code; HB checks it; APEX applies.

"Gemini should have access to write to Studio proposals and tasks but should be instructed to make code changes through HB, not by itself."

  create(...)  tool studio_proposal: a Studio step in the living plan ("Proposal (<agent>): <title>") with why, and a DRAFT change set
               (exact edits and/or new files, plus the test that proves it). Nothing in HB's code changes.
  tick(...)    HB checks one draft at a time in the background: core/hb_change_sets.prepare applies it, runs its test and puts the files back.
               Passes -> the step becomes a ready APEX task with the change set ("HB extra tools: change_set"); fails or has no test -> it waits
               for review with the reason. Either way main chat says so.
"""
import json
import re
import threading
import time
from contextlib import closing
from pathlib import Path

from core import hb_change_sets as cs

PLAN = 'P-2AB8250A87'
MAIN_CHAT = 2834
NEVER = re.compile(r'(^|/)(config\.py|\.env[^/]*|.*credential.*|.*secret.*|.*\.key|.*\.pem)$|^(\.git|runtime)/', re.I)
_RUNNING = threading.Lock()


def _post(conn, text, details=()):
    from core.hb_plain import message
    return conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                        (MAIN_CHAT, message(text, details=[d for d in details if d]))).lastrowid


def _clean(args):
    title, why = str(args.get('title') or '').strip(), str(args.get('why') or '').strip()
    if not 4 <= len(title) <= 140 or not 10 <= len(why) <= 3000:
        raise ValueError('studio_proposal needs a title (4-140 characters) and why (10-3000 characters)')
    edits = [{'path': str(e.get('path', '')), 'old': str(e.get('old', '')), 'new': str(e.get('new', ''))} for e in (args.get('edits') or [])]
    files = {str(f.get('path', '')): str(f.get('content', '')) for f in (args.get('new_files') or [])}
    if len(edits) > 20 or len(files) > 5 or any(len(e['old']) + len(e['new']) > 40000 or not e['old'] for e in edits) or any(len(c) > 80000 for c in files.values()):
        raise ValueError('A proposal holds at most 20 exact edits (each with its old text) and 5 new files')
    for path in [e['path'] for e in edits] + list(files):
        if not path or path.startswith('/') or '..' in Path(path).parts or NEVER.search(path):
            raise PermissionError(f'{path!r} cannot be proposed (outside HB code, or a secrets/config file)')
    tests = [str(t) for t in (args.get('tests') or [])][:5]
    if any(not re.fullmatch(r'tests/[\w/.-]+\.py', t) for t in tests):
        raise ValueError('tests must be test files under tests/')
    return title, why, edits, files, ({'tests': tests, **({'keyword': str(args['keyword'])[:120]} if args.get('keyword') else {})} if tests else None)


def create(conn, agent, args, task=None):
    title, why, edits, files, test = _clean(args)
    from core.knowledge import projects
    desc = (f'Proposed by {agent} (an advisor; it does not change HB itself). HB checks the proposal by running its test with the change applied, '
            f'then puts the files back.\nWhy: {why}\n' + (f"Files: {', '.join(sorted({e['path'] for e in edits} | set(files)))}\n" if edits or files else 'No code: a proposal for discussion.\n')
            + (f"Test: {', '.join(test['tests'])}{' -k ' + test['keyword'] if test.get('keyword') else ''}\n" if test else ''))
    sid = projects.add_step(PLAN, f'Proposal ({agent}): {title}'[:160], description=desc, owner='claude-code')
    conn.execute('UPDATE project_steps SET order_idx=?, updated_at=? WHERE step_id=?', (35.0, time.time(), sid))
    d = cs._dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    (d / 'proposal.json').write_text(json.dumps({'agent': agent, 'title': title, 'why': why, 'edits': edits, 'new_files': files, 'test': test,
                                                 'at': time.time(), 'task_id': task['task_id'] if task else None}, indent=1))
    from core.hb_plain import name
    _post(conn, f"📜 {agent} proposed a change: {name(title)}. HB will check it by running its test.", [f'Studio step {sid}'])
    if task:
        from core import hb_tasks
        hb_tasks.event(conn, task, agent, 'studio_proposal', {'step_id': sid, 'title': title, 'files': sorted({e['path'] for e in edits} | set(files))})
    return {'step_id': sid, 'state': 'proposed', 'next': 'HB checks it by running its test; if it passes, APEX applies it through HB. Tell JD the step id.'}


def pending(root=None):
    base = Path(root or cs.ROOT) / 'runtime' / 'change_sets' / 'steps'
    return sorted((p.parent.name for p in base.glob('*/proposal.json') if not (p.parent / 'result.json').exists()),
                  key=lambda s: (base / s / 'proposal.json').stat().st_mtime)


def check(conn, sid, root=None, run=None):
    root = root or cs.ROOT
    """Check one proposal now. Returns the result dict (also saved as result.json)."""
    d = cs._dir(sid, root)
    p = json.loads((d / 'proposal.json').read_text())
    result = {'at': time.time()}
    from core import hb_background as bg
    bg.start('proposal', {'title': p['title'], 'conversation_id': MAIN_CHAT}, 'tests', f"checking {p['agent']}'s proposal by running its test")
    if not (p['edits'] or p['new_files']):
        result.update(verified=False, why='no code in the proposal: kept for discussion')
    elif not p['test']:
        result.update(verified=False, why='no test given: HB cannot prove it; kept for review')
    else:
        try:
            saved = cs.prepare(sid, why=f"{p['why']} (proposed by {p['agent']})", edits=p['edits'], new_files=p['new_files'], test=p['test'],
                               prepared_by=p['agent'], root=root, run=run)
            result.update(verified=True, why=saved['verified']['result'])
        except Exception as exc:
            result.update(verified=False, why=str(exc)[:300])
    (d / 'result.json').write_text(json.dumps(result, indent=1))
    bg.finish('proposal')
    from core.hb_plain import name
    if result['verified']:
        line = (f"HB extra tools: change_set\nPREPARED (proposed by {p['agent']}, checked by HB {time.strftime('%d %b %H:%M')}): change_set show, "
                f"change_set apply, then run_tests with {json.dumps(p['test'])}, then report in 2-4 lines.\nDone when: python -m pytest "
                f"{' '.join(p['test']['tests'])}{' -k ' + repr(p['test']['keyword']) if p['test'].get('keyword') else ''} passes\n")
        conn.execute("UPDATE project_steps SET owner='apex', description=?||description, updated_at=? WHERE step_id=?", (line, time.time(), sid))
        from core import hb_tasks
        title = conn.execute('SELECT title, description FROM project_steps WHERE step_id=?', (sid,)).fetchone()
        mid = _post(conn, f"✅ HB checked {p['agent']}'s proposal {name(p['title'])}: its test passes. APEX will apply it through HB.", [f'Studio step {sid}', result['why']])
        hb_tasks.bind(conn, MAIN_CHAT, mid, title=f'{sid} {title[0]}'[:140], objective=f'Studio step {sid} ({PLAN}): {title[0]}\n{title[1]}',
                      project_id=PLAN, step_id=sid)
    else:
        conn.execute("UPDATE project_steps SET residual_risk=?, updated_at=? WHERE step_id=?", ('HB check: ' + result['why'], time.time(), sid))
        _post(conn, f"↺ {p['agent']}'s proposal {name(p['title'])} is kept for review: {result['why'][:200]}", [f'Studio step {sid}'])
    return result


def tick(conn):
    """Coordinator tick: check the oldest unchecked proposal in its own thread (a test run can take a while)."""
    todo = pending()
    if not todo or not _RUNNING.acquire(blocking=False):
        return None
    sid = todo[0]

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                check(own, sid)
        except Exception:
            import logging
            logging.getLogger('hb.proposals').exception('proposal check failed for %s', sid)
            try:
                (cs._dir(sid) / 'result.json').write_text(json.dumps({'verified': False, 'why': 'HB could not check it (see the log)'}))
            except OSError:
                pass
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-proposals', daemon=True).start()
    return sid
