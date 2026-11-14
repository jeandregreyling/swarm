import sqlite3
import pytest
from core import apex_knowledge as kc

@pytest.fixture
def corpus(tmp_path,monkeypatch):
    path=tmp_path/'knowledge.sqlite'
    def connect(): return sqlite3.connect(path)
    with connect() as c:
        c.execute('CREATE TABLE project_docs(id INTEGER PRIMARY KEY,doc_name TEXT,content TEXT,tags TEXT)')
        c.execute('INSERT INTO project_docs VALUES(1,?,?,?)',('DOES source','Decides, Executes, Operates, Sustains. '+'evidence '*400,'all'))
    monkeypatch.setattr(kc,'get_connection',connect)


def test_knowledge_search_reports_real_sources_and_missing_queries(corpus):
    found=kc.search('DOES')
    assert found['items'][0]['document_id']==1
    assert found['items'][0]['title']=='DOES source'
    assert len(found['items'][0]['excerpt'])<=650
    assert kc.search('absent')['status']=='not_found'
    assert kc.search('%%')['status']=='not_found'


def test_read_pages_without_exposing_sql_or_private_memory(corpus):
    page=kc.read(1)
    assert len(page['content'])==1500 and page['next_offset']==1500
    original='Decides, Executes, Operates, Sustains. '+'evidence '*400
    assert kc.read(1,1500)['content']==original[1500:3000]
    missing=kc.read(2)
    assert {k:missing[k] for k in ('status','document_id')}=={'status':'not_found','document_id':2} and 'knowledge_search' in missing['hint']
    with pytest.raises(ValueError):kc.read(True)
    with pytest.raises(ValueError):kc.read(1,10000)


def test_word_search_finds_titles_with_reordered_words_and_ranks_them_first(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    from core import apex_knowledge
    path = tmp_path / 'kc.sqlite'
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript("""CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY,title TEXT,raw_text TEXT,domain_tags TEXT,
                                  source_ref TEXT,status TEXT,subcategory TEXT);
            INSERT INTO knowledge_sources VALUES(1,'Australian Tax — PAYG','See the payroll schema AU01 chapter.','[]','r1','active',NULL);
            INSERT INTO knowledge_sources VALUES(2,'Payroll Schema Fundamentals — AU01 and Key Subschemas','Schema AU01 steps.','[]','r2','active',NULL);
            INSERT INTO knowledge_sources VALUES(3,'Cooking basics','Nothing here about anything.','[]','r3','active',NULL);""")
    monkeypatch.setattr(apex_knowledge, 'get_connection', lambda: sqlite3.connect(path))
    found = apex_knowledge.search('payroll schema AU01')['items']
    assert found[0]['source_id'] == 2 and found[1]['source_id'] == 1       # all words in the title beat a body phrase
    assert apex_knowledge.search('AU01 payroll')['items'][0]['source_id'] == 2
    monkeypatch.setattr('core.hf_text_index.search', lambda q: [])
    monkeypatch.setattr('core.hf_mirror.catalogue_search', lambda q: [])
    assert apex_knowledge.search('zzqx nothing here')['status'] == 'not_found'   # common words alone are not a match
