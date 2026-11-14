"""Practice 65 (owner 15 Nov): JD's work material is confidential - local models only - and can arrive through a local inbox folder."""
import sqlite3
import time
import pytest
from core import apex_knowledge as kc, agent_identity
import core.hb_email_intake as e


@pytest.fixture
def library(tmp_path, monkeypatch):
    path = tmp_path / 'k.sqlite'
    connect = lambda: sqlite3.connect(path)
    with connect() as c:
        c.execute("CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY, title TEXT, raw_text TEXT, domain_tags TEXT, source_ref TEXT, status TEXT DEFAULT 'active', subcategory TEXT)")
        c.execute("INSERT INTO knowledge_sources(title, raw_text, domain_tags, source_ref) VALUES ('Inbox file: payrun.xlsx','wagetype 1234 secretfigure','[\"inbox-file\", \"confidential\"]','file://x')")
        c.execute("INSERT INTO knowledge_sources(title, raw_text, domain_tags, source_ref) VALUES ('Public wagetype guide','wagetype basics','[\"sap\"]','http://x')")
        c.execute('CREATE TABLE hb_agents(agent_id TEXT, kind TEXT)')
        c.executemany('INSERT INTO hb_agents VALUES (?,?)', [('gemini-advisor', 'online'), ('qwen2-5-14b', 'local')])
    monkeypatch.setattr(kc, 'get_connection', connect)


def as_agent(name):
    return agent_identity.CURRENT.set({'principal': name} if name else None)


def test_practice_65_online_agents_never_see_confidential_sources(library):
    doc = kc.LIBRARY_ID + 1
    for who, sees in ((None, True), ('apex', True), ('qwen2-5-14b', True), ('gemini-advisor', False), ('claude-code', False), ('some-new-agent', False)):
        token = as_agent(who)
        try:
            titles = [i['title'] for i in kc.search('wagetype')['items']]
            assert ('Inbox file: payrun.xlsx' in titles) is sees, who
            assert 'Public wagetype guide' in titles, who
            page = kc.read(doc)
            assert (page['status'] == 'found') is sees and (sees or 'secretfigure' not in str(page)), who
            assert kc.read(kc.LIBRARY_ID + 2)['status'] == 'found'
        finally:
            agent_identity.CURRENT.reset(token)


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INTEGER)')
    e.ensure_schema(c)
    return c


def test_practice_65_inbox_folder_files_are_taken_in_as_confidential(tmp_path):
    c, kept = db(), []
    (tmp_path / 'notes.csv').write_text('note,title\n2382421,network\n')
    (tmp_path / 'mail.rpmsg').write_bytes(b'\x00protected')
    (tmp_path / 'taken').mkdir()
    keep = lambda conn, title, ref, text, tags: kept.append((title, tags, text)) or 41
    now = time.time() + 60
    assert e.folder_check(c, tmp_path, keep, now) == 1
    assert kept[0][0] == 'Inbox file: notes.csv' and kept[0][1] == ['inbox-file', 'confidential'] and '2382421,network' in kept[0][2]
    assert not (tmp_path / 'notes.csv').exists() and len(list((tmp_path / 'taken').glob('*-notes.csv'))) == 1
    assert (tmp_path / 'mail.rpmsg').exists()                                   # unreadable files stay put
    lines = [r[0] for r in c.execute('SELECT content FROM messages ORDER BY id')]
    assert any("protected by the sender's organisation" in l for l in lines) and any('notes.csv taken in' in l and 'KC41' in l for l in lines)
    assert e.folder_check(c, tmp_path, keep, now + 5) == 0 and len(lines) == c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]   # said once


def test_practice_65_email_is_tagged_confidential():
    import inspect
    src = inspect.getsource(e.ingest)
    assert "['email', 'confidential']" in src and "['email', 'email-attachment', 'confidential']" in src
    assert e.attachment_text('m.rpmsg', 'application/x-microsoft-rpmsg-message', b'x')[1].startswith("protected by the sender's organisation")
