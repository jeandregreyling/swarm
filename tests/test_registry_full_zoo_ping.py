from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_temp_db(monkeypatch, tmp_path):
    db = str(tmp_path / "swarm.db")
    monkeypatch.setenv("SWARM_DB_PATH", db)

    import utils.db._connection as conn_mod
    conn_mod.DB_PATH = db

    from utils.db._schema import initialise_database
    initialise_database()
    return conn_mod


def test_full_zoo_ping_persists_runtime_truth(monkeypatch, tmp_path):
    conn_mod = _bootstrap_temp_db(monkeypatch, tmp_path)

    from utils.db import registry

    def fake_probe_local(rows):
        out = {}
        for row in rows:
            name = str(row.get("name") or "").lower()
            if name == "gemma":
                out[name] = {
                    "provider": "ollama",
                    "fault_domain": "OLLAMA_RUNTIME",
                    "runtime_status": "LOADED",
                    "runtime_reason": "model_loaded:gemma3:latest",
                    "registry_status": "ACTIVE",
                }
            elif name == "llama":
                out[name] = {
                    "provider": "ollama",
                    "fault_domain": "OLLAMA_RUNTIME",
                    "runtime_status": "FAULT",
                    "runtime_reason": "model_missing:llama3.2:latest",
                    "registry_status": "STATUS_ORPHANED",
                }
        return out

    def fake_probe_paid(row):
        name = str(row.get("name") or "").lower()
        if name == "nine":
            return {
                "provider": "groq",
                "fault_domain": "EXTERNAL_API",
                "runtime_status": "FAULT",
                "runtime_reason": "identity_ping:403:Access denied",
                "registry_status": "STATUS_ORPHANED",
            }
        return {
            "provider": "anthropic",
            "fault_domain": "EXTERNAL_API",
            "runtime_status": "READY",
            "runtime_reason": "identity_ping:200",
            "registry_status": "ACTIVE",
        }

    monkeypatch.setattr(registry, "_probe_local_rows", fake_probe_local)
    monkeypatch.setattr(registry, "_probe_paid_row", fake_probe_paid)

    report = registry.full_zoo_ping()

    assert report["ok"] is True
    assert report["summary"]["orphaned"] >= 2

    conn = conn_mod.get_connection()
    try:
        rows = conn.execute(
            """SELECT name, provider, fault_domain, runtime_status,
                      runtime_reason, registry_status, runtime_checked_at
               FROM agents
               WHERE name IN ('gemma', 'llama', 'nine', 'twelve')
               ORDER BY name"""
        ).fetchall()
    finally:
        conn.close()

    data = {row["name"]: dict(row) for row in rows}
    assert data["gemma"]["runtime_status"] == "LOADED"
    assert data["gemma"]["registry_status"] == "ACTIVE"
    assert data["llama"]["runtime_status"] == "FAULT"
    assert data["llama"]["registry_status"] == "STATUS_ORPHANED"
    assert data["nine"]["provider"] == "groq"
    assert data["nine"]["registry_status"] == "STATUS_ORPHANED"
    assert data["twelve"]["runtime_status"] == "READY"
    assert data["twelve"]["runtime_checked_at"]


def test_full_zoo_ping_preserves_disabled_rows(monkeypatch, tmp_path):
    conn_mod = _bootstrap_temp_db(monkeypatch, tmp_path)

    conn = conn_mod.get_connection()
    try:
        conn.execute("UPDATE agents SET enabled = 0 WHERE name = 'nine'")
        conn.commit()
    finally:
        conn.close()

    from utils.db import registry

    monkeypatch.setattr(
        registry,
        "_probe_local_rows",
        lambda rows: {},
    )
    monkeypatch.setattr(
        registry,
        "_probe_paid_row",
        lambda row: {
            "provider": "groq",
            "fault_domain": "EXTERNAL_API",
            "runtime_status": "FAULT",
            "runtime_reason": "identity_ping:403:Access denied",
            "registry_status": "STATUS_ORPHANED",
        },
    )

    report = registry.full_zoo_ping()
    assert report["ok"] is True

    conn = conn_mod.get_connection()
    try:
        row = conn.execute(
            "SELECT registry_status, runtime_status FROM agents WHERE name = 'nine'"
        ).fetchone()
    finally:
        conn.close()

    assert row["runtime_status"] == "FAULT"
    assert row["registry_status"] == "DISABLED"
