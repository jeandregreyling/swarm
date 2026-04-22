"""proposals_git.py — Git operations for work proposals.

Extracted from frontend/blueprints/proposals.py during Session 25 Step 4.
Handles the DEV → UAT → PROD worktree promotion flow plus revert.

Routes registered under `/api/work-proposals/<id>/...`:
  GET  /diff
  POST /approve-to-uat
  POST /promote-to-prod
  POST /revert
"""
from flask import Blueprint, jsonify, request

from database import get_connection

from services.proposal_helpers import (
    _SWARM_DEV_ROOT,
    _SWARM_PROD_ROOT,
    _SWARM_UAT_ROOT,
    _find_proposal,
    _git,
    _restart_service_async,
    _worktrees_ready,
)

proposals_git_bp = Blueprint('proposals_git', __name__)


@proposals_git_bp.route("/api/work-proposals/<proposal_id>/diff", methods=["GET"])
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


@proposals_git_bp.route("/api/work-proposals/<proposal_id>/approve-to-uat", methods=["POST"])
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


@proposals_git_bp.route("/api/work-proposals/<proposal_id>/promote-to-prod", methods=["POST"])
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


@proposals_git_bp.route("/api/work-proposals/<proposal_id>/revert", methods=["POST"])
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
                                note='revert_proposal (git revert)')
        except GovernanceError as ge:
            return jsonify({"ok": False, "error": str(ge)}), 409

        return jsonify({"ok": True, "message": f"Proposal {norm_id} rejected.", "detail": detail})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
