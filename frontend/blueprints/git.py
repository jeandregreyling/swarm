"""git.py — Git Operations routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

git_bp = Blueprint('git', __name__)

def _git_repo_root() -> Path:
    return Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent.parent)))


_GIT_ENVS = {
    'prod': Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent.parent))),
    'uat':  Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent.parent)) + '-uat'),
    'dev':  Path(os.environ.get('SWARM_ROOT', str(Path(__file__).parent.parent.parent)) + '-dev'),
}


def _git_env_root(env: str = '') -> Path:
    """Return repo root for the given environment label, or default."""
    env = str(env or '').strip().lower()
    if env in _GIT_ENVS:
        p = _GIT_ENVS[env]
        if p.is_dir():
            return p
    return _git_repo_root()



def _git_rel_path(path_value: str, env: str = '') -> str:
    rel_path = str(path_value or '').strip().replace('\\', '/').lstrip('/')
    if not rel_path:
        raise ValueError('path required')
    repo_root = _git_env_root(env).resolve()
    full_path = (repo_root / rel_path).resolve()
    if not full_path.is_relative_to(repo_root):
        raise ValueError('path outside repository')
    try:
        return str(full_path.relative_to(repo_root)).replace('\\', '/')
    except Exception as exc:
        raise ValueError(f'invalid repository path: {exc}') from exc



def _run_git_command(args, timeout=20, env=''):
    import subprocess

    repo_root = _git_env_root(env)
    proc = subprocess.run(
        ['git', '-C', str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc



def _build_git_operation_description(action: str, paths=None, message='') -> str:
    paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
    action = str(action or '').strip().lower()
    message = str(message or '').strip()

    if action == 'stage':
        human = f"Stage repository path via Git panel: {paths[0] if paths else ''}"
    elif action == 'unstage':
        human = f"Unstage repository path via Git panel: {paths[0] if paths else ''}"
    else:
        human = f"Commit staged repository changes via Git panel: {message}"

    payload = {
        'kind': 'git_operation',
        'action': action,
        'paths': paths,
        'message': message,
    }
    return f"{human}\n\nALM Git payload:\n{json.dumps(payload, ensure_ascii=True)}"



def _parse_git_operation_from_proposal(title: str, description: str):
    title_l = str(title or '').lower()
    desc = str(description or '')

    marker = re.search(r'ALM Git payload:\s*(\{.*\})\s*$', desc, flags=re.IGNORECASE | re.DOTALL)
    if marker:
        try:
            payload = json.loads(marker.group(1))
            action = str(payload.get('action') or '').strip().lower()
            if action in ('stage', 'unstage'):
                return {
                    'action': action,
                    'paths': [str(p).strip() for p in (payload.get('paths') or []) if str(p).strip()],
                }
            if action == 'commit':
                return {'action': action, 'message': str(payload.get('message') or '').strip()}
        except Exception:
            pass

    if 'git stage file' in title_l:
        m = re.search(r'Stage repository path via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'stage', 'paths': [m.group(1).strip()]} if m else None
    if 'git unstage file' in title_l:
        m = re.search(r'Unstage repository path via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'unstage', 'paths': [m.group(1).strip()]} if m else None
    if 'git commit staged changes' in title_l:
        m = re.search(r'Commit staged repository changes via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'commit', 'message': m.group(1).strip()} if m else None
    return None



def _execute_git_operation(operation: dict, proposal_id=''):
    action = str((operation or {}).get('action') or '').strip().lower()
    if action not in ('stage', 'unstage', 'commit'):
        raise ValueError('unsupported git action')

    if action in ('stage', 'unstage'):
        raw_paths = operation.get('paths') or []
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
        if not rel_paths:
            raise ValueError('paths required')
        cmd = ['add', '--', *rel_paths] if action == 'stage' else ['reset', 'HEAD', '--', *rel_paths]
        proc = _run_git_command(cmd, timeout=20)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or f'git {action} failed').strip()[:500])
        return {'action': action, 'paths': rel_paths, 'count': len(rel_paths)}

    message = str(operation.get('message') or '').strip()
    if not message:
        raise ValueError('message required')

    staged = _run_git_command(['diff', '--cached', '--name-only'], timeout=20)
    if staged.returncode != 0:
        raise RuntimeError((staged.stderr or staged.stdout or 'git diff failed').strip()[:500])

    staged_paths = [line.strip() for line in (staged.stdout or '').splitlines() if line.strip()]
    if not staged_paths:
        raise ValueError('no staged changes to commit')

    final_message = message if not proposal_id else f'{message} (proposal:{proposal_id[:12]})'
    commit = _run_git_command(['commit', '-m', final_message], timeout=40)
    if commit.returncode != 0:
        raise RuntimeError((commit.stderr or commit.stdout or 'git commit failed').strip()[:500])

    rev = _run_git_command(['rev-parse', 'HEAD'], timeout=10)
    commit_hash = (rev.stdout or '').strip() if rev.returncode == 0 else ''
    return {
        'action': 'commit',
        'commit_hash': commit_hash,
        'files_changed': len(staged_paths),
        'paths': staged_paths[:200],
        'message': final_message,
    }



def _parse_git_status_porcelain(status_text: str):
    branch = ''
    upstream = ''
    ahead = 0
    behind = 0
    detached = False
    files = []

    for raw_line in (status_text or '').splitlines():
        line = raw_line.rstrip('\n')
        if not line:
            continue
        if line.startswith('## '):
            header = line[3:]
            if header.startswith('HEAD '):
                detached = True
            branch_part = header.split('...')[0].strip()
            branch = branch_part.replace('No commits yet on ', '').strip()
            if '...' in header:
                upstream = header.split('...', 1)[1].split(' [', 1)[0].strip()
            if '[' in header and ']' in header:
                details = header.split('[', 1)[1].split(']', 1)[0]
                for part in details.split(','):
                    piece = part.strip()
                    if piece.startswith('ahead '):
                        try:
                            ahead = int(piece.split(' ', 1)[1])
                        except Exception:
                            ahead = 0
                    elif piece.startswith('behind '):
                        try:
                            behind = int(piece.split(' ', 1)[1])
                        except Exception:
                            behind = 0
            continue

        if len(line) < 4:
            continue

        x = line[0]
        y = line[1]
        path_text = line[3:].strip()
        display_path = path_text.split(' -> ')[-1].strip()
        staged = x not in (' ', '?')
        unstaged = y != ' '
        untracked = x == '?' and y == '?'
        deleted = x == 'D' or y == 'D'
        renamed = x == 'R' or y == 'R' or ' -> ' in path_text
        conflicted = x == 'U' or y == 'U' or (x == 'A' and y == 'A') or (x == 'D' and y == 'D')

        if conflicted:
            status_label = 'conflict'
        elif untracked:
            status_label = 'untracked'
        elif deleted:
            status_label = 'deleted'
        elif renamed:
            status_label = 'renamed'
        elif staged and unstaged:
            status_label = 'mixed'
        elif staged:
            status_label = 'staged'
        elif unstaged:
            status_label = 'modified'
        else:
            status_label = 'unknown'

        files.append({
            'path': display_path,
            'raw_path': path_text,
            'x': x,
            'y': y,
            'staged': staged,
            'unstaged': unstaged,
            'untracked': untracked,
            'deleted': deleted,
            'renamed': renamed,
            'conflicted': conflicted,
            'status_label': status_label,
        })

    return {
        'branch': branch,
        'upstream': upstream,
        'ahead': ahead,
        'behind': behind,
        'detached': detached,
        'files': files,
    }


@git_bp.route('/api/git/environments', methods=['GET'])
def api_git_environments():
    """List available git environments (worktrees)."""
    envs = []
    for label, path in _GIT_ENVS.items():
        envs.append({
            'name': label,
            'path': str(path),
            'available': path.is_dir(),
        })
    return jsonify({'ok': True, 'environments': envs})


@git_bp.route('/api/git/status', methods=['GET'])
def api_git_status():
    """Return repository status for the Fridays Git panel."""
    env = request.args.get('environment', '')
    check_remote = str(request.args.get('check_remote') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    remote_check = {'checked': False, 'ok': True, 'error': ''}
    try:
        if check_remote:
            fetch = _run_git_command(['fetch', '--quiet', '--prune', 'origin'], timeout=40, env=env)
            remote_check['checked'] = True
            if fetch.returncode != 0:
                remote_check['ok'] = False
                remote_check['error'] = (fetch.stderr or fetch.stdout or 'git fetch failed').strip()[:500]
        proc = _run_git_command(['status', '--porcelain=1', '--branch'], timeout=20, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git status failed').strip()[:500]}), 500

    parsed = _parse_git_status_porcelain(proc.stdout or '')
    files = parsed['files']
    return jsonify({
        'ok': True,
        'environment': env or 'prod',
        'branch': parsed['branch'],
        'upstream': parsed['upstream'],
        'ahead': parsed['ahead'],
        'behind': parsed['behind'],
        'remote_check': remote_check,
        'out_of_sync': {
            'needs_pull': parsed['behind'] > 0,
            'needs_push': parsed['ahead'] > 0,
            'summary': (
                f"Local branch is behind {parsed['upstream']} by {parsed['behind']} commit(s). Pull before continuing."
                if parsed['behind'] > 0 and parsed['upstream'] else
                f"Local branch is ahead of {parsed['upstream']} by {parsed['ahead']} commit(s). Push when ready."
                if parsed['ahead'] > 0 and parsed['upstream'] else
                ''
            ),
        },
        'detached': parsed['detached'],
        'clean': len(files) == 0,
        'counts': {
            'changed': len(files),
            'staged': sum(1 for entry in files if entry['staged']),
            'unstaged': sum(1 for entry in files if entry['unstaged']),
            'untracked': sum(1 for entry in files if entry['untracked']),
            'conflicted': sum(1 for entry in files if entry['conflicted']),
        },
        'files': files,
    })



@git_bp.route('/api/git/diff', methods=['GET'])
def api_git_diff():
    """Return a unified diff for a repository path."""
    path_value = request.args.get('path', '')
    staged = request.args.get('staged', '0') == '1'
    env = request.args.get('environment', '')
    try:
        rel_path = _git_rel_path(path_value, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    args = ['diff']
    if staged:
        args.append('--cached')
    args.extend(['--', rel_path])

    try:
        proc = _run_git_command(args, timeout=20, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git diff failed').strip()[:500]}), 500

    diff_text = proc.stdout or ''
    truncated = len(diff_text) > 120000
    if truncated:
        diff_text = diff_text[:120000] + '\n[... diff truncated]'

    return jsonify({
        'ok': True,
        'path': rel_path,
        'staged': staged,
        'diff': diff_text,
        'truncated': truncated,
    })



@git_bp.route('/api/git/stage', methods=['POST'])
def api_git_stage():
    """Stage one or more repository paths."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    env = str(data.get('environment', '')).strip()
    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    try:
        rel_paths = [_git_rel_path(item, env=env) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required'}), 400

    try:
        proc = _run_git_command(['add', '--', *rel_paths], timeout=20, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git add failed').strip()[:500]}), 500

    log_activity('terminal', 'git_stage', ', '.join(rel_paths[:8]))
    return jsonify({'ok': True, 'paths': rel_paths, 'count': len(rel_paths)})



@git_bp.route('/api/git/unstage', methods=['POST'])
def api_git_unstage():
    """Unstage one or more repository paths."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    env = str(data.get('environment', '')).strip()
    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    try:
        rel_paths = [_git_rel_path(item, env=env) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required'}), 400

    try:
        proc = _run_git_command(['reset', 'HEAD', '--', *rel_paths], timeout=20, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git reset failed').strip()[:500]}), 500

    log_activity('terminal', 'git_unstage', ', '.join(rel_paths[:8]))
    return jsonify({'ok': True, 'paths': rel_paths, 'count': len(rel_paths)})



@git_bp.route('/api/git/commit', methods=['POST'])
def api_git_commit():
    """Commit staged repository changes."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    env = str(data.get('environment', '')).strip()
    message = str(data.get('message') or '').strip()
    proposal_id = str(data.get('proposal_id') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'message required'}), 400

    try:
        staged = _run_git_command(['diff', '--cached', '--name-only'], timeout=20, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if staged.returncode != 0:
        return jsonify({'ok': False, 'error': (staged.stderr or staged.stdout or 'git diff failed').strip()[:500]}), 500

    staged_paths = [line.strip() for line in (staged.stdout or '').splitlines() if line.strip()]
    if not staged_paths:
        return jsonify({'ok': False, 'error': 'no staged changes to commit'}), 400

    final_message = message if not proposal_id else f'{message} (proposal:{proposal_id[:12]})'
    try:
        commit = _run_git_command(['commit', '-m', final_message], timeout=40, env=env)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if commit.returncode != 0:
        return jsonify({'ok': False, 'error': (commit.stderr or commit.stdout or 'git commit failed').strip()[:500]}), 500

    rev = _run_git_command(['rev-parse', 'HEAD'], timeout=10, env=env)
    commit_hash = (rev.stdout or '').strip() if rev.returncode == 0 else ''
    log_activity('terminal', 'git_commit', commit_hash[:12] or final_message[:48])
    return jsonify({
        'ok': True,
        'commit_hash': commit_hash,
        'files_changed': len(staged_paths),
        'paths': staged_paths[:200],
        'message': final_message,
    })


