"""Prepared change sets (owner 14 Nov 2026): "prepare the patch files for HB on all open tasks and let them run through APEX instead of
making APEX and Fred do everything from scratch".

Claude Code (or later a capable model) prepares a step's change as exact edits and new files, PROVES it (applies it, runs the step's
test, reverts), and saves it with the fingerprint of every file it touches. APEX then operates it with one tool, change_set:

  show    the diff, the files and the test - APEX reads what will change (this is where it learns)
  apply   HB applies the edits exactly (no copying by the model, so no copy errors), keeps a before-copy of every file, refuses an
          edit whose text is no longer there, and checks Python / JavaScript still parse
  status  applied, not applied, or partly applied

Then APEX runs the step's test and reports in a few lines what changed and why. Each applied set is a verified worked example.
"""
import ast
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'runtime' / 'change_sets' / 'steps'


def _dir(step_id, root=None):
    return Path(root or ROOT) / 'runtime' / 'change_sets' / 'steps' / step_id


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _problem(rel, text):
    if rel.endswith('.py'):
        try:
            ast.parse(text, filename=rel)
        except SyntaxError as exc:
            return f'Python does not parse at line {exc.lineno}: {exc.msg}'
    if rel.endswith('.json'):
        try:
            json.loads(text)
        except ValueError as exc:
            return f'JSON does not parse: {exc}'
    if rel.endswith('.js') and shutil.which('node'):
        out = subprocess.run(['node', '--check', '-'], input=text, capture_output=True, text=True, timeout=20)
        if out.returncode:
            return 'JavaScript does not parse: ' + (out.stderr.strip().splitlines() or ['?'])[-1][:200]
    return None


def load(step_id, root=ROOT):
    path = _dir(step_id, root) / 'change_set.json'
    return json.loads(path.read_text()) if path.is_file() else None


def _target(root, rel):
    full = (Path(root) / rel).resolve()
    if not full.is_relative_to(Path(root).resolve()) or rel.startswith(('runtime/', '.git/')):
        raise PermissionError(f'{rel} is outside the files a change set may touch')
    return full


def _after(root, cs):
    """{path: (before, after)} for the whole set, or raises with the first edit that does not fit."""
    out = {}
    for rel, content in (cs.get('new_files') or {}).items():
        full = _target(root, rel)
        before = full.read_text() if full.is_file() else None
        out[rel] = (before, content)
    for n, edit in enumerate(cs.get('edits') or [], 1):
        rel = edit['path']
        full = _target(root, rel)
        before = out[rel][1] if rel in out else (full.read_text() if full.is_file() else None)
        if before is None:
            raise ValueError(f'edit {n}: {rel} does not exist')
        found = before.count(edit['old'])
        if found != 1:
            if found == 0 and before.count(edit['new']) == 1:
                out[rel] = (out[rel][0] if rel in out else before, before)    # this edit is already in
                continue
            raise ValueError(f'edit {n} in {rel}: its text is found {found} times (expected once); the file changed since the set was prepared')
        out[rel] = (out[rel][0] if rel in out else before, before.replace(edit['old'], edit['new'], 1))
    return out


def diff_text(root, cs, limit=7000):
    parts = []
    for rel, (before, after) in _after(root, cs).items():
        parts += difflib.unified_diff((before or '').splitlines(True), after.splitlines(True), f'a/{rel}', f'b/{rel}')
    text = ''.join(parts)
    return text if len(text) <= limit else text[:limit] + f'\n... ({len(text) - limit} more characters; the change set is applied whole)\n'


def status(step_id, root=ROOT):
    cs = load(step_id, root)
    if not cs:
        return {'step_id': step_id, 'state': 'none', 'note': 'No prepared change set for this step.'}
    done = []
    for rel, content in (cs.get('new_files') or {}).items():
        full = Path(root) / rel
        done.append(full.is_file() and full.read_text() == content)
    for edit in cs.get('edits') or []:
        full = Path(root) / edit['path']
        text = full.read_text() if full.is_file() else ''
        done.append(edit['old'] not in text and text.count(edit['new']) >= 1)
    state = 'applied' if all(done) else 'not applied' if not any(done) else 'partly applied'
    return {'step_id': step_id, 'state': state, 'parts': len(done), 'parts_in': sum(done), 'test': cs.get('test')}


def apply(step_id, root=ROOT):
    cs = load(step_id, root)
    if not cs:
        raise ValueError('No prepared change set for this step; do the step with your other tools.')
    if status(step_id, root)['state'] == 'applied':
        return {'state': 'ALREADY APPLIED', 'next': _next(cs)}
    planned = _after(root, cs)
    for rel, (_, after) in planned.items():
        problem = _problem(rel, after)
        if problem:
            raise ValueError(f'{rel} would break ({problem}); nothing was changed')
    backup = _dir(step_id, root) / 'before' / time.strftime('%Y%m%d-%H%M%S')
    changed = []
    for rel, (before, after) in planned.items():
        if before == after:
            continue
        if before is not None:
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            (backup / rel).write_text(before)
        full = _target(root, rel)
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_name(full.name + '.hb-tmp')
        tmp.write_text(after)
        tmp.replace(full)
        changed.append(rel)
    return {'state': 'applied', 'files': changed, 'before_copies': str(backup.relative_to(root)) if changed else None, 'next': _next(cs)}


def _next(cs):
    t = cs.get('test') or {}
    return (f'run_tests with {json.dumps({k: v for k, v in t.items() if v})}, then report in 2-4 lines what changed and why.'
            if t else 'run the step check, then report what changed and why.')


def call(args, step_id, root=ROOT):
    """APEX tool change_set: {"action": "show" | "apply" | "status"} for the step of its task."""
    action = args.get('action')
    if set(args) - {'action'} or action not in ('show', 'apply', 'status'):
        raise ValueError('change_set takes only action: show, apply or status (it works on your own step)')
    if not step_id:
        raise PermissionError('change_set needs a task linked to a Studio step')
    if action == 'status':
        return status(step_id, root)
    if action == 'apply':
        return apply(step_id, root)
    cs = load(step_id, root)
    if not cs:
        return {'state': 'none', 'note': 'No prepared change set for this step; do the step with your other tools.'}
    return {'step_id': step_id, 'why': cs.get('why', ''), 'files': sorted({e['path'] for e in cs.get('edits') or []} | set(cs.get('new_files') or {})),
            'diff': diff_text(root, cs), 'test': cs.get('test'), 'prepared_by': cs.get('prepared_by'), 'verified': cs.get('verified'),
            'next': 'Read the diff. Then change_set apply, then run the test.'}


# ------------------------------------------------------------------ preparing (Claude Code / a capable model)
def prepare(step_id, *, why, edits=(), new_files=None, test, prepared_by='claude-code', root=ROOT, run=None):
    """Save a change set and PROVE it: apply to the real files, run its test, put the files back. Returns the saved set.
    test = {"tests": [...], "keyword": "..."}; raises when the test does not pass (nothing is left changed)."""
    cs = {'step_id': step_id, 'why': why, 'edits': [dict(e) for e in edits], 'new_files': dict(new_files or {}), 'test': test,
          'prepared_by': prepared_by}
    planned = _after(root, cs)
    for rel, (_, after) in planned.items():
        problem = _problem(rel, after)
        if problem:
            raise ValueError(f'{rel}: {problem}')
    originals = {rel: before for rel, (before, _) in planned.items()}
    try:
        for rel, (_, after) in planned.items():
            _target(root, rel).write_text(after)
        cmd = [sys.executable, '-m', 'pytest', '-q', '-o', 'addopts=', '-p', 'no:cacheprovider', *test['tests']] + (
            ['-k', test['keyword']] if test.get('keyword') else [])
        out = (run or (lambda c: subprocess.run(c, cwd=root, capture_output=True, text=True, timeout=900)))(cmd)
        passed = out.returncode == 0
        summary = (out.stdout.strip().splitlines() or [''])[-1]
    finally:
        for rel, before in originals.items():
            full = _target(root, rel)
            if before is None:
                full.unlink(missing_ok=True)
            else:
                full.write_text(before)
    if not passed:
        raise AssertionError(f'change set for {step_id} does not pass its test: {summary}')
    cs['verified'] = {'at': time.strftime('%Y-%m-%d %H:%M'), 'result': summary}
    d = _dir(step_id, root)
    d.mkdir(parents=True, exist_ok=True)
    (d / 'change_set.json').write_text(json.dumps(cs, indent=1))
    (d / 'patch.diff').write_text(diff_text(root, cs, limit=10 ** 7))
    return cs
