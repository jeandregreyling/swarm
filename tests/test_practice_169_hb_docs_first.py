"""Practice 169 (owner 19 Nov 2026): questions about HB search HB's own documentation first and skip the SAP-note ranking."""


def test_practice_169_hb_docs_first_for_hb_questions():
    src = open('core/apex_knowledge.py').read()
    assert "COALESCE(subcategory,'')='hb-doc'" in src and 'not hb_question' in src
    from core.apex_tools import sap_question, _HB_TOPIC
    q = 'How does HB decide which model plays APEX for a question?'
    assert _HB_TOPIC.search(q) and not sap_question(q)
    assert sap_question('What is wage type /XQE and when does payroll create it?')
