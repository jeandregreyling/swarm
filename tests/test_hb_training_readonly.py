"""A prompt/card reader must not acquire SQLite's writer lock to read optional lessons."""
import sqlite3
from core import hb_training as training


def test_absent_training_tables_are_not_created_by_reading():
    conn=sqlite3.connect(':memory:')
    assert training.lessons_learned(conn)==[]
    assert not conn.in_transaction
    assert conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'hb_training_%'").fetchall()==[]


def test_lesson_reader_succeeds_while_another_connection_holds_writer(tmp_path):
    path=tmp_path/'live-like.db'
    writer=sqlite3.connect(path)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('CREATE TABLE unrelated(value TEXT)')
    writer.commit()
    reader=sqlite3.connect(path,timeout=0)
    try:
        writer.execute("INSERT INTO unrelated VALUES ('writer held by API')")
        assert training.lessons_learned(reader)==[]
        writer.rollback()
        training.ensure(writer)
        writer.execute("INSERT INTO hb_training_lessons VALUES ('ex','Read receipts before retrying',1)")
        writer.commit()
        writer.execute("INSERT INTO unrelated VALUES ('writer held again')")
        assert training.lessons_learned(reader)==['Read receipts before retrying']
        assert not reader.in_transaction
    finally:
        writer.rollback();reader.close();writer.close()
