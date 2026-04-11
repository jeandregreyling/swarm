import os
import uuid
import mimetypes
from flask import Blueprint, jsonify, request, send_file
from database import get_connection   # <-- this is the key import (used everywhere else)

# Attachment storage directory (sibling to swarm.db)
_ATTACHMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'attachments', 'proposals')
os.makedirs(_ATTACHMENTS_DIR, exist_ok=True)

def _normalize_proposal_id(raw_id):
    if isinstance(raw_id, str):
        raw_id = raw_id.replace("INTERNAL-ELEVEN-", "").replace("INTERNAL-", "")
    return str(raw_id).strip()

proposals_bp = Blueprint('proposals', __name__)

@proposals_bp.route("/api/work-proposals", methods=["GET"])
def get_work_proposals():
    try:
        conn = get_connection()
        c = conn.cursor()
        rows = c.execute("""
            SELECT id, proposal_id, title, description, agent, status,
                   notes, source_conv_id, duck_verdict, duck_note,
                   ticket_number, queue_id, created_at, updated_at
            FROM work_proposals
            ORDER BY id DESC
        """).fetchall()
        columns = [desc[0] for desc in c.description]
        proposals = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return jsonify({"count": len(proposals), "ok": True, "proposals": proposals})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

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
        new_status = data.get("status")
        actor = data.get("actor", "ghost")
        note  = data.get("note", "")
        if not new_status:
            return jsonify({"ok": False, "error": "status required"})
        conn = get_connection()
        c = conn.cursor()
        normalized_id = _normalize_proposal_id(proposal_id)
        c.execute("""UPDATE work_proposals
                     SET status = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE proposal_id = ?""",
                  (new_status, normalized_id))
        conn.commit()
        conn.close()

        # Notify originating chat thread of the status change
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

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@proposals_bp.route("/api/work-proposals/<proposal_id>/agent-advance", methods=["POST"])
def agent_advance(proposal_id):
    """ALM self-approve / complete endpoint called by skills.py"""
    try:
        data = request.get_json(silent=True) or {}
        agent = data.get("agent", "unknown")
        action = data.get("action", "start")
        vortex_label = data.get("vortex_label", "")


        norm_id = _normalize_proposal_id(proposal_id)

        conn = get_connection()
        c = conn.cursor()

        if action == "start":
            new_status = "in_progress"
            msg = f"Proposal {norm_id} advanced to IN_PROGRESS by {agent}"
        elif action == "complete":
            new_status = "done"
            msg = f"Proposal {norm_id} marked DONE by {agent}"
        else:
            return jsonify({"ok": False, "error": "Invalid action"}), 400

        # Use the original proposal_id for DB update
        c.execute("""UPDATE work_proposals 
                     SET status = ?, updated_at = CURRENT_TIMESTAMP 
                     WHERE proposal_id = ?""", (new_status, proposal_id))

        updated = c.rowcount
        conn.commit()
        conn.close()

        if updated == 0:
            return jsonify({"ok": False, "error": "Proposal not found"}), 404

        # Extra logging for troubleshooting
        print(f"[Agent Advance] {norm_id} -> {new_status} by {agent}")

        try:
            from core.time_machine import time_wizard
            time_wizard.create_workflow_checkpoint(
                label=f"{norm_id}-{action}",
                agent=agent,
                description=msg
            )
        except:
            pass

        # Notify originating chat thread
        try:
            import sys as _sys, threading as _t
            _sys.path.insert(0, '/home/seven/swarm/utils')
            from proposal_review import notify_proposal_status_change
            _t.Thread(
                target=notify_proposal_status_change,
                args=(norm_id, new_status, agent, ''),
                daemon=True
            ).start()
        except Exception:
            pass

        return jsonify({"ok": True, "status": new_status, "message": msg, "vortex_checkpoint": vortex_label or "none"})

    except Exception as e:
        print(f"[Agent Advance ERROR] {e}")
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
