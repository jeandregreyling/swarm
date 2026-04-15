"""workspace.py — Workspace & Code Ops routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *
import os as _os
_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              str(Path(__file__).parent.parent.parent))

workspace_bp = Blueprint('workspace', __name__)

@workspace_bp.route('/api/workspace/dir', methods=['GET'])
def api_workspace_dir():
    """
    Browse workspace directory structure.
    Query params:
    - path: directory path to list (default: /home/seven/swarm) — must be within SWARM_ROOT
    - depth: recursion depth for tree listing (default: 1, max: 3) — 0 = flat list only
    
    Returns: {ok, path, entries: [{name, type, size, modified, is_dir, permissions, ...}]}
    """
    import stat as _stat
    
    base_path = request.args.get('path', _SWARM_ROOT).strip() or _SWARM_ROOT
    try:
        depth = int(request.args.get('depth', 1) or 1)
    except ValueError:
        depth = 1
    depth = max(0, min(depth, 3))  # Cap at 3 levels
    
    # Security: only allow paths within SWARM_ROOT
    try:
        swarm_root = Path(_SWARM_ROOT)
        requested = Path(base_path).resolve()
        if not str(requested).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400
    
    if not requested.exists():
        return jsonify({'ok': False, 'error': 'path not found'}), 404
    if not requested.is_dir():
        return jsonify({'ok': False, 'error': 'path is not a directory'}), 400
    
    def _entry_dict(path):
        """Convert a file/dir to a dict with metadata."""
        try:
            stat = path.stat()
            is_dir = path.is_dir()
            return {
                'name': path.name,
                'type': 'dir' if is_dir else 'file',
                'size': stat.st_size if not is_dir else 0,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'permissions': oct(stat.st_mode)[-3:],
                'path': str(path.relative_to(swarm_root)),
            }
        except Exception:
            return None
    
    def _list_dir_recursive(dir_path, current_depth):
        """Recursively list directory with depth limit."""
        entries = []
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            for item in items:
                # Skip hidden files/dirs and common noise
                if item.name.startswith('.') or item.name in ('__pycache__', '.pytest_cache', 'node_modules'):
                    continue
                entry = _entry_dict(item)
                if entry:
                    entries.append(entry)
                    # Recurse into subdirs if within limit
                    if item.is_dir() and current_depth < depth:
                        entries.extend(_list_dir_recursive(item, current_depth + 1))
        except PermissionError:
            pass
        return entries
    
    entries = _list_dir_recursive(requested, 0)
    
    return jsonify({
        'ok': True,
        'path': str(requested.relative_to(swarm_root)),
        'absolute_path': str(requested),
        'entries': entries,
        'count': len(entries),
        'depth_limit': depth,
    })



@workspace_bp.route('/api/workspace/file', methods=['GET'])
def api_workspace_file():
    """
    Read a file from the workspace.
    Query params:
    - path: file path relative to SWARM_ROOT (required)
    - max_bytes: max size to read (default: 100000, max: 500000)
    
    Returns: {ok, path, content, size, mime_type}
    """
    import mimetypes
    
    file_path = request.args.get('path', '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'path required'}), 400
    
    try:
        max_bytes = int(request.args.get('max_bytes', 100000) or 100000)
    except ValueError:
        max_bytes = 100000
    max_bytes = max(1024, min(max_bytes, 500000))  # 1KB min, 500KB max
    
    try:
        swarm_root = Path(_SWARM_ROOT)
        full_path = (swarm_root / file_path).resolve()
        
        # Security check
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400
    
    if not full_path.exists():
        return jsonify({'ok': False, 'error': 'file not found'}), 404
    if not full_path.is_file():
        return jsonify({'ok': False, 'error': 'path is not a file'}), 400
    
    try:
        size = full_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        # Read file content (with limit)
        with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read(max_bytes)
        
        # Flag if truncated
        truncated = size > max_bytes
        
        return jsonify({
            'ok': True,
            'path': str(full_path.relative_to(swarm_root)),
            'content': content,
            'size': size,
            'truncated': truncated,
            'mime_type': mime_type or 'text/plain',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@workspace_bp.route('/api/workspace/file', methods=['PUT'])
def api_workspace_file_save():
    """
    Save a text file inside the workspace.
    JSON body:
    - path: file path relative to SWARM_ROOT (required)
    - content: new text content (required)
    - proposal_id: required when ALM gate is active
    """
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'workspace_file_write')
    if gate:
        return gate

    file_path = str(data.get('path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'path required'}), 400

    if 'content' not in data:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    content = str(data.get('content') or '')

    # Soft limit to keep payloads bounded in UI workflow.
    if len(content.encode('utf-8', errors='replace')) > 1_000_000:
        return jsonify({'ok': False, 'error': 'content too large (max 1MB)'}), 413

    try:
        swarm_root = Path(_SWARM_ROOT)
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    if not full_path.exists():
        return jsonify({'ok': False, 'error': 'file not found'}), 404
    if not full_path.is_file():
        return jsonify({'ok': False, 'error': 'path is not a file'}), 400

    # Basic binary-file guard for UI save operations.
    try:
        with open(full_path, 'rb') as fh:
            probe = fh.read(4096)
        if b'\x00' in probe:
            return jsonify({'ok': False, 'error': 'refusing to overwrite binary file'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'file probe failed: {e}'}), 500

    try:
        with open(full_path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        size = full_path.stat().st_size
        rel_path = str(full_path.relative_to(swarm_root))
        log_activity('terminal', 'workspace_file_saved', rel_path)
        return jsonify({'ok': True, 'path': rel_path, 'size': size})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@workspace_bp.route('/api/workspace/search', methods=['GET'])
def api_workspace_search():
    """
    Search for files in workspace by name pattern.
    Query params:
    - pattern: filename pattern (glob-style, * = wildcard, default: *)
    - max_results: max results to return (default: 50, max: 500)
    
    Returns: {ok, pattern, matches: [{name, path, size, type}]}
    """
    from fnmatch import fnmatch
    
    pattern = request.args.get('pattern', '*').strip() or '*'
    try:
        max_results = int(request.args.get('max_results', 50) or 50)
    except ValueError:
        max_results = 50
    max_results = max(1, min(max_results, 500))
    
    swarm_root = Path(_SWARM_ROOT)
    matches = []
    
    try:
        for path in swarm_root.rglob('*'):
            # Skip hidden, noise
            if any(part.startswith('.') for part in path.parts):
                continue
            if any(part in ('__pycache__', '.pytest_cache', 'node_modules') for part in path.parts):
                continue
            
            # Match against pattern
            if not fnmatch(path.name, pattern):
                continue
            
            if len(matches) >= max_results:
                break
            
            try:
                stat = path.stat()
                matches.append({
                    'name': path.name,
                    'path': str(path.relative_to(swarm_root)),
                    'type': 'dir' if path.is_dir() else 'file',
                    'size': stat.st_size if path.is_file() else 0,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                pass
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    
    return jsonify({
        'ok': True,
        'pattern': pattern,
        'matches': matches,
        'count': len(matches),
        'truncated': len(matches) >= max_results,
    })



def _workspace_replace_candidates(scope_path, pattern, max_files=300):
    """Return candidate files inside workspace for find/replace operations."""
    swarm_root = Path(_SWARM_ROOT)
    rel_scope = str(scope_path or '').strip().lstrip('/')
    scope = (swarm_root / rel_scope).resolve() if rel_scope else swarm_root
    if not str(scope).startswith(str(swarm_root)):
        raise ValueError('scope outside workspace')
    if not scope.exists():
        raise ValueError('scope not found')

    def _skip(path_obj):
        parts = path_obj.parts
        if any(part.startswith('.') for part in parts):
            return True
        if any(part in ('__pycache__', '.pytest_cache', 'node_modules') for part in parts):
            return True
        return False

    candidates = []
    if scope.is_file():
        if not _skip(scope.relative_to(swarm_root)):
            candidates.append(scope)
        return swarm_root, candidates

    for path in scope.rglob(pattern or '*.py'):
        if len(candidates) >= max_files:
            break
        if not path.is_file():
            continue
        rel = path.relative_to(swarm_root)
        if _skip(rel):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except Exception:
            continue
        candidates.append(path)
    return swarm_root, candidates



@workspace_bp.route('/api/workspace/replace/preview', methods=['POST'])
def api_workspace_replace_preview():
    """Preview bulk find/replace without writing files."""
    data = request.get_json() or {}
    find_text = str(data.get('find_text') or '')
    replace_text = str(data.get('replace_text') or '')
    pattern = str(data.get('pattern') or '*.py').strip() or '*.py'
    scope_path = str(data.get('scope_path') or '').strip()

    if not find_text:
        return jsonify({'ok': False, 'error': 'find_text required'}), 400
    if len(find_text) > 5000:
        return jsonify({'ok': False, 'error': 'find_text too large'}), 400

    try:
        swarm_root, candidates = _workspace_replace_candidates(scope_path, pattern, max_files=400)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    matches = []
    total_replacements = 0
    scanned = 0
    for file_path in candidates:
        scanned += 1
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        occurrences = content.count(find_text)
        if occurrences <= 0:
            continue
        total_replacements += occurrences
        line_hits = []
        for idx, line in enumerate(content.splitlines(), start=1):
            if find_text in line:
                line_hits.append(idx)
                if len(line_hits) >= 8:
                    break
        matches.append({
            'path': str(file_path.relative_to(swarm_root)),
            'occurrences': occurrences,
            'lines': line_hits,
        })

    return jsonify({
        'ok': True,
        'scope_path': scope_path,
        'pattern': pattern,
        'find_text': find_text,
        'replace_text': replace_text,
        'scanned_files': scanned,
        'matched_files': len(matches),
        'total_replacements': total_replacements,
        'matches': matches[:200],
        'truncated': len(matches) > 200,
    })



@workspace_bp.route('/api/workspace/replace/apply', methods=['POST'])
def api_workspace_replace_apply():
    """Apply bulk find/replace across workspace files."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    find_text = str(data.get('find_text') or '')
    replace_text = str(data.get('replace_text') or '')
    pattern = str(data.get('pattern') or '*.py').strip() or '*.py'
    scope_path = str(data.get('scope_path') or '').strip()

    if not find_text:
        return jsonify({'ok': False, 'error': 'find_text required'}), 400
    if len(find_text) > 5000:
        return jsonify({'ok': False, 'error': 'find_text too large'}), 400

    try:
        swarm_root, candidates = _workspace_replace_candidates(scope_path, pattern, max_files=400)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    changed_files = []
    total_replacements = 0
    for file_path in candidates:
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        occurrences = content.count(find_text)
        if occurrences <= 0:
            continue

        updated = content.replace(find_text, replace_text)
        if updated == content:
            continue

        try:
            file_path.write_text(updated, encoding='utf-8')
        except Exception:
            continue

        total_replacements += occurrences
        changed_files.append({
            'path': str(file_path.relative_to(swarm_root)),
            'occurrences': occurrences,
        })

    log_activity('terminal', 'workspace_replace_apply', f"scope={scope_path or '/'} pattern={pattern} files={len(changed_files)} replacements={total_replacements}")
    return jsonify({
        'ok': True,
        'scope_path': scope_path,
        'pattern': pattern,
        'changed_files': len(changed_files),
        'total_replacements': total_replacements,
        'changes': changed_files[:200],
        'truncated': len(changed_files) > 200,
    })



@workspace_bp.route('/api/code-ops/pytest', methods=['POST'])
def api_code_ops_pytest():
    """Run pytest on a file inside the workspace."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400

    try:
        swarm_root = Path(_SWARM_ROOT)
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
        if not full_path.exists() or not full_path.is_file():
            return jsonify({'ok': False, 'error': 'file not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'pytest', str(full_path), '-q', '--maxfail=20'],
            cwd=str(swarm_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        passed = output.count(' passed')
        failed = output.count(' failed')
        return jsonify({
            'ok': proc.returncode == 0,
            'passed': passed,
            'failed': failed,
            'returncode': proc.returncode,
            'output': output[-8000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'pytest timed out'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@workspace_bp.route('/api/code-ops/pylint', methods=['POST'])
def api_code_ops_pylint():
    """Run pylint on a Python file inside the workspace."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400
    if not file_path.endswith('.py'):
        return jsonify({'ok': False, 'error': 'only .py files supported'}), 400

    try:
        swarm_root = Path(_SWARM_ROOT)
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
        if not full_path.exists() or not full_path.is_file():
            return jsonify({'ok': False, 'error': 'file not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'pylint', str(full_path), '--output-format=text', '--score=n'],
            cwd=str(swarm_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        issue_lines = [ln for ln in output.splitlines() if ': ' in ln and ('warning' in ln.lower() or 'error' in ln.lower() or 'convention' in ln.lower() or 'refactor' in ln.lower())]
        issues = [{'line': 0, 'msg': ln[:240]} for ln in issue_lines[:20]]
        return jsonify({
            'ok': len(issues) == 0 and proc.returncode == 0,
            'count': len(issues),
            'issues': issues,
            'returncode': proc.returncode,
            'output': output[-8000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'pylint timed out'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



@workspace_bp.route('/api/code-ops/format', methods=['POST'])
def api_code_ops_format():
    """Format Python source text using black and return formatted content."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    content = str(data.get('content') or '')
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400
    if not file_path.endswith('.py'):
        return jsonify({'ok': False, 'error': 'only .py files supported'}), 400

    try:
        swarm_root = Path(_SWARM_ROOT)
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    try:
        import black
        formatted = black.format_str(content, mode=black.FileMode())
    except ImportError:
        return jsonify({'ok': False, 'error': 'black not installed'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': f'black format failed: {e}'}), 400

    orig_lines = content.split('\n')
    new_lines = formatted.split('\n')
    changed = sum(1 for a, b in zip(orig_lines, new_lines) if a != b) + abs(len(orig_lines) - len(new_lines))
    return jsonify({
        'ok': True,
        'formatted_content': formatted,
        'lines_changed': changed,
    })



@workspace_bp.route('/api/code-ops/commit', methods=['POST'])
def api_code_ops_commit():
    """Commit staged workspace changes."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    message = str(data.get('message') or 'Update via Files panel').strip()
    proposal_id = str(data.get('proposal_id') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'message required'}), 400

    import subprocess
    try:
        swarm_root = _SWARM_ROOT
        subprocess.run(['git', '-C', swarm_root, 'add', '-A'], capture_output=True, text=True, timeout=20)
        status = subprocess.run(['git', '-C', swarm_root, 'status', '--porcelain'], capture_output=True, text=True, timeout=20)
        status_lines = [ln for ln in (status.stdout or '').splitlines() if ln.strip()]
        if not status_lines:
            return jsonify({'ok': True, 'message': 'No changes to commit', 'files_changed': 0})

        final_msg = message
        if proposal_id:
            final_msg = f"{message} (proposal:{proposal_id[:12]})"

        commit = subprocess.run(
            ['git', '-C', swarm_root, 'commit', '-m', final_msg],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if commit.returncode != 0:
            return jsonify({'ok': False, 'error': (commit.stderr or commit.stdout or 'commit failed').strip()[:500]}), 500

        rev = subprocess.run(['git', '-C', swarm_root, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10)
        commit_hash = (rev.stdout or '').strip()
        return jsonify({
            'ok': True,
            'commit_hash': commit_hash,
            'files_changed': len(status_lines),
            'message': 'Changes committed',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500



