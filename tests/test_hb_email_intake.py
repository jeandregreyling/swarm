"""Practice 64 (owner 15 Nov): email intake - JD's mail to HB's mailbox, spreadsheets included, lands in the Knowledge Centre as data."""
import io
import sqlite3
import zipfile
from email.message import EmailMessage
import core.hb_email_intake as e
import core.hb_commands as cmds

NOW = 1_800_000_000.0


def workbook():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                                      '<sheets><sheet name="Pay run" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                                 '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Wage type</t></si><si><t>Amount</t></si><si><r><t>/1</t></r><r><t>01</t></r></si></sst>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>1234.5</v></c></row>'
                   '<row r="3"><c r="A3" t="inlineStr"><is><t>Total</t></is></c><c r="B3"><f>SUM(B2)</f><v>99</v></c></row></sheetData></worksheet>')
    return buf.getvalue()


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    e.ensure_schema(c)
    c.execute('UPDATE hb_email_intake SET since=?', (NOW - 3600,))
    c.execute("INSERT INTO hb_email_trusted(address) VALUES ('jd@example.com')")
    return c


def mail(sender='JD <jd@example.com>', subject='Pay run sheet', mid='<m1@x>', when='Tue, 15 Jan 2027 08:00:00 +0000', attach=True):
    m = EmailMessage()
    m['From'], m['Subject'], m['Message-ID'], m['Date'] = sender, subject, mid, when
    m.set_content('Sanitised copy attached.')
    if attach:
        m.add_attachment(workbook(), maintype='application', subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename='payrun.xlsx')
        m.add_attachment(b'\xd0\xcf\x11\xe0', maintype='application', subtype='vnd.ms-excel', filename='old.xls')
    return m


class Box:
    def __init__(self, mails):
        self.mails, self.seen = mails, []

    def select(self, *_): return 'OK', []
    def search(self, *_): return 'OK', [b' '.join(str(i).encode() for i in range(1, len(self.mails) + 1))]
    def fetch(self, num, _): return 'OK', [(b'x', self.mails[int(num) - 1].as_bytes())]
    def store(self, num, *_): self.seen.append(int(num))
    def logout(self): pass


def test_practice_64_spreadsheet_becomes_rows_of_text():
    text = e.xlsx_text(workbook())
    assert text.splitlines() == ['## Sheet: Pay run (3 rows)', 'Wage type\tAmount', '/101\t\t1234.5', 'Total\t99']
    assert e.attachment_text('x.xls', 'application/vnd.ms-excel', b'..')[1].startswith('old .xls format')
    assert e.attachment_text('a.csv', 'text/csv', b'\xef\xbb\xbfa,b\n1,2')[0] == 'a,b\n1,2'
    assert e.attachment_text('big.csv', 'text/csv', b'x' * (e.MAX_ATTACHMENT + 1))[1].startswith('too large')
    assert e.attachment_text('broken.xlsx', 'application/zip', b'not a zip')[1].startswith('could not be read')


def test_practice_64_only_trusted_new_mail_is_taken_in_and_marked_read(monkeypatch):
    c = db()
    kept = []
    monkeypatch.setattr(e, '_keep', lambda conn, title, ref, text, tags: kept.append((title, text)) or len(kept))
    monkeypatch.setattr(e, 'trusted', lambda conn: {'jd@example.com'})
    monkeypatch.setattr(e, 'ingest', lambda conn, msg, keep=None, now=None, _real=e.ingest: _real(conn, msg, keep=e._keep, now=now))
    stamp = lambda offset: __import__('email.utils').utils.formatdate(NOW + offset)
    box = Box([mail(when=stamp(-60)), mail(sender='spam@evil.test', mid='<m2@x>', when=stamp(-60)), mail(mid='<m3@x>', when=stamp(-90000), attach=False)])
    assert e.check(c, lambda: box, now=NOW) == '1 taken in, 2 left alone'
    assert box.seen == [1]                                                     # only the taken-in mail is marked read
    assert [t for t, _ in kept] == ['Email: Pay run sheet', 'Email attachment: payrun.xlsx (Pay run sheet)']
    assert 'Wage type\tAmount' in kept[1][1]
    line = c.execute('SELECT content FROM messages').fetchone()[0]
    assert line.startswith('📧 Email from jd@example.com: "Pay run sheet"') and 'payrun.xlsx (KC2)' in line and 'old.xls - old .xls format' in line
    assert dict(c.execute('SELECT message_id, outcome FROM hb_email_seen')) == {'<m1@x>': 'taken in', '<m2@x>': 'left alone: not a trusted sender',
                                                                             '<m3@x>': 'left alone: older than the intake'}
    assert e.check(c, lambda: box, now=NOW + 200) == '0 taken in, 0 left alone'   # nothing is taken twice


def test_practice_64_command_and_tick():
    c = db()
    assert e.command(c, ['trust', 'New@Example.com'], 'jd') == 'new@example.com is trusted: HB takes in what it sends.'
    assert 'new@example.com' in e.trusted(c) and e.command(c, ['untrust', 'new@example.com'], 'jd').endswith('no longer trusted.')
    assert e.command(c, [], 'jd').startswith('Email intake: send to ')

    def broken():
        raise OSError('network down')
    assert e.command(c, ['check'], 'jd', broken) == 'The mailbox could not be checked: OSError: network down'
    c.execute('UPDATE hb_email_intake SET last_check=?', (NOW,))
    assert e.tick(c, now=NOW + 30) is False                                    # not yet: every two minutes
    assert 'email' in cmds.NAMES and cmds.parse('email check') == ('email', ['check'])
