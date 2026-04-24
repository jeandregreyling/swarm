"""blueprints/coding_bible.py — Coding Bible retrieval API.

Endpoints:
- GET /api/coding-bible        → full Markdown body (text/plain).
- GET /api/coding-bible/quick  → just the quick-card block injected into
                                  coder agent system prompts (text/plain).
- GET /api/coding-bible/json   → JSON {full, quick, version}.
"""
from flask import Blueprint, Response, jsonify

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'utils'))

from coding_bible import full_text, quick_card  # type: ignore

coding_bible_bp = Blueprint('coding_bible_bp', __name__)


def _version() -> str:
    txt = full_text()
    for line in txt.splitlines():
        s = line.strip()
        if s.lower().startswith('version:'):
            return s.split(':', 1)[1].strip()
    return ''


@coding_bible_bp.route('/api/coding-bible', methods=['GET'])
def get_full():
    return Response(full_text(), mimetype='text/markdown; charset=utf-8')


@coding_bible_bp.route('/api/coding-bible/quick', methods=['GET'])
def get_quick():
    return Response(quick_card(), mimetype='text/plain; charset=utf-8')


@coding_bible_bp.route('/api/coding-bible/json', methods=['GET'])
def get_json():
    return jsonify({
        'ok': True,
        'version': _version(),
        'full': full_text(),
        'quick': quick_card(),
    })


@coding_bible_bp.route('/api/coding-bible/probe', methods=['GET'])
def get_probe():
    """V7C-R15 runtime probe — is the Bible actually prefixed on every coder
    agent's in-memory system prompt right now? Proves rollout rather than
    asserting source-file strings."""
    try:
        from core.coding_bible_probe import probe
        return jsonify(probe())
    except Exception as e:
        return jsonify({'ok': False, 'error': f'probe failed: {e}'}), 500
