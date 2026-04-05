"""
db.approvals — Pending emails and approval tokens.
"""
import uuid
from ._connection import get_connection, logger


def save_pending_email(from_addr, subject, body, message_id=''):
    conn = get_connection()
    conn.execute(
        "INSERT INTO pending_emails (from_addr,subject,body,message_id) VALUES (?,?,?,?)",
        (from_addr, subject, body, message_id or '')
    )
    conn.commit()
    conn.close()


def get_pending_emails(from_addr=None):
    conn = get_connection()
    if from_addr:
        rows = conn.execute("""
            SELECT id,from_addr,subject,body,message_id,status,received_at
            FROM pending_emails WHERE status='pending' AND from_addr=?
            ORDER BY received_at ASC
        """, (from_addr,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id,from_addr,subject,body,message_id,status,received_at
            FROM pending_emails WHERE status='pending'
            ORDER BY received_at ASC
        """).fetchall()
    conn.close()
    return rows


def mark_pending_processed(pending_id):
    conn = get_connection()
    conn.execute(
        "UPDATE pending_emails SET status='processed' WHERE id=?",
        (pending_id,)
    )
    conn.commit()
    conn.close()


# ── Approval tokens — clickable TRUST/NOTIFY/IGNORE links ──────────────────

def create_approval_token(action, target_email, created_by='system'):
    """Generate a UUID token for a TRUST/NOTIFY/IGNORE action. Returns the token."""
    token = uuid.uuid4().hex
    conn = get_connection()
    conn.execute(
        "INSERT INTO approval_tokens (token, action, target_email, created_by) VALUES (?,?,?,?)",
        (token, action.lower(), target_email.lower(), created_by)
    )
    conn.commit()
    conn.close()
    return token


def use_approval_token(token):
    """
    Consume a token. Returns dict with action+target_email, or None if invalid/used/missing.
    Marks token as used so it cannot fire twice.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT action, target_email, status FROM approval_tokens WHERE token=?",
        (token,)
    ).fetchone()
    if not row or row['status'] != 'pending':
        conn.close()
        return None
    conn.execute(
        "UPDATE approval_tokens SET status='used', used_at=datetime('now') WHERE token=?",
        (token,)
    )
    conn.commit()
    conn.close()
    return {'action': row['action'], 'target_email': row['target_email']}
