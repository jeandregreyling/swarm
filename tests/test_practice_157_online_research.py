"""Practice 157 (owner 18 Nov 2026: "yes search online and download the relevant notes so it can be indexed"): an answer saying our notes
do not cover the question goes back once to search public SAP pages; HB keeps the SAP pages a search found and queues the notes they cite."""
import json
import sqlite3

import core.apex_tools as t
import core.hb_web_research as w
from core import hb_kc_records as kc, hb_learning
from core.apex_tools import ReadOnlyRepository, run_apex_tools

Q = 'tell be how the wage types /001 and /002 work? How to they get their values? What are they for?'
RESULT = {'provider': 'serper', 'query': 'SAP valuation basis /001 /002',
          'sources': ['https://help.sap.com/docs/HR/x/valuation.html', 'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636',
                      'https://example.com/other'],
          'text': ('- Valuation bases, valuation of wage types: Valuation bases are rates used to value other wage types.\n'
                   '  Source: https://help.sap.com/docs/HR/x/valuation.html\n'
                   '- Solved: Valuation Basis /001 & /002: calculated by adding the basic pay in calculation rule X010; see SAP Note 1234567.\n'
                   '  Source: https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636\n')}


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, source_type TEXT, source_ref TEXT, raw_text TEXT, '
              'domain_tags TEXT, added_by TEXT, category TEXT, subcategory TEXT, content_hash TEXT, chunk_count INT, updated_at TEXT)')
    c.execute('CREATE TABLE knowledge_chunks(source_id INT, chunk_index INT, chunk_text TEXT, embedding BLOB)')
    return c


def test_practice_157_page_text_and_sites():
    title, text = w.page_text('<html><head><title>Valuation Bases</title><script>x()</script></head><body><p>Rates used to value'
                              ' wage types.</p><nav>menu</nav></body></html>')
    assert title == 'Valuation Bases' and 'Rates used to value wage types.' in text and 'menu' not in text and 'x()' not in text
    assert w.allowed('https://help.sap.com/docs/x') and w.allowed('https://community.sap.com/t5') and not w.allowed('https://example.com/a')


def test_practice_157_capture_keeps_pages_and_queues_notes():
    c = db()
    pages = {'https://help.sap.com/docs/HR/x/valuation.html': '<title>Valuation bases</title><p>' + 'Valuation bases are rates. ' * 20 + '</p>'}

    def fetcher(url):
        if url in pages:
            return pages[url]
        raise OSError('blocked')
    out = w.capture(c, RESULT, fetcher, extractor=lambda urls: {u: 'Thread text about valuation bases. ' * 10 for u in urls if 'community' in u})
    refs = {r[0]: r[1] for r in c.execute('SELECT source_ref, subcategory FROM knowledge_sources')}
    assert refs == {'https://help.sap.com/docs/HR/x/valuation.html': 'sap-web',
                    'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636': 'sap-web'}
    assert out['queued_notes'] == ['1234567']
    community = c.execute("SELECT raw_text FROM knowledge_sources WHERE source_ref LIKE 'https://community%'").fetchone()[0]
    assert 'Thread text about valuation bases.' in community
    again = w.capture(c, RESULT, fetcher, extractor=lambda urls: {u: 'Thread text about valuation bases. ' * 10 for u in urls if 'community' in u})
    assert not any(k['changed'] for k in again['kept']) and again['queued_notes'] == []


def test_practice_157_not_covered_answer_goes_online(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    monkeypatch.setattr(w, 'capture_later', lambda result: None)
    seen = []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'wage type /001 /002'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'valuation basis /001'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': 'Our notes do not define /001 and /002. General knowledge: they are basic pay.'}),
             json.dumps({'tool_calls': [{'name': 'web_search', 'arguments': {'query': 'SAP valuation basis /001 /002 help.sap.com',
                                                                             'provider': 'serper'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': ('Our notes do not define them; public SAP pages do: /001 and /002 are valuation bases, '
                                                      'rates from basic pay (rule X010) used to value time wage types. '
                                                      'https://community.sap.com/t5/q/valuation-basis-001-002/qaq-p/8131636')})] + \
            [json.dumps({'tool_calls': [], 'answer': 'done'})] * 4

    def model(_n, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1
    answer, _, receipts = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                         studio_handler=lambda name, args: {'status': 'found', 'matches': []},
                                         web_handler=lambda args: RESULT)
    assert any(s.startswith('BACKEND ONLINE CHECK') for s in seen)
    assert any(r['tool'] == 'web_search' for r in receipts) and 'valuation bases' in answer


def test_practice_157_method():
    assert "web_search for public SAP documentation" in hb_learning.research_method()
