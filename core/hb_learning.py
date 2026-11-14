"""Learning from experience (step 0, no weights touched).

Verified past work becomes worked examples that HB shows on the DREAM clipboard of a new
task of the same kind. Verified = the task had a passing guarded check, or it was completed
(accepted). Three skills the owner named: research, remembering past work, using the wrapper.

The same examples are the raw material for the later dataset / exam / LoRA steps
(see export_dataset), so nothing here is throw-away.
"""
import json
import re

SKILL_TOOLS = {
    'research': {'knowledge_search', 'knowledge_read', 'web_search', 'reference_lookup', 'archive_status'},
    'memory': {'task_evidence', 'task_context', 'task_memory', 'memory_search', 'studio_resume', 'alm_step_get'},
    'wrapper': {'read_file', 'grep_repo', 'get_diff', 'git_status', 'run_tests', 'propose_patch', 'propose_write_file',
                'studio_note', 'studio_status', 'studio_task', 'task_plan', 'runtime_status', 'local_review'},
}
SKILL_WORDS = {
    'research': r'research|find out|look up|learn|search|documentation|docs|what is|explain|sap|payroll|consultant|hugging ?face|dataset',
    'memory': r'remember|earlier|previous|before|last time|what did|history|decided|recall|again|which task',
    'wrapper': r'\bfile|code|fix|repair|patch|implement|build|test|studio|tool|wrapper|service|function|\.py\b|install|ui\b|interface',
}


MAX_EXAMPLE_CALLS = 20
BODY_KEYS = {'content', 'exact_old_text', 'new_text'}


def safe_arguments(args):
    """Tool arguments as stored for learning: large edit bodies become a hash + length; text capped at 300 chars."""
    import hashlib
    out = {}
    for key, value in (args or {}).items() if isinstance(args, dict) else ():
        if key in BODY_KEYS:
            out[key] = {'sha256': hashlib.sha256(str(value).encode()).hexdigest(), 'length': len(str(value))}
        elif value is None or isinstance(value, (bool, int, float)):
            out[key] = value
        else:
            out[key] = str(value)[:300]
    return out


def skills_for_text(text):
    text = str(text or '').lower()
    found = {skill for skill, rx in SKILL_WORDS.items() if re.search(rx, text)}
    return found or {'wrapper'}


def _payload(raw):
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


FAILED_REPLY_RE = re.compile(r'^(Attached \S+ request did not complete|Error:|.{0,40}could not answer this request)', re.I)


def verified_task_ids(conn):
    """Accepted tasks, plus tasks with a passing check that ended well.

    A task the owner paused, or whose last APEX reply is a failure notice, is not an example
    to learn from even if it passed a check on the way (e.g. the 118-checkpoint DREAM loop)."""
    passed = {r[0] for r in conn.execute("SELECT DISTINCT task_id FROM hb_task_events WHERE kind='test_result' "
                                         "AND json_extract(payload,'$.alm_run_status')='pass'")}
    done = {r[0] for r in conn.execute("SELECT task_id FROM hb_tasks WHERE state='completed'")}
    clean = set()
    for tid in passed - done:
        state = conn.execute('SELECT state FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()
        last = conn.execute("SELECT m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id WHERE tm.task_id=? "
                            "AND m.from_agent='apex' ORDER BY m.id DESC LIMIT 1", (tid,)).fetchone()
        if state and state[0] != 'paused' and not (last and FAILED_REPLY_RE.search(str(last[0]).strip())):
            clean.add(tid)
    return done | clean


def worked_example(conn, task_id):
    """Compact, factual example built only from recorded events of a verified task."""
    t = conn.execute('SELECT title, state FROM hb_tasks WHERE task_id=?', (task_id,)).fetchone()
    if not t:
        return None
    rows = conn.execute("SELECT event_id, kind, payload FROM hb_task_events WHERE task_id=? AND agent='apex' "
                        "AND kind IN ('tool_result','test_result') ORDER BY event_id", (task_id,)).fetchall()
    # Keep only the final segment that produced the verified result: after the previous check, up to the last pass.
    passes = [i for i, (_, kind, raw) in enumerate(rows) if kind == 'test_result' and _payload(raw).get('alm_run_status') == 'pass']
    if passes:
        end = passes[-1]
        earlier = [i for i, (_, kind, _) in enumerate(rows[:end]) if kind == 'test_result']
        rows = rows[(earlier[-1] + 1 if earlier else 0):end + 1]
    else:
        rows = rows[-15:]
    steps, counts, used = [], {}, set()
    for _, kind, raw in rows:
        p = _payload(raw)
        if kind == 'test_result':
            name = 'run_tests (' + str(p.get('alm_run_status', '?')).upper() + ')'
        elif p.get('status') == 'succeeded' and p.get('tool'):
            name = p['tool']
        else:
            continue
        used.add(name.split(' ')[0])
        if steps and steps[-1] == name:
            counts[len(steps) - 1] = counts.get(len(steps) - 1, 1) + 1
        else:
            steps.append(name)
    if not steps:
        return None
    calls = len(rows)
    seq = ' -> '.join(s + (f' x{counts[i]}' if counts.get(i, 1) > 1 else '') for i, s in enumerate(steps[:12]))
    if len(steps) > 12:
        seq += f' -> ... ({len(steps) - 12} more)'
    verdict = conn.execute("SELECT json_extract(payload,'$.verdict') FROM hb_task_events WHERE task_id=? AND kind='test_result' "
                           "AND json_extract(payload,'$.alm_run_status')='pass' ORDER BY event_id DESC LIMIT 1", (task_id,)).fetchone()
    answer = conn.execute("SELECT m.content FROM hb_task_messages tm JOIN messages m ON m.id=tm.message_id WHERE tm.task_id=? "
                          "AND m.from_agent='apex' ORDER BY m.id DESC LIMIT 1", (task_id,)).fetchone()
    skills = {skill for skill, tools in SKILL_TOOLS.items() if used & tools} or {'wrapper'}
    return {'task_id': task_id, 'title': str(t[0])[:120], 'state': t[1], 'skills': sorted(skills), 'steps': seq, 'calls': calls,
            'verdict': str(verdict[0])[:160] if verdict and verdict[0] else ('accepted' if t[1] == 'completed' else ''),
            'answer': ' '.join(str(answer[0]).split())[:300] if answer else ''}


def examples_for(conn, task, limit=2):
    """Best verified worked examples for this task's kind of work (never the task itself)."""
    from core.hb_dream_method import _words
    wanted = skills_for_text(str(task.get('title') or '') + ' ' + str(task.get('objective') or '')[:800])
    mine = _words(str(task.get('title') or '') + ' ' + str(task.get('objective') or '')[:800])
    scored = []
    for tid in verified_task_ids(conn):
        if tid == task['task_id']:
            continue
        ex = worked_example(conn, tid)
        if not ex:
            continue
        skill_match = len(wanted & set(ex['skills']))
        if not skill_match or ex['calls'] > MAX_EXAMPLE_CALLS:
            continue                                   # a meandering path is not an example worth copying
        overlap = len(mine & _words(ex['title']))
        score = skill_match * 3 + overlap + (2 if ex['state'] == 'completed' else 0) - ex['calls'] / 10
        scored.append((score, ex['task_id'], ex))
    return [ex for _, _, ex in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[:limit]]


def examples_block(conn, task, limit=2):
    picked = examples_for(conn, task, limit)
    if not picked:
        return ''
    lines = ['Worked examples from verified past work (how similar tasks were actually completed):']
    for ex in picked:
        lines.append(f"- {ex['task_id']} \"{ex['title']}\" [{', '.join(ex['skills'])}]: {ex['steps']}"
                     + (f"; verified: {ex['verdict']}" if ex['verdict'] else ''))
    return '\n'.join(lines)


def export_dataset(conn, path):
    """L1: write verified worked examples (with provenance) as JSONL for the exam / LoRA steps. Returns count."""
    count = 0
    with open(path, 'w', encoding='utf-8') as out:
        for tid in sorted(verified_task_ids(conn)):
            ex = worked_example(conn, tid)
            if not ex:
                continue
            objective = conn.execute('SELECT objective FROM hb_tasks WHERE task_id=?', (tid,)).fetchone()[0]
            out.write(json.dumps({'task_id': tid, 'skills': ex['skills'], 'objective': str(objective or '')[:4000],
                                  'tool_steps': ex['steps'], 'verdict': ex['verdict'], 'final_answer': ex['answer'],
                                  'provenance': 'hb_task_events + messages (verified: passing check or accepted)'}) + '\n')
            count += 1
    return count


def coding_lessons():
    """Owner 13 Nov: lessons from coaching carry over to every later coding turn (core/capability_packs/coding.lessons.v1.json)."""
    from pathlib import Path
    pack = json.loads((Path(__file__).resolve().parent / 'capability_packs' / 'coding.lessons.v1.json').read_text())
    return 'Coding lessons learned in earlier tasks (follow them): ' + ' '.join(f'({i}) {l}' for i, l in enumerate(pack['lessons'], 1))
