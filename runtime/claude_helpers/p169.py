"""Prepare Practice 169: questions about HB/code search HB's own docs first and skip the SAP-note ranking."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
K = 'core/apex_knowledge.py'
OLD = '''            if 'hb_note_fts' in tables and not hb_reference:
                from core import hb_note_index
                items,families=hb_note_index.rank(conn,query,items,LIBRARY_ID)
'''
NEW = '''            # Practice 169 (owner 19 Nov 2026, question suite Q7): "How does HB decide which model plays APEX?" returned 12 SAP notes
            # ("Time-stat money selection model") and never HB's own page. A question about HB or code (not SAP) skips the SAP-note
            # ranking, and HB's documentation (subcategory hb-doc, e.g. hb-doc://how-hb-works) comes first when it carries the words.
            hb_question=False
            try:
                from core.apex_tools import sap_question,_HB_TOPIC
                hb_question=bool(_HB_TOPIC.search(query)) and not sap_question(query)
            except Exception:
                pass
            try:
                words={w.lower() for w in _re.findall(r'[A-Za-z]{4,}',query)}
                docs=[]
                for sid,title,text,ref,tags in conn.execute("SELECT source_id,title,raw_text,source_ref,domain_tags FROM knowledge_sources "
                                                            "WHERE COALESCE(subcategory,'')='hb-doc' AND status='active'"):
                    hits=sum(1 for w in words if w in (str(title)+' '+str(text)).lower())
                    if hits>=2:
                        docs.append((hits,{'document_id':LIBRARY_ID+sid,'source_id':sid,'title':title,'excerpt':str(text or '')[:650],
                                           'tags':tags,'source_ref':ref,'store':'knowledge_sources','kind':'hb documentation'}))
                if docs:
                    ids={d['source_id'] for _h,d in docs}
                    items=[d for _h,d in sorted(docs,key=lambda x:-x[0])]+[i for i in items if i.get('source_id') not in ids]
            except Exception:
                pass
            if 'hb_note_fts' in tables and not hb_reference and not hb_question:
                from core import hb_note_index
                items,families=hb_note_index.rank(conn,query,items,LIBRARY_ID)
'''
test = r'''"""Practice 169 (owner 19 Nov 2026): questions about HB search HB's own documentation first and skip the SAP-note ranking."""


def test_practice_169_hb_docs_first_for_hb_questions():
    src = open('core/apex_knowledge.py').read()
    assert "COALESCE(subcategory,'')='hb-doc'" in src and 'not hb_question' in src
    from core.apex_tools import sap_question, _HB_TOPIC
    q = 'How does HB decide which model plays APEX for a question?'
    assert _HB_TOPIC.search(q) and not sap_question(q)
    assert sap_question('What is wage type /XQE and when does payroll create it?')
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov (\"go be amazing\"): question suite Q7 described old code because 'How does HB decide which model plays APEX?' "
                            "returned 12 SAP notes and never HB's documentation. Claude Code wrote hb-doc://how-hb-works (KC 11204, from the Studio "
                            "practice records). core/apex_knowledge.search: questions about HB/code (HB topic, not SAP) skip the SAP-note ranking, "
                            "and hb-doc sources come first when they carry the query's words."),
                 edits=[{'path': K, 'old': OLD, 'new': NEW}], new_files={'tests/test_practice_169_hb_docs_first.py': test},
                 test={'tests': ['tests/test_practice_169_hb_docs_first.py', 'tests/test_apex_knowledge.py', 'tests/test_practice_147_meaning_search.py',
                                 'tests/test_practice_131_note_index.py', 'tests/test_practice_136_note_summaries.py'], 'keyword': ''}, run=run)
print(out['verified'])
