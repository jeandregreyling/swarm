"""Owner 13 Nov: DEOS becomes DOES everywhere in HB. A guarded, reviewed rename that APEX operates file by file (tool does_rename).

The mapping lives in core/capability_packs/does.rename.v1.json (rules, files to skip, files changed by hand, file moves).
Every change: the result must still parse (Python, JSON, JavaScript), a "before" copy is kept under runtime/change_sets/does-rename/,
and the change is recorded on the task. Moved modules leave a temporary alias at the old path so nothing breaks half-way;
remove_alias deletes it once nothing uses the old name.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'core' / 'capability_packs' / 'does.rename.v1.json'
BEFORE = ROOT / 'runtime' / 'change_sets' / 'does-rename'
ALIAS_MARK = 'DOES rename: temporary alias'


def pack():
    return json.loads(PACK.read_text())


def _keep(line, data):
    return any(mark in line for mark in data['keep_line_markers'])


def rewrite(text, data=None):
    """Apply the rename rules line by line; lines with a keep marker are left alone."""
    data = data or pack()
    rules = [(re.compile(old), new) for old, new in data['rules']]
    out = []
    for line in text.split('\n'):
        if not _keep(line, data):
            for pattern, new in rules:
                line = pattern.sub(new, line)
        out.append(line)
    return '\n'.join(out)


def remaining(root=ROOT, data=None):
    """Every line in HB's code that still says deos (any case), outside the skipped files and kept lines: the progress meter."""
    data = data or pack()
    found = []
    for top in data['roots']:
        for path in sorted((Path(root) / top).rglob('*')):
            rel = str(path.relative_to(root))
            if (not path.is_file() or path.suffix not in data['extensions'] or rel in data['skip_files']
                    or '__pycache__' in rel or '.orig' in rel):
                continue
            try:
                text = path.read_text(errors='replace')
            except OSError:
                continue
            if ALIAS_MARK in text:
                continue
            for number, line in enumerate(text.split('\n'), 1):
                if re.search('(?<![a-z])deos', line, re.I) and not _keep(line, data):     # 'videos' is not a DEOS reference
                    found.append((rel, number, line.strip()[:160]))
    return found


def _problem(path, text):
    if path.endswith('.py'):
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return f'Python does not parse at line {exc.lineno}: {exc.msg}'
    elif path.endswith('.json'):
        try:
            json.loads(text)
        except ValueError as exc:
            return f'JSON does not parse: {exc}'
    elif path.endswith('.js') and shutil.which('node'):
        with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8') as handle:
            handle.write(text); handle.flush()
            result = subprocess.run([shutil.which('node'), '--check', handle.name], capture_output=True, text=True, timeout=15)
        if result.returncode:
            return 'JavaScript does not parse'
    return None


def _write(target, text):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name('.' + target.name + '.does-rename.tmp')
    tmp.write_text(text)
    os.replace(tmp, target)


def _save_before(rel, text, root):
    copy = Path(root) / 'runtime' / 'change_sets' / 'does-rename' / (rel + f'.{int(time.time())}.before')
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(text)
    return str(copy.relative_to(root))


def _safe_rel(path, root, data):
    rel = str(Path(path)).lstrip('/')
    full = (Path(root) / rel).resolve()
    if not str(full).startswith(str(Path(root).resolve()) + os.sep):
        raise PermissionError('Path is outside the repository')
    if not any(rel.startswith(top + '/') for top in data['roots']) or Path(rel).suffix not in data['extensions']:
        raise PermissionError('Only HB code files (core, utils, agents, fridays, frontend, scripts, tests) are part of the DOES rename')
    return rel, full


def apply(path, root=ROOT):
    """Rename DEOS to DOES in one file. Returns what changed; refuses files changed by hand, skipped files and broken results."""
    data = pack()
    rel, full = _safe_rel(path, root, data)
    if rel in data['skip_files']:
        raise PermissionError(f'{rel} is skipped on purpose (it records the rename itself)')
    if rel in data['manual']:
        raise PermissionError(f'{rel} is changed by hand, not by the tool: ' + data['manual'][rel])
    if not full.is_file():
        raise ValueError(f'{rel} does not exist')
    before = full.read_text()
    pending = [line for line in data.get('manual_first', {}).get(rel, []) if line in before]
    if pending:
        raise PermissionError(f'{rel}: patch these lines by hand first (' + data.get('manual_first_note', '') + '): ' + ' | '.join(pending)
                              + '. This file has its own step that lists the exact hand edits; if your step does not give them, skip this file '
                              'and apply the next one.')
    after = rewrite(before, data)
    if after == before:
        return {'path': rel, 'lines_changed': 0, 'note': 'nothing left to rename in this file'}
    problem = _problem(rel, after)
    if problem:
        raise ValueError(f'The renamed {rel} would break ({problem}); nothing was changed')
    copy = _save_before(rel, before, root)
    _write(full, after)
    changed = sum(1 for a, b in zip(before.split('\n'), after.split('\n')) if a != b)
    return {'path': rel, 'lines_changed': changed, 'before_copy': copy}


def _module(rel):
    return rel[:-3].replace('/', '.')


def move(path, root=ROOT):
    """Move a renamed module to its DOES name (contents renamed too). The old Python module becomes a temporary alias;
    an old test file is removed (a copy is kept) so tests are not collected twice."""
    data = pack()
    rel, full = _safe_rel(path, root, data)
    target_rel = dict(data['moves']).get(rel)
    if not target_rel:
        raise PermissionError(f'{rel} is not in the list of files to move')
    target = Path(root) / target_rel
    if target.exists():
        raise ValueError(f'{target_rel} already exists; the move is done')
    before = full.read_text()
    after = rewrite(before, data)
    problem = _problem(target_rel, after)
    if problem:
        raise ValueError(f'The moved {target_rel} would break ({problem}); nothing was changed')
    copy = _save_before(rel, before, root)
    _write(target, after)
    if rel.startswith('tests/'):
        full.unlink()
        return {'moved': rel, 'to': target_rel, 'before_copy': copy, 'old_path': 'removed (test file)'}
    alias = (f'"""{ALIAS_MARK}. This module moved to {target_rel}; remove the alias when nothing imports the old name."""  # DOES-compat\n'
             f'import importlib as _importlib  # DOES-compat\nimport sys as _sys  # DOES-compat\n'
             f"_sys.modules[__name__] = _importlib.import_module('{_module(target_rel)}')  # DOES-compat\n")
    _write(full, alias)
    return {'moved': rel, 'to': target_rel, 'before_copy': copy, 'old_path': 'temporary alias'}


def remove_alias(path, root=ROOT):
    """Delete a temporary alias once no HB code imports the old module name."""
    data = pack()
    rel, full = _safe_rel(path, root, data)
    if not full.is_file() or ALIAS_MARK not in full.read_text():
        raise ValueError(f'{rel} is not a temporary DOES alias')
    old = _module(rel)
    users = [r for r in remaining(root, data) if old.split('.')[-1] in r[2]]
    if users:
        raise ValueError(f'{old} is still used: ' + '; '.join(f'{p}:{n}' for p, n, _ in users[:5]))
    _save_before(rel, full.read_text(), root)
    full.unlink()
    return {'removed_alias': rel}


def call(args):
    """APEX tool does_rename: {"action": "apply" | "move" | "remove_alias" | "status", "path": "..."}."""
    action = args.get('action')
    if set(args) - {'action', 'path'} or action not in ('apply', 'move', 'remove_alias', 'status'):
        raise ValueError('does_rename takes action (apply, move, remove_alias or status) and path')
    if action == 'status':
        left = remaining()
        files = {}
        for p, n, _ in left:
            files[p] = files.get(p, 0) + 1
        return {'lines_left': len(left), 'files_left': files, 'moves_left': [a for a, b in pack()['moves'] if not (ROOT / b).exists()],
                'manual_files': pack()['manual']}
    if not args.get('path'):
        raise ValueError('does_rename needs a path for ' + action)
    result = {'apply': apply, 'move': move, 'remove_alias': remove_alias}[action](args['path'])
    if action == 'apply':
        # Owner 14 Nov: APEX re-applied six finished files in a loop ("succeeded, nothing left") and never reached the rest.
        # Every apply now says what is still left in the same folder and what to do next, so the tool itself keeps APEX on track.
        top = str(result['path']).split('/', 1)[0] + '/'
        files = []
        for p, _, _ in remaining():
            if p.startswith(top) and p not in files and p not in pack()['manual'] and p not in pack().get('manual_first', {}):
                files.append(p)
        result['still_to_rename_in_' + top] = files[:12]
        later = [p for p in pack().get('manual_first', {}) if p.startswith(top) and p != result['path']]
        if later:
            result['later_steps'] = {p: 'its own step patches lines by hand first; leave it' for p in later}
        if files:
            result['next'] = (f"apply {files[0]} next. " if result.get('lines_changed') == 0 else '') + \
                f"{len(files)} file(s) in {top} still say DEOS; do not apply a file that already reported nothing left."
        else:
            elsewhere = []
            for p, _, _ in remaining():
                if p not in elsewhere and p not in pack()['manual'] and p not in pack().get('manual_first', {}):
                    elsewhere.append(p)
            result['next'] = (f'{top} is clean. Still DEOS in other folders: ' + ', '.join(elsewhere[:10]) +
                              '. Apply the ones your step covers, then run the step test.' if elsewhere
                              else f'{top} is clean and nothing is left anywhere: run the step test now.')
    return result
