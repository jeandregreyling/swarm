"""grokpot_bp.py — Studio Grok Pot tile backend.

Lists the curated Grok Pot intake docs and the matching origin/grok-pot-*
branches so the operator can review Grok suggestions, compare branches, and
pull selected work without using the shell.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request

grokpot_bp = Blueprint('grokpot', __name__)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_GROK_DIRS = [
    _REPO_ROOT / 'sandpits' / 'studio' / 'grok_pot',
    _REPO_ROOT / 'sandpits' / 'studio' / 'Grok-Pot-Money-Maker',
]


def _list_docs(base: Path):
    out = []
    if not base.exists():
        return out
    for p in sorted(base.rglob('*')):
        if not p.is_file():
            continue
        if any(part.startswith('.') for part in p.relative_to(base).parts):
            continue
        if p.suffix.lower() not in {'.md', '.txt', '.json', '.yml', '.yaml'}:
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        out.append({
            'path': str(p.relative_to(_REPO_ROOT)),
            'name': p.name,
            'bytes': stat.st_size,
            'mtime': int(stat.st_mtime),
        })
    return out


def _grok_branches():
    try:
        proc = subprocess.run(
            ['git', '-C', str(_REPO_ROOT), 'for-each-ref',
             '--sort=-committerdate',
             '--format=%(refname:short)\t%(committerdate:iso8601)\t%(subject)',
             'refs/remotes/origin/'],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        return [], str(exc)
    if proc.returncode != 0:
        return [], (proc.stderr or '').strip()[:300]
    rows = []
    for line in (proc.stdout or '').splitlines():
        parts = line.split('\t', 2)
        if len(parts) < 2:
            continue
        ref = parts[0].strip()
        short = ref.split('/', 1)[1] if ref.startswith('origin/') else ref
        if 'grok' not in short.lower() and 'pot' not in short.lower():
            continue
        rows.append({
            'ref': ref,
            'short': short,
            'committed_at': parts[1].strip(),
            'subject': parts[2].strip() if len(parts) > 2 else '',
        })
    return rows, None


@grokpot_bp.route('/api/grokpot/summary', methods=['GET'])
def api_grokpot_summary():
    sections = []
    for base in _GROK_DIRS:
        sections.append({
            'label': base.name,
            'path': str(base.relative_to(_REPO_ROOT)) if base.exists() else None,
            'exists': base.exists(),
            'docs': _list_docs(base),
        })
    branches, branch_err = _grok_branches()
    return jsonify({
        'ok': True,
        'sections': sections,
        'branches': branches,
        'branch_error': branch_err,
    })


@grokpot_bp.route('/api/grokpot/doc', methods=['GET'])
def api_grokpot_doc():
    rel = (request.args.get('path') or '').strip().lstrip('/')
    if not rel or '..' in rel.split('/'):
        return jsonify({'ok': False, 'error': 'invalid path'}), 400
    target = (_REPO_ROOT / rel).resolve()
    try:
        target.relative_to(_REPO_ROOT / 'sandpits' / 'studio')
    except ValueError:
        return jsonify({'ok': False, 'error': 'outside grok pot scope'}), 400
    if not target.exists() or not target.is_file():
        return jsonify({'ok': False, 'error': 'not found'}), 404
    try:
        size = target.stat().st_size
        with open(target, encoding='utf-8', errors='replace') as f:
            content = f.read(200_000)
    except OSError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({
        'ok': True,
        'path': rel,
        'bytes': size,
        'truncated': size > 200_000,
        'content': content,
    })
