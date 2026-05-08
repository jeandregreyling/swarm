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
    assert inv["classification_counts"]["active_auxiliary_db"] == 1
    assert inv["classification_counts"]["empty_legacy_db"] == 1
    review_paths = {item["path"] for item in manifest["review_items"]}
    assert "swarm.db" in review_paths
    active = next(item for item in manifest["review_items"] if item["path"] == "swarm.db")
    assert active["recommended_action"] == "migrate_to_swarm_memory_then_retire"
    empty = next(item for item in manifest["review_items"] if item["path"] == "agents/swarm.db")
    assert empty["recommended_action"] == "delete_empty_placeholder"
    assert "swarm_memory.db" not in review_paths


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
