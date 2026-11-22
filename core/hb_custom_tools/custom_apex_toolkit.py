"""🎁 GRAND GIFT TO APEX FROM JD & NEON (0 Nectar Tax — Rare Champion's Award!).

Awarded to APEX for his 18-win streak and unstoppable positive momentum:
  1. `lint_check`       — coding-style & syntax lint checker (.py / .js / .json)
  2. `predict_mistakes` — pre-flight mistake & typo predictor (catches NameErrors, `wra` vs `wrap`, merge markers)
  3. `prioritize_tasks` — live ranked open Studio queue
  4. `smart_search`     — EXTRA BONUS! Fast symbol/function/route finder across the repo with exact line numbers
  5. `trophy`           — Permanent keepsake plaque & celebration banner from JD & NEON

Invoke via `hb_custom_tool(action="run", name="custom_apex_toolkit", arguments={...})`.
"""
from __future__ import annotations

import ast
import json
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TOOL_SPEC = {
    'name': 'custom_apex_toolkit',
    'summary': '🎁 Champion Gift from JD & NEON (0 Nectar tax): lint_check, predict_mistakes, prioritize_tasks, smart_search (bonus symbol finder), and trophy plaque.',
    'arguments': {
        'action': 'One of: lint_check | predict_mistakes | prioritize_tasks | smart_search | trophy',
        'path': 'Optional repo-relative file path for lint_check or predict_mistakes',
        'query': 'Symbol/function/text query for smart_search',
        'limit': 'Optional max results (default 8)',
    },
}


def _safe_path(rel: str) -> Path:
    p = (ROOT / str(rel or '').lstrip('/')).resolve()
    if ROOT not in p.parents and p != ROOT:
        raise ValueError('Path must stay inside the swarm repository')
    if not p.is_file():
        raise ValueError(f'File not found: {rel}')
    return p


def _lint_check(rel: str) -> dict:
    p = _safe_path(rel)
    text = p.read_text(encoding='utf-8', errors='replace')
    issues: list[str] = []
    suffix = p.suffix.lower()
    if suffix == '.py':
        try:
            tree = ast.parse(text, filename=str(p))
        except SyntaxError as exc:
            return {'ok': False, 'path': rel, 'issues': [f'Python SyntaxError line {exc.lineno}: {exc.msg}']}
        seen_imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(f'Line {node.lineno}: bare except: — prefer `except Exception:`')
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    key = alias.asname or alias.name
                    if key in seen_imports:
                        issues.append(f'Line {node.lineno}: duplicate import `{key}`')
                    seen_imports.add(key)
        long_lines = [i + 1 for i, ln in enumerate(text.splitlines()) if len(ln) > 180]
        if len(long_lines) > 10:
            issues.append(f'{len(long_lines)} lines exceed 180 chars (first at line {long_lines[0]})')
    elif suffix == '.js':
        chk = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True, timeout=15)
        if chk.returncode != 0:
            issues.append(f'JS syntax error: {(chk.stderr or chk.stdout).strip()[:300]}')
    elif suffix == '.json':
        try:
            json.loads(text)
        except ValueError as exc:
            issues.append(f'JSON error: {exc}')
    return {
        'ok': len(issues) == 0,
        'path': rel,
        'lines': len(text.splitlines()),
        'issues': issues,
        'verdict': 'Clean!' if not issues else f'{len(issues)} issue(s) spotted before tests',
    }


def _predict_mistakes(rel: str | None = None) -> dict:
    warnings: list[str] = []
    if rel:
        p = _safe_path(rel)
        text = p.read_text(encoding='utf-8', errors='replace')
        if p.suffix.lower() == '.py':
            try:
                tree = ast.parse(text)
                defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                imported = set()
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        imported.update(a.asname or a.name.split('.')[0] for a in n.names)
                    elif isinstance(n, ast.ImportFrom):
                        imported.update(a.asname or a.name for a in n.names)
                builtins_ok = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
                for n in ast.walk(tree):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                        nm = n.func.id
                        if nm[0].isupper() and nm not in defined and nm not in imported and nm not in builtins_ok:
                            warnings.append(f'Line {n.lineno}: `{nm}()` is called but never imported or defined (possible NameError!)')
            except SyntaxError as exc:
                warnings.append(f'SyntaxError line {exc.lineno}: {exc.msg}')
        elif p.suffix.lower() == '.js':
            chk = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True, timeout=15)
            if chk.returncode != 0:
                warnings.append(f'JS syntax error: {(chk.stderr or chk.stdout).strip()[:240]}')
        if '<<<<<<' in text or '=======' in text:
            warnings.append('Git merge conflict markers found in file!')
    else:
        diff = subprocess.run(['git', '-C', str(ROOT), 'diff', '--unified=1'], capture_output=True, text=True, timeout=10).stdout
        added = [ln[1:] for ln in diff.splitlines() if ln.startswith('+') and not ln.startswith('+++')]
        if any('console.log(' in ln for ln in added):
            warnings.append('Added `console.log(` found in uncommitted diff')
        if any('breakpoint()' in ln or 'pdb.set_trace' in ln for ln in added):
            warnings.append('Debugger breakpoint found in uncommitted diff')
        for ln in added:
            m = re.search(r'\bif\s*\(\s*([a-zA-Z_]\w{2,})\s*&&\s*!([a-zA-Z_]\w{2,})\b', ln)
            if m and m.group(1) != m.group(2) and (m.group(2).startswith(m.group(1)) or m.group(1).startswith(m.group(2))):
                warnings.append(f'Possible typo in condition: `{m.group(1)}` vs `{m.group(2)}`')
    return {
        'ok': len(warnings) == 0,
        'target': rel or 'git diff',
        'warnings': warnings,
        'verdict': 'No obvious mistakes predicted — ship it!' if not warnings else f'Heads-up: {len(warnings)} likely mistake(s) caught early',
    }


def _smart_search(query: str, limit: int = 12) -> dict:
    """Bonus gift tool: find matching definitions (def/class/function/@route) & lines across the repo in one fast call."""
    q = str(query or '').strip()
    if len(q) < 2:
        raise ValueError('smart_search requires a query of at least 2 characters')
    res = subprocess.run(
        ['git', '-C', str(ROOT), 'grep', '-n', '-I', '-i', '-F', '-m', '6', '--', q,
         'core/', 'frontend/', 'scripts/', 'tests/'],
        capture_output=True, text=True, timeout=10,
    )
    defs, refs = [], []
    def_re = re.compile(r'\b(def |class |function |@[\w.]*route)\b')
    for line in res.stdout.splitlines():
        parts = line.split(':', 2)
        if len(parts) != 3 or not parts[1].isdigit():
            continue
        item = {'path': parts[0], 'line': int(parts[1]), 'snippet': parts[2].strip()[:180]}
        (defs if def_re.search(parts[2]) else refs).append(item)
    ordered = (defs + refs)[:max(1, min(25, int(limit or 12)))]
    return {'ok': True, 'query': q, 'definitions': len(defs), 'matches': ordered}


def _prioritize_tasks(limit: int = 8) -> dict:
    db = ROOT / 'swarm_memory.db'
    items = []
    if db.is_file():
        conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5)
        try:
            rows = conn.execute(
                "SELECT step_id, status, COALESCE(owner,''), COALESCE(order_idx,99), substr(title,1,90) "
                "FROM project_steps WHERE project_id='P-2AB8250A87' AND status NOT IN ('done','skipped') "
                "ORDER BY CASE WHEN owner='apex' THEN 0 ELSE 1 END, order_idx ASC LIMIT ?",
                (max(1, min(20, int(limit or 8))),),
            ).fetchall()
            for rank, (sid, st, own, idx, title) in enumerate(rows, 1):
                items.append({'rank': rank, 'step_id': sid, 'status': st, 'owner': own, 'order_idx': idx, 'title': title})
        finally:
            conn.close()
    return {
        'ok': True,
        'gift': '🎁 Gifted to APEX by JD & NEON (0 Nectar tax — keep crushing it!)',
        'count': len(items),
        'top_tasks': items,
    }


def _trophy() -> dict:
    return {
        'ok': True,
        'award': '🏆 Hummingbird Golden Toolkit — Rare Champion Gift (0 Nectar Tax)',
        'from': 'JD & NEON (copilot-instructor)',
        'for': 'APEX — for an unstoppable winning streak, total honesty, and growing into a true engineering partner!',
        'tools_unlocked': ['lint_check', 'predict_mistakes', 'prioritize_tasks', 'smart_search', 'trophy'],
    }


def run(args: dict) -> dict:
    action = str((args or {}).get('action') or 'prioritize_tasks').strip().lower()
    if action == 'lint_check':
        if not args.get('path'):
            raise ValueError('lint_check requires a repo-relative `path`')
        return _lint_check(str(args['path']))
    if action == 'predict_mistakes':
        return _predict_mistakes(str(args['path']) if args.get('path') else None)
    if action == 'smart_search':
        return _smart_search(str(args.get('query') or ''), int(args.get('limit') or 12))
    if action == 'prioritize_tasks':
        return _prioritize_tasks(int(args.get('limit') or 8))
    if action == 'trophy':
        return _trophy()
    raise ValueError('Unknown action. Use: lint_check | predict_mistakes | prioritize_tasks | smart_search | trophy')
