"""Model scorecards and worked examples (owner 14 Nov 2026).

scorecards(conn)   per model and task type, from HB's own records: turns answered / failed and average seconds (hb_model_runs),
                   checked successes and corrections (hb_merits). No model is asked anything.
examples(conn, q)  verified worked examples, model-neutral: change sets that were applied and whose step was approved - "how this was
                   done last time and the check passed" - ranked by shared words with the question.
next_rung(...)     the doer ladder: after two failed checks in a row a task moves one rung up (hb -> small -> apex -> fred)."""
import json
import re

LADDER = ('hb', 'small', 'apex', 'fred')
FAILS_PER_RUNG = 2


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def scorecards(conn):
    """{(model, category): {'answered', 'failed', 'avg_s', 'successes', 'corrections', 'pass_rate'}}"""
    tables = _tables(conn)
    cards = {}
    blank = lambda: {'answered': 0, 'failed': 0, 'avg_s': None, 'successes': 0, 'corrections': 0, 'pass_rate': None}
    if 'hb_model_runs' in tables:
        for model, cat, status, n, avg in conn.execute("SELECT model, COALESCE(category,'general'), status, COUNT(*), AVG(elapsed_seconds) FROM hb_model_runs "
                                                       "WHERE COALESCE(model,'') NOT IN ('', 'unknown') GROUP BY 1, 2, 3"):
            card = cards.setdefault((model, cat), blank())
            if status == 'answered':
                card['answered'], card['avg_s'] = n, round(avg or 0, 1)
            else:
                card['failed'] += n
    if 'hb_merits' in tables:
        for model, cat, kind, n in conn.execute("SELECT model, COALESCE(category,'general'), kind, COUNT(*) FROM hb_merits WHERE COALESCE(model,'')<>'' "
                                                "AND kind IN ('success','correction') GROUP BY 1, 2, 3"):
            cards.setdefault((model, cat), blank())['successes' if kind == 'success' else 'corrections'] += n
    for card in cards.values():
        turns = card['answered'] + card['failed']
        card['pass_rate'] = round(card['answered'] / turns, 2) if turns else None
    return cards


def text(conn):
    cards = scorecards(conn)
    if not cards:
        return 'No scorecards yet: no model has finished a recorded turn.'
    lines = ['Scorecards (HB\'s own records):']
    for (model, cat), c in sorted(cards.items(), key=lambda kv: (-kv[1]['successes'], kv[0])):
        lines.append(f"- {model} / {cat}: {c['successes']} checked success(es), {c['corrections']} correction(s), {c['answered']} turn(s) answered"
                     + (f", {c['failed']} failed" if c['failed'] else '') + (f", {int(c['pass_rate'] * 100)}% of turns answered" if c['pass_rate'] is not None else '')
                     + (f", {c['avg_s']} s per turn" if c['avg_s'] is not None else ''))
    return '\n'.join(lines)


def _words(s):
    return {w for w in re.findall(r'[a-z0-9_]{4,}', str(s).lower()) if w not in {'owner', 'practice', 'that', 'this', 'with', 'from', 'when', 'into'}}


def examples(conn, question, limit=3, load=None):
    """[{'step_id', 'title', 'why', 'files', 'test'}] - approved steps with an applied change set, closest to the question first."""
    if load is None:
        from core import hb_change_sets
        load = hb_change_sets.load
    want = _words(question)
    found = []
    for step_id, title in conn.execute("SELECT step_id, title FROM project_steps WHERE status='done' ORDER BY updated_at DESC LIMIT 400"):
        cs = load(step_id)
        if not cs:
            continue
        files = sorted({e['path'] for e in cs.get('edits') or []} | set(cs.get('new_files') or {}))
        score = len(want & (_words(title) | _words(cs.get('why', '')) | _words(' '.join(files))))
        if score:
            found.append((score, {'step_id': step_id, 'title': str(title)[:140], 'why': str(cs.get('why', ''))[:400], 'files': files,
                                  'test': (cs.get('test') or {}).get('tests', [])[:3]}))
    return [e for _, e in sorted(found, key=lambda x: -x[0])[:limit]]


def examples_text(conn, question, load=None):
    found = examples(conn, question, load=load)
    if not found:
        return 'No worked example matches that yet.'
    return 'How this was done before (check passed):\n' + '\n'.join(
        f"- {e['title']} ({e['step_id']}): {e['why']} Files: {', '.join(e['files'][:5])}. Check: {', '.join(e['test']) or 'its step test'}." for e in found)


def failed_checks(conn, task_id):
    """Failed checks in a row since the last pass for a task."""
    if not task_id or 'hb_task_events' not in _tables(conn):
        return 0
    n = 0
    for (status,) in conn.execute("SELECT json_extract(payload,'$.alm_run_status') FROM hb_task_events WHERE task_id=? AND kind='test_result' "
                                  "ORDER BY event_id DESC LIMIT 20", (task_id,)):
        if status == 'pass':
            break
        n += 1
    return n


def next_rung(doer, fails):
    """(doer, why): one rung up for every FAILS_PER_RUNG failed checks in a row; the top rung stays."""
    if doer not in LADDER or fails < FAILS_PER_RUNG:
        return doer, ''
    at = min(LADDER.index(doer) + fails // FAILS_PER_RUNG, len(LADDER) - 1)
    return LADDER[at], (f'moved up from {doer} after {fails} failed checks in a row' if LADDER[at] != doer else '')
