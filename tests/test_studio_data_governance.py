from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_governance_apply_bootstraps_fresh_database(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "legacy.sqlite").write_text("not really sqlite", encoding="utf-8")

    result = gov.apply_governance()

    assert result["project_id"] == gov.CONTROL_PROJECT_ID
    assert result["proposal_id"] == gov.CONTROL_PROPOSAL_ID
    assert result["inventory_counts"]["duplicate_or_legacy_db"] == 1

    conn = sqlite3.connect(tmp_path / "swarm_memory.db")
    conn.row_factory = sqlite3.Row
    try:
        proposal_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(work_proposals)")
        }
        assert "source_node" in proposal_cols

        docs = {
            row["doc_name"]
            for row in conn.execute("SELECT doc_name FROM project_docs")
        }
        assert "Studio Data Governance - Deletion Manifest and Retention Gate" in docs
        assert "Studio Data Governance - Operating Model" in docs
    finally:
        conn.close()


def test_retention_manifest_distinguishes_active_and_empty_dbs(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "swarm_memory.db").write_text("", encoding="utf-8")
    (tmp_path / "swarm.db").write_text("legacy", encoding="utf-8")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "swarm.db").write_text("", encoding="utf-8")

    inv = gov.inventory()
    manifest = gov.retention_manifest(inv)

    assert manifest["destructive_actions_taken"] is False
    assert manifest["review_items_total"] == len(manifest["review_items"])
    assert manifest["review_items_truncated"] is False
    assert inv["classification_counts"]["active_auxiliary_db"] == 1
    assert inv["classification_counts"]["empty_legacy_db"] == 1
    review_paths = {item["path"] for item in manifest["review_items"]}
    assert "swarm.db" in review_paths
    active = next(item for item in manifest["review_items"] if item["path"] == "swarm.db")
    assert active["recommended_action"] == "migrate_to_swarm_memory_then_retire"
    empty = next(item for item in manifest["review_items"] if item["path"] == "agents/swarm.db")
    assert empty["recommended_action"] == "delete_empty_placeholder"
    assert "swarm_memory.db" not in review_paths


def test_retention_manifest_prioritizes_dbs_before_loose_docs(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "swarm_memory.db").write_text("", encoding="utf-8")
    (tmp_path / "swarm.db").write_text("legacy", encoding="utf-8")
    for i in range(20):
        (tmp_path / f"doc-{i}.md").write_text("# loose\n", encoding="utf-8")

    manifest = gov.retention_manifest(gov.inventory())

    assert manifest["review_items"][0]["path"] == "swarm.db"
    assert manifest["review_items"][0]["classification"] == "active_auxiliary_db"


def test_retention_summary_groups_actions_and_top_paths(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "swarm_memory.db").write_text("", encoding="utf-8")
    (tmp_path / "swarm.db").write_text("legacy", encoding="utf-8")
    (tmp_path / "old.log").write_text("x" * 100, encoding="utf-8")
    old = tmp_path / "stage1.log"
    old.write_text("generated", encoding="utf-8")
    old.touch()

    manifest = gov.retention_manifest(gov.inventory())
    summary = gov.retention_summary(manifest, limit=3)

    assert summary["destructive_actions_taken"] is False
    assert summary["review_items_total"] == manifest["review_items_total"]
    assert summary["review_items_truncated"] is False
    assert "migrate_to_swarm_memory_then_retire" in summary["actions"]
    action = summary["actions"]["migrate_to_swarm_memory_then_retire"]
    assert action["count"] == 1
    assert action["top_paths"][0]["path"] == "swarm.db"
    assert "guard" in action["top_paths"][0]


def test_swarm_db_retirement_check_accepts_retired_root_db(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "swarm.db.retired.20260502").write_text("legacy copy", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "swarm_memory.db")
    try:
        for table in (
            "user_2fa",
            "settings_sysmod",
            "enrollment_invites",
            "gmail_labels_cache",
            "user_profiles",
        ):
            conn.execute(f"CREATE TABLE {table} (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    result = gov.swarm_db_retirement_check()

    assert result["ok"] is True
    assert result["live_swarm_db_exists"] is False
    assert result["central_db_exists"] is True
    assert result["missing_tables"] == []
    assert result["retired_copies"] == ["swarm.db.retired.20260502"]


def test_swarm_db_retirement_check_blocks_live_or_incomplete_state(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    (tmp_path / "swarm.db").write_text("still live", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "swarm_memory.db")
    try:
        conn.execute("CREATE TABLE user_2fa (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    result = gov.swarm_db_retirement_check()

    assert result["ok"] is False
    assert result["live_swarm_db_exists"] is True
    assert "settings_sysmod" in result["missing_tables"]


def test_governance_apply_migrates_auxiliary_db_state(tmp_path, monkeypatch):
    import scripts.studio_data_governance as gov

    monkeypatch.setattr(gov, "ROOT", tmp_path)
    monkeypatch.setattr(gov, "DB_PATH", tmp_path / "swarm_memory.db")

    aux = sqlite3.connect(tmp_path / "swarm.db")
    try:
        aux.execute(
            """CREATE TABLE user_2fa (
                username TEXT PRIMARY KEY,
                secret TEXT NOT NULL,
                verified_at REAL,
                created_at REAL NOT NULL
            )"""
        )
        aux.execute(
            "INSERT INTO user_2fa (username, secret, verified_at, created_at) VALUES ('seven', 'SECRET', 1, 2)"
        )
        aux.execute(
            """CREATE TABLE settings_sysmod (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        aux.execute("INSERT INTO settings_sysmod (key, value, updated_at) VALUES ('enabled', 'true', 3)")
        aux.commit()
    finally:
        aux.close()

    result = gov.apply_governance()

    assert result["migrated_auxiliary"]["user_2fa"] == 1
    assert result["migrated_auxiliary"]["settings_sysmod"] == 1
    conn = sqlite3.connect(tmp_path / "swarm_memory.db")
    try:
        assert conn.execute("SELECT secret FROM user_2fa WHERE username='seven'").fetchone()[0] == "SECRET"
        assert conn.execute("SELECT value FROM settings_sysmod WHERE key='enabled'").fetchone()[0] == "true"
    finally:
        conn.close()
