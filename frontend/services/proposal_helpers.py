"""proposal_helpers.py — Shared helpers for proposal-related blueprints.

Extracted from frontend/blueprints/proposals.py during Session 25 Step 4.
Consumed by:
  frontend/blueprints/proposals.py
  frontend/blueprints/proposals_git.py
  frontend/blueprints/proposals_attachments.py

Keeps environment roots, git helpers, and proposal-lookup helpers in one place
so the three blueprints do not drift apart.
"""
import os
import subprocess
import threading
import time


# ── Environment roots ─────────────────────────────────────────────────────────
# PROD is always /home/seven/swarm (master branch, never touched by agents).
# UAT  is /home/seven/swarm-uat (uat branch git worktree).
# DEV  is /home/seven/swarm-dev (proposal/<id> branch git worktree).
# These must match the WorkingDirectory in the systemd service files.
_SWARM_PROD_ROOT = os.environ.get(
    'SWARM_ROOT',
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
_SWARM_UAT_ROOT = os.environ.get('SWARM_UAT_ROOT', _SWARM_PROD_ROOT + '-uat')
_SWARM_DEV_ROOT = os.environ.get('SWARM_DEV_ROOT', _SWARM_PROD_ROOT + '-dev')


def _worktrees_ready():
    """True once both swarm-uat and swarm-dev worktrees exist on disk."""
    return os.path.isdir(_SWARM_UAT_ROOT) and os.path.isdir(_SWARM_DEV_ROOT)


def _git(args, cwd=None):
    """Run a git command. Returns (stdout, returncode)."""
    try:
        result = subprocess.run(
            ['git'] + args,
            capture_output=True, text=True, timeout=30,
            cwd=cwd or _SWARM_PROD_ROOT,
        )
        return (result.stdout + result.stderr).strip(), result.returncode
    except Exception as e:
        return str(e), 1


def _restart_service_async(service_name, delay_secs=2):
    """Restart a swarm systemd service in a background thread after a brief delay.

    The delay lets the current HTTP response return before the process is killed.
    """
    def _do():
        time.sleep(delay_secs)
        subprocess.run(['sudo', 'systemctl', 'restart', service_name], timeout=30)
    threading.Thread(target=_do, daemon=True).start()


def _run_dev_tests(norm_id, title):
    """Run health check + syntax checks in the DEV worktree. Returns result string."""
    lines = [f'=== DEV Test Run — {norm_id} ===']
    dev = _SWARM_DEV_ROOT if _worktrees_ready() else _SWARM_PROD_ROOT

    # 1. Syntax check all modified Python files in this commit
    mod_out, _ = _git(['diff', '--name-only', 'HEAD~1', 'HEAD'], cwd=dev)
    py_files = [f for f in (mod_out or '').splitlines() if f.endswith('.py')]
    if py_files:
        lines.append(f'\nSyntax check ({len(py_files)} Python file(s) changed):')
        for f in py_files:
            full = os.path.join(dev, f)
            if not os.path.exists(full):
                lines.append(f'  SKIP  {f} (deleted)')
                continue
            out = subprocess.run(
                ['python3', '-m', 'py_compile', full],
                capture_output=True, text=True, timeout=10,
            )
            status = 'PASS' if out.returncode == 0 else 'FAIL'
            lines.append(f'  {status}  {f}')
            if out.returncode != 0:
                lines.append(f'       {(out.stdout + out.stderr).strip()[:200]}')
    else:
        lines.append('\nNo Python files changed in this commit.')

    # 2. Health check against DEV server (port 5051)
    lines.append('\nHealth check → http://localhost:5051/')
    try:
        import urllib.request
        resp = urllib.request.urlopen('http://localhost:5051/', timeout=5)
        lines.append(f'  PASS  DEV server responding (HTTP {resp.status})')
    except Exception as e:
        lines.append(f'  FAIL  DEV server not responding: {e}')

    # 3. Quick health_check.py smoke test (if it exists)
    hc_path = os.path.join(dev, 'scripts', 'health_check.py')
    if os.path.exists(hc_path):
        lines.append('\nSmoke test → scripts/health_check.py --port 5051:')
        hc = subprocess.run(
            ['python3', hc_path, '--port', '5051'],
            capture_output=True, text=True, timeout=30,
            cwd=dev,
        )
        hc_out = (hc.stdout + hc.stderr).strip()
        status = 'PASS' if hc.returncode == 0 else 'FAIL'
        lines.append(f'  {status}')
        lines.append('  ' + '\n  '.join(hc_out[-800:].splitlines()))

    lines.append('\n=== End test run ===')
    return '\n'.join(lines)


# Attachment storage directory (sibling to swarm.db).
# Resolved from this file: frontend/services/proposal_helpers.py → parents[2]
_ATTACHMENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'attachments', 'proposals',
)
os.makedirs(_ATTACHMENTS_DIR, exist_ok=True)


def _normalize_proposal_id(raw_id):
    if isinstance(raw_id, str):
        raw_id = raw_id.replace("INTERNAL-ELEVEN-", "").replace("INTERNAL-", "")
    return str(raw_id).strip()


def _find_proposal(conn, proposal_id, fields='*'):
    """Lookup a proposal by ID, trying the original value first before normalizing.

    _normalize_proposal_id over-strips INTERNAL-MISTRAL-NNN → MISTRAL-NNN which
    doesn't exist in the DB.  This helper tries the most-specific form first so
    IDs like INTERNAL-MISTRAL-0655 are found correctly.
    """
    norm = _normalize_proposal_id(proposal_id)
    for cid in dict.fromkeys([proposal_id, norm, f'INTERNAL-{norm}', f'INTERNAL-ELEVEN-{norm}']):
        row = conn.execute(
            f'SELECT {fields} FROM work_proposals WHERE proposal_id=?', (cid,)
        ).fetchone()
        if row:
            return row, cid
    return None, None


__all__ = [
    '_ATTACHMENTS_DIR',
    '_SWARM_DEV_ROOT',
    '_SWARM_PROD_ROOT',
    '_SWARM_UAT_ROOT',
    '_find_proposal',
    '_git',
    '_normalize_proposal_id',
    '_restart_service_async',
    '_run_dev_tests',
    '_worktrees_ready',
]
