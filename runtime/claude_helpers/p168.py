"""Prepare Practice 168: HB's auto-created 'Guarded task regression checks' case no longer blocks steps as 'needs a spec'."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
DM = 'core/hb_dream_method.py'
AT = 'core/hb_agent_tools.py'
edits = [
    {'path': DM, 'old': '''        cases = [r[0] for r in conn.execute('SELECT title FROM project_test_cases WHERE step_id=? ORDER BY created_at',
                                            (task['step_id'],)) if r[0]]
''', 'new': '''        # Practice 168 (owner 19 Nov 2026): run_tests auto-creates a case titled 'Guarded task regression checks' for a step with none;
        # taken as the step's done criterion it has no command, so 9 bug steps were skipped as 'needs a spec'. That placeholder is not
        # a criterion - the step's own 'Done when:' line is.
        cases = [r[0] for r in conn.execute('SELECT title FROM project_test_cases WHERE step_id=? ORDER BY created_at',
                                            (task['step_id'],)) if r[0] and r[0] != 'Guarded task regression checks']
'''},
    {'path': AT, 'old': "                case=projects.add_test_case(task['project_id'],'Guarded task regression checks',step_id=task['step_id'],owner='apex')\n",
     'new': ("                # Practice 168: the auto case names the command it runs, so it is a runnable criterion\n"
             "                title='Guarded task regression checks: python -m pytest '+' '.join(str(t) for t in (args.get('tests') or [])[:4])\n"
             "                case=projects.add_test_case(task['project_id'],title.strip()[:200],step_id=task['step_id'],owner='apex')\n")},
]

test = r'''"""Practice 168 (owner 19 Nov 2026): 9 bug steps were skipped as 'needs a spec' because run_tests' auto case 'Guarded task regression checks'
became their done criterion."""
import sqlite3

from core import hb_dream_method as dm, hb_plan_workflow as wf


def test_practice_168_placeholder_case_is_not_a_criterion(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE project_test_cases(case_id TEXT, step_id TEXT, title TEXT, created_at REAL)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, agent TEXT, payload TEXT)')
    c.execute("INSERT INTO project_test_cases VALUES ('C-1','S-1','Guarded task regression checks',1)")
    task = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': 'Bug: x\nDone when: python -m pytest tests/test_x.py passes\n'}
    src, crit = dm.done_when(c, task)
    assert src == 'task' and wf.runnable_check(crit[0])


def test_practice_168_auto_case_names_its_command():
    assert "'Guarded task regression checks: python -m pytest '" in open('core/hb_agent_tools.py').read()
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov (\"go be amazing\"): the bug queue stalled - 9 Bug steps skipped as 'needs a spec: no runnable check in its "
                            "Done when'. run_tests auto-creates a Studio case 'Guarded task regression checks' for a step with none, and "
                            "done_when() took that title (no command) as the step's criterion. done_when ignores the placeholder (the step's own "
                            "'Done when: python -m pytest ...' counts); new auto cases name their pytest command."),
                 edits=edits, new_files={'tests/test_practice_168_placeholder_case.py': test},
                 test={'tests': ['tests/test_practice_168_placeholder_case.py', 'tests/test_hb_plan_workflow.py', 'tests/test_hb_agent_tools.py'],
                       'keyword': ''}, run=run)
print(out['verified'])
