from flask import Flask, jsonify, request
from datetime import datetime
from utils.db._connection import get_connection

app = Flask(__name__)

def get_db_connection():
    return get_connection()

# Ensure the table exists with proper columns
conn = get_db_connection()
conn.execute('''
    CREATE TABLE IF NOT EXISTS work_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id TEXT UNIQUE,
        agent TEXT DEFAULT 'studio',
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        git_branch TEXT,
        source_node TEXT DEFAULT 'proposals_api'
    )
''')
conn.commit()
conn.close()

@app.route('/proposals', methods=['GET'])
def list_proposals():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM work_proposals ORDER BY id DESC").fetchall()
    proposals = [dict(row) for row in rows]
    conn.close()
    return jsonify(proposals)

@app.route('/proposals/<int:prop_id>/approve', methods=['POST'])
def approve_proposal(prop_id):
    conn = get_db_connection()
    now = datetime.now().isoformat()
    conn.execute("UPDATE work_proposals SET status='approved', updated_at=? WHERE id=?", (now, prop_id))
    conn.commit()
    row = conn.execute("SELECT * FROM work_proposals WHERE id=?", (prop_id,)).fetchone()
    conn.close()
    if row:
        return jsonify({"message": f"Proposal {prop_id} approved", "proposal": dict(row), "status": "success"})
    return jsonify({"error": "Proposal not found"}), 404

@app.route('/proposals/<int:prop_id>/reject', methods=['POST'])
def reject_proposal(prop_id):
    conn = get_db_connection()
    now = datetime.now().isoformat()
    conn.execute("UPDATE work_proposals SET status='rejected', updated_at=? WHERE id=?", (now, prop_id))
    conn.commit()
    row = conn.execute("SELECT * FROM work_proposals WHERE id=?", (prop_id,)).fetchone()
    conn.close()
    if row:
        return jsonify({"message": f"Proposal {prop_id} rejected", "proposal": dict(row), "status": "success"})
    return jsonify({"error": "Proposal not found"}), 404

@app.route('/proposals/<int:prop_id>/promote', methods=['POST'])
def promote_proposal(prop_id):
    conn = get_db_connection()
    now = datetime.now().isoformat()
    conn.execute("UPDATE work_proposals SET status='promoted', updated_at=? WHERE id=?", (now, prop_id))
    conn.commit()
    row = conn.execute("SELECT * FROM work_proposals WHERE id=?", (prop_id,)).fetchone()
    conn.close()
    if row:
        return jsonify({"message": f"Proposal {prop_id} promoted", "proposal": dict(row), "status": "success"})
    return jsonify({"error": "Proposal not found"}), 404

if __name__ == '__main__':
    print("🚀 Proposals API (central swarm_memory.db) running on http://0.0.0.0:5050")
    print("   GET  /proposals")
    print("   POST /proposals/<id>/approve")
    print("   POST /proposals/<id>/reject")
    print("   POST /proposals/<id>/promote")
    app.run(host='0.0.0.0', port=5050, debug=False)
