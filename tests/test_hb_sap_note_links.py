"""Practice 84 (owner 15 Nov 2026: "the one I want is the email task to read and download the notes")."""
import io
import sqlite3
import zipfile

import core.hb_sap_note_job as job
from lib.knowledge.sources import document_reader as reader

M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'


def linked_workbook():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{M}" xmlns:r="{R}"><sheets><sheet name="Needs check" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{P}"><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{M}"><si><t>Title</t></si><si><t>Payroll fix</t></si></sst>')
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', f'<Relationships xmlns="{P}"><Relationship Id="rId1" Type="hyperlink" '
                   'Target="https://me.sap.com/notes/3089413" TargetMode="External"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{M}" xmlns:r="{R}"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
                   '<row r="3"><c r="A3" t="str"><f>HYPERLINK("https://launchpad.support.sap.com/#/notes/2382421","click here")</f><v>click here</v></c></row>'
                   '<row r="4"><c r="A4" t="inlineStr"><is><t>https://userapps.support.sap.com/sap/support/knowledge/en/3412345</t></is></c></row>'
                   '<row r="5"><c r="A5" t="inlineStr"><is><t>see https://example.com/search?q=7654321</t></is></c></row>'
                   '</sheetData><hyperlinks><hyperlink ref="A2" r:id="rId1"/></hyperlinks></worksheet>')
    return buf.getvalue()


def test_practice_84_linked_cells_keep_their_address():
    text = reader.xlsx_text(linked_workbook())
    assert 'Payroll fix https://me.sap.com/notes/3089413' in text
    assert 'click here https://launchpad.support.sap.com/#/notes/2382421' in text


def test_practice_84_note_links_count_and_other_links_do_not():
    plan = job.plan(reader.xlsx_text(linked_workbook()))
    assert plan['matched'] and plan['numbers'] == ['3089413', '2382421', '3412345']


def test_practice_84_the_notes_report_goes_to_the_chat_jd_is_in():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, '
              'message_type TEXT, tokens_used INTEGER)')
    c.execute("INSERT INTO messages(conversation_id, from_agent, content) VALUES (2837, 'user', 'download the notes')")
    job._say(c, 'notes found')
    assert c.execute("SELECT conversation_id FROM messages WHERE from_agent='hummingbird'").fetchone()[0] == 2837
