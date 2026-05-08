import sys
sys.path.insert(0, '/home/seven/swarm')
from config import GMAIL_ADDRESS, GMAIL_PASSWORD, GHOST_NAME
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import time
import socket


def _describe_image_with_gemma(image_bytes, filename):
    """Use Gemma3 vision via Ollama HTTP to describe an image attachment."""
    import base64, json, urllib.request
    try:
        b64 = base64.b64encode(image_bytes).decode()
        payload = json.dumps({
            'model': 'gemma3:latest',
            'stream': False,
            'messages': [{
                'role': 'user',
                'content': (
                    f'This is an email attachment named "{filename}". '
                    'Describe what the image shows in detail.'
                ),
                'images': [b64]
            }]
        }).encode()
        req = urllib.request.Request(
            'http://localhost:11434/api/chat',
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            return data['message']['content']
    except Exception as e:
        return f'(Image description failed: {e})'


def _extract_text_from_pdf(data):
    """Extract text from PDF bytes using pdfplumber."""
    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return '\n\n'.join(pages) if pages else '(PDF contained no extractable text)'
    except Exception as e:
        return f'(PDF extraction failed: {e})'


def _extract_text_from_docx(data):
    """Extract text from .docx bytes using python-docx."""
    try:
        import docx, io
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return '\n'.join(paragraphs) if paragraphs else '(Document contained no text)'
    except Exception as e:
        return f'(DOCX extraction failed: {e})'


def extract_attachments(msg):
    """
    Walk MIME tree, extract attachments, return list of dicts:
      {'filename': str, 'type': str, 'text': str}
    Handles: plain text, markdown, PDF, .docx, images (via Gemma3 vision).
    """
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        disposition = part.get('Content-Disposition', '')
        filename = part.get_filename() or ''
        # Only process explicit attachments, or inline parts that have a named file
        if 'attachment' not in disposition and not (filename and 'inline' in disposition):
            continue
        content_type = part.get_content_type()
        data = part.get_payload(decode=True)
        if not data:
            continue
        name_lower = filename.lower()
        text = None
        if content_type == 'text/plain' or name_lower.endswith(('.txt', '.md', '.csv')):
            text = data.decode('utf-8', errors='replace')
        elif content_type == 'application/pdf' or name_lower.endswith('.pdf'):
            text = _extract_text_from_pdf(data)
        elif name_lower.endswith('.docx') or content_type in (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword'
        ):
            text = _extract_text_from_docx(data)
        elif content_type.startswith('image/') or name_lower.endswith(
            ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
        ):
            text = _describe_image_with_gemma(data, filename)
        if text is not None:
            attachments.append({
                'filename': filename or content_type,
                'type': content_type,
                'text': text.strip()
            })
    return attachments

def connect_imap():
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
    return mail

def connect_smtp():
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
    return server

def _record_delivery(to_address, cc_clean, subject, in_reply_to, status, attempts, error):
    """2026-05-02 (S-90C2B45FAF) — append a row to email_delivery_log.
    Failure to record must NEVER crash the send path."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO email_delivery_log "
                "(to_address, cc, subject, in_reply_to, status, attempts, error, sender) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (to_address or '', ', '.join(cc_clean or []),
                 (subject or '')[:300], in_reply_to or '',
                 status, int(attempts), str(error or '')[:1000],
                 GMAIL_ADDRESS),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _enqueue_retry(to_address, cc_clean, subject, body, html_body,
                   in_reply_to, attempts, error):
    """2026-05-02 (S-086BC371AD) — enqueue failed sends for later retry.
    Failure to enqueue must NEVER crash the send path."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO email_retry_queue "
                "(to_address, cc, subject, body, html_body, in_reply_to, "
                " attempts, attempts_remaining, last_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (to_address or '', ', '.join(cc_clean or []),
                 (subject or '')[:300], body or '', html_body or '',
                 in_reply_to or '', int(attempts), 3,
                 str(error or '')[:1000]),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def send_reply(to_address, subject, body, original_message_id=None, html_body=None, cc=None):
    """
    Send an email reply.
    cc: list of additional addresses to CC (e.g. other recipients from the original thread).
    """
    cc_clean = [a for a in (cc or []) if a and a.lower() != GMAIL_ADDRESS.lower()]
    attempts = 2
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            server = connect_smtp()
            msg = MIMEMultipart('alternative')
            msg['From'] = GMAIL_ADDRESS
            msg['To'] = to_address
            if cc_clean:
                msg['Cc'] = ', '.join(cc_clean)
            msg['Subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
            if original_message_id:
                msg['In-Reply-To'] = original_message_id
                msg['References'] = original_message_id
            msg.attach(MIMEText(body, 'plain'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            # send_message uses To + Cc headers automatically
            server.send_message(msg)
            server.quit()
            cc_note = f' (cc: {", ".join(cc_clean)})' if cc_clean else ''
            print(f"[Email] Reply sent to {to_address}{cc_note}")
            _record_delivery(to_address, cc_clean, subject,
                             original_message_id or '', 'ok', attempt, '')
            return True
        except (socket.gaierror, TimeoutError) as e:
            last_error = e
            print(f"[Email] Send attempt {attempt}/{attempts} transient failure: {e}")
            time.sleep(1.5)
        except Exception as e:
            last_error = e
            print(f"[Email] Send attempt {attempt}/{attempts} failed: {e}")
            break

    print(f"[Email] Send failed after {attempts} attempt(s): {last_error}")
    _record_delivery(to_address, cc_clean, subject,
                     original_message_id or '', 'failed', attempts, last_error)
    _enqueue_retry(to_address, cc_clean, subject, body, html_body or '',
                   original_message_id or '', attempts, last_error)
    return False

def fetch_unread():
    try:
        mail = connect_imap()
        mail.select('inbox')
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK' or not messages[0]:
            mail.logout()
            return []
        unread = []
        for msg_id in messages[0].split():
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            raw_subject = msg['Subject'] or ''
            decoded = decode_header(raw_subject)[0][0]
            subject = decoded.decode() if isinstance(decoded, bytes) else (decoded or '')
            from_addr   = msg['From']
            to_header   = msg['To']         or ''
            cc_header   = msg['Cc']         or ''
            message_id  = msg['Message-ID'] or ''
            in_reply_to = msg['In-Reply-To'] or ''
            references  = msg['References']  or ''
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
            # Extract and append attachment content so agents can read it
            attachments = extract_attachments(msg)
            if attachments:
                body = body.strip()
                for att in attachments:
                    body += (
                        f'\n\n--- Attachment: {att["filename"]} ---\n'
                        f'{att["text"]}\n'
                        f'--- End Attachment ---'
                    )
            # BUG-008 fix: do NOT mark as read here.
            # Marking before processing means a crash drops the email silently.
            # Caller (process_emails) marks as read after successful processing.
            unread.append({
                'id':          msg_id,
                'message_id':  message_id,
                'in_reply_to': in_reply_to,
                'references':  references,
                'from':        from_addr,
                'to':          to_header,
                'cc':          cc_header,
                'subject':     subject,
                'body':        body.strip()
            })
        mail.logout()
        return unread
    except Exception as e:
        print(f"[Email] Fetch failed: {str(e)}")
        return []

def mark_as_read(msg_id):
    """Mark a single message as read. Called after successful processing."""
    try:
        mail = connect_imap()
        mail.select('inbox')
        mail.store(msg_id, '+FLAGS', '\\Seen')
        mail.logout()
    except Exception as e:
        print(f'[Email] Could not mark as read: {e}')


if __name__ == "__main__":
    print("Testing email connection...")
    print(f"Connecting to Gmail as {GMAIL_ADDRESS}...")
    try:
        mail = connect_imap()
        mail.select('inbox')
        status, messages = mail.search(None, 'UNSEEN')
        count = len(messages[0].split()) if messages[0] else 0
        mail.logout()
        print(f"Connection successful. Unread emails: {count}")
    except Exception as e:
        print(f"Connection failed: {str(e)}")
