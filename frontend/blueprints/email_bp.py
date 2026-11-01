"""
blueprints/email_bp.py — Email tile API
Exposes inbox data from swarm DB + live IMAP fetch for both Gmail accounts.
"""
import imaplib
import smtplib
import email as _email_lib
import email.header
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import os
from pathlib import Path
from flask import Blueprint, jsonify, request

from database import get_connection, log_activity

email_bp = Blueprint('email', __name__)


def _attach_sandpit_text_files(message, paths):
    if not isinstance(paths, list) or len(paths) > 5:
        raise ValueError('attachments must be a list of at most five sandpit text-file paths')
    root = Path(os.environ.get('SWARM_ROOT') or Path(__file__).resolve().parents[2]).resolve()
    allowed = (root / 'sandpits').resolve()
    names = []
    for value in paths:
        if not isinstance(value, str):
            raise ValueError('Each attachment path must be a string')
        path = (root / value).resolve()
        if not path.is_relative_to(allowed) or path.suffix.lower() != '.txt' or not path.is_file():
            raise ValueError('Attachments must be existing .txt files inside sandpits')
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Text attachments must be no larger than 1 MiB')
        part = MIMEText(path.read_text(encoding='utf-8'), 'plain', 'utf-8')
        part.add_header('Content-Disposition', 'attachment', filename=path.name)
        message.attach(part)
        names.append(path.name)
    return names

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
    folder = (request.args.get('folder') or 'inbox').strip().lower()
    if folder == 'sent':
        return jsonify(_sent_folder(account_filter, limit))
    if folder in {'drafts', 'trash'}:
        return jsonify({'ok': True, 'emails': [], 'count': 0, 'folder': folder,
                        'note': f'{folder.title()} is not synced from Gmail yet.'})

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


def _sent_folder(account_filter: str, limit: int) -> dict:
    """Every email the swarm sent (or tried to send), newest first."""
    conn = get_connection()
    try:
        sql = ("SELECT id, sender, to_address, cc, subject, in_reply_to, sent_at, status, attempts, error "
               "FROM email_delivery_log")
        args: list = []
        if account_filter:
            sql += " WHERE lower(sender) = lower(?)"
            args.append(account_filter)
        sql += " ORDER BY sent_at DESC, id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()
    for r in rows:
        r['swarm_account'] = r.get('sender') or 'sevenpotato9@gmail.com'
    return {'ok': True, 'emails': rows, 'count': len(rows), 'folder': 'sent'}


def _message_text(msg) -> str:
    html = ''
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition', '').startswith('attachment'):
            continue
        try:
            payload = part.get_payload(decode=True) or b''
            text = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        except Exception:
            continue
        if part.get_content_type() == 'text/plain':
            return text
        if part.get_content_type() == 'text/html' and not html:
            html = text
    if html:
        import re as _re
        return _re.sub(r'<[^>]+>', '', _re.sub(r'(?i)<br\s*/?>|</p>', '\n', html))
    return ''


def _norm_subject(value: str) -> str:
    import re as _re
    text = ' '.join((value or '').split())
    return _re.sub(r'^(?:(?:re|fwd?)\s*:\s*)+', '', text, flags=_re.IGNORECASE).lower()


def _imap_sent_body(account: str, password: str, to_addr: str, subject: str, sent_at: str) -> dict:
    """Find one sent message in Gmail's Sent Mail by recipient, day and subject."""
    try:
        day = datetime.strptime(sent_at[:10], '%Y-%m-%d')
    except Exception:
        return {'found': False, 'error': 'bad sent_at'}
    from datetime import timedelta
    mail = imaplib.IMAP4_SSL('imap.gmail.com', timeout=15)
    try:
        mail.login(account, password)
        mail.select('"[Gmail]/Sent Mail"', readonly=True)
        criteria = ['SINCE', (day - timedelta(days=1)).strftime('%d-%b-%Y'),
                    'BEFORE', (day + timedelta(days=2)).strftime('%d-%b-%Y')]
        if to_addr:
            criteria += ['TO', '"' + to_addr.split(',')[0].strip().replace('"', '') + '"']
        _, data = mail.search(None, *criteria)
        want = _norm_subject(subject)
        try:
            target = datetime.strptime(sent_at[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except Exception:
            target = day.replace(tzinfo=timezone.utc)
        best = None
        for uid in (data[0] or b'').split():
            _, hdr = mail.fetch(uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
            head = _email_lib.message_from_bytes(hdr[0][1])
            if _norm_subject(_decode_header(head.get('Subject', ''))) != want:
                continue
            try:
                gap = abs((email.utils.parsedate_to_datetime(head.get('Date', '')) - target).total_seconds())
            except Exception:
                gap = float('inf')
            if best is None or gap < best[0]:
                best = (gap, uid)
        if best is None:
            return {'found': False}
        _, full = mail.fetch(best[1], '(BODY.PEEK[])')
        msg = _email_lib.message_from_bytes(full[0][1])
        return {'found': True, 'body': _message_text(msg)[:200000],
                'date': msg.get('Date', ''), 'message_id': msg.get('Message-ID', '')}
    finally:
        try:
            mail.logout()
        except Exception:
            pass


@email_bp.route('/api/email/sent/<int:log_id>', methods=['GET'])
def get_sent_email(log_id):
    """One delivery-log row plus its body from the sender's Gmail Sent Mail."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM email_delivery_log WHERE id = ?", (log_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    item = dict(row)
    sender = item.get('sender') or ''
    try:
        from config import GMAIL_ADDRESS, GMAIL_PASSWORD, NINE_EMAIL, NINE_PASSWORD
        password = {GMAIL_ADDRESS: GMAIL_PASSWORD, NINE_EMAIL: NINE_PASSWORD}.get(sender)
    except ImportError:
        password = None
    if item.get('status') != 'ok':
        item['body_lookup'] = {'found': False, 'error': 'not delivered'}
    elif not password:
        item['body_lookup'] = {'found': False, 'error': 'no password for sender'}
    else:
        try:
            item['body_lookup'] = _imap_sent_body(sender, password, item.get('to_address') or '',
                                                  item.get('subject') or '', str(item.get('sent_at') or ''))
        except Exception as exc:
            item['body_lookup'] = {'found': False, 'error': str(exc)[:300]}
    return jsonify({'ok': True, 'email': item})


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


@email_bp.route('/api/email/send', methods=['POST'])
def send_email():
    """Send an email via Gmail SMTP from one of the swarm accounts.

    Pass ``internal_test: true`` in the JSON body to tag this send as an
    internal probe. Internal-test sends add an ``X-Swarm-Internal-Test: 1``
    header and a ``[SWARM-INTERNAL-TEST]`` subject tag so any bounce-back
    can be correlated and silently discarded by the listener's bounce
    short-circuit (Session 28 Backlog #1).
    """
    body = request.get_json(force=True, silent=True) or {}
    to_addr = str(body.get('to', '')).strip()
    subject = str(body.get('subject', '')).strip()
    message = str(body.get('body', '')).strip()
    from_account = str(body.get('from_account', '')).strip()
    internal_test = bool(body.get('internal_test', False))

    if not to_addr or not subject:
        return jsonify({'ok': False, 'error': 'to and subject are required'}), 400

    try:
        from config import GMAIL_ADDRESS, GMAIL_PASSWORD, NINE_EMAIL, NINE_PASSWORD
    except ImportError:
        return jsonify({'ok': False, 'error': 'Email credentials not configured'}), 503

    accounts = {GMAIL_ADDRESS: GMAIL_PASSWORD, NINE_EMAIL: NINE_PASSWORD}
    sender = from_account if from_account in accounts else GMAIL_ADDRESS
    password = accounts.get(sender)
    if not password:
        return jsonify({'ok': False, 'error': 'No password for selected account'}), 503

    if internal_test and '[SWARM-INTERNAL-TEST]' not in subject:
        subject = f'[SWARM-INTERNAL-TEST] {subject}'

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg['Message-ID'] = email.utils.make_msgid()
    if internal_test:
        msg['X-Swarm-Internal-Test'] = '1'
        msg['Auto-Submitted'] = 'auto-generated'
    msg.attach(MIMEText(message, 'plain', 'utf-8'))
    try:
        attachments = _attach_sandpit_text_files(msg, body.get('attachments', []))
    except (ValueError, OSError, UnicodeError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as smtp:
            smtp.login(sender, password)
            refused = smtp.send_message(msg)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except Exception as exc:
        log_activity('email', 'send_error', f'to={to_addr} err={exc}')
        from lib.email.email_handler import _record_delivery
        _record_delivery(to_addr, [], subject, '', 'failed', 1, str(exc), sender=sender)
        return jsonify({'ok': False, 'error': f'SMTP error: {exc}'}), 502

    log_activity(
        'email',
        'send_internal_test' if internal_test else 'send',
        f'from={sender} to={to_addr} subj={subject[:60]}',
    )
    from lib.email.email_handler import _record_delivery
    _record_delivery(to_addr, [], subject, '', 'ok', 1, '', sender=sender)
    return jsonify({'ok': True, 'message': 'Accepted by SMTP server', 'smtp_accepted': True,
                    'message_id': msg['Message-ID'], 'attachments': attachments, 'internal_test': internal_test})
