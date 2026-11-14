"""Owner 13 Nov: system review and cleanup. APEX (with Nanny checking) maps the repository and moves files into one folder
structure with a visible archive. Nothing is deleted. Every move is logged and can be undone (tool: layout).

Actions: inventory (map of the repo root), move {path, to} (file or folder inside the repo), undo (last move), log.
A move is refused if the target exists, if it touches .git/.venv/runtime, or if live code still imports the path
(move it to an archive only when nothing uses it; references must be fixed first)."""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'runtime' / 'change_sets' / 'layout' / 'moves.jsonl'
PROTECTED = {'.git', '.venv', 'runtime', 'swarm_memory.db', 'node_modules'}


def _rel(path, root):
    rel = str(Path(str(path).strip()).as_posix()).strip('/')
    full = (Path(root) / rel).resolve()
    if not rel or not str(full).startswith(str(Path(root).resolve()) + os.sep):
        raise PermissionError('Path must be inside the repository')
    if rel.split('/')[0] in PROTECTED or rel.endswith(('.db', '.sqlite')):
        raise PermissionError(f'{rel} is protected (git, environment, runtime data or databases)')
    return rel, full


def _references(rel, root):
    """Live code that names this path or its Python module."""
    stem = rel[:-3].replace('/', '.') if rel.endswith('.py') else rel
    names = {rel, stem, Path(rel).name}
    if rel.endswith('.py'):
        names.add(Path(rel).stem)
    pattern = '|'.join(re.escape(n) for n in names if len(n) > 3)
    try:
        out = subprocess.run(['grep', '-rlE', pattern, '--include=*.py', '--include=*.js', '--include=*.html', '--include=*.service',
                              'core', 'utils', 'agents', 'fridays', 'frontend', 'scripts'], cwd=root, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ['(reference check failed)']
    return [p for p in out.split() if p != rel and not p.startswith(rel + '/')][:20]


def inventory(root=ROOT):
    rows = []
    for entry in sorted(Path(root).iterdir()):
        if entry.name in PROTECTED or entry.name.startswith('.'):
            continue
        files = [entry] if entry.is_file() else [p for p in entry.rglob('*') if p.is_file()][:20000]
        size = sum(p.stat().st_size for p in files if p.exists())
        latest = max((p.stat().st_mtime for p in files if p.exists()), default=0)
        rows.append({'path': entry.name, 'kind': 'file' if entry.is_file() else 'folder', 'files': len(files),
                     'size_mb': round(size / 1e6, 2), 'last_changed': time.strftime('%Y-%m-%d', time.localtime(latest)) if latest else '',
                     'used_by': _references(entry.name, root)[:5]})
    return {'root_entries': len(rows), 'entries': rows}


def move(path, to, root=ROOT):
    rel, full = _rel(path, root)
    dst_rel, dst = _rel(to, root)
    if not full.exists():
        raise ValueError(f'{rel} does not exist')
    if dst.exists():
        raise ValueError(f'{dst_rel} already exists; nothing moved')
    users = _references(rel, root)
    if users:
        raise PermissionError(f'{rel} is still used by live code: ' + ', '.join(users[:8]) + '. Fix those references first or leave it.')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(full), str(dst))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as handle:
        handle.write(json.dumps({'at': time.time(), 'from': rel, 'to': dst_rel}) + '\n')
    return {'moved': rel, 'to': dst_rel, 'undo': 'layout undo restores it'}


def _entries():
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []


def undo(root=ROOT):
    entries = _entries()
    if not entries:
        raise ValueError('No moves to undo')
    last = entries[-1]
    src, dst = Path(root) / last['to'], Path(root) / last['from']
    if dst.exists() or not src.exists():
        raise ValueError(f"Cannot undo: {last['from']} exists again or {last['to']} is gone")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    LOG.write_text(''.join(json.dumps(e) + '\n' for e in entries[:-1]))
    return {'restored': last['from']}


def call(args):
    action = args.get('action')
    if action == 'inventory':
        return inventory()
    if action == 'log':
        return {'moves': _entries()[-50:]}
    if action == 'undo':
        return undo()
    if action == 'move':
        if not args.get('path') or not args.get('to'):
            raise ValueError('layout move needs path and to')
        return move(args['path'], args['to'])
    raise ValueError('layout takes action inventory, move (path, to), undo or log')
