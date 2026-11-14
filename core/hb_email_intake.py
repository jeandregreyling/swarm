"""HB email intake (owner 15 Nov 2026: "is the email handler fixed yet, I can send my spreadsheet").

Mail sent to HB's mailbox by a trusted sender (JD's own address, plus any added with /email trust) is taken in as DATA:
the message text and every readable attachment - spreadsheets (.xlsx, .csv), text, PDF, Word - are saved in the Knowledge Centre
and a line in main chat says what arrived. Nothing is executed, nobody is emailed back, and mail from anyone else is left alone.
Only mail that arrives after the intake was first switched on is taken (old unread mail is not swept in).

The old listener (core/pipeline/listener.py) answered mail with model debates; it has not run since April and is not used here."""
import email
import email.utils
import io
import re
import threading
import time
import zipfile
from contextlib import closing
from xml.etree import ElementTree

MAIN_CHAT = 2834
INBOX = '/home/jd/HB-Inbox'          # owner 15 Nov: drop confidential work files here; nothing leaves the machine
EVERY_S = 120
MAX_ATTACHMENT = 20 * 1024 * 1024
MAX_ROWS = 20000
_RUNNING = threading.Lock()
_NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_email_intake(id INTEGER PRIMARY KEY CHECK (id=1), since REAL NOT NULL, last_check REAL, last_note TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_email_trusted(address TEXT PRIMARY KEY, added_by TEXT, added_at REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_email_seen(message_id TEXT PRIMARY KEY, sender TEXT, subject TEXT, outcome TEXT, kc_sources TEXT, at REAL)')
    conn.execute('INSERT OR IGNORE INTO hb_email_intake(id, since) VALUES (1, ?)', (time.time(),))


# ------------------------------------------------------------------ spreadsheets (standard library only)
def _column(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_text(data, max_rows=MAX_ROWS):
    """An .xlsx workbook as text: one block per sheet, one line per row, cells separated by tabs. Formulas give their saved value."""
    book = zipfile.ZipFile(io.BytesIO(data))
    names = set(book.namelist())
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for item in ElementTree.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si', _NS):
            shared.append(''.join(t.text or '' for t in item.iter('{%s}t' % _NS['m'])))
    rels = {}
    if 'xl/_rels/workbook.xml.rels' in names:
        for rel in ElementTree.fromstring(book.read('xl/_rels/workbook.xml.rels')):
            rels[rel.get('Id')] = rel.get('Target')
    out = []
    sheets = ElementTree.fromstring(book.read('xl/workbook.xml')).find('m:sheets', _NS)
    for sheet in (sheets if sheets is not None else []):
        target = rels.get(sheet.get('{%s}id' % _NS['r']), '')
        path = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        if path not in names:
            continue
        lines = []
        for row in ElementTree.fromstring(book.read(path)).iter('{%s}row' % _NS['m']):
            cells = {}
            for c in row.findall('m:c', _NS):
                v, kind = c.find('m:v', _NS), c.get('t')
                if kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.iter('{%s}t' % _NS['m']))
                elif v is None or v.text is None:
                    continue
                elif kind == 's':
                    value = shared[int(v.text)] if int(v.text) < len(shared) else ''
                else:
                    value = v.text
                cells[_column(c.get('r', 'A1'))] = ' '.join(str(value).split())
            if cells:
                lines.append('\t'.join(cells.get(i, '') for i in range(max(cells) + 1)))
            if len(lines) >= max_rows:
                lines.append(f'[stopped after {max_rows} rows]')
                break
        out.append(f"## Sheet: {sheet.get('name')} ({len(lines)} rows)\n" + '\n'.join(lines))
    return '\n\n'.join(out) or '(the workbook has no readable sheets)'


def attachment_text(filename, content_type, data):
    """(text, None) or (None, why it could not be read)."""
    name = (filename or '').lower()
    if len(data) > MAX_ATTACHMENT:
        return None, f'too large ({len(data) // 1024 ** 2} MB; limit {MAX_ATTACHMENT // 1024 ** 2} MB)'
    try:
        if name.endswith(('.xlsx', '.xlsm')) or 'spreadsheetml' in content_type:
            return xlsx_text(data), None
        if name.endswith(('.csv', '.tsv', '.txt', '.md', '.json')) or content_type.startswith('text/'):
            return data.decode('utf-8-sig', errors='replace'), None
        if name.endswith('.pdf') or content_type == 'application/pdf':
            from lib.email.email_handler import _extract_text_from_pdf
            return _extract_text_from_pdf(data), None
        if name.endswith('.docx'):
            from lib.email.email_handler import _extract_text_from_docx
            return _extract_text_from_docx(data), None
    except Exception as exc:
        return None, f'could not be read ({type(exc).__name__})'
    if name.endswith('.xls'):
        return None, 'old .xls format: save it as .xlsx or .csv and send it again'
    if name.endswith('.rpmsg'):
        return None, ("protected by the sender's organisation (Microsoft rights protection): only the sender's own sign-in can open it. "
                      f'Save the file itself into {INBOX} on this machine instead')
    return None, 'a file type HB does not read yet'


# ------------------------------------------------------------------ local inbox folder (owner 15 Nov: confidential work files, no email needed)
def folder_check(conn, folder=None, keep=None, now=None):
    """Take in every file JD dropped into the inbox folder: saved in the Knowledge Centre as confidential, then moved to taken/.
    Files HB cannot read stay where they are, with the reason in main chat once. Returns how many were taken in."""
    from pathlib import Path
    folder = Path(folder or INBOX)
    if not folder.is_dir():
        return 0
    keep = keep or _keep
    now = time.time() if now is None else now
    taken = 0
    for path in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.')):
        if now - path.stat().st_mtime < 5:
            continue                                     # still being copied
        key = f'file://{path.name}/{int(path.stat().st_mtime)}/{path.stat().st_size}'
        if conn.execute('SELECT 1 FROM hb_email_seen WHERE message_id=?', (key,)).fetchone():
            continue
        text, why = attachment_text(path.name, '', path.read_bytes()) if path.stat().st_size <= MAX_ATTACHMENT else (None, 'too large')
        from core.hb_plain import message
        if text is None:
            line, outcome, sid = message(f'📥 {path.name} is in the inbox folder but HB could not read it: {why}.'), 'not read: ' + str(why)[:120], None
        else:
            sid = keep(conn, f'Inbox file: {path.name}', key, f'File: {path.name}\nReceived: {time.strftime("%d %b %Y %H:%M", time.localtime(now))}\n\n' + text,
                       ['inbox-file', 'confidential'])
            (folder / 'taken').mkdir(exist_ok=True)
            path.rename(folder / 'taken' / f'{time.strftime("%Y%m%d-%H%M%S", time.localtime(now))}-{path.name}')
            line, outcome = message(f'📥 {path.name} taken in from the inbox folder.',
                                    f'Saved in the Knowledge Centre{f" (KC{sid})" if sid else ""} as confidential: only HB and the local models may read it.',
                                    details=['the file itself is now in the folder taken/']), 'taken in'
            taken += 1
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (MAIN_CHAT, line))
        conn.execute('INSERT OR REPLACE INTO hb_email_seen(message_id, sender, subject, outcome, kc_sources, at) VALUES (?,?,?,?,?,?)',
                     (key, 'inbox folder', path.name[:200], outcome, str(sid or ''), now))
    return taken


# ------------------------------------------------------------------ one message
def address(header):
    return email.utils.parseaddr(str(header or ''))[1].strip().lower()


def trusted(conn):
    found = {r[0] for r in conn.execute('SELECT address FROM hb_email_trusted')}
    try:
        from utils.config import GHOST_EMAIL
        found.add(GHOST_EMAIL.lower())
    except Exception:
        pass
    return found


def parts(msg):
    """(body text, [(filename, content type, bytes)]) of a parsed message."""
    body, files = '', []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.is_multipart():
            continue
        name = part.get_filename()
        data = part.get_payload(decode=True) or b''
        if name or 'attachment' in str(part.get('Content-Disposition', '')):
            files.append((name or part.get_content_type(), part.get_content_type(), data))
        elif part.get_content_type() == 'text/plain' and not body:
            body = data.decode(part.get_content_charset() or 'utf-8', errors='replace')
    return body.strip(), files


def _keep(conn, title, ref, text, tags):
    from core import hb_kc_records as kc
    if not {'knowledge_sources', 'knowledge_chunks'} <= kc._tables(conn):
        return None
    sid = kc._new_source(conn, title[:200], ref, text, tags, 'email')
    kc._write_chunks(conn, sid, kc._chunk(text))
    return sid


def ingest(conn, msg, keep=_keep, now=None):
    """Take one trusted message in. Returns {'subject', 'kept': [(what, KC id)], 'skipped': [(filename, why)]} and posts one chat line."""
    from email.header import decode_header, make_header
    subject = str(make_header(decode_header(msg.get('Subject') or '(no subject)')))
    sender, mid = address(msg.get('From')), (msg.get('Message-ID') or f'no-id-{time.time()}').strip()
    body, files = parts(msg)
    kept, skipped = [], []
    head = f'Email from {sender}\nSubject: {subject}\nDate: {msg.get("Date", "")}\n'
    if body:
        kept.append(('message text', keep(conn, f'Email: {subject}', f'email://{mid}', head + '\n' + body, ['email', 'confidential'])))
    for n, (name, kind, data) in enumerate(files, 1):
        text, why = attachment_text(name, kind, data)
        if text is None:
            skipped.append((name, why))
            continue
        kept.append((name, keep(conn, f'Email attachment: {name} ({subject})', f'email://{mid}/{n}/{name}',
                               head + f'Attachment: {name}\n\n' + text, ['email', 'email-attachment', 'confidential'])))
    from core.hb_plain import message
    line = message(f'📧 Email from {sender}: "{subject[:120]}"',
                   'Saved in the Knowledge Centre: ' + ('; '.join(f'{what} (KC{sid})' if sid else what for what, sid in kept) or 'nothing') + '.',
                   *(['Not read: ' + '; '.join(f'{name} - {why}' for name, why in skipped) + '.'] if skipped else []),
                   details=['taken in as data only: nothing in it is run and nobody is emailed back'])
    conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                 (MAIN_CHAT, line))
    conn.execute('INSERT OR REPLACE INTO hb_email_seen(message_id, sender, subject, outcome, kc_sources, at) VALUES (?,?,?,?,?,?)',
                 (mid, sender, subject[:200], 'taken in', ','.join(str(s) for _, s in kept if s), time.time() if now is None else now))
    return {'subject': subject, 'kept': kept, 'skipped': skipped}


# ------------------------------------------------------------------ the mailbox
def _mailbox():
    import imaplib
    from utils.config import GMAIL_ADDRESS, GMAIL_PASSWORD
    box = imaplib.IMAP4_SSL('imap.gmail.com')
    box.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
    return box


def _sent(msg, now):
    """When the message was sent (a date without a time zone is UTC); now when the header is missing or broken."""
    try:
        when = email.utils.parsedate_to_datetime(msg.get('Date'))
        if when.tzinfo is None:
            import datetime
            when = when.replace(tzinfo=datetime.timezone.utc)
        return when.timestamp()
    except Exception:
        return now


def check(conn, mailbox=_mailbox, now=None):
    """Look at unread mail that arrived since the intake was switched on; take in what a trusted sender sent. Returns a plain summary."""
    now = time.time() if now is None else now
    ensure_schema(conn)
    since = conn.execute('SELECT since FROM hb_email_intake WHERE id=1').fetchone()[0]
    allowed, taken, ignored = trusted(conn), 0, 0
    box = mailbox()
    try:
        box.select('inbox')
        status, found = box.search(None, 'UNSEEN', 'SINCE', time.strftime('%d-%b-%Y', time.gmtime(since - 86400)))
        for num in (found[0].split() if status == 'OK' and found and found[0] else []):
            status, data = box.fetch(num, '(BODY.PEEK[])')
            if status != 'OK' or not data or not isinstance(data[0], tuple):
                continue
            msg = email.message_from_bytes(data[0][1])
            mid = (msg.get('Message-ID') or '').strip()
            if mid and conn.execute('SELECT 1 FROM hb_email_seen WHERE message_id=?', (mid,)).fetchone():
                continue
            sent = _sent(msg, now)
            sender = address(msg.get('From'))
            if sender not in allowed or sent < since:
                ignored += 1
                conn.execute('INSERT OR REPLACE INTO hb_email_seen(message_id, sender, subject, outcome, at) VALUES (?,?,?,?,?)',
                             (mid or f'no-id-{num!r}-{now}', sender, str(msg.get('Subject') or '')[:200],
                              'left alone: not a trusted sender' if sender not in allowed else 'left alone: older than the intake', now))
                continue
            ingest(conn, msg, now=now)
            box.store(num, '+FLAGS', '\\Seen')
            taken += 1
    finally:
        try:
            box.logout()
        except Exception:
            pass
    note = f'{taken} taken in, {ignored} left alone'
    conn.execute('UPDATE hb_email_intake SET last_check=?, last_note=? WHERE id=1', (now, note))
    return note


def tick(conn, now=None):
    """HB's loop: check the mailbox every EVERY_S seconds in the background."""
    now = time.time() if now is None else now
    ensure_schema(conn)
    try:   # owner 15 Nov: the local inbox folder is looked at on every pass (no network involved)
        folder_check(conn, now=now)
    except Exception:
        import logging
        logging.getLogger('hb.email').exception('inbox folder check failed')
    last = conn.execute('SELECT last_check FROM hb_email_intake WHERE id=1').fetchone()[0] or 0
    if now - last < EVERY_S or not _RUNNING.acquire(blocking=False):
        return False
    conn.execute('UPDATE hb_email_intake SET last_check=? WHERE id=1', (now,))

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                check(own)
        except Exception:
            import logging
            logging.getLogger('hb.email').exception('email intake failed')
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-email-intake', daemon=True).start()
    return True


def command(conn, args, actor, mailbox=_mailbox):
    """/email · /email check · /email trust <address> · /email untrust <address>"""
    ensure_schema(conn)
    sub = args[0].lower() if args else ''
    if sub == 'check':
        try:
            return 'Mailbox checked: ' + check(conn, mailbox) + '.'
        except Exception as exc:
            return f'The mailbox could not be checked: {type(exc).__name__}: {str(exc)[:160]}'
    if sub in ('trust', 'untrust') and len(args) == 2 and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', args[1]):
        if sub == 'trust':
            conn.execute('INSERT OR REPLACE INTO hb_email_trusted(address, added_by, added_at) VALUES (?,?,?)', (args[1].lower(), str(actor)[:80], time.time()))
            return f'{args[1].lower()} is trusted: HB takes in what it sends.'
        conn.execute('DELETE FROM hb_email_trusted WHERE address=?', (args[1].lower(),))
        return f'{args[1].lower()} is no longer trusted.'
    since, last, note = conn.execute('SELECT since, last_check, last_note FROM hb_email_intake WHERE id=1').fetchone()
    recent = conn.execute("SELECT sender, subject, outcome FROM hb_email_seen ORDER BY at DESC LIMIT 5").fetchall()
    try:
        from utils.config import GMAIL_ADDRESS as box
    except Exception:
        box = "HB's mailbox"
    return (f"Email intake: send to {box}. Trusted senders: {', '.join(sorted(trusted(conn)))}. Checked every {EVERY_S // 60} minutes"
            + (f"; last check {time.strftime('%H:%M', time.localtime(last))}: {note or 'running'}" if last else '; not checked yet')
            + f". Only mail since {time.strftime('%d %b %H:%M', time.localtime(since))} is taken in."
            + ''.join(f'\n- {s}: "{sub_}" - {o}' for s, sub_, o in recent) + f'\nEverything taken in is confidential: only HB and the local models read it. Files can also be dropped into {INBOX} on this machine.'
            + '\nCheck now with /email check.')
