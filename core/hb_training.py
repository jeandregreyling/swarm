"""APEX's training (Practice 203; JD 20 Nov 2026: "training scripts with learning and lessons learned ... you will teach our APEX";
trainer: Claude Code).

/train run     runs core/capability_packs/apex.curriculum.v1.json through APEX (the answer-only turn, queued on APEX's own lock), grades
               every answer (facts it must contain, phrases it must not use), posts a scorecard in main chat and records each result
/train report  the last runs and the lessons learned
An exercise that fails twice in a row puts its lesson into APEX's standing lessons (core/hb_training.lessons_learned), which ride on
every card next to apex.lessons."""
import json
import threading
import time
from pathlib import Path

PACK = Path(__file__).resolve().parent / 'capability_packs' / 'apex.curriculum.v1.json'
_RUNNING = threading.Lock()


def ensure(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_training_runs(run_id TEXT, at REAL, exercise TEXT, passed INTEGER, why TEXT, answer TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_training_lessons(exercise TEXT PRIMARY KEY, lesson TEXT, learned_at REAL)')


def curriculum():
    return json.loads(PACK.read_text())['exercises']


def grade(ex, answer):
    """(passed, why) for one answer."""
    text = str(answer or '')
    low = text.lower()
    missing = [w for w in ex.get('expect_all', []) if w.lower() not in low]
    if missing:
        return False, 'missing: ' + ', '.join(missing)
    anyof = ex.get('expect_any', [])
    if anyof and not any(w.lower() in low for w in anyof):
        return False, 'none of: ' + ', '.join(anyof)
    bad = [w for w in ex.get('forbid', []) if w.lower() in low]
    if bad:
        return False, 'said: ' + ', '.join(bad)
    return True, 'ok'


def lessons_learned(conn):
    ensure(conn)
    return [r[0] for r in conn.execute('SELECT lesson FROM hb_training_lessons ORDER BY learned_at')]


def run(connect, answer=None, say=None, now=None):
    """Run the curriculum once. Returns (passed, total)."""
    if answer is None:
        from core.hb_channels import answer_only as answer
    run_id = 'TR-' + time.strftime('%Y%m%d-%H%M%S')
    exercises = curriculum()
    passed = 0
    lines = []
    for ex in exercises:
        try:
            reply = answer(ex['prompt'], [])
        except Exception as exc:
            reply = f'(no answer: {type(exc).__name__}: {exc})'
        ok, why = grade(ex, reply)
        passed += ok
        lines.append(f"{'✅' if ok else '❌'} {ex['id']} ({ex['kind']}){'' if ok else ' - ' + why}")
        conn = connect()
        try:
            ensure(conn)
            conn.execute('INSERT INTO hb_training_runs VALUES (?,?,?,?,?,?)', (run_id, now or time.time(), ex['id'], int(ok), why, str(reply)[:3000]))
            if not ok:
                last = [r[0] for r in conn.execute('SELECT passed FROM hb_training_runs WHERE exercise=? ORDER BY at DESC LIMIT 2', (ex['id'],))]
                if len(last) == 2 and not any(last):
                    conn.execute('INSERT OR REPLACE INTO hb_training_lessons VALUES (?,?,?)', (ex['id'], ex['lesson'], time.time()))
                    lines.append(f"   ↳ lesson learned (failed twice): {ex['lesson']}")
            conn.commit()
        finally:
            conn.close()
    if say:
        say(f'🎓 Training run {run_id} (trainer: Claude Code): APEX passed {passed} / {len(exercises)}\n' + '\n'.join(lines))
    return passed, len(exercises)


def report(conn):
    ensure(conn)
    runs = conn.execute('SELECT run_id, SUM(passed), COUNT(*), MAX(at) FROM hb_training_runs GROUP BY run_id ORDER BY MAX(at) DESC LIMIT 5').fetchall()
    learned = lessons_learned(conn)
    return ('🎓 APEX training: ' + ('; '.join(f'{r[0]} {r[1]}/{r[2]}' for r in runs) if runs else 'no runs yet - /train run starts one') +
            ('\nLessons learned: ' + ' | '.join(learned) if learned else ''))


def command(conn, args, actor):
    """/train [run|report]"""
    if args and args[0].lower() == 'run':
        if not _RUNNING.acquire(blocking=False):
            return 'A training run is already going - its scorecard comes here.'

        def work():
            from contextlib import closing
            from utils.db._connection import get_connection
            from core.hb_model_bench import _post

            def say(text):
                with closing(get_connection()) as c:
                    _post(c, text)
                    c.commit()
            try:
                run(get_connection, say=say)
            finally:
                _RUNNING.release()
        threading.Thread(target=work, name='hb-apex-training', daemon=True).start()
        return f'🎓 Training run started ({len(curriculum())} exercises through APEX, one at a time) - the scorecard comes here.'
    return report(conn)
