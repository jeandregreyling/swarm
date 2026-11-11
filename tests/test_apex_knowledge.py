import sqlite3
import pytest
from core import apex_knowledge as kc

@pytest.fixture
def corpus(tmp_path,monkeypatch):
    path=tmp_path/'knowledge.sqlite'
    def connect(): return sqlite3.connect(path)
    with connect() as c:
        c.execute('CREATE TABLE project_docs(id INTEGER PRIMARY KEY,doc_name TEXT,content TEXT,tags TEXT)')
        c.execute('INSERT INTO project_docs VALUES(1,?,?,?)',('DEOS source','Decides, Executes, Operates, Sustains. '+'evidence '*400,'all'))
    monkeypatch.setattr(kc,'get_connection',connect)


def test_knowledge_search_reports_real_sources_and_missing_queries(corpus):
    found=kc.search('DEOS')
    assert found['items'][0]['document_id']==1
    assert found['items'][0]['title']=='DEOS source'
    assert len(found['items'][0]['excerpt'])<=650
    assert kc.search('absent')['status']=='not_found'
    assert kc.search('%%')['status']=='not_found'


def test_read_pages_without_exposing_sql_or_private_memory(corpus):
    page=kc.read(1)
    assert len(page['content'])==1500 and page['next_offset']==1500
    original='Decides, Executes, Operates, Sustains. '+'evidence '*400
    assert kc.read(1,1500)['content']==original[1500:3000]
    assert kc.read(2)=={'status':'not_found','document_id':2}
    with pytest.raises(ValueError):kc.read(True)
    with pytest.raises(ValueError):kc.read(1,10000)
