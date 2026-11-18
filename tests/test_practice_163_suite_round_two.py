"""Practice 163 (owner 18 Nov 2026, question suite): SAP-note checks for SAP questions only; a new research question starts without old chat;
a note is not credited with a wage type it does not contain; the exact-title note gets read."""
import json

import core.apex_tools as t
from core.chat_continuity import apex_request_history, fresh_research


def test_practice_163_sap_or_not():
    assert t.sap_question('What is wage type /XQE and when does payroll create it?')
    assert t.sap_question('What is a personnel calculation rule (PCR) in SAP payroll?')
    assert not t.sap_question('What does the HB GPU guard do when the graphics card resets?')
    assert not t.sap_question('In this repo, where is the SAP note meaning (vector) index built?')
    assert not t.sap_question('How does HB decide which model plays APEX for a question?')


def test_practice_163_fresh_research_drops_old_chat():
    h = [{'role': 'user', 'content': 'What do the SAP notes say about the MCB cap?'}, {'role': 'assistant', 'content': 'super super super'}]
    q = 'tell be how the wage types /001 and /002 work? How to they get their values?'
    assert fresh_research(q)
    out = apex_request_history(h, q)
    assert out[-1] == {'role': 'user', 'content': q} and 'super' not in json.dumps(out)
    follow = 'what about /003?'
    assert not fresh_research(follow) and len(apex_request_history(h, follow)) == 3


def test_practice_163_misattributed():
    texts = {'3800022': 'The Superannuation Guarantee (SG) fund employer contribution wage type is not generated for CE.',
             '3793457': 'the amount above the ceiling is stored in wage type /XQE ... view V_T5QSF'}
    a = ('/002 is the employer SG contribution. SAP Note 3800022 calls /002 the SG employer contribution wage type.\n'
         'SAP Note 3793457 introduces /XQE and the Apply MCB flag in V_T5QSF.')
    assert t.misattributed(a, texts) == [('3800022', '/002')]


def test_practice_163_exact_title_note_unread():
    out = json.dumps({'matches': ['SAP Note 3609437: [document_id 11] 3609437 - Thresholds & limits for tax year 2025-2026 | x',
                                  'SAP Note 3757848: [document_id 12] 3757848 - Thresholds & limits for tax year 2026-2027 | y',
                                  'SAP Note 3684378: [document_id 13] 3684378 - Benefits tax limits US | z']})
    rec = [{'tool': 'knowledge_search', 'status': 'succeeded', 'arguments': {'query': 'tax'}, 'output': out}]
    q = 'What are the tax thresholds and limits for the 2025-2026 tax year in Australian payroll according to our notes?'
    assert t.exact_note_unread(q, rec)[:2] == ('3609437', 11)
    rec.append({'tool': 'knowledge_read', 'status': 'succeeded', 'arguments': {'document_id': 11}, 'output': '{}'})
    assert t.exact_note_unread(q, rec)[0] == '3757848'
