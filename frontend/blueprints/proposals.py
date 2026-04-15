import os
import uuid
import mimetypes
import subprocess
import threading
import time
from flask import Blueprint, jsonify, request, send_file
from database import get_connection   # <-- this is the key import (used everywhere else)
from proposal_status import ALL_PROPOSAL_STATUSES, normalize_proposal_status

# ── Environment roots ─────────────────────────────────────────────────────────
# PROD is always /home/seven/swarm (master branch, never touched by agents).
# UAT  is /home/seven/swarm-uat (uat branch git worktree).
# DEV  is /home/seven/swarm-dev (proposal/<id> branch git worktree).
# These must match the WorkingDirectory in the systemd service files.
_SWARM_PROD_ROOT = '/home/seven/swarm'
_SWARM_UAT_ROOT  = '/home/seven/swarm-uat'
_SWARM_DEV_ROOT  = '/home/seven/swarm-dev'

# True once both worktrees exist on disk
def _worktrees_ready():
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
    The delay lets the current HTTP response return before the process is killed."""
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

    lines.append(f'\n=== End test run ===')
    return '\n'.join(lines)

# Attachment storage directory (sibling to swarm.db)
_ATTACHMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'attachments', 'proposals')
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

proposals_bp = Blueprint('proposals', __name__)

@proposals_bp.route("/api/work-proposals", methods=["GET"])
def get_work_proposals():
    try:
        conn = get_connection()
        c = conn.cursor()
        rows = c.execute("""
            SELECT id, proposal_id, title, description, agent, status,
                   notes, source_conv_id, duck_verdict, duck_note,
                   ticket_number, queue_id, git_branch, git_commit, test_results,
                   created_at, updated_at
            FROM work_proposals
            ORDER BY id DESC
        """).fetchall()
        columns = [desc[0] for desc in c.description]
        proposals = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return jsonify({"count": len(proposals), "ok": True, "proposals": proposals})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@proposals_bp.route("/api/work-proposals/<proposal_id>", methods=["GET"])
def get_proposal_detail(proposal_id):
    """Single proposal with cross-referenced ticket + conversation."""
    try:
        conn = get_connection()
        row = conn.execute(
            """SELECT id, proposal_id, title, description, agent, status,
                      notes, source_conv_id, duck_verdict, duck_note,
                      ticket_number, queue_id, git_branch, git_commit, test_results,
                      created_at, updated_at
               FROM work_proposals WHERE proposal_id=?""",
            (proposal_id,)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"ok": False, "error": "not found"}), 404
        proposal = dict(row)

        # Linked ticket
        ticket = None
        tn = proposal.get('ticket_number')
        if tn:
            t = conn.execute(
                """SELECT ticket_number, status, question, channel, created_at, conv_id
                   FROM tickets WHERE ticket_number=?""", (tn,)
            ).fetchone()
            if t:
                ticket = dict(t)

        # Linked conversation
        conversation = None
        cid = proposal.get('source_conv_id')
        if cid:
            c = conn.execute(
                "SELECT id, title, source, created_at FROM conversations WHERE id=?", (cid,)
            ).fetchone()
            if c:
                conversation = dict(c)

        conn.close()
        return jsonify({
            "ok": True,
            "proposal": proposal,
            "ticket": ticket,
            "conversation": conversation,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@proposals_bp.route("/api/queue", methods=["POST"])
def intake():
    data = request.get_json() or {}
    agent = data.get("agent", "manual_test")
    title = data.get("title", "Untitled")
    description = data.get("description", "")
    try:
        conn = get_connection()
        c = conn.cursor()
        proposal_id = f"MANUAL-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}"
        c.execute("""INSERT INTO work_proposals
                     (proposal_id, title, description, agent, status)
                     VALUES (?,?,?,?,?)""",
                  (proposal_id, title, description, agent, "pending"))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "proposal_id": proposal_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@proposals_bp.route("/api/work-proposals/<proposal_id>/edit", methods=["PATCH"])
def edit_proposal(proposal_id):
    """Edit proposal title, description, and/or notes text."""
    try:
        data = request.get_json() or {}
        conn = get_connection()
        c = conn.cursor()
        updates, values = [], []
        if 'title' in data:
            updates.append("title = ?")
            values.append((data['title'] or '').strip())
        if 'description' in data:
            updates.append("description = ?")
            values.append(data['description'])
        if 'notes' in data:
            updates.append("notes = ?")
            values.append(data['notes'])
        if not updates:
            conn.close()
            return jsonify({"ok": False, "error": "nothing to update"})
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(proposal_id)
        c.execute(f"UPDATE work_proposals SET {', '.join(updates)} WHERE proposal_id = ?", values)
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>", methods=["DELETE"])
def delete_proposal(proposal_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM work_proposals WHERE proposal_id = ?", (proposal_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted == 0:
            return jsonify({"ok": False, "error": "proposal not found"}), 404
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@proposals_bp.route("/api/work-proposals/<proposal_id>", methods=["PATCH"])
def update_proposal_status(proposal_id):
    try:
        data = request.get_json() or {}
        new_status = normalize_proposal_status(data.get("status"))
        actor = data.get("actor", "ghost")
        note  = data.get("note", "")
        if not new_status:
            return jsonify({"ok": False, "error": "status required"})
        if new_status not in ALL_PROPOSAL_STATUSES:
            return jsonify({"ok": False, "error": f"invalid status: {new_status}"})

        normalized_id = _normalize_proposal_id(proposal_id)

        # Look up owning agent for the governance gate
        conn = get_connection()
        row = conn.execute(
            'SELECT agent FROM work_proposals WHERE proposal_id=?',
            (normalized_id,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"ok": False, "error": "proposal not found"}), 404
        agent = row['agent'] or 'unknown'

        # Route through governance state machine
        from utils.governance import transition_proposal, GovernanceError
        try:
            result = transition_proposal(
                normalized_id, new_status, agent,
                actor=actor, note=note,
            )
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        # Notify chat thread + trigger Duck quality check when done
        try:
            import sys as _sys
            _sys.path.insert(0, '/home/seven/swarm/utils')
            from proposal_review import notify_proposal_status_change
            import threading as _t
            _t.Thread(
                target=notify_proposal_status_change,
                args=(normalized_id, new_status, actor, note),
                daemon=True
            ).start()
        except Exception:
            pass

        return jsonify({"ok": True, "transition": result})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@proposals_bp.route("/api/work-proposals/<proposal_id>/duck-execute", methods=["POST"])
def duck_execute_route(proposal_id):
    """Ghost tells Duck to ship a UAT proposal to production."""
    try:
        data = request.get_json(silent=True) or {}
        actor = data.get("actor", "duck")
        import sys as _sys
        _sys.path.insert(0, '/home/seven/swarm/utils')
        from proposal_review import duck_execute_proposal
        ok, msg = duck_execute_proposal(proposal_id, actor=actor)
        return jsonify({"ok": ok, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>/agent-advance", methods=["POST"])
def agent_advance(proposal_id):
    """ALM self-approve / complete endpoint called by skills.py.

    action='start':
        - Creates proposal/<id> branch in the PROD git repo
        - Switches DEV worktree to that branch
        - Restarts DEV server so it serves the proposal branch
        - Agents then work in the DEV environment only — PROD/UAT untouched

    action='complete':
        - Commits all DEV worktree changes with agent attribution
        - Runs syntax checks + DEV health check
        - Stores test results in the proposal record for Ghost review
    """
    try:
        data = request.get_json(silent=True) or {}
        agent = data.get("agent", "unknown")
        action = data.get("action", "start")
        vortex_label = data.get("vortex_label", "")

        norm_id = _normalize_proposal_id(proposal_id)
        worktrees_up = _worktrees_ready()
        # The worktree where agent work happens (DEV if available, PROD fallback)
        dev = _SWARM_DEV_ROOT if worktrees_up else _SWARM_PROD_ROOT

        if action not in ("start", "complete"):
            return jsonify({"ok": False, "error": "Invalid action"}), 400

        new_status = "in_progress" if action == "start" else "done"

        # ── Governance gate (singleton + state machine) ───────────────────
        # Validate the transition BEFORE doing any git work.
        from utils.governance import transition_proposal, GovernanceError
        try:
            # Find the real proposal_id in the DB (handles INTERNAL- prefix variants)
            conn = get_connection()
            _row, matched_id = _find_proposal(conn, norm_id, 'proposal_id, agent')
            conn.close()
            if not _row:
                return jsonify({"ok": False, "error": "Proposal not found"}), 404
            matched_id = _row['proposal_id']
            prop_agent = _row['agent'] or agent

            gov_result = transition_proposal(
                matched_id, new_status, prop_agent,
                actor=agent, note=f'agent_advance action={action}',
            )
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        msg = (
            f"Proposal {norm_id} advanced to IN_PROGRESS by {agent}"
            if action == "start"
            else f"Proposal {norm_id} marked DONE by {agent}"
        )

        # ── Git operations ────────────────────────────────────────────────────
        git_branch = ''
        git_commit = ''
        test_results = ''

        if action == "start":
            branch_name = f'proposal/{norm_id}'
            # Create branch from master in the PROD repo (the git origin for all worktrees)
            out, rc = _git(['checkout', '-b', branch_name], cwd=_SWARM_PROD_ROOT)
            if rc != 0:
                # Branch already exists — switch master back and re-use it
                _git(['checkout', 'master'], cwd=_SWARM_PROD_ROOT)
                print(f'[proposals] branch already exists: {branch_name} — {out}')

            git_branch = branch_name

            if worktrees_up:
                # Switch DEV worktree to the proposal branch
                out2, rc2 = _git(['checkout', branch_name], cwd=dev)
                if rc2 != 0:
                    print(f'[proposals] DEV worktree checkout warn: {out2}')
                # Restart DEV server async so its Python picks up the branch change
                _restart_service_async('swarm-terminal-dev', delay_secs=1)
                msg += f'\nDEV worktree switching to {branch_name}. DEV server restarting in ~1s.'
            else:
                msg += (
                    f'\nGit branch {branch_name} created. '
                    'WARNING: worktrees not set up — run setup_worktrees.sh for true isolation. '
                    'Changes will affect the live filesystem until worktrees are configured.'
                )

        elif action == "complete":
            _conn2 = get_connection()
            prop_row = _conn2.execute(
                'SELECT title, git_branch FROM work_proposals WHERE proposal_id=?',
                (matched_id,)
            ).fetchone()
            _conn2.close()
            prop_title = (prop_row['title'] if prop_row else norm_id)[:100]
            stored_branch = (prop_row['git_branch'] if prop_row else '') or ''

            # Stage and commit all changes in the DEV (or PROD fallback) worktree
            _git(['add', '-A'], cwd=dev)
            commit_msg = (
                f'[{norm_id}] {prop_title}\n\n'
                f'Agent: {agent}\n'
                f'Branch: {stored_branch or "unknown"}\n'
                f'Status: done — awaiting Ghost review'
            )
            out, rc = _git(['commit', '-m', commit_msg], cwd=dev)
            if rc == 0:
                commit_hash, hrc = _git(['rev-parse', 'HEAD'], cwd=dev)
                if hrc == 0:
                    git_commit = commit_hash[:12]
                print(f'[proposals] committed {norm_id}: {git_commit}')
            else:
                # Nothing staged — record but don't block
                print(f'[proposals] git commit (nothing to commit): {out}')

            # Run DEV tests and record results
            test_results = _run_dev_tests(norm_id, prop_title)

            if worktrees_up:
                msg += f'\nCommit: {git_commit or "nothing to commit"}. DEV server remains on proposal branch for Ghost review.'
            else:
                msg += f'\nCommit: {git_commit or "nothing to commit"}.'

        # ── Update DB (git metadata only — status already set by governance) ──
        conn = get_connection()
        c = conn.cursor()
        if git_branch or git_commit or test_results:
            fields, vals = [], []
            if git_branch:
                fields.append('git_branch = ?')
                vals.append(git_branch)
            if git_commit:
                fields.append('git_commit = ?')
                vals.append(git_commit)
            if test_results:
                fields.append('test_results = ?')
                vals.append(test_results)
            if fields:
                vals.append(matched_id)
                c.execute(
                    f"UPDATE work_proposals SET {', '.join(fields)} WHERE proposal_id = ?",
                    vals
                )
        conn.commit()
        conn.close()

        print(f"[Agent Advance] {norm_id} -> {new_status} by {agent} | worktrees={'yes' if worktrees_up else 'no'}")

        try:
            from core.time_machine import time_wizard
            time_wizard.create_workflow_checkpoint(
                label=f"{norm_id}-{action}",
                agent=agent,
                description=msg
            )
        except Exception:
            pass

        try:
            import sys as _sys
            _sys.path.insert(0, '/home/seven/swarm/utils')
            from proposal_review import notify_proposal_status_change
            threading.Thread(
                target=notify_proposal_status_change,
                args=(matched_id, new_status, agent, ''),
                daemon=True
            ).start()
        except Exception:
            pass

        return jsonify({
            "ok": True,
            "status": new_status,
            "message": msg,
            "vortex_checkpoint": vortex_label or "none",
            "git_branch": git_branch,
            "git_commit": git_commit,
            "worktrees_active": worktrees_up,
        })

    except Exception as e:
        print(f"[Agent Advance ERROR] {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Proposal Git Operations ───────────────────────────────────────────────────

@proposals_bp.route("/api/work-proposals/<proposal_id>/diff", methods=["GET"])
def proposal_diff(proposal_id):
    """Return git diff and test results for Studio review."""
    try:
        conn = get_connection()
        row, norm_id = _find_proposal(conn, proposal_id, 'git_branch, git_commit, test_results')
        conn.close()

        if not row:
            return jsonify({"ok": False, "error": "Proposal not found"}), 404

        git_branch   = (row['git_branch']   or '').strip()
        git_commit   = (row['git_commit']   or '').strip()
        test_results = (row['test_results'] or '').strip()

        dev = _SWARM_DEV_ROOT if _worktrees_ready() else _SWARM_PROD_ROOT

        if git_commit:
            diff_out, _ = _git(['show', '--stat', '--patch', git_commit], cwd=dev)
        elif git_branch:
            diff_out, _ = _git(['diff', f'master...{git_branch}'], cwd=dev)
            if not diff_out:
                diff_out = '(Branch exists but no diff from master — no file changes recorded.)'
        else:
            diff_out = '(No git branch recorded — changes were applied directly to the filesystem.)'

        return jsonify({
            "ok": True,
            "diff": diff_out,
            "test_results": test_results,
            "git_branch": git_branch,
            "git_commit": git_commit,
            "worktrees_active": _worktrees_ready(),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>/approve-to-uat", methods=["POST"])
def approve_to_uat(proposal_id):
    """Ghost approves: merge proposal branch into UAT worktree and restart UAT.

    DEV stays on the proposal branch (frozen) until Ghost also promotes to PROD.
    UAT now has the changes for Ghost to manually test on port 5053.
    """
    try:
        data = request.get_json(silent=True) or {}
        actor = data.get("actor", "ghost")
        worktrees_up = _worktrees_ready()

        conn = get_connection()
        row, norm_id = _find_proposal(conn, proposal_id, 'git_branch, git_commit, title')
        conn.close()

        if not row:
            return jsonify({"ok": False, "error": "Proposal not found"}), 404

        git_branch = (row['git_branch'] or '').strip()
        git_commit = (row['git_commit'] or '').strip()
        title = (row['title'] or norm_id)[:80]

        # Look up agent for governance gate
        conn = get_connection()
        _ar = conn.execute('SELECT agent FROM work_proposals WHERE proposal_id=?', (norm_id,)).fetchone()
        conn.close()
        _prop_agent = (_ar['agent'] if _ar else 'unknown')

        if not worktrees_up:
            # No worktrees — simulate the approve step via governance
            from utils.governance import transition_proposal, GovernanceError
            try:
                transition_proposal(norm_id, 'uat', _prop_agent, actor=actor,
                                    note='approve_to_uat (no worktrees)')
            except GovernanceError as ge:
                return jsonify({"ok": False, "error": str(ge)}), 409
            return jsonify({
                "ok": True,
                "message": (
                    f"Proposal {norm_id} marked UAT. "
                    "WARNING: worktrees not set up — run setup_worktrees.sh for real isolation. "
                    "Changes are already live on all ports."
                ),
            })

        if not git_branch:
            return jsonify({"ok": False, "error": "No git branch recorded — cannot merge to UAT."}), 400

        # Merge proposal branch into the UAT worktree
        merge_msg = f'UAT: {norm_id} — {title} (approved by {actor})'
        out, rc = _git(['merge', '--no-ff', git_branch, '-m', merge_msg], cwd=_SWARM_UAT_ROOT)
        if rc != 0:
            return jsonify({"ok": False, "error": f"Merge to UAT failed: {out}"}), 500

        # Restart UAT server to pick up the merge
        _restart_service_async('swarm-terminal-uat', delay_secs=1)

        # Update proposal status via governance
        from utils.governance import transition_proposal, GovernanceError
        try:
            transition_proposal(norm_id, 'uat', _prop_agent, actor=actor,
                                note='approve_to_uat (merged to UAT worktree)')
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        return jsonify({
            "ok": True,
            "message": (
                f"Proposal {norm_id} merged to UAT. UAT server restarting. "
                f"Test on port 5053, then use Promote to PROD when satisfied."
            ),
            "detail": out,
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>/promote-to-prod", methods=["POST"])
def promote_to_prod(proposal_id):
    """Ghost manually promotes: merge UAT branch into master and restart PROD.

    This is the FINAL step — changes go live on port 5050.
    """
    try:
        data = request.get_json(silent=True) or {}
        actor = data.get("actor", "ghost")
        worktrees_up = _worktrees_ready()

        conn = get_connection()
        row, norm_id = _find_proposal(conn, proposal_id, 'git_branch, title')
        conn.close()

        if not row:
            return jsonify({"ok": False, "error": "Proposal not found"}), 404

        git_branch = (row['git_branch'] or '').strip()
        title = (row['title'] or norm_id)[:80]

        # Look up agent for governance gate
        conn = get_connection()
        _ar2 = conn.execute('SELECT agent FROM work_proposals WHERE proposal_id=?', (norm_id,)).fetchone()
        conn.close()
        _prop_agent2 = (_ar2['agent'] if _ar2 else 'unknown')

        if not worktrees_up:
            # No worktrees — mark closed via governance
            from utils.governance import transition_proposal, GovernanceError
            try:
                transition_proposal(norm_id, 'closed', _prop_agent2, actor=actor,
                                    note='promote_to_prod (no worktrees)')
            except GovernanceError as ge:
                return jsonify({"ok": False, "error": str(ge)}), 409
            return jsonify({
                "ok": True,
                "message": f"Proposal {norm_id} closed. (Worktrees not active — no merge step needed.)",
            })

        if not git_branch:
            return jsonify({"ok": False, "error": "No git branch — cannot promote."}), 400

        # Merge proposal branch into master (PROD repo)
        out1, rc1 = _git(['checkout', 'master'], cwd=_SWARM_PROD_ROOT)
        if rc1 != 0:
            return jsonify({"ok": False, "error": f"Could not switch to master: {out1}"}), 500

        merge_msg = f'PROD: {norm_id} — {title} (promoted by {actor})'
        out2, rc2 = _git(['merge', '--no-ff', git_branch, '-m', merge_msg], cwd=_SWARM_PROD_ROOT)
        if rc2 != 0:
            return jsonify({"ok": False, "error": f"Merge to PROD failed: {out2}"}), 500

        # Restart PROD server
        _restart_service_async('swarm-terminal-prod', delay_secs=2)

        # Return DEV worktree to dev branch (ready for next proposal)
        _git(['checkout', 'dev'], cwd=_SWARM_DEV_ROOT)
        _restart_service_async('swarm-terminal-dev', delay_secs=3)

        # Mark closed via governance
        from utils.governance import transition_proposal, GovernanceError
        try:
            transition_proposal(norm_id, 'closed', _prop_agent2, actor=actor,
                                note='promote_to_prod (merged to PROD)')
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        return jsonify({
            "ok": True,
            "message": (
                f"Proposal {norm_id} promoted to PROD. "
                "PROD server restarting in ~2s. DEV reset to dev branch."
            ),
            "detail": out2,
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>/revert", methods=["POST"])
def revert_proposal(proposal_id):
    """Ghost rejects: revert the DEV commit and discard the proposal branch."""
    try:
        data = request.get_json(silent=True) or {}
        actor = data.get("actor", "ghost")
        worktrees_up = _worktrees_ready()

        conn = get_connection()
        row, norm_id = _find_proposal(conn, proposal_id, 'git_branch, git_commit')
        conn.close()

        if not row:
            return jsonify({"ok": False, "error": "Proposal not found"}), 404

        git_commit = (row['git_commit'] or '').strip()
        git_branch = (row['git_branch'] or '').strip()

        detail = ''
        dev = _SWARM_DEV_ROOT if worktrees_up else _SWARM_PROD_ROOT

        if git_commit and worktrees_up:
            # Revert the commit in DEV (undoes agent file changes)
            out, rc = _git(['revert', '--no-commit', git_commit], cwd=dev)
            if rc == 0:
                revert_msg = f'Revert {norm_id} — rejected by {actor}'
                _git(['commit', '-m', revert_msg], cwd=dev)
                detail = f'Commit {git_commit} reverted in DEV. '
            else:
                # Hard reset DEV to dev branch instead
                _git(['reset', '--hard', 'HEAD~1'], cwd=dev)
                detail = f'DEV reset to HEAD~1 (revert failed: {out[:200]}). '
            # Switch DEV back to dev branch
            _git(['checkout', 'dev'], cwd=dev)
            _restart_service_async('swarm-terminal-dev', delay_secs=1)
            detail += 'DEV reset to dev branch.'
        elif git_commit:
            # No worktrees — revert in PROD (dangerous but best we can do)
            out, rc = _git(['revert', '--no-commit', git_commit], cwd=_SWARM_PROD_ROOT)
            if rc == 0:
                _git(['commit', '-m', f'Revert {norm_id} — rejected by {actor}'], cwd=_SWARM_PROD_ROOT)
                detail = f'Commit {git_commit} reverted on master.'
            else:
                detail = f'Revert note: {out[:300]}'
        else:
            detail = 'No commit recorded — proposal rejected without revert (no file changes to undo).'

        # Look up agent for governance gate
        conn = get_connection()
        _ar3 = conn.execute('SELECT agent FROM work_proposals WHERE proposal_id=?', (norm_id,)).fetchone()
        conn.close()
        _prop_agent3 = (_ar3['agent'] if _ar3 else 'unknown')

        from utils.governance import transition_proposal, GovernanceError
        try:
            transition_proposal(norm_id, 'rejected', _prop_agent3, actor=actor,
                                note=f'revert_proposal (git revert)')
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        return jsonify({"ok": True, "message": f"Proposal {norm_id} rejected.", "detail": detail})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Proposal Attachments ──────────────────────────────────────────────────────

@proposals_bp.route("/api/work-proposals/<proposal_id>/attachments", methods=["GET"])
def list_proposal_attachments(proposal_id):
    """List file attachments for a proposal."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, filename, original_name, mime_type, size_bytes, uploaded_by, created_at "
        "FROM proposal_attachments WHERE proposal_id=? ORDER BY created_at DESC",
        (proposal_id,)
    ).fetchall()
    conn.close()
    return jsonify({"ok": True, "attachments": [dict(r) for r in rows]})


@proposals_bp.route("/api/work-proposals/<proposal_id>/attachments", methods=["POST"])
def upload_proposal_attachment(proposal_id):
    """Upload a file attachment for a proposal."""
    conn = get_connection()
    row = conn.execute("SELECT id FROM work_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "proposal not found"}), 404
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "file field required"}), 400

    f = request.files["file"]
    original_name = f.filename or "attachment"
    ext = os.path.splitext(original_name)[1]
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(_ATTACHMENTS_DIR, stored_name)
    f.save(dest)
    size = os.path.getsize(dest)
    mime = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    uploaded_by = (request.form.get("uploaded_by") or "ghost").strip()

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO proposal_attachments (proposal_id, filename, original_name, mime_type, size_bytes, uploaded_by) "
        "VALUES (?,?,?,?,?,?)",
        (proposal_id, stored_name, original_name, mime, size, uploaded_by)
    )
    att_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True,
        "attachment": {
            "id": att_id, "filename": stored_name, "original_name": original_name,
            "mime_type": mime, "size_bytes": size, "uploaded_by": uploaded_by,
        }
    }), 201


@proposals_bp.route("/api/work-proposals/<proposal_id>/attachments/<int:att_id>", methods=["GET"])
def download_proposal_attachment(proposal_id, att_id):
    """Download a specific attachment."""
    conn = get_connection()
    row = conn.execute(
        "SELECT filename, original_name, mime_type FROM proposal_attachments WHERE id=? AND proposal_id=?",
        (att_id, proposal_id)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "attachment not found"}), 404
    path = os.path.join(_ATTACHMENTS_DIR, row["filename"])
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "file missing on disk"}), 404
    return send_file(path, mimetype=row["mime_type"],
                     download_name=row["original_name"], as_attachment=True)


@proposals_bp.route("/api/work-proposals/<proposal_id>/attachments/<int:att_id>", methods=["DELETE"])
def delete_proposal_attachment(proposal_id, att_id):
    """Delete an attachment record and its file."""
    conn = get_connection()
    row = conn.execute(
        "SELECT filename FROM proposal_attachments WHERE id=? AND proposal_id=?",
        (att_id, proposal_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "attachment not found"}), 404
    conn.execute("DELETE FROM proposal_attachments WHERE id=?", (att_id,))
    conn.commit()
    conn.close()
    try:
        os.remove(os.path.join(_ATTACHMENTS_DIR, row["filename"]))
    except OSError:
        pass
    return jsonify({"ok": True})


# ── Proposal Notes ────────────────────────────────────────────────────────────

@proposals_bp.route("/api/work-proposals/<proposal_id>/notes", methods=["GET"])
def list_proposal_notes(proposal_id):
    """List notes on a proposal (from Ghost, Duck, or any agent)."""
    conn = get_connection()
    # notes column is a freeform text blob on the proposal row itself;
    # agent_notes are stored separately in work_proposal_notes if the table exists,
    # otherwise we fall back to the notes text column.
    try:
        rows = conn.execute(
            "SELECT id, author, content, created_at FROM work_proposal_notes "
            "WHERE proposal_id=? ORDER BY id ASC",
            (proposal_id,)
        ).fetchall()
        conn.close()
        return jsonify({"ok": True, "notes": [dict(r) for r in rows]})
    except Exception:
        # Table doesn't exist yet — return notes from the text column
        row = conn.execute(
            "SELECT notes FROM work_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        conn.close()
        text = (row["notes"] or "") if row else ""
        return jsonify({"ok": True, "notes": [{"id": 0, "author": "system", "content": text, "created_at": ""}] if text else []})


@proposals_bp.route("/api/work-proposals/<proposal_id>/notes", methods=["POST"])
def add_proposal_note(proposal_id):
    """Add a note to a proposal. Used by Duck, agents, and Ghost."""
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    author  = (data.get("author") or "ghost").strip()
    if not content:
        return jsonify({"ok": False, "error": "content required"}), 400

    conn = get_connection()
    row = conn.execute("SELECT id FROM work_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "proposal not found"}), 404

    # Try structured notes table first; fall back to appending to notes text column
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS work_proposal_notes "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT NOT NULL, "
            "author TEXT DEFAULT 'ghost', content TEXT NOT NULL, "
            "created_at TEXT DEFAULT (datetime('now')))"
        )
        cur = conn.execute(
            "INSERT INTO work_proposal_notes (proposal_id, author, content) VALUES (?,?,?)",
            (proposal_id, author, content)
        )
        note_id = cur.lastrowid
    except Exception:
        # Fallback: append to notes text column
        existing = conn.execute(
            "SELECT notes FROM work_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        prev = (existing["notes"] or "") if existing else ""
        combined = f"{prev}\n[{author}] {content}".strip()
        conn.execute(
            "UPDATE work_proposals SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE proposal_id=?",
            (combined, proposal_id)
        )
        note_id = 0

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "note_id": note_id}), 201



# ── Deferred / Pinboard ──────────────────────────────────────────────────────

@proposals_bp.route('/api/deferred', methods=['GET'])
def api_deferred_list():
    """List deferred / pinned items (Ghost pinboard in Docs tile)."""
    include_resolved = request.args.get('resolved', '0') == '1'
    where = '' if include_resolved else 'WHERE resolved=0'
    conn = get_connection()
    rows = conn.execute(
        f'SELECT id, content, source, source_id, pinned_by, resolved, created_at, resolved_at '
        f'FROM deferred_items {where} ORDER BY created_at DESC LIMIT 200'
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'items': [dict(r) for r in rows]})


@proposals_bp.route('/api/deferred', methods=['POST'])
def api_deferred_create():
    """Pin a new deferred item."""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    source    = (data.get('source') or 'manual').strip()
    source_id = (data.get('source_id') or '').strip()
    pinned_by = (data.get('pinned_by') or 'ghost').strip()
    conn = get_connection()
    cur = conn.execute(
        'INSERT INTO deferred_items (content, source, source_id, pinned_by) VALUES (?,?,?,?)',
        (content, source, source_id, pinned_by)
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'id': item_id})


@proposals_bp.route('/api/deferred/<int:item_id>', methods=['PATCH'])
def api_deferred_patch(item_id):
    """Resolve or edit a deferred item."""
    data = request.get_json() or {}
    conn = get_connection()
    row = conn.execute('SELECT id FROM deferred_items WHERE id=?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404
    if 'resolved' in data:
        resolved = 1 if data['resolved'] else 0
        resolved_at = 'datetime("now")' if resolved else 'NULL'
        conn.execute(f'UPDATE deferred_items SET resolved=?, resolved_at={resolved_at} WHERE id=?',
                     (resolved, item_id))
    if 'content' in data:
        conn.execute('UPDATE deferred_items SET content=? WHERE id=?',
                     ((data['content'] or '').strip(), item_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@proposals_bp.route('/api/deferred/<int:item_id>', methods=['DELETE'])
def api_deferred_delete(item_id):
    """Hard-delete a deferred item."""
    conn = get_connection()
    conn.execute('DELETE FROM deferred_items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
