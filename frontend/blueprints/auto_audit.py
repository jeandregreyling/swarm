"""auto_audit.py — Periodic self-audit: pytest + basic lint checks.
Results stored in audit_results table; exposed via /api/audit/latest.
"""
import subprocess
import json
from datetime import datetime
from flask import Blueprint, jsonify, request
from database import get_connection, log_activity

audit_bp = Blueprint('audit', __name__)

import os as _os
_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))


def _ensure_table():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            test_passed INTEGER DEFAULT 0,
            test_failed INTEGER DEFAULT 0,
            test_errors INTEGER DEFAULT 0,
            test_skipped INTEGER DEFAULT 0,
            lint_issues INTEGER DEFAULT 0,
            summary TEXT DEFAULT '',
            raw_output TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def run_audit():
    """Execute pytest and basic lint, store results."""
    _ensure_table()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Run pytest
    # NOTE: test_chat_quality.py is excluded — it POSTs live /api/chat requests
    # which trigger ollama to load models. Not suitable for unattended audit.
    try:
        proc = subprocess.run(
            ['python3', '-m', 'pytest', 'tests/', '-x', '-q', '--tb=short',
             '--ignore=tests/test_chat_quality.py'],
            capture_output=True, text=True, timeout=120,
            cwd=_SWARM_ROOT,
        )
        test_output = (proc.stdout or '') + '\n' + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        test_output = 'pytest timed out after 120s'
    except Exception as exc:
        test_output = f'pytest error: {exc}'

    # Parse pytest summary line (e.g. "399 passed, 1 skipped")
    passed = failed = errors = skipped = 0
    for line in test_output.splitlines():
        ll = line.lower().strip()
        if 'passed' in ll or 'failed' in ll or 'error' in ll:
            import re
            m_passed = re.search(r'(\d+)\s+passed', ll)
            m_failed = re.search(r'(\d+)\s+failed', ll)
            m_errors = re.search(r'(\d+)\s+error', ll)
            m_skipped = re.search(r'(\d+)\s+skipped', ll)
            if m_passed: passed = int(m_passed.group(1))
            if m_failed: failed = int(m_failed.group(1))
            if m_errors: errors = int(m_errors.group(1))
            if m_skipped: skipped = int(m_skipped.group(1))

    # Basic lint: check for common issues
    lint_issues = 0
    try:
        proc_lint = subprocess.run(
            ['python3', '-m', 'py_compile', '--help'],
            capture_output=True, text=True, timeout=10,
            cwd=_SWARM_ROOT,
        )
        # Just count syntax errors in key files
        for subdir in ['frontend/blueprints', 'utils', 'core', 'fridays']:
            find_proc = subprocess.run(
                ['find', subdir, '-name', '*.py', '-type', 'f'],
                capture_output=True, text=True, timeout=10, cwd=_SWARM_ROOT,
            )
            for pyfile in (find_proc.stdout or '').strip().splitlines():
                if not pyfile.strip():
                    continue
                chk = subprocess.run(
                    ['python3', '-m', 'py_compile', pyfile.strip()],
                    capture_output=True, text=True, timeout=5,
                    cwd=_SWARM_ROOT,
                )
                if chk.returncode != 0:
                    lint_issues += 1
    except Exception:
        pass

    summary = f'{passed} passed, {failed} failed, {errors} errors, {skipped} skipped, {lint_issues} lint issues'
    raw = test_output[:8000]

    conn = get_connection()
    conn.execute("""
        INSERT INTO audit_results (run_at, test_passed, test_failed, test_errors, test_skipped, lint_issues, summary, raw_output)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (now, passed, failed, errors, skipped, lint_issues, summary, raw))
    conn.commit()
    conn.close()

    log_activity('audit', 'auto_audit', summary)
    return {'passed': passed, 'failed': failed, 'errors': errors, 'skipped': skipped, 'lint_issues': lint_issues, 'summary': summary}


@audit_bp.route('/api/audit/latest', methods=['GET'])
def api_audit_latest():
    """Return the most recent audit results."""
    _ensure_table()
    limit = min(int(request.args.get('limit', 10)), 50)
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, run_at, test_passed, test_failed, test_errors, test_skipped, lint_issues, summary FROM audit_results ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'results': [dict(r) for r in rows]})


@audit_bp.route('/api/audit/run', methods=['POST'])
def api_audit_run():
    """Trigger an immediate audit run."""
    result = run_audit()
    return jsonify({'ok': True, **result})
