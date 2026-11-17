"""Practice 137 (owner 17 Nov 2026): "the references should be links to the actual notes" - "shouldn't it reference KC and the actual
online sources it used instead?". Note numbers link HB's Knowledge Centre copy (what APEX used) and, once, the online origin (SAP for Me);
a "Sources used" list names every KC document APEX read, with HB's copy and its online original when there is one."""
import shutil
import sqlite3
import subprocess
from pathlib import Path

from core import hb_note_links as nl, hb_agent_tools
from core.apex_knowledge import LIBRARY_ID

ANSWER = ('1. SAP Note 3710504 - STP2: Authorization error after implementing Note 3660828 (receipt fe7ac8fa6cd242faa6eb72cb208686b4)\n'
          '2. 3660828 - CE performance; see [3660828](https://me.sap.com/notes/3660828) and document 1099511634208.\n'
          '3. Note 3999999 is not in the KC.')


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_ref TEXT, raw_text TEXT)')
    c.executemany('INSERT INTO knowledge_sources VALUES (?,?,?,?)', [
        (7114, 'SAP Note 3710504: 3710504 - STP2: Authorization error', 'sap://note/3710504', 'Symptom'),
        (7200, 'Payroll mail from Sue', 'email://<abc@x>', 'Hi'), (7300, 'ATO STP guide', 'https://www.ato.gov.au/stp', 'Guide')])
    return c


def test_practice_137_note_numbers_link_the_kc_copy_and_the_origin():
    out = nl.link_notes(ANSWER, known={'3710504', '3660828'})
    assert out.startswith('1. SAP Note [3710504](/kc/note/3710504) ([SAP for Me](https://me.sap.com/notes/3710504)) - STP2')
    assert 'implementing Note [3660828](/kc/note/3660828) ([SAP for Me](https://me.sap.com/notes/3660828))' in out
    assert '2. [3660828](/kc/note/3660828) - CE' in out                                      # later mentions: the KC copy only
    assert 'see [3660828](https://me.sap.com/notes/3660828) and document 1099511634208' in out   # existing links, long ids untouched
    assert 'receipt fe7ac8fa6cd242faa6eb72cb208686b4' in out and 'Note 3999999 is not' in out
    assert nl.kc_notes({'3710504', '3999999'}, _db()) == {'3710504'}


def test_practice_137_sources_used_lists_what_was_read():
    read = lambda doc: {'tool': 'knowledge_read', 'status': 'succeeded', 'arguments': {'document_id': doc}}
    receipts = [read(LIBRARY_ID + 7114), read(LIBRARY_ID + 7200), read(LIBRARY_ID + 7300), read(LIBRARY_ID + 7114),
                {'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'STP2'}}]
    foot = nl.sources_footer(receipts, _db())
    assert foot.startswith('\n\n**Sources used**')
    assert '- [SAP Note 3710504: STP2: Authorization error](/kc/source/7114) · [online](https://me.sap.com/notes/3710504)' in foot
    assert '- [Payroll mail from Sue](/kc/source/7200) · Knowledge Centre only' in foot
    assert '- [ATO STP guide](/kc/source/7300) · [online](https://www.ato.gov.au/stp)' in foot and foot.count('7114)') == 1
    assert nl.sources_footer([], _db()) == ''


def test_practice_137_answers_get_links(monkeypatch):
    monkeypatch.setattr(nl, 'kc_notes', lambda numbers, conn=None: {'3660828'})
    monkeypatch.setattr(nl, 'sources_footer', lambda receipts, conn=None: '')
    assert hb_agent_tools.ground_answer('Note 3660828 fixes it.', []) == \
        'Note [3660828](/kc/note/3660828) ([SAP for Me](https://me.sap.com/notes/3660828)) fixes it.'


def test_practice_137_source_page_and_wiring():
    page = nl.source_html(7114, 'SAP Note 3710504: STP2 <CE>', 'sap://note/3710504', 'Symptom\n\nSlow & big.')
    assert 'https://me.sap.com/notes/3710504' in page and 'STP2 &lt;CE&gt;' in page and 'Slow &amp; big.' in page
    assert 'No online original: email source' in nl.source_html(7200, 'Mail', 'email://<abc@x>', 'Hi')
    root = Path(__file__).resolve().parents[1]
    lib = (root / 'frontend/blueprints/library.py').read_text()
    assert "/kc/source/<int:source_id>" in lib and "/kc/note/<int:number>" in lib
    assert 'hb-chat-links.js' in (root / 'frontend/templates/terminal_base.html').read_text()
    if shutil.which('node'):
        assert subprocess.run(['node', '--check', str(root / 'frontend/static/js/hb-chat-links.js')], capture_output=True).returncode == 0
