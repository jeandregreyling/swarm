"""Practice 67 (owner 15 Nov): one reader for whatever arrives. Real files are made here (zipped formats by hand, the rest with the
machine's own LibreOffice / pdftotext, skipped where a tool is missing) and read back; each must give its marker text."""
import io
import shutil
import zipfile
from email.message import EmailMessage
import pytest
from lib.knowledge.sources import document_reader as d
import core.hb_email_intake as intake

OFFICE = shutil.which('soffice') or shutil.which('libreoffice')
MARK = 'Quarterly payroll reconciliation marker ZEBRA-4417'


def z(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as book:
        for name, body in files.items():
            book.writestr(name, body)
    return buf.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOCX = z({'word/document.xml': f'<w:document {W}><w:body><w:p><w:r><w:t>{MARK}</w:t></w:r></w:p>'
          '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Wage type</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>/101</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
          '<w:p><w:r><w:t>Second</w:t><w:tab/><w:t>line</w:t></w:r></w:p></w:body></w:document>'})
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
PPTX = z({'ppt/slides/slide2.xml': f'<p:sld {A}><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Second slide</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>',
          'ppt/slides/slide1.xml': f'<p:sld {A}><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{MARK}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'})
XLSX = z({'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                             '<sheets><sheet name="Needs check" sheetId="1" r:id="rId1"/></sheets></workbook>',
          'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
          'xl/worksheets/sheet1.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                                      '<row r="1"><c r="A1" t="inlineStr"><is><t>SAP Note</t></is></c></row><row r="2"><c r="A2"><v>2382421</v></c></row></sheetData></worksheet>'})


def test_practice_67_zipped_office_formats_without_any_extra_package():
    assert d.read('a.docx', DOCX) == (f'{MARK}\nWage type\t/101\nSecond\tline', None)
    assert d.read('a.pptx', PPTX)[0] == f'## Slide 1\n{MARK}\n\n## Slide 2\nSecond slide'
    assert d.read('a.xlsx', XLSX)[0] == '## Sheet: Needs check (2 rows)\nSAP Note\n2382421'


def test_practice_67_text_html_mail_and_zip():
    assert d.read('n.csv', b'\xef\xbb\xbfnote,title\n2382421,x')[0] == 'note,title\n2382421,x'
    assert d.read('p.html', f'<html><style>x</style><body><h1>{MARK}</h1><p>a&amp;b</p></body></html>'.encode())[0] == f'{MARK}\na&b'
    m = EmailMessage()
    m['From'], m['Subject'] = 'jd@example.com', 'sheet'
    m.set_content('see attached')
    m.add_attachment(XLSX, maintype='application', subtype='octet-stream', filename='notes.xlsx')
    text = d.read('mail.eml', m.as_bytes())[0]
    assert 'Subject: sheet' in text and 'see attached' in text and '--- Attachment: notes.xlsx ---\n## Sheet: Needs check' in text
    packed = d.read('all.zip', z({'a/notes.xlsx': XLSX, 'b.docx': DOCX, 'pic.png': b'\x89PNG\r\n\x1a\n\x00\x00'}))[0]
    assert '--- a/notes.xlsx ---\n## Sheet: Needs check' in packed and MARK in packed and '(not read: a picture' in packed


def test_practice_67_unreadable_files_say_why_and_never_raise():
    assert d.read('m.rpmsg', b'x')[1].startswith("protected by the sender's organisation")
    assert d.read('m.msg', b'x')[1].startswith('an Outlook .msg file')
    assert d.read('bad.xlsx', b'not a zip')[1] == 'the file is damaged, or it is not really the type its name says'
    assert d.read('locked.xlsx', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'x' * 50)[1].startswith('the file is password-protected')
    assert d.read('e.txt', b'')[1] == 'the file is empty'
    assert d.read('p.png', b'\x89PNG\r\n\x1a\n\x00\x00\x00')[1].startswith('a picture')
    assert d.read('x.bin', bytes(range(256)))[1].startswith('a file type HB does not read yet')
    assert d.read('big.csv', b'x' * (d.MAX_BYTES + 1))[1].startswith('too large')


@pytest.mark.skipif(not OFFICE or not shutil.which('pdftotext'), reason='needs LibreOffice and pdftotext')
def test_practice_67_real_pdf_and_old_office_files_made_on_this_machine():
    source = f'{MARK}\nSecond paragraph about wage types.\n'.encode()
    pdf = d.office_convert('in.txt', source, 'pdf')
    assert pdf and pdf[:5] == b'%PDF-' and MARK in d.read('report.pdf', pdf)[0]
    assert d.read('scan.pdf', b'%PDF-1.4\n%%EOF')[0] is None
    doc = d.office_convert('in.txt', source, 'doc')
    assert doc and MARK in d.read('old.doc', doc)[0]
    rtf = d.office_convert('in.txt', source, 'rtf')
    assert rtf and MARK in d.read('old.rtf', rtf)[0]
    xls = d.office_convert('in.csv', b'SAP Note,Area\n2382421,PY-AU\n', 'xls')
    lines = d.read('old.xls', xls)[0].splitlines()
    assert lines[0].startswith('## Sheet: ') and lines[0].endswith('(2 rows)') and lines[1:] == ['SAP Note\tArea', '2382421\tPY-AU']
    ods = d.office_convert('in.csv', b'SAP Note,Area\n2382421,PY-AU\n', 'ods')
    assert d.read('sheet.ods', ods)[0].splitlines()[1:] == ['SAP Note\tArea', '2382421\tPY-AU']
    odt = d.office_convert('in.txt', source, 'odt')
    assert odt and MARK in d.read('text.odt', odt)[0]


def test_practice_67_the_intake_uses_the_one_reader():
    assert intake.attachment_text('a.docx', '', DOCX)[0].startswith(MARK)
    assert intake.attachment_text('a.pptx', '', PPTX)[0].startswith('## Slide 1')
    assert intake.attachment_text('m.rpmsg', '', b'x')[1].startswith("protected by the sender's organisation")
    assert intake.xlsx_text(XLSX) == d.xlsx_text(XLSX)
