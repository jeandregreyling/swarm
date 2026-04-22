"""proposals_attachments.py — Attachment routes for work proposals.

Extracted from frontend/blueprints/proposals.py during Session 25 Step 4.
Handles upload/download/delete/list of file attachments on proposals.

Routes registered under `/api/work-proposals/<id>/attachments/...`.
"""
import mimetypes
import os
import uuid

from flask import Blueprint, jsonify, request, send_file

from database import get_connection

from services.proposal_helpers import _ATTACHMENTS_DIR

proposals_attachments_bp = Blueprint('proposals_attachments', __name__)


@proposals_attachments_bp.route("/api/work-proposals/<proposal_id>/attachments", methods=["GET"])
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


@proposals_attachments_bp.route("/api/work-proposals/<proposal_id>/attachments", methods=["POST"])
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


@proposals_attachments_bp.route("/api/work-proposals/<proposal_id>/attachments/<int:att_id>", methods=["GET"])
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


@proposals_attachments_bp.route("/api/work-proposals/<proposal_id>/attachments/<int:att_id>", methods=["DELETE"])
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
