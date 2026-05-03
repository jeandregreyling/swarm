import os
import os as _os  # kept for legacy `_os.path.join(...)` sites below
import subprocess
import threading
from flask import Blueprint, jsonify, request
from database import get_connection   # <-- this is the key import (used everywhere else)
from proposal_status import ALL_PROPOSAL_STATUSES, normalize_proposal_status

# Shared helpers now live in services.proposal_helpers and are consumed by both
# this blueprint and the proposals_git / proposals_attachments blueprints.
from services.proposal_helpers import (
    _SWARM_DEV_ROOT,
    _SWARM_PROD_ROOT,
    _SWARM_UAT_ROOT,
    _find_proposal,
    _git,
    _normalize_proposal_id,
    _restart_service_async,
    _run_dev_tests,
    _worktrees_ready,
)


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
    data = request.get_json(silent=True) or {}
    # Y.56: type-check before .strip() (Y.50 class).
    for col in ("agent", "title"):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({"ok": False, "error": f"{col} must be a string"}), 400
    agent = data.get("agent", "manual_test")
    title = (data.get("title") or "").strip()
    description = data.get("description", "") or ""
    if not title:
        return jsonify({"ok": False, "error": "title required"}), 400
    # Length guards: prevent audit-probe / abuse payloads from polluting the
    # proposals stream. 256 chars is already far longer than any legitimate
    # human-authored proposal title.
    if len(title) > 256:
        return jsonify({"ok": False, "error": "title too long (max 256)"}), 413
    if isinstance(description, str) and len(description) > 16384:
        return jsonify({"ok": False, "error": "description too long (max 16384)"}), 413
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
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('proposal', proposal_id, actor='proposal_intake')
        except Exception:
            pass
        linked_project_id = ""
        try:
            from utils.studio_intake import link_proposal_to_project
            linked_project_id = link_proposal_to_project(
                proposal_id,
                title=title,
                description=description,
                requested_project_id=data.get("project_id") or "",
            )
        except Exception:
            linked_project_id = ""
        return jsonify({"ok": True, "proposal_id": proposal_id, "project_id": linked_project_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@proposals_bp.route("/api/work-proposals/<proposal_id>/edit", methods=["PATCH"])
def edit_proposal(proposal_id):
    """Edit proposal title, description, and/or notes text."""
    try:
        data = request.get_json(silent=True) or {}
        conn = get_connection()
        c = conn.cursor()
        updates, values = [], []
        if 'title' in data:
            new_title = (data['title'] or '').strip()
            if len(new_title) > 256:
                conn.close()
                return jsonify({"ok": False, "error": "title too long (max 256)"}), 413
            updates.append("title = ?")
            values.append(new_title)
        if 'description' in data:
            new_desc = data['description'] or ''
            if isinstance(new_desc, str) and len(new_desc) > 16384:
                conn.close()
                return jsonify({"ok": False, "error": "description too long (max 16384)"}), 413
            updates.append("description = ?")
            values.append(new_desc)
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
        try:
            from core.records import mirror as _records_mirror
            _records_mirror('proposal', proposal_id, actor='proposal_edit')
        except Exception:
            pass
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
            _sys.path.insert(0, _os.path.join(_SWARM_PROD_ROOT, 'utils'))
            from proposal_review import notify_proposal_status_change
            import threading as _t
            _t.Thread(
                target=notify_proposal_status_change,
                args=(normalized_id, new_status, actor, note),
                daemon=True
            ).start()
        except Exception:
            pass

        try:
            from core.records import mirror as _records_mirror
            _records_mirror('proposal', normalized_id, actor='proposal_status')
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
        _sys.path.insert(0, _os.path.join(_SWARM_PROD_ROOT, 'utils'))
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
            _sys.path.insert(0, _os.path.join(_SWARM_PROD_ROOT, 'utils'))
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
    # Y.56: type-check before .strip() (Y.50 class).
    for col in ("content", "author"):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({"ok": False, "error": f"{col} must be a string"}), 400
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
