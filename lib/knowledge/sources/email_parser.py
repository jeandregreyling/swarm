"""lib/knowledge/sources/email_parser.py — Extract structured text from emails."""
import email
import email.header
import logging
import re

logger = logging.getLogger('seven.knowledge.email')


def extract(raw_email):
    """
    Parse a raw email string (RFC 2822) OR a dict {from, subject, body/text}.
    Returns (title: str, plain_text: str).
    """
    if isinstance(raw_email, dict):
        subject  = (raw_email.get('subject') or 'Email').strip()
        from_addr = (raw_email.get('from') or '').strip()
        body     = (raw_email.get('body') or raw_email.get('text') or '').strip()
        text     = f"From: {from_addr}\nSubject: {subject}\n\n{body}"
        return subject[:200], text[:200_000]

    try:
        msg = email.message_from_string(raw_email)

        subject = _decode_header_val(msg.get('Subject', 'Email') or 'Email')
        from_addr = _decode_header_val(msg.get('From', '') or '')
        date = msg.get('Date', '')

        body_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        body_parts.append(payload.decode(charset, errors='replace'))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body_parts.append(payload.decode(charset, errors='replace'))

        body = '\n'.join(body_parts)
        text = f"From: {from_addr}\nSubject: {subject}\nDate: {date}\n\n{body}"
        return subject[:200], text[:200_000]

    except Exception as exc:
        logger.warning(f'[Email] parse error: {exc}')
        # Return raw content as fallback
        return 'Email', (raw_email or '')[:200_000]


def _decode_header_val(value):
    """Decode RFC 2047 encoded header value to plain string."""
    try:
        parts = email.header.decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(str(part))
        return ' '.join(decoded)
    except Exception:
        return str(value)
