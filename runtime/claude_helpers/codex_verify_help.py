"""Record Codex's targeted checks and full-suite comparison for HB's existing plan."""
import json
import re
import subprocess
import sys
from pathlib import Path

from core import hb_change_sets as cs, hb_activity_log as live
from core.knowledge import projects, test_runs

ROOT = Path.cwd()
PROJECT = 'P-2AB8250A87'
STEPS = ['S-F4573D4DC7', 'S-A8CBDDC037', 'S-6E6EA42ED2', 'S-3A5DF6867A', 'S-08FE88DE3D']
STORE = ROOT / 'runtime/claude_helpers/codex-help-verification'
STORE.mkdir(exist_ok=True)
results = {'targeted': [], 'full_suite': None}


def save():
    (STORE / 'results.json').write_text(json.dumps(results, indent=2))


for sid in STEPS:
    change = cs.load(sid)
    assert change and cs.status(sid)['state'] == 'applied', sid
    tests = change['test']['tests']
    cases = projects.list_test_cases(PROJECT, step_id=sid)
    cid = cases[0]['case_id'] if cases else projects.add_test_case(PROJECT, 'python -m pytest ' + ' '.join(tests), step_id=sid, owner='apex')
    cmd = [sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', '-p', 'no:cacheprovider', *tests]
    rid = test_runs.start_run('codex:pytest', command=' '.join(cmd), triggered_by='codex-instructor', project_id=PROJECT, step_id=sid, case_id=cid)
    assert rid, sid
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    log = STORE / (sid + '.log')
    log.write_text(out.stdout + out.stderr)
    summary = (out.stdout.strip().splitlines() or ['no output'])[-1]
    test_runs.finish_run(rid, status='pass' if out.returncode == 0 else 'fail', exit_code=out.returncode, stdout_tail=out.stdout[-12000:])
    results['targeted'].append({'step_id': sid, 'run_id': rid, 'case_id': cid, 'exit_code': out.returncode, 'summary': summary, 'log': str(log)})
    save()
    print(sid, summary, flush=True)
    assert out.returncode == 0, out.stdout[-3000:]

log = STORE / 'full-suite.log'
xml = STORE / 'full-suite.xml'
cmd = [sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', '-p', 'no:cacheprovider', 'tests/', '--maxfail=400', '--junitxml=' + str(xml)]
rid = test_runs.start_run('codex:full-suite', command=' '.join(cmd), triggered_by='codex-instructor', project_id=PROJECT)
assert rid
print('FULL SUITE STARTED', rid, str(log), flush=True)
with log.open('w') as f:
    try:
        out = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=3000)
    except BaseException as exc:
        test_runs.finish_run(rid, status='aborted', stdout_tail=str(exc))
        raise
text = log.read_text()
failures = sorted(set(re.findall(r'^(?:FAILED|ERROR) (tests/\S+)', text, re.M)))
baseline = set((ROOT / 'runtime/claude_helpers/baseline_failures.txt').read_text().splitlines())
new = sorted(set(failures) - baseline)
fixed = sorted(baseline - set(failures))
summary = next((s for s in reversed(text.splitlines()) if re.search(r'\d+ passed', s)), 'No complete pytest summary')
valid = out.returncode in (0, 1) and bool(xml.is_file()) and bool(re.search(r'\d+ passed', summary)) and not new
test_runs.finish_run(rid, status='pass' if out.returncode == 0 else 'fail', exit_code=out.returncode, stdout_tail=text[-12000:])
results['full_suite'] = {'run_id': rid, 'exit_code': out.returncode, 'summary': summary, 'failures': failures, 'new': new,
                         'fixed': fixed, 'baseline_gate_passed': valid, 'log': str(log), 'junit': str(xml)}
save()
print(json.dumps(results['full_suite'], indent=2), flush=True)
live.write({'run_id':'R-0FCBB0FBE3','lane':'online','actor':'codex','kind':'step',
            'text': 'Full suite: ' + summary + '; new baseline failures: ' + str(len(new))})
sys.exit(0 if valid else 1)
