from flask import Blueprint, jsonify, request
import sqlite3

proposals_bp = Blueprint('proposals', __name__)

@proposals_bp.route("/api/work-proposals", methods=["GET"])
def get_work_proposals():
    try:
        conn = sqlite3.connect("swarm.db")
        c = conn.cursor()
        rows = c.execute("SELECT * FROM work_proposals").fetchall()
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
        conn = sqlite3.connect("swarm.db")
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

print("[Proposals] Blueprint loaded with simple working routes")
@proposals_bp.route("/api/work-proposals/<proposal_id>", methods=["DELETE"])
def delete_proposal(proposal_id):
    try:
        conn = sqlite3.connect("swarm.db")
        c = conn.cursor()
        c.execute("DELETE FROM work_proposals WHERE proposal_id = ?", (proposal_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        
        if deleted == 0:
            return jsonify({"ok": False, "error": "proposal not found"}), 404
            
        # Optional: also clean any linked queue entry if you want
        # c.execute("DELETE FROM queue WHERE proposal_id = ?", (proposal_id,))
        
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@proposals_bp.route("/api/work-proposals/<proposal_id>", methods=["PATCH"])
def update_proposal_status(proposal_id):
    try:
        import sqlite3
        from flask import request, jsonify
        data = request.get_json() or {}
        new_status = data.get("status")
        if not new_status:
            return jsonify({"ok": False, "error": "status required"})
        conn = sqlite3.connect("swarm.db")
        c = conn.cursor()
        c.execute("UPDATE work_proposals SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE proposal_id = ?", 
                  (new_status, proposal_id))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

