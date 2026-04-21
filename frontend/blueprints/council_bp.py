"""Council API blueprint — serves Agent 20 output to the frontend.

GET  /api/council/latest     — active (non-expired, non-dismissed) thoughts
POST /api/council/dismiss/<id> — user dismisses a thought
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from utils.db._connection import get_connection

council_bp = Blueprint('council_bp', __name__)


@council_bp.route('/api/council/latest')
def council_latest():
    """Return active council thoughts, ordered by urgency then recency."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, orb_role, thought, detail, urgency, confidence,
                      pfv_p, pfv_f, pfv_v, source_refs, created_at, expires_at
               FROM council_output
               WHERE dismissed = 0
                 AND expires_at > ?
               ORDER BY urgency DESC, created_at DESC
               LIMIT 20""",
            (now,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    finally:
        conn.close()


@council_bp.route('/api/council/dismiss/<int:thought_id>', methods=['POST'])
def council_dismiss(thought_id):
    """Mark a council thought as dismissed.  Feeds back into future V scoring."""
    conn = get_connection()
    try:
        result = conn.execute(
            "UPDATE council_output SET dismissed = 1 WHERE id = ?",
            (thought_id,),
        )
        conn.commit()
        if result.rowcount == 0:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'dismissed': thought_id})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    finally:
        conn.close()
