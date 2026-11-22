import importlib.util
import sqlite3
import sys
import types
from pathlib import Path


def test_import_keeps_studio_documents_and_does_not_overwrite_on_repeat(tmp_path, monkeypatch):
    db = tmp_path / 'studio.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE project_docs(doc_name TEXT UNIQUE, content TEXT)')
        conn.execute("INSERT INTO project_docs VALUES ('Owner document','keep this')")
    fake = types.ModuleType('database')
    fake.get_connection = lambda: sqlite3.connect(db)
    monkeypatch.setitem(sys.modules, 'database', fake)
    path = Path(__file__).resolve().parents[1] / 'utils/load_project_docs.py'
    spec = importlib.util.spec_from_file_location('isolated_project_doc_import', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.PROJECT_MD = tmp_path / 'PROJECT.md'
    mod.PROJECT_MD.write_text('## Task\nOriginal section')
    mod.load()
    mod.PROJECT_MD.write_text('## Task\nChanged section')
    mod.load()
    with sqlite3.connect(db) as conn:
        assert list(conn.execute('SELECT doc_name,content FROM project_docs ORDER BY doc_name')) == [
            ('Owner document', 'keep this'), ('PROJECT.md: Task', 'Original section')]
