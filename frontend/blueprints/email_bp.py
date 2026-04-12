"""
blueprints/email_bp.py — Email tile API
Exposes inbox data from swarm DB + live IMAP fetch for both Gmail accounts.
"""
import imaplib
import email as _email_lib
import email.header
import email.utils
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from database import get_connection, log_activity

email_bp = Blueprint('email', __name__)

_ACCOUNTS = {
    'sevenpotato9@gmail.com': 'seven',
    'ninepotato7@gmail.com':  'nine',
}


def _decode_header(value):
    if not value:
        return ''
    parts = []
    for part, enc in _email_lib.header.decode_header(value):
        if isinstance(part, bytes):
            parts.append(part.decode(enc or 'utf-8', errors='replace'))
        else:
            parts.append(str(part))
    return ''.join(parts)


def _imap_fetch(account: str, password: str, limit: int = 30) -> list:
    """Fetch recent emails from Gmail IMAP for one account."""
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=10)
        mail.login(account, password)
        mail.select('INBOX')
        _, data = mail.search(None, 'ALL')
        uids = data[0].split() if data and data[0] else []
        uids = uids[-limit:]  # most recent
        results = []
        for uid in reversed(uids):
            try:
                _, msg_data = mail.fetch(uid, '(RFC822.HEADER)')
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = _email_lib.message_from_bytes(raw)
                from_raw  = _decode_header(msg.get('From', ''))
                subj_raw  = _decode_header(msg.get('Subject', '(no subject)'))
                date_raw  = msg.get('Date', '')
                msg_id    = msg.get('Message-ID', '')
                try:
                    dt = email.utils.parsedate_to_datetime(date_raw)
                    ts = dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')
                except Exception:
                    ts = date_raw[:20]
                results.append({
                    'uid': uid.decode(),
                    'from': from_raw,
                    'subject': subj_raw,
                    'date': ts,
                    'msg_id': msg_id,
                    'account': account,
                })
            except Exception:
                continue
        mail.logout()
        return results
    except Exception as exc:
        return [{'error': str(exc), 'account': account}]


@email_bp.route('/api/email/inbox', methods=['GET'])
def get_email_inbox():
    """
    Return recent emails from swarm queue DB for both accounts,
    enriched with ticket/agent handling info.
    Optional ?account=<addr> to filter.
    """
    account_filter = request.args.get('account', '')
    limit = min(int(request.args.get('limit', 50)), 200)

    conn = get_connection()
    rows = conn.execute("""
        SELECT q.id, q.from_addr, q.subject, q.status, q.priority, q.created_at,
               t.ticket_number, t.status AS ticket_status, t.final_answer,
               t.sender_email, t.tags, t.duck_result
        FROM queue q
        LEFT JOIN tickets t ON t.queue_id = q.id
        WHERE q.from_addr NOT LIKE 'agent:%'
        ORDER BY q.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    emails = []
    for r in rows:
        d = dict(r)
        # Determine which swarm account handled this
        sender = d.get('sender_email') or d.get('from_addr') or ''
        d['swarm_account'] = 'sevenpotato9@gmail.com'  # default
        if 'nine' in sender.lower() or 'ninepotato7' in sender.lower():
            d['swarm_account'] = 'ninepotato7@gmail.com'
        if account_filter and d['swarm_account'] != account_filter:
            continue
        emails.append(d)

    return jsonify({'ok': True, 'emails': emails, 'count': len(emails)})


@email_bp.route('/api/email/live', methods=['GET'])
def get_email_live():
    """
    Live IMAP fetch from Gmail for both accounts.
    Requires GMAIL_PASSWORD and NINE_PASSWORD in env/.env.
    Slow — only called on demand, not on every tile load.
    """
    limit = min(int(request.args.get('limit', 20)), 50)
    account_filter = request.args.get('account', '')

    try:
        from config import GMAIL_ADDRESS, GMAIL_PASSWORD, NINE_EMAIL, NINE_PASSWORD
    except ImportError:
        return jsonify({'ok': False, 'error': 'Email credentials not configured'}), 503

    results = []
    accounts = {GMAIL_ADDRESS: GMAIL_PASSWORD, NINE_EMAIL: NINE_PASSWORD}
    for addr, pw in accounts.items():
        if account_filter and addr != account_filter:
            continue
        if not pw:
            results.append({'account': addr, 'error': 'password not set'})
            continue
        msgs = _imap_fetch(addr, pw, limit=limit)
        results.extend(msgs)

    log_activity('email', 'live_fetch', f'{len(results)} messages fetched')
    return jsonify({'ok': True, 'messages': results, 'count': len(results)})


@email_bp.route('/api/email/stats', methods=['GET'])
def get_email_stats():
    """Summary stats: email counts per account, ticket resolution rates."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM queue WHERE from_addr NOT LIKE 'agent:%'").fetchone()[0]
    by_status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM queue WHERE from_addr NOT LIKE 'agent:%' GROUP BY status"
    ).fetchall())
    recent_activity = conn.execute("""
        SELECT service, event, detail, created_at FROM activity_log
        WHERE service IN ('listener','email')
        ORDER BY id DESC LIMIT 10
    """).fetchall()

    conn.close()
    return jsonify({
        'ok': True,
        'total_emails': total,
        'by_status': by_status,
        'recent_activity': [dict(r) for r in recent_activity],
        'accounts': list(_ACCOUNTS.keys()),
    })


@email_bp.route('/api/email/thread/<ticket_number>', methods=['GET'])
def get_email_thread(ticket_number):
    """Full agent handling thread for a given ticket number."""
    conn = get_connection()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE ticket_number=?", (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'ok': False, 'error': 'ticket not found'}), 404

    notes = conn.execute(
        "SELECT agent, note_type, content, created_at FROM ticket_notes WHERE ticket_id=? ORDER BY id ASC",
        (ticket['id'],)
    ).fetchall()
    # debates table links via proposal_id, not ticket_id — skip if column absent
    debates = []
    try:
        debates = conn.execute(
            "SELECT * FROM debates WHERE proposal_id=? ORDER BY id ASC",
            (ticket_number,)
        ).fetchall()
    except Exception:
        pass
    activity = conn.execute(
        "SELECT * FROM activity_log WHERE detail LIKE ? ORDER BY id ASC LIMIT 30",
        (f'%{ticket_number}%',)
    ).fetchall()
    conn.close()

    return jsonify({
        'ok': True,
        'ticket': dict(ticket),
        'notes': [dict(n) for n in notes],
        'debates': [dict(d) for d in debates],
        'activity': [dict(a) for a in activity],
    })
