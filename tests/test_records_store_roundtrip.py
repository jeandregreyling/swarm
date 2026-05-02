"""Acceptance test for S-7221671DD4 — separate-file artifact path.

Acceptance: deleting a row from the DB and re-importing the on-disk JSON
file must restore the record byte-for-byte.
"""
import json
import sqlite3

import pytest

from core.records import store


@pytest.fixture
def tmp_records_root(tmp_path, monkeypatch):
    """Redirect runtime/records/ to a temp dir so tests don't pollute the repo."""
    monkeypatch.setattr(store, "_SWARM_ROOT", tmp_path)
    monkeypatch.setattr(store, "RECORDS_ROOT", tmp_path / "records")
    monkeypatch.setattr(store, "LEDGER_PATH", tmp_path / "records" / "_ledger.jsonl")
    monkeypatch.setattr(store, "XREF_PATH", tmp_path / "records" / "_xref.json")
    monkeypatch.setattr(store, "LINKS_DB", tmp_path / "records" / "_links.db")
    return tmp_path / "records"


@pytest.fixture
def project_db(tmp_path):
    db = tmp_path / "swarm.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT,
            created_at TEXT
        );
        """
    )
    con.commit()
    yield db, con
    con.close()


class TestSaveLoadRoundTrip:
    def test_save_then_load_returns_same_data(self, tmp_records_root):
        data = {
            "project_id": "P-TEST001",
            "name": "Round-trip lab",
            "status": "active",
            "created_at": "2026-05-02 10:00:00",
        }
        store.save_record("project", "P-TEST001", data, actor="test")
        loaded = store.load_record("project", "P-TEST001")
        assert loaded is not None
        assert loaded["data"] == data

    def test_save_writes_json_and_md(self, tmp_records_root):
        data = {
            "project_id": "P-TEST002",
            "name": "JSON+MD",
            "status": "active",
            "created_at": "2026-05-02 10:00:00",
        }
        path = store.save_record("project", "P-TEST002", data)
        assert path.exists() and path.suffix == ".json"
        assert path.with_suffix(".md").exists()

    def test_save_appends_to_ledger(self, tmp_records_root):
        data = {"project_id": "P-LEDGER", "name": "x", "status": "active",
                "created_at": "2026-05-02 10:00:00"}
        store.save_record("project", "P-LEDGER", data, actor="alice")
        assert store.LEDGER_PATH.exists()
        lines = store.LEDGER_PATH.read_text().splitlines()
        assert any("P-LEDGER" in line and '"actor": "alice"' in line for line in lines)

    def test_idempotent_save_does_not_double_log(self, tmp_records_root):
        data = {"project_id": "P-IDEMP", "name": "x", "status": "active",
                "created_at": "2026-05-02 10:00:00"}
        store.save_record("project", "P-IDEMP", data)
        first_count = len(store.LEDGER_PATH.read_text().splitlines())
        store.save_record("project", "P-IDEMP", data)
        second_count = len(store.LEDGER_PATH.read_text().splitlines())
        assert first_count == second_count


class TestAcceptanceRestoreRoundTrip:
    def test_delete_row_and_reimport_restores_record(self, tmp_records_root, project_db):
        db, con = project_db
        data = {
            "project_id": "P-ACCEPT1",
            "name": "Acceptance project",
            "status": "active",
            "created_at": "2026-05-02 11:00:00",
        }
        # 1. Insert into DB and snapshot to disk.
        cols = ",".join(data.keys())
        placeholders = ",".join("?" for _ in data)
        con.execute(
            f"INSERT INTO projects ({cols}) VALUES ({placeholders})",
            list(data.values()),
        )
        con.commit()
        store.save_record("project", "P-ACCEPT1", data, actor="snapshot")

        # 2. Delete the row.
        con.execute("DELETE FROM projects WHERE project_id='P-ACCEPT1'")
        con.commit()
        assert con.execute(
            "SELECT 1 FROM projects WHERE project_id='P-ACCEPT1'"
        ).fetchone() is None

        # 3. Re-import from file.
        result = store.restore_record("project", "P-ACCEPT1", conn=con)
        assert result["ok"] is True
        assert result["action"] == "inserted"

        # 4. Compare row vs original byte-for-byte.
        cur = con.execute(
            "SELECT project_id, name, status, created_at FROM projects WHERE project_id=?",
            ("P-ACCEPT1",),
        )
        row = dict(zip([c[0] for c in cur.description], cur.fetchone()))
        assert row == data

    def test_restore_existing_row_is_an_update(self, tmp_records_root, project_db):
        db, con = project_db
        data = {
            "project_id": "P-ACCEPT2",
            "name": "Original",
            "status": "active",
            "created_at": "2026-05-02 11:00:00",
        }
        store.save_record("project", "P-ACCEPT2", data)
        # Pre-existing row with a stale name
        con.execute(
            "INSERT INTO projects (project_id, name, status, created_at) VALUES (?,?,?,?)",
            ("P-ACCEPT2", "STALE", "active", "2026-05-02 11:00:00"),
        )
        con.commit()
        result = store.restore_record("project", "P-ACCEPT2", conn=con)
        assert result["action"] == "updated"
        row = con.execute(
            "SELECT name FROM projects WHERE project_id='P-ACCEPT2'"
        ).fetchone()
        assert row[0] == "Original"

    def test_missing_file_returns_missing(self, tmp_records_root, project_db):
        _, con = project_db
        result = store.restore_record("project", "P-NOSUCH", conn=con)
        assert result["ok"] is False
        assert result["action"] == "missing"

    def test_thread_kind_is_unsupported(self, tmp_records_root, project_db):
        _, con = project_db
        result = store.restore_record("thread", "1", conn=con)
        assert result["ok"] is False
        assert result["action"] == "unsupported"


class TestRecordPath:
    def test_path_has_kind_year_month_layout(self, tmp_records_root):
        data = {"project_id": "P-LAYOUT", "name": "x", "status": "active",
                "created_at": "2026-05-02 10:00:00"}
        path = store.save_record("project", "P-LAYOUT", data)
        # ...records/project/2026/05/P-LAYOUT.json
        rel = path.relative_to(tmp_records_root)
        parts = rel.parts
        assert parts[0] == "project"
        assert parts[1] == "2026"
        assert parts[2] == "05"
        assert parts[3] == "P-LAYOUT.json"

    def test_unknown_kind_raises(self):
        with pytest.raises(KeyError):
            store._kind_meta("not_a_kind")


class TestLoadRecord:
    def test_load_returns_none_when_missing(self, tmp_records_root):
        assert store.load_record("project", "P-DOES-NOT-EXIST") is None

    def test_load_finds_record_anywhere_in_kind_tree(self, tmp_records_root):
        data = {"project_id": "P-FIND", "name": "x", "status": "active",
                "created_at": "2026-03-01 10:00:00"}  # different month bucket
        store.save_record("project", "P-FIND", data)
        loaded = store.load_record("project", "P-FIND")
        assert loaded is not None
        assert loaded["data"]["name"] == "x"
